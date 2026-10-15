# -*- coding: utf-8 -*-
"""
선상낚시 통합 예약조회 (선상24 + 더피싱) — 웹 버전 (Streamlit)

[선상24]
- 배 목록: 조황정보 지역별 페이지 app.sunsang24.com/ship/board?area=<west|east|south|jeju>&page=N
- 예약현황: app.sunsang24.com/ship/schedule_fleet/<배번호>/<YYYYMM>
[더피싱]
- 배 목록: thefishing.kr/reservation/list.php?page=N  (배마다 '서해권 > 충청남도 > 서천군 > 홍원항')
- 예약현황: 이번 달 = thefishing.kr/reservation/list.php?uid=<번호>
            다른 달 = <선박홈페이지>.thefishing.kr/index.php?mid=bk&year=YYYY&month=MM&day=01

화면: 사이트 선택 / 지역(바다 → 시·도 → 시·군 → 항구) / 날짜(달력) / 어종
로컬 실행:  pip install -r requirements.txt  →  streamlit run streamlit_app.py
"""
import calendar
import gzip
import html as htmlmod
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

MOBILE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
SS_APP = "https://app.sunsang24.com"
TF = "https://thefishing.kr"
CS = "https://www.clubsea.co.kr"
SEAS = {"west": "서해", "east": "동해", "south": "남해", "jeju": "제주"}
SITES = {"ss": "선상24", "tf": "더피싱", "cs": "클럽씨피싱", "lm": "라마르호"}
CACHE_VER = 3            # 저장된 목록을 새로 만들게 할 때 올림
SS_BOARD_MAX_PAGES = 12
TF_LIST_MAX_PAGES = 40
MAX_SHIPS = 150
WORKERS = 8
WEEK = "월화수목금토일"
KST = timezone(timedelta(hours=9))


def kst_now():
    return datetime.now(KST)


def kst_today():
    """서버(미국, UTC)가 아니라 한국 날짜 기준 '오늘'"""
    return kst_now().date()

APP_VERSION = "v10.17-4 (바람·파고 지역 표시)"

# ---------------------------------------------------------------- 어종
SS_FISH = ["참돔", "광어", "우럭", "참우럭", "감성돔", "문어", "무늬오징어", "주꾸미", "갑오징어", "한치",
           "오징어", "낙지", "호래기", "화살촉오징어", "부시리", "삼치", "갈치", "열기", "노래미", "황열기",
           "볼락", "벤자리", "전갱이", "민어", "농어", "백조기", "수조기", "도다리", "대구", "어구가자미",
           "참가자미", "붉바리", "방어", "돌돔", "붕장어", "쥐치", "벵에돔", "옥돔", "쏨뱅이", "고등어",
           "망둥어", "홍감펭", "임연수어", "참치", "상어", "뿔돔", "꽃게", "홍어", "시즌어종", "기타",
           "체험낚시", "갯바위", "좌대유터", "해루질", "탐사"]
# 더피싱 '낚시종류' 목록 (2026-10 기준 thefishing.kr/reservation/list.php)
TF_FISH = ["가자미", "갈치", "감성돔", "갑오징어", "고등어", "광어", "우럭", "낙지", "노래미", "농어", "대구",
           "외수질", "도다리", "문어", "민어", "백조기", "부시리", "볼락", "삼치", "숭어", "열기", "오징어",
           "주꾸미", "쭈갑", "꽃게", "참돔", "한치", "갯바위", "광어다운샷", "다잡아", "생미끼", "어초침선",
           "타이라바", "탐사", "체험낚시", "방어", "잉어", "배스", "송어", "쏨뱅이", "피문어", "붕어", "돌문어"]
FISH_ALIAS = {"주꾸미": ["주꾸미", "쭈꾸미", "쭈갑"], "갑오징어": ["갑오징어", "쭈갑", "갑오"],
              "쭈갑": ["쭈갑", "쭈꾸미&갑", "주꾸미,갑오징어", "쭈꾸미/갑오징어", "주꾸미/갑오징어", "쭈꾸미,갑오징어"],
              "우럭": ["우럭", "조피볼락"], "광어": ["광어", "넙치"], "백조기": ["백조기", "보구치"],
              "볼락": ["볼락", "뽈락"], "무늬오징어": ["무늬오징어", "에깅"], "열기": ["열기", "불볼락"],
              "문어": ["문어", "돌문어", "대문어", "피문어"], "도다리": ["도다리", "문치가자미"],
              "붕장어": ["붕장어", "아나고"], "대구": ["대구", "외수질"], "외수질": ["외수질", "대구"],
              "가자미": ["가자미"], "타이라바": ["타이라바", "참돔"]}

# ---------------------------------------------------------------- 지역 표기 통일
SIDO_SHORT = {"경기도": "경기", "충청남도": "충남", "충청북도": "충북", "전라북도": "전북", "전북특별자치도": "전북",
              "전라남도": "전남", "경상남도": "경남", "경상북도": "경북", "강원도": "강원",
              "강원특별자치도": "강원", "제주도": "제주", "제주특별자치도": "제주", "인천광역시": "인천",
              "부산광역시": "부산", "울산광역시": "울산"}
SIDO_OVERRIDE = {"인천": "인천", "영흥도": "인천", "부산": "부산", "울산": "울산", "제주": "제주",
                 "서귀포": "제주"}

# 선상24 배 이름 앞의 항구/지명 → (시·도, 시·군, 항구)
PLACES = {
    "인천": ("인천", "인천", ""), "영종도": ("인천", "인천", "영종도"), "연안부두": ("인천", "인천", "연안부두"),
    "남항": ("인천", "인천", "인천남항"), "영흥도": ("인천", "영흥도", ""), "덕적도": ("인천", "옹진", "덕적도"),
    "강화": ("인천", "강화", ""), "선재도": ("인천", "옹진", "선재도"),
    "오이도": ("경기", "시흥", "오이도"), "시흥": ("경기", "시흥", ""), "전곡항": ("경기", "화성", "전곡항"),
    "궁평항": ("경기", "화성", "궁평항"), "제부도": ("경기", "화성", "제부도"), "화성": ("경기", "화성", ""),
    "대부도": ("경기", "안산", "대부도"), "탄도항": ("경기", "안산", "탄도항"), "안산": ("경기", "안산", ""),
    "평택": ("경기", "평택", ""), "김포": ("경기", "김포", ""),
    "당진": ("충남", "당진", ""), "장고항": ("충남", "당진", "장고항"), "왜목": ("충남", "당진", "왜목항"),
    "석문": ("충남", "당진", ""), "한진": ("충남", "당진", "한진항"), "서산": ("충남", "서산", ""),
    "삼길포": ("충남", "서산", "삼길포"), "태안": ("충남", "태안", ""), "안면도": ("충남", "안면도", ""),
    "신진도": ("충남", "태안", "신진도항"), "안흥": ("충남", "태안", "안흥항"), "마검포": ("충남", "태안", "마검포항"),
    "영목": ("충남", "안면도", "영목항"), "영목항": ("충남", "안면도", "영목항"), "모항": ("충남", "태안", "모항"),
    "백사장": ("충남", "안면도", "백사장항"), "학암포": ("충남", "태안", "학암포"),
    "홍성": ("충남", "홍성", ""), "남당항": ("충남", "홍성", "남당항"), "보령": ("충남", "보령", ""),
    "오천": ("충남", "보령", "오천항"), "오천항": ("충남", "보령", "오천항"), "대천": ("충남", "보령", "대천항"),
    "대천항": ("충남", "보령", "대천항"), "무창포": ("충남", "보령", "무창포항"), "원산도": ("충남", "보령", ""),
    "서천": ("충남", "서천", ""), "홍원항": ("충남", "서천", "홍원항"),
    "군산": ("전북", "군산", ""), "비응항": ("전북", "군산", "비응항"), "야미도": ("전북", "군산", ""),
    "부안": ("전북", "부안", ""), "격포": ("전북", "격포", ""), "위도": ("전북", "부안", "위도"),
    "고창": ("전북", "고창", ""),
    "영광": ("전남", "영광", ""), "목포": ("전남", "목포", ""), "신안": ("전남", "신안", ""),
    "무안": ("전남", "무안", ""), "영암": ("전남", "영암", ""), "진도": ("전남", "진도", ""),
    "해남": ("전남", "해남", ""), "완도": ("전남", "완도", ""), "여수": ("전남", "여수", ""),
    "돌산": ("전남", "여수", "돌산항"), "고흥": ("전남", "고흥", ""), "녹동": ("전남", "고흥", "녹동항"),
    "장흥": ("전남", "장흥", ""), "강진": ("전남", "강진", ""), "보성": ("전남", "보성", ""),
    "광양": ("전남", "광양", ""),
    "속초": ("강원", "속초", ""), "양양": ("강원", "양양", ""), "주문진": ("강원", "강릉", "주문진항"),
    "강릉": ("강원", "강릉", ""), "동해": ("강원", "동해", ""), "묵호": ("강원", "동해", "묵호항"),
    "삼척": ("강원", "삼척", ""), "임원": ("강원", "삼척", "임원항"), "대진": ("강원", "고성", "대진항"),
    "아야진": ("강원", "고성", "아야진항"), "공현진": ("강원", "고성", "공현진항"),
    "울진": ("경북", "울진", ""), "후포": ("경북", "울진", "후포항"), "영덕": ("경북", "영덕", ""),
    "강구": ("경북", "영덕", "강구항"), "축산": ("경북", "영덕", "축산항"), "포항": ("경북", "포항", ""),
    "구룡포": ("경북", "포항", "구룡포항"), "경주": ("경북", "경주", ""), "감포": ("경북", "경주", "감포항"),
    "울산": ("울산", "울산", ""), "정자": ("울산", "울산", "정자항"), "부산": ("부산", "부산", ""),
    "기장": ("부산", "기장", ""), "다대포": ("부산", "부산", "다대포"), "거제": ("경남", "거제", ""),
    "통영": ("경남", "통영", ""), "남해": ("경남", "남해", ""), "사천": ("경남", "사천", ""),
    "삼천포": ("경남", "사천", "삼천포항"), "진해": ("경남", "진해", ""), "마산": ("경남", "마산", ""),
    "창원": ("경남", "창원", ""),
    "제주": ("제주", "제주", ""), "서귀포": ("제주", "서귀포", ""), "한림": ("제주", "제주", "한림항"),
    "도두": ("제주", "제주", "도두항"), "김녕": ("제주", "제주", "김녕항"), "차귀도": ("제주", "제주", "차귀도"),
    "모슬포": ("제주", "서귀포", "모슬포항"), "성산": ("제주", "서귀포", "성산항"), "애월": ("제주", "제주", "애월항"),
}


# ---------------------------------------------------------------- 공통 유틸
def fetch_html(url, tries=3, headers=None, timeout=20):
    """페이지 가져오기 — 일시적 오류(시간초과, 429/5xx)는 잠깐 쉬었다가 다시 시도"""
    last_err = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers or HEADERS, timeout=timeout)
            code = getattr(r, "status_code", 200)
            if code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(1.5 * (i + 1))
                continue
            r.raise_for_status()
            break
        except requests.RequestException as ex:
            last_err = ex
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    else:
        raise last_err or RuntimeError("페이지를 가져오지 못했습니다")
    raw = getattr(r, "content", None)
    if not isinstance(raw, bytes):                       # (테스트용 가짜 응답)
        return r.text
    # ① UTF-8로 먼저 엄격하게 시도: 한글 UTF-8 페이지는 깨끗이 풀리고, EUC-KR 바이트는 거의 항상 실패함.
    #    (선상24처럼 실제는 UTF-8인데 euc-kr이라고 선언한 페이지가 있어 선언만 믿으면 글자가 깨짐)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    # ①-2 대부분 UTF-8인데 깨진 바이트가 몇 개 섞인 페이지(클럽씨피싱 등) → UTF-8로 읽고 깨진 글자만 버림
    loose = raw.decode("utf-8", errors="replace")
    if loose.count("\ufffd") <= max(20, len(raw) // 2000) and re.search(r"[가-힣]", loose):
        return loose.lstrip("\ufeff")
    # ② 실패하면 선언된 인코딩 → 자동 추정 → cp949 순서
    headers = getattr(r, "headers", {}) or {}
    m = re.search(r"charset=([\w\-]+)", headers.get("Content-Type", ""), re.I)
    enc = m.group(1) if m else None
    if not enc:
        mb = re.search(rb"charset=[\"']?([\w\-]+)", raw[:3000], re.I)
        enc = mb.group(1).decode("ascii", "ignore") if mb else None
    enc = (enc or getattr(r, "apparent_encoding", None) or "cp949").lower()
    if enc in ("euc-kr", "euckr", "ks_c_5601-1987", "x-windows-949", "korean", "utf-8", "utf8"):
        enc = "cp949"                                    # 한글 옛 인코딩은 cp949로 읽어야 깨지지 않음
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("cp949", errors="replace")


def clean_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for img in soup.find_all("img"):                     # 상태가 아이콘(대체텍스트)으로만 나오는 경우 대비
        alt = (img.get("alt") or "").strip()
        img.replace_with(f"\n{alt}\n" if alt else "")
    out = []
    for raw in soup.get_text("\n").split("\n"):
        s = re.sub(r"\s+", " ", raw).strip()
        if s:
            out.append(s)
    return out


def ss_locate(name, sea):
    first = name.split()[0] if " " in name else ""
    if first == "고성" or name.startswith("고성"):
        return ("강원", "고성", "") if sea == "east" else ("경남", "고성", "")
    if first in PLACES:
        return PLACES[first]
    for k in sorted(PLACES, key=len, reverse=True):
        if name.startswith(k):
            return PLACES[k]
    return ("기타", first or "기타", "")


def tf_region(path):
    """'서해권 > 충청남도 > 서천군 > 홍원항' → (sea, 시도, 시군, 항구)"""
    parts = [p.strip() for p in path.split(">") if p.strip()]
    sea = {"서해권": "west", "남해권": "south", "동해권": "east"}.get(parts[0] if parts else "", "")
    sido = SIDO_SHORT.get(parts[1], parts[1]) if len(parts) > 1 else "기타"
    sgg = parts[2] if len(parts) > 2 else ""
    if len(sgg) > 2 and sgg.endswith(("시", "군")):
        sgg = sgg[:-1]
    port = parts[3] if len(parts) > 3 else ""
    sido = SIDO_OVERRIDE.get(sgg, sido)
    if sido == "제주":
        sea = "jeju"
    return sea, sido, sgg or sido, port


JJU_RE = re.compile(r"주꾸미|쭈꾸미|쭈꾸|주꾸")
GAB_RE = re.compile(r"갑오징어|갑오|갑\b|&\s*갑")


def fish_match(text, selected):
    if not selected:
        return True
    for f in selected:
        if any(alias in text for alias in FISH_ALIAS.get(f, [f])):
            return True
        if f == "쭈갑" and JJU_RE.search(text) and GAB_RE.search(text):   # 주꾸미와 갑오징어를 함께 하는 배
            return True
    return False


# ---------------------------------------------------------------- 공통 일정 파싱 도구
DATE_RE = re.compile(r"(?:(\d{1,2})[ \t]*월[ \t]*)?(\d{1,2})\s*일\s*[,]?\s*\(?\s*([월화수목금토일])(?:요일)?\s*\)?")
FULL_DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
TIDE_RE = re.compile(r"(\d{1,2}\s*물|조금|무시)")
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})")
ONE_TIME_RE = re.compile(r"(\d{1,2}:\d{2})")
PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+\s*원|\d{1,3}\s*만\s*원)")
STATUS_RE = re.compile(
    r"남은\s*(?:자리|인원)\s*:?\s*(\d+)\s*명"
    r"|(예약\s*마감|예약\s*완료|만석)"
    r"|(기상\s*악화|출조\s*취소|배\s*정비일?|정비일|예약을?\s*받지\s*않|휴\s*무|휴\s*항|출조\s*없음"
    r"|(?<![가-힣])취\s*소(?!\s*(?:대기|완료)))")
NOISE = ("바로예약", "대기하기", "예약하기", "전화예약", "예약완료", "입금대기", "취소대기", "취소완료",
         "예약대기", "출조대기", "TOP")


def status_of(m):
    """STATUS_RE 매치 → (남은자리, 상태)"""
    if m is None:
        return None, "확인필요"
    if m.group(1) is not None:
        n = int(m.group(1))
        return n, ("예약가능" if n > 0 else "마감")
    if m.group(2):
        return 0, "마감"
    word = re.sub(r"\s+", "", m.group(3))
    word = {"배정비": "정비", "배정비일": "정비", "정비일": "정비", "예약을받지않": "예약중단",
            "예약받지않": "예약중단", "취소": "출조취소"}.get(word, word)
    return 0, word


def line_start_dates(full, regex):
    out = []
    for m in regex.finditer(full):
        ls = full.rfind("\n", 0, m.start()) + 1
        if full[ls:m.start()].strip(" -|*[]") == "":
            out.append(m)
    return out


def _is_name(line):
    if not line or len(line) > 30 or ":" in line:
        return False
    if DATE_RE.search(line) or TIDE_RE.fullmatch(line) or STATUS_RE.search(line):
        return False
    if any(w in line for w in NOISE) or line.startswith(("공지", "(")):
        return False
    return not re.fullmatch(r"[\d\s명/|\-*]+", line)


# ---------------------------------------------------------------- 선상24
SP_LABEL = re.compile(r"(?:대상\s*어종|(?<![가-힣])어\s*종)\s*:?\s*")
TIME_LABEL = re.compile(r"(?:출항\s*시간|운항\s*시간)\s*:?\s*")
BOOKED_RE = re.compile(r"\s*(?:(\d+)\s*명\s*)?예약\s*/\s*(\d+)\s*명|\s*(\d+)\s*명")


SS_REMAIN_RE = re.compile(r"남은\s*자리\s*:?\s*(\d+)\s*명")
SS_CLOSED_RE = re.compile(r"(예약\s*마감)|(기상\s*악화|출조\s*취소|휴\s*항|휴\s*무)")


def ss_status_of(m):
    if m is None:
        return None, "확인필요"
    if m.re is SS_REMAIN_RE:
        n = int(m.group(1))
        return n, ("예약가능" if n > 0 else "마감")
    if m.group(1):
        return 0, "마감"
    return 0, re.sub(r"\s+", "", m.group(2))


def ss_parse(html, year, month, ship):
    full = "\n".join(clean_lines(html))
    dates = line_start_dates(full, DATE_RE)
    out = []
    for i, m in enumerate(dates):
        block = full[m.end(): dates[i + 1].start() if i + 1 < len(dates) else len(full)]
        mo = int(m.group(1)) if m.group(1) else month
        yr = year + (1 if mo < month - 6 else 0)
        try:
            d = date(yr, mo, int(m.group(2)))
        except ValueError:
            continue
        tide_m = TIDE_RE.search(block[:30])
        tide = tide_m.group(1).replace(" ", "") if tide_m else ""
        prev_end = tide_m.end() if tide_m else 0
        labels = list(SP_LABEL.finditer(block))
        for k, lab in enumerate(labels):
            nxt = labels[k + 1].start() if k + 1 < len(labels) else len(block)
            tl = TIME_LABEL.search(block, lab.end(), nxt)
            tm = TIME_RE.search(block, lab.end(), nxt)
            sp_end = tl.start() if tl else (tm.start() if tm else block.find("\n", lab.end()))
            species = re.sub(r"\s+", " ", block[lab.end(): sp_end if sp_end > 0 else nxt]).strip(" /")
            # 선상24 화면에는 '예약완료·입금대기·취소대기…' 범례가 남은자리 앞에 붙어 있음.
            # 범례의 '예약완료'를 마감으로 읽지 않도록 '남은자리 N명'을 먼저 찾고, 없을 때만 마감/기상 문구를 봄
            start_at = tm.end() if tm else lab.end()
            stm = SS_REMAIN_RE.search(block, start_at, nxt) or SS_CLOSED_RE.search(block, start_at, nxt)
            remain, status = ss_status_of(stm)
            end = stm.end() if stm else (tm.end() if tm else lab.end())
            if stm:
                bm = BOOKED_RE.match(block, stm.end())
                if bm and bm.end() - stm.end() < 25:
                    end = bm.end()
            pre = [re.sub(r"\(일정-?\d*\)", "", l.strip(" |-*")).strip()
                   for l in block[prev_end: lab.start()].split("\n")]
            names = [l for l in pre if _is_name(l)]
            boat = names[0] if names else ship["name"]
            notice = " ".join(l for l in pre if l and l != boat and l not in NOISE)
            notice = re.sub(r"^공지사항\s*:?\s*", "", notice).strip()
            out.append({**ship_cols(ship), "date": d, "tide": tide, "boat": boat, "species": species,
                        "time": f"{tm.group(1)}~{tm.group(2)}" if tm else "", "price": "",
                        "remain": remain, "status": status, "notice": notice[:200],
                        "url": f"{SS_APP}/ship/schedule_fleet/{ship['id']}/{yr}{mo:02d}", "home": ""})
            prev_end = end
    return out


class CatalogError(RuntimeError):
    """목록 수집 실패 — 캐시에 남기지 않기 위해 예외로 던지고, 모은 만큼(rows)은 함께 전달"""
    def __init__(self, msg, rows):
        super().__init__(msg)
        self.rows = rows


SS_SEM = threading.Semaphore(4)                          # 선상24 동시 요청 수 제한


def ss_fetch(url):
    with SS_SEM:
        html = fetch_html(url)
        time.sleep(0.15)
        return html


def _ss_board_page(sea, page):
    try:
        html = ss_fetch(f"{SS_APP}/ship/board?area={sea}&page={page}")
    except Exception:
        return None
    found = {}
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        m = re.search(r"/ship/schedule/(\d+)", a["href"])
        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if m and name and len(name) <= 30:
            found.setdefault(int(m.group(1)), name)
    return found


def _ss_crawl_sea(sea):
    ships, streak = {}, 0
    for page in range(1, SS_BOARD_MAX_PAGES + 1):
        found = _ss_board_page(sea, page)
        if found is None:
            if page == 1:
                return sea, None                         # 첫 페이지부터 실패 = 이 바다 목록 실패
            break
        new = {k: v for k, v in found.items() if k not in ships}
        ships.update(new)
        streak = 0 if new else streak + 1
        if streak >= 2:
            break
        time.sleep(0.3)
    return sea, ships


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def ss_catalog(_ver=CACHE_VER):
    rows, seen, failed = [], set(), []
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(_ss_crawl_sea, list(SEAS)))
    for sea, ships in results:
        if ships is None:
            failed.append(SEAS[sea])
            continue
        if True:
            for sid, name in ships.items():
                if sid in seen:
                    continue
                seen.add(sid)
                sido, sgg, port = ss_locate(name, sea)
                rows.append({"site": "ss", "id": sid, "name": name, "sea": sea, "sido": sido,
                             "sigungu": sgg, "port": port, "hint": ""})
    if failed or not rows:
        # 실패한 결과는 캐시에 남기지 않도록 예외로 처리 (다음 화면 갱신 때 다시 시도)
        raise CatalogError(f"선상24 목록을 일부 불러오지 못했습니다({', '.join(failed) or '전체'})", rows)
    return rows


def _probe(url, html=None, err=None):
    """서버가 실제로 받은 화면 요약 (원인 확인용)"""
    if err is not None:
        return {"url": url, "result": f"접속 실패: {err}"}
    t = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I)
    head = " ".join(clean_lines(html or ""))[:160]
    return {"url": url, "result": f"글자 {len(html or ''):,}자 · 제목 '{(t.group(1).strip() if t else '-')[:40]}'",
            "head": head}


# ---- 선상24 배 목록 배경 수집: 조황정보 게시판을 깊은 페이지까지 천천히 읽어 배 목록을 계속 늘림
#      (게시판 60페이지가 사흘치 정도라, 최근에 글을 안 올린 배까지 찾으려면 깊이 읽어야 함)
SS_BG_MAX_PAGES = {"west": 250, "south": 250, "east": 120, "jeju": 80}
SS_BG_FILE = os.path.join(tempfile.gettempdir(), f"sunsang24_ships_v{CACHE_VER}.json")


def _ss_bg_loop(state):
    while True:
        for sea, maxp in SS_BG_MAX_PAGES.items():
            empty = 0
            for page in range(1, maxp + 1):
                found = _ss_board_page(sea, page)
                with state["lock"]:
                    state["page"][sea] = page
                if found is None:                        # 일시 오류: 잠깐 쉬고 다음 페이지
                    time.sleep(5)
                    continue
                with state["lock"]:
                    for sid, name in found.items():
                        state["ships"].setdefault(str(sid), [name, sea])
                # 앞쪽 페이지는 같은 배가 반복되고 새 배는 띄엄띄엄 나오므로 끝까지 읽음.
                # 글이 하나도 없는 페이지가 두 번 연속이면 게시판 끝으로 보고 멈춤
                empty = empty + 1 if not found else 0
                if empty >= 2:
                    break
                if page % 20 == 0:
                    _ss_bg_save(state)
                time.sleep(0.4)
            _ss_bg_save(state)
        with state["lock"]:
            state["rounds"] += 1
        time.sleep(12 * 3600)                            # 12시간마다 다시 훑어 새 배 반영


def _ss_bg_save(state):
    try:
        with state["lock"]:
            data = json.dumps(state["ships"], ensure_ascii=False)
        with open(SS_BG_FILE, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception:
        pass


@st.cache_resource(show_spinner=False)
def ss_bg_state():
    state = {"ships": {}, "page": {k: 0 for k in SS_BG_MAX_PAGES}, "rounds": 0, "lock": threading.Lock()}
    try:
        with open(SS_BG_FILE, encoding="utf-8") as f:
            state["ships"] = json.load(f)                # 이전에 모아 둔 목록부터 사용
    except Exception:
        pass
    threading.Thread(target=_ss_bg_loop, args=(state,), daemon=True).start()
    return state


def ss_bg_rows():
    st_ = ss_bg_state()
    with st_["lock"]:
        items = list(st_["ships"].items())
    rows = []
    for sid, (name, sea) in items:
        sido, sgg, port = ss_locate(name, sea)
        rows.append({"site": "ss", "id": int(sid), "name": name, "sea": sea, "sido": sido,
                     "sigungu": sgg, "port": port, "hint": ""})
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def ss_month(ship_t, yyyymm, _ver=CACHE_VER):
    """선상24 한 척의 한 달 일정 → {"rows": [...], "probe": [...]}
    순서대로 시도: 앱 월별 일정 → (이번 달) 앱 일정 → 모바일 화면 → 배 홈페이지(xxx.sunsang24.com).
    하나도 못 읽으면 각 시도에서 서버가 받은 화면 요약을 probe로 돌려줌."""
    ship = dict(ship_t)
    y, m = int(yyyymm[:4]), int(yyyymm[4:])
    today = kst_today()
    tries = [(f"{SS_APP}/ship/schedule_fleet/{ship['id']}/{yyyymm}", None)]
    if (y, m) == (today.year, today.month):
        tries.append((f"{SS_APP}/ship/schedule/{ship['id']}", None))
    tries.append((f"{SS_APP}/ship/schedule_fleet/{ship['id']}/{yyyymm}", MOBILE_HEADERS))
    probe = []

    def attempt(url, hdr):
        try:
            with SS_SEM:
                html = fetch_html(url, headers=hdr, tries=2, timeout=45)
                time.sleep(0.15)
        except Exception as ex:
            probe.append(_probe(url, err=ex))
            return []
        rows = [r for r in ss_parse(html, y, m, ship) if (r["date"].year, r["date"].month) == (y, m)]
        if not rows:
            probe.append(_probe(url, html))
        return rows

    for url, hdr in tries:
        rows = attempt(url, hdr)
        if rows:
            return {"rows": rows, "probe": []}
    home = ss_home(ship["id"])                           # 배 홈페이지 쪽 예약현황 (다른 서버 주소)
    if home:
        rows = attempt(f"{home}ship/schedule_fleet/{yyyymm}", None)
        if rows:
            for r in rows:
                r["url"] = f"{home}ship/schedule_fleet/{yyyymm}"
            return {"rows": rows, "probe": []}
    else:
        probe.append({"url": f"{SS_APP}/ship/info/{ship['id']}", "result": "배 홈페이지 주소를 찾지 못함"})
    return {"rows": [], "probe": probe}


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def ss_home(ship_id, _ver=CACHE_VER):
    """선상24 배의 홈페이지(xxx.sunsang24.com) — 배 소개 페이지의 사진 경로 ship_img/<xxx>/ 에서 찾음"""
    try:
        html = ss_fetch(f"{SS_APP}/ship/info/{ship_id}")
    except Exception:
        return None
    m = re.search(r"ship_img/([a-z0-9][a-z0-9\-]*)/", html)
    return f"https://{m.group(1)}.sunsang24.com/" if m else None


# ---------------------------------------------------------------- 더피싱
TF_SEM = threading.Semaphore(4)                          # 더피싱 동시 요청 수 제한


def tf_fetch(url):
    with TF_SEM:
        html = fetch_html(url)
        time.sleep(0.15)
        return html


TF_PATH_RE = re.compile(r"(서해권|남해권|동해권)((?:\s*>\s*(?:영흥도 진두항|제주 [가-힣]+항|[가-힣·/]+)){1,3})")


def _tf_list_page(page):
    try:
        html = tf_fetch(f"{TF}/reservation/list.php?page={page}")
    except Exception:
        return None, 0
    soup = BeautifulSoup(html, "html.parser")
    last = max([int(x) for x in re.findall(r"list\.php\?page=(\d+)", html)] or [page])
    items = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"list\.php\?uid=(\d+)", a["href"])
        if not m or "type=" in a["href"]:
            continue
        uid = int(m.group(1))
        node, pm, joined = a, None, ""
        for _ in range(4):                               # 링크 안/주변에서 '권 > 도 > ...' 경로 찾기
            joined = re.sub(r"\s+", " ", node.get_text(" ")).strip()
            pm = TF_PATH_RE.search(joined)
            if pm or node.parent is None:
                break
            node = node.parent
        if not pm:
            continue
        name = joined[:pm.start()].strip()
        name = name[-25:].strip() if len(name) > 25 else name
        hint = joined[pm.end(): pm.end() + 80].strip()
        if uid not in items or (name and not items[uid][0]):
            items[uid] = (name, pm.group(0), hint)
    return items, last


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def tf_catalog(_ver=CACHE_VER):
    first, last = _tf_list_page(1)
    if not first:
        raise CatalogError("더피싱 목록 첫 페이지를 불러오지 못했습니다", [])
    pages = list(range(2, min(last, TF_LIST_MAX_PAGES) + 1))
    allitems, bad = dict(first), 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        for items, _ in ex.map(_tf_list_page, pages):
            if items is None:
                bad += 1
            for uid, v in (items or {}).items():
                allitems.setdefault(uid, v)
    partial_err = (f"더피싱 목록 {bad}/{len(pages) + 1}페이지를 불러오지 못했습니다"
                   if pages and bad > len(pages) * 0.2 else None)
    rows = []
    for uid, (name, path, hint) in allitems.items():
        sea, sido, sgg, port = tf_region(path)
        name = re.sub(r"\s*(실시간결제|캐시적립|좌석제|신규선박|회원추천)\s*", " ", name or "").strip()
        rows.append({"site": "tf", "id": uid, "name": name or f"더피싱 {uid}", "sea": sea, "sido": sido,
                     "sigungu": sgg, "port": port, "hint": hint})
    if partial_err:
        raise CatalogError(partial_err, rows)
    return rows


TF_DAY_RE = re.compile(r"(?m)^()(\d{1,2})\n([월화수목금토일])요일\s*$")


def tf_title(html):
    """'<title>[오천항 월드레저] 독수리호 - 더피싱,…' → ('독수리호', '오천항 월드레저')"""
    m = re.search(r"<title>\s*(?:\[([^\]]+)\]\s*)?([^<]+?)\s*-\s*더피싱", html, re.S)
    if not m:
        return None, None
    return re.sub(r"\s+", " ", m.group(2)).strip(), (m.group(1) or "").strip() or None


def tf_homepage(html):
    """선사 홈페이지 주소 — 예약모듈(index.php?mid=bk) 링크가 있는 곳. 외부 도메인(eagleho.com 등)도 포함"""
    links = re.findall(r"""href=["']?(https?://[^"'\s>]+)""", html)
    for u in links:
        if "mid=bk" in u and not re.match(r"https?://(www\.)?thefishing\.kr/", u):
            return re.match(r"https?://[^/]+", u).group(0)
    for u in links:
        if re.match(r"https?://[a-z0-9\-]+\.thefishing\.kr", u) and not re.match(r"https?://(www|m|img|icon)\.", u):
            return re.match(r"https?://[^/]+", u).group(0)
    return None


def tf_parse_calendar(html, year, month, ship):
    """thefishing.kr/reservation/list.php?uid=… 의 달력(이번 달) → 일정"""
    full = "\n".join(clean_lines(html))
    home = tf_homepage(html)
    # 더피싱 달력은 '15⏎목요일⏎11물' 형식(숫자 줄 + 요일 줄). '15일 (목)' 형식도 함께 지원
    found = list(TF_DAY_RE.finditer(full)) + line_start_dates(full, DATE_RE)
    found.sort(key=lambda m: m.start())
    dates = []
    for m in found:
        if not dates or m.start() >= dates[-1].end():
            dates.append(m)

    def shift(yy, mm, k):
        mm += k
        while mm > 12:
            mm, yy = mm - 12, yy + 1
        while mm < 1:
            mm, yy = mm + 12, yy - 1
        return yy, mm

    def fits(yy, mm, dnum, wd):
        try:
            return WEEK[date(yy, mm, dnum).weekday()] == wd
        except ValueError:
            return False

    # 요일이 가장 많이 맞는 달을 이 달력의 달로 판단 (리뷰 날짜 등에 속지 않도록)
    cands = [shift(year, month, k) for k in (0, 1, -1, 2)]
    base = max(cands, key=lambda c: sum(fits(c[0], c[1], int(m.group(2)), m.group(3)) for m in dates))
    days = {}
    for i, m in enumerate(dates):
        block = full[m.end(): dates[i + 1].start() if i + 1 < len(dates) else len(full)]
        dnum, wd = int(m.group(2)), m.group(3)
        d = None
        for k in (0, 1, -1):                             # 앞뒤 달 칸은 요일로 구분
            yy, mm = shift(base[0], base[1], k)
            if fits(yy, mm, dnum, wd):
                d = date(yy, mm, dnum)
                break
        if d is None:
            continue
        stm = STATUS_RE.search(block)
        if d in days and days[d]["status"] != "확인필요":
            continue
        remain, status = status_of(stm)
        tide_m = TIDE_RE.search(block[:30])
        tm = TIME_RE.search(block) or ONE_TIME_RE.search(block)
        pm = PRICE_RE.search(block)
        notice = " ".join(l for l in block.split("\n") if l and l not in NOISE and not STATUS_RE.search(l)
                          and not TIDE_RE.fullmatch(l))[:200]
        days[d] = {**ship_cols(ship), "date": d, "tide": tide_m.group(1).replace(" ", "") if tide_m else "",
                   "boat": ship.get("boat") or ship["name"], "species": ship.get("hint", ""),
                   "time": (f"{tm.group(1)}~{tm.group(2)}" if tm and tm.re is TIME_RE else
                            (f"{tm.group(1)} 출항" if tm else "")),
                   "price": pm.group(1) if pm else "", "remain": remain, "status": status,
                   "notice": notice, "url": f"{TF}/reservation/list.php?uid={ship['id']}",
                   "home": (ship.get("home") or "")}
    return list(days.values()), home


def tf_parse_home(html, ship):
    """<선박>.thefishing.kr/index.php?mid=bk… 예약현황 → 이 배의 일정"""
    full = "\n".join(clean_lines(html))
    heads = line_start_dates(full, FULL_DATE_RE)
    out = []
    name = ship.get("boat") or ship["name"]
    for i, m in enumerate(heads):
        block = full[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(full)]
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        tide_m = TIDE_RE.search(block[:40])
        lines = block.split("\n")
        # 선단(여러 척) 페이지면 이 배 이름 줄부터 다음 배 이름 줄 전까지만
        idx = next((k for k, l in enumerate(lines) if l.replace(" ", "") == name.replace(" ", "")), None)
        if idx is not None:
            seg = [lines[idx]]
            for l in lines[idx + 1:]:
                if l != name and len(l) <= 15 and re.search(r"(호|피싱|마린|\d호)$", l) and not STATUS_RE.search(l):
                    break
                seg.append(l)
            text = "\n".join(seg)
        else:
            text = block
        stm = STATUS_RE.search(text)
        remain, status = status_of(stm)
        tm = TIME_RE.search(text) or ONE_TIME_RE.search(text)
        pm = PRICE_RE.search(text)
        notice = " ".join(l for l in text.split("\n")[1:] if l not in NOISE and not STATUS_RE.search(l))[:200]
        out.append({**ship_cols(ship), "date": d, "tide": tide_m.group(1).replace(" ", "") if tide_m else "",
                    "boat": name, "species": ship.get("hint", ""),
                    "time": (f"{tm.group(1)}~{tm.group(2)}" if tm and tm.re is TIME_RE else
                             (f"{tm.group(1)} 출항" if tm else "")),
                    "price": pm.group(1) if pm else "", "remain": remain, "status": status,
                    "notice": notice, "url": f"{TF}/reservation/list.php?uid={ship['id']}",
                   "home": (ship.get("home") or "")})
    return out


@st.cache_data(ttl=180, show_spinner=False)
def tf_ship(ship_t, months, _ver=CACHE_VER):
    """더피싱 한 척: 예약 페이지 달력(이번 달) + 선사 홈페이지 예약현황(가까운 8일, 다른 달)"""
    ship = dict(ship_t)
    today = kst_today()
    html = tf_fetch(f"{TF}/reservation/list.php?uid={ship['id']}")
    boat, company = tf_title(html)                       # 정확한 배 이름/선사명
    if boat:
        ship["boat"] = boat
        ship["name"] = f"{boat} ({company})" if company else boat
    home = tf_homepage(html)
    ship["home"] = (home + "/") if home else f"{TF}/reservation/list.php?uid={ship['id']}"
    portal, _ = tf_parse_calendar(html, today.year, today.month, ship)
    best = {r["date"]: r for r in portal}
    if home:
        pages = [f"{home}/index.php?mid=bk"]
        have = {f"{d.year}{d.month:02d}" for d, r in best.items() if r["status"] != "확인필요"}
        pages += [f"{home}/index.php?mid=bk&year={ym[:4]}&month={ym[4:]}&day=01"
                  for ym in months if ym not in have]
        for url in pages:
            try:
                for r in tf_parse_home(tf_fetch(url), ship):
                    old = best.get(r["date"])
                    # 홈페이지 쪽이 출항시간·가격까지 있어 더 자세하므로, 상태를 알면 그쪽을 우선
                    if old is None or r["status"] != "확인필요":
                        best[r["date"]] = r
            except Exception:
                pass
    want = set(months)
    return [r for r in best.values() if f"{r['date'].year}{r['date'].month:02d}" in want]


# ---------------------------------------------------------------- 조류세기 (남당항 물때표)
# 바다타임 남당항(코드 356) 월별 물때표의 만조·간조 높이(cm)로 그날 조차를 구하고,
# 그 달 최대 조차(사리) 대비 백분율을 '조류세기'로 표시
TIDE_PORT_NAME, TIDE_PORT_CODE = "남당항", 356
TIDE_DAY_RE = re.compile(r"(?m)^([월화수목금토일])\s+(\d{1,2})(?=\s|$)")


def parse_tide(html, y, m):
    """바다타임 물때표 텍스트 → {날짜: {range, mul}}
    하루치는 '월 19' 줄로 시작해 '9.9 무시 08:34 (479) … (544) … (326) … (264)' 처럼 여러 줄에 걸쳐 있음.
    표 구조에 기대지 않고, 날짜 줄부터 다음 날짜 줄 전까지를 하루로 읽음."""
    full = "\n".join(clean_lines(html))
    heads = list(TIDE_DAY_RE.finditer(full))
    days = {}
    for i, mt in enumerate(heads):
        block = full[mt.end(): heads[i + 1].start() if i + 1 < len(heads) else len(full)]
        try:
            d = date(y, m, int(mt.group(2)))
        except ValueError:
            continue
        if WEEK[d.weekday()] != mt.group(1) or d in days:
            continue
        # 바다날씨 표 등 다른 내용이 섞이지 않게: 그날 블록에서 '시각 (높이)' 형태만 높이로 인정
        heights = [int(h) for h in re.findall(r"\d{1,2}:\d{2}\s*\(\s*(\d{1,4})\s*\)", block)][:4]   # '( 81)'처럼 괄호 안 공백 허용
        if len(heights) < 2 or max(heights) - min(heights) < 50:   # 만조·간조가 다 안 잡힌 날은 계산에서 제외
            continue
        # 하루 조차 = 만조 높이 평균 − 간조 높이 평균 (자정을 넘어 만조/간조가 3번만 있는 날도 고르게 계산)
        mid = sum(heights) / len(heights)
        highs = [h for h in heights if h > mid] or [max(heights)]
        lows = [h for h in heights if h <= mid] or [min(heights)]
        mul = re.search(r"(\d{1,2}\s*물|조금|무시)", block)
        # ▲/▼ 뒤 숫자 = 직전 물때와의 높이 변화(cm). 바다타임 '물흐름 %'는 이 값의 하루 평균과 거의 정확히 비례함
        deltas = [abs(int(x)) for x in re.findall(r"[▲▼]\s*([+-]?\d{1,4})", block)][:4]
        days[d] = {"range": round(sum(highs) / len(highs) - sum(lows) / len(lows)),
                   "mul": mul.group(1).replace(" ", "") if mul else "", "heights": heights,
                   "flow": round(sum(deltas) / len(deltas), 1) if deltas else None}
    return days


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def tide_month(yyyymm, code=TIDE_PORT_CODE, _ver=CACHE_VER + 5):
    y, m = int(yyyymm[:4]), int(yyyymm[4:])
    html = fetch_html(f"https://www.badatime.com/{code}-{y}-{m:02d}-01.html")
    days = parse_tide(html, y, m)
    if len(days) < 20:
        raise RuntimeError(f"남당항 물때표를 제대로 읽지 못했습니다({len(days)}일만 인식)")
    return days


# 바다타임 남당항 '물흐름 %' 환산 기준 — 2026년 10월 13~27일 바다타임 화면 값과 대조해 맞춘 값
# (▲/▼ 변화량 하루 평균이 201cm면 0%, 732cm면 100%; 10/13~19는 매일 ±1%p 이내로 일치)
FLOW_ZERO, FLOW_FULL = 201.0, 732.0                       # 사리 → 조금 (물살이 약해지는 기간)
FLOW_ZERO_UP, FLOW_FULL_UP = 234.0, 727.0                 # 조금 → 사리 (물살이 세지는 기간)


def tide_with_strength(all_days):
    out = {}
    for d, v in all_days.items():
        if v.get("flow") is not None:
            prev = all_days.get(d - timedelta(days=1), {}).get("flow")
            rising = prev is not None and v["flow"] > prev and len(v.get("heights", [])) >= 4
            z, f = (FLOW_ZERO_UP, FLOW_FULL_UP) if rising else (FLOW_ZERO, FLOW_FULL)
            pct = round((v["flow"] - z) / (f - z) * 100)
        else:                                            # ▲/▼ 값이 없을 때만 예전 방식(앞뒤 7일 조차 기준)
            win = [all_days[d + timedelta(days=k)]["range"] for k in range(-7, 8) if d + timedelta(days=k) in all_days]
            lo, hi = min(win), max(win)
            pct = round((v["range"] - lo) / (hi - lo) * 100) if hi > lo else None
        out[d] = {**v, "pct": None if pct is None else max(0, min(100, pct))}
    return out


# ---- 날씨: 바다타임 남당항 페이지의 '바다날씨' 예보(약 1주일). 그림 파일은 쓰지 않고 날씨 글자만 읽어 앱 아이콘으로 표시
WX_WORD_RE = re.compile(r"(흐리고\s*비|구름많고\s*비|흐리고\s*눈|구름많고\s*눈|흐리고\s*비/눈|차차\s*흐려짐|차차\s*맑아짐|"
                        r"흐린\s*후\s*갬|비\s*또는\s*눈|눈\s*또는\s*비|구름\s*조금|구름\s*많음|맑음|흐림|소나기|천둥번개|"
                        r"뇌우|진눈깨비|안개|황사|(?<![가-힣])비(?![가-힣])|(?<![가-힣])눈(?![가-힣]))")
WX_DAY_RE = re.compile(r"(\d{1,2})\s*일\s*\(\s*([월화수목금토일])\s*\)")


def wx_icon(word):
    w = word.replace(" ", "")
    for keys, icon in ((("천둥", "뇌우"), "⛈️"), (("비또는눈", "눈또는비", "진눈깨비", "비/눈"), "🌨️"), (("눈",), "❄️"),
                       (("소나기",), "🌦️"), (("비",), "🌧️"), (("안개", "황사"), "🌫️"), (("흐림", "흐리고", "흐려짐"), "☁️"),
                       (("구름많",), "⛅"), (("구름조금", "맑아짐", "갬"), "🌤️"), (("맑음",), "☀️")):
        if any(k in w for k in keys):
            return icon
    return "🌡️"


@st.cache_data(ttl=3600, show_spinner=False)
def tide_weather(code=TIDE_PORT_CODE, _ver=CACHE_VER):
    """{날짜: '☀️ 맑음' 또는 '🌧️ 흐리고 비 → ⛅ 구름많음'(오전→오후)}, 예보 지역명"""
    html = fetch_html(f"https://www.badatime.com/{code}.html")
    full = "\n".join(clean_lines(html))
    i = full.find("바다날씨")
    sec = full[i:] if i >= 0 else full
    m_area = re.search(r"([가-힣]{2,6}앞바다)", sec)
    area = m_area.group(1) if m_area else "바다날씨"
    cut = re.search(r"시간별|지역날씨|낚시포인트", sec[50:])
    if cut:
        sec = sec[: cut.start() + 50]
    heads = list(WX_DAY_RE.finditer(sec))
    today = kst_today()
    out = {}
    for k, mh in enumerate(heads):
        block = sec[mh.end(): heads[k + 1].start() if k + 1 < len(heads) else len(sec)]
        words = []
        for w in WX_WORD_RE.findall(block):
            w = re.sub(r"\s+", " ", w).strip()
            if w and (not words or words[-1] != w) and w not in words:
                words.append(w)
        if not words:
            continue
        dnum, wd = int(mh.group(1)), mh.group(2)
        for add in (0, 1):                               # 이번 달 또는 다음 달(월말 넘김)
            yy, mm = today.year + (today.month + add - 1) // 12, (today.month + add - 1) % 12 + 1
            try:
                d = date(yy, mm, dnum)
            except ValueError:
                continue
            if WEEK[d.weekday()] == wd and d >= today - timedelta(days=1):
                out.setdefault(d, " → ".join(f"{wx_icon(w)} {w}" for w in words[:2]))
                break
    return out, area


# ---- 기온: 바다타임 날짜별 페이지(356-YYYY-MM-DD.html)의 시간별 지역날씨 표 (단기예보 기간만 값이 있음)
TEMP_HOURS = ("06", "09", "12", "15")
SEA_HOURS = ("00", "03", "06", "09", "12", "15", "18", "21")   # 바람·파고: 밤 12시부터 3시간 간격


def parse_hourly_temps(html):
    """'10.13' 날짜 줄 아래 '06시 … 17°C' 행들 → {(날짜, '06'): 17, ...}"""
    lines = clean_lines(html)
    today = kst_today()
    out, cur = {}, None
    for i, l in enumerate(lines):
        md = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", l)
        if md:
            mo, dy = int(md.group(1)), int(md.group(2))
            if any(re.fullmatch(r"\d{1,2}\s*시", x) for x in lines[i + 1: i + 25]):   # 시간표 머리 날짜만
                for yy in (today.year, today.year + 1):
                    try:
                        cand = date(yy, mo, dy)
                    except ValueError:
                        continue
                    if abs((cand - today).days) <= 10:
                        cur = cand
                        break
            continue
        mh = re.fullmatch(r"(\d{1,2})\s*시", l)
        if mh and cur:
            for x in lines[i + 1: i + 8]:
                if re.fullmatch(r"\d{1,2}\s*시", x):
                    break
                mt = re.search(r"(-?\d{1,2}(?:\.\d)?)\s*°\s*C?", x)
                if mt:
                    out.setdefault((cur, f"{int(mh.group(1)):02d}"), round(float(mt.group(1))))
                    break
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def day_temps(dstr, code=TIDE_PORT_CODE, _ver=CACHE_VER):
    html = fetch_html(f"https://www.badatime.com/{code}-{dstr}.html")
    return parse_hourly_temps(html)


# 기온 예보: Open-Meteo 공개 날씨 API (앱에서 쓰라고 공개된 무료 API — 비상업 용도). 남당항 좌표 기준 16일치 시간별 기온
TEMP_LAT, TEMP_LON = 36.533, 126.467                     # 남당항 (북위 36°32′, 동경 126°28′)


@st.cache_data(ttl=600, show_spinner=False)
def openmeteo_fc(lat=TEMP_LAT, lon=TEMP_LON, _ver=CACHE_VER):
    """Open-Meteo 최신 예보 → ({(날짜, 'HH'): 기온°C}, {(날짜, 'HH'): 바람 Kts}) — 조회할 때마다 새로 받음"""
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m&wind_speed_unit=kn"
           "&timezone=Asia%2FSeoul&forecast_days=16")
    last = None
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as ex:
            last = ex
            time.sleep(1.5 * (i + 1))
    else:
        raise RuntimeError(f"기온·바람 예보를 가져오지 못했습니다: {last}")
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps, winds = {}, {}
    for key, store, conv in (("temperature_2m", temps, round), ("wind_speed_10m", winds, lambda v: round(v))):
        for t, v in zip(times, hourly.get(key, []) or []):
            if v is None:
                continue
            d, hh = t[:10], t[11:13]                      # '2026-10-19T06:00'
            if hh in (TEMP_HOURS if store is temps else SEA_HOURS):
                store[(date.fromisoformat(d), hh)] = conv(v)
    return temps, winds


# 파고: Open-Meteo 해양 예보(공개 무료 API). 남당항은 천수만 안쪽이라 격자에 값이 없을 수 있어
# 가까운 바다 지점부터 차례로 시도해 값이 있는 첫 지점을 씀
WAVE_POINTS = [("천수만", 36.50, 126.40), ("천수만 입구", 36.42, 126.33), ("안면도 앞바다", 36.40, 126.20)]


@st.cache_data(ttl=600, show_spinner=False)
def openmeteo_waves(_ver=CACHE_VER):
    """{(날짜, 'HH'): 파고 m}, 지점 이름 — 조회할 때마다 새로 받음"""
    last = None
    for name, lat, lon in WAVE_POINTS:
        for days_ in (16, 8, 7):
            url = ("https://marine-api.open-meteo.com/v1/marine"
                   f"?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=Asia%2FSeoul&forecast_days={days_}")
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if getattr(r, "status_code", 200) == 400:
                    last = RuntimeError(f"{name}: 예보 기간 {days_}일 불가")
                    continue
                r.raise_for_status()
                data = r.json()
            except Exception as ex:
                last = ex
                break
            hourly = data.get("hourly", {})
            out = {}
            for t, v in zip(hourly.get("time", []), hourly.get("wave_height", []) or []):
                if v is not None and t[11:13] in SEA_HOURS:
                    out[(date.fromisoformat(t[:10]), t[11:13])] = round(v, 1)
            if out:
                return out, name
            last = RuntimeError(f"{name}: 파고 값 없음")
            break
    raise RuntimeError(f"파고 예보를 가져오지 못했습니다: {last}")


def temp_label(d):
    t = ss.get("temps", {})
    vals = [t.get((d, h)) for h in TEMP_HOURS]
    if all(v is None for v in vals):
        return "예보 전"
    return " / ".join("–" if v is None else f"{v}°" for v in vals)


def sea_label(d, key, unit):
    """바람(Kts)·파고(m) — 밤 12시부터 3시간 간격, 예보가 없으면 '예보 전'"""
    w = ss.get(key, {})
    vals = [w.get((d, h)) for h in SEA_HOURS]
    if all(v is None for v in vals):
        return "예보 전"
    return " / ".join(f"{int(h)}시 {'–' if v is None else v}" for h, v in zip(SEA_HOURS, vals)) + f" {unit}"


def wind_label(d):
    return sea_label(d, "winds", "Kts")


def wave_label(d):
    return sea_label(d, "waves", "m")


def sea_grid_html(d):
    """날짜 줄 아래 작은 표: 시각별 바람·파고"""
    w, v = ss.get("winds", {}), ss.get("waves", {})
    if not any((d, h) in w or (d, h) in v for h in SEA_HOURS):
        return "<span class='gf'><span class='gk'>바람·파고</span>예보 전</span>"
    def cell(x, warn):
        if x is None:
            return "<td>–</td>"
        return f"<td class='{'hi' if x >= warn else ''}'>{x}</td>"
    hrs = "".join(f"<th>{int(h)}시</th>" for h in SEA_HOURS)
    wr = "".join(cell(w.get((d, h)), 16) for h in SEA_HOURS)          # 16 Kts ≈ 8 m/s
    vr = "".join(cell(v.get((d, h)), 1.5) for h in SEA_HOURS)
    wl = "<th class='rk'>바람<small>Kts</small></th>"
    vl = "<th class='rk'>파고<small>m</small></th>"
    wave_row = (f"<tr>{vl}{vr}</tr>" if any((d, h) in v for h in SEA_HOURS)
                else f"<tr>{vl}<td colspan='{len(SEA_HOURS)}'>예보 전</td></tr>")
    wind_row = (f"<tr>{wl}{wr}</tr>" if any((d, h) in w for h in SEA_HOURS)
                else f"<tr>{wl}<td colspan='{len(SEA_HOURS)}'>예보 전</td></tr>")
    # 첫 칸 = 바람·파고 값을 가져온 지역 (바람은 남당항 좌표, 파고는 값이 있는 가까운 바다 지점)
    wa = ss.get("wave_area") or ""
    loc = TIDE_PORT_NAME if not wa or wa == TIDE_PORT_NAME else f"{TIDE_PORT_NAME}<small>파고: {htmlmod.escape(wa)}</small>"
    return f"<table class='sea'><tr><th class='rk loc'>📍 {loc}</th>{hrs}</tr>{wind_row}{wave_row}</table>"


def tide_label(d):
    t = ss.get("tide", {}).get(d)
    if not t:
        return ""
    if t.get("pct") is None:
        return ""
    return "최소" if t["pct"] <= 0 else f"{t['pct']}%"


# ---------------------------------------------------------------- 선상24 사전조회 데이터 (GitHub Actions가 data 브랜치에 저장)
DEFAULT_DATA_REPO = "eastsealee/COOL"                     # 사전조회 데이터가 저장되는 GitHub 저장소


def data_repo_slug():
    """사전조회 데이터가 있는 GitHub 저장소 'owner/repo' — secrets의 DATA_REPO 또는 앱 폴더의 .git 설정에서 찾음"""
    try:
        v = st.secrets.get("DATA_REPO")
        if v:
            return str(v).strip()
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(globals().get("__file__", "") or "."))
    try:
        txt = open(os.path.join(here, ".git", "config"), encoding="utf-8").read()
        m = re.search(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?\s*$", txt, re.M)
        if m:
            return m.group(1)
    except Exception:
        pass
    return DEFAULT_DATA_REPO or None


@st.cache_data(ttl=600, show_spinner=False)
def load_snapshot(slug, _ver=CACHE_VER):
    base = f"https://raw.githubusercontent.com/{slug}/data"
    r1 = requests.get(f"{base}/ss_ships.json", headers=HEADERS, timeout=20)
    r1.raise_for_status()
    ships = json.loads(r1.content.decode("utf-8"))
    sched, gen = {}, ""
    try:
        r2 = requests.get(f"{base}/ss_sched.json.gz", headers=HEADERS, timeout=30)
        r2.raise_for_status()
        js = json.loads(gzip.decompress(r2.content).decode("utf-8"))
        sched, gen = js.get("ships", {}), js.get("generated", "")
    except Exception:
        pass
    return {"ships": ships, "sched": sched, "generated": gen}


def snapshot_ships(snap):
    out = []
    for sid, v in (snap or {}).get("ships", {}).items():
        sido, sgg, port = ss_locate(v["name"], v["sea"])
        out.append({"site": "ss", "id": int(sid), "name": v["name"], "sea": v["sea"], "sido": sido,
                    "sigungu": sgg, "port": port, "hint": ""})
    return out


def snapshot_rows(snap, ship, ym):
    """사전조회해 둔 일정을 앱 일정 형식으로 (해당 월만)"""
    if not snap:
        return []
    gen_hm = snap.get("generated", "")[5:].replace("-", "/")   # '10/14 11:00'
    out = []
    for d, tide, boat, species, tm, remain, status, notice in snap.get("sched", {}).get(str(ship["id"]), []):
        if d[:7].replace("-", "") != ym:
            continue
        out.append({**ship_cols(ship), "date": date.fromisoformat(d), "tide": tide, "boat": boat,
                    "species": species, "time": tm, "price": "", "remain": remain, "status": status,
                    "notice": notice, "url": f"{SS_APP}/ship/schedule_fleet/{ship['id']}/{ym}", "home": "",
                    "snap": gen_hm})
    return out


# ---------------------------------------------------------------- 클럽씨피싱 (충남 홍성 남당항)
# 예약 페이지(www.clubsea.co.kr/reservation?search_date=YYYY-MM&day=DD)에 그날부터 약 열흘치가
# 날짜 → 배별 줄(배 이름 | 공지·어종·예약자 목록 | 남은인원) 표로 나옴.
# 예약자 이름 목록은 개인정보라 읽지도 저장하지도 않음 — 배 이름·어종·남은인원만 사용.
CS_SHIP = {"site": "cs", "id": 1, "name": "클럽씨피싱", "sea": "west", "sido": "충남", "sigungu": "홍성",
           "port": "남당항", "hint": "쭈꾸미 갑오징어"}
CS_REMAIN_RE = re.compile(r"^\s*(\d{1,3})\s*명\s*$|^\s*(예약\s*완료|예약\s*마감|마감)\s*$|^\s*(예약\s*불가|출조\s*취소|기상\s*악화|휴\s*무)\s*$")
CS_DATE_RE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*\(?\s*([월화수목금토일])")
CS_TIDE_RE = re.compile(r"^\s*(\d{1,2}\s*물|조금|무시|한객기|두객기|사리)\s*$")
CS_TIME_RE = re.compile(r"출항\s*(\d{1,2})\s*시\s*(?:(\d{1,2})\s*분)?")


def _cs_lines(el):
    return [x for x in (re.sub(r"\s+", " ", t).strip() for t in el.get_text("\n").split("\n")) if x]


CS_DATE_RE2 = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\(?\s*([월화수목금토일]))?")


def _norm(t):
    return re.sub(r"\s+", " ", t or "").strip()


def _pos(el):
    return (getattr(el, "sourceline", 0) or 0, getattr(el, "sourcepos", 0) or 0)


def _smallest(soup, test, maxlen):
    """조건에 맞는 글자를 가진 '가장 작은' 요소들 (날짜·물때가 여러 태그로 쪼개져 있어도 찾기 위해)"""
    out = []
    for el in soup.find_all(True):
        if el.name in ("html", "body", "table", "tbody", "thead"):
            continue
        t = _norm(el.get_text(" "))
        if not t or len(t) > maxlen or not test(t):
            continue
        if any(test(_norm(c.get_text(" "))) for c in el.find_all(True)):
            continue                                     # 더 작은 자식이 이미 조건에 맞음
        out.append((el, t))
    return out


def _cs_boat_cells(tr):
    tds = tr.find_all("td", recursive=False)
    if len(tds) < 2:
        return None
    last = _norm(tds[-1].get_text(" "))
    first = _norm(tds[0].get_text(" "))
    if CS_REMAIN_RE.match(last) or "예약하기" in first:
        return tds
    return None


def parse_clubsea_marked(soup, year, month):
    """실제 클럽씨피싱 페이지 구조(2026-10 확인): 배 줄 = <tr> 안에 td.left_person(남은인원),
    첫 칸 <strong>배 이름</strong> + 예약하기 버튼(data-dn_date=날짜), 둘째 칸 div.notice_title .desc(어종).
    예약자 목록(div.reservation_list)은 읽지 않음."""
    out, cur = [], None
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        if th is not None and not tr.select_one("td.left_person"):
            md = CS_DATE_RE2.search(_norm(th.get_text(" ")))
            if md:
                cur = _cs_mkdate(md, year, month) or cur
            continue
        lp = tr.select_one("td.left_person")
        if lp is None:
            continue
        tds = tr.find_all("td", recursive=False)
        nm_el = tds[0].find("strong") if tds else None
        name = _norm(nm_el.get_text("")) if nm_el else ""
        md = CS_DATE_RE2.search(name)
        if md:                                           # 날짜 구분 줄
            cur = _cs_mkdate(md, year, month) or cur
            continue
        if not name or name == "공지":
            continue
        btn = tr.select_one("[data-dn_date]")
        try:
            d = date.fromisoformat(btn["data-dn_date"]) if btn else cur
        except ValueError:
            d = cur
        if d is None:
            continue
        desc_el = tr.select_one("div.notice_title .desc") or tr.select_one("div.notice_title")
        desc = [l for l in (_cs_lines(desc_el) if desc_el else []) if l != "공지"]
        species = next((l for l in desc if "낚시" in l), desc[0] if desc else "")
        notice = " ".join(l for l in desc if l != species)
        tm = CS_TIME_RE.search(notice) or CS_TIME_RE.search(species)
        rm = CS_REMAIN_RE.match(_norm(lp.get_text(" ")))
        if rm and rm.group(1) is not None:
            remain = int(rm.group(1))
            status = "예약가능" if remain > 0 else "마감"
        elif rm and rm.group(2):
            remain, status = 0, "마감"
        elif rm and rm.group(3):
            remain, status = 0, re.sub(r"\s+", "", rm.group(3))
        else:
            remain, status = None, "확인필요"
        out.append({**ship_cols(CS_SHIP), "date": d, "tide": "", "boat": name, "species": species,
                    "time": f"{int(tm.group(1)):02d}:{int(tm.group(2) or 0):02d} 출항" if tm else "",
                    "price": "", "remain": remain, "status": status, "notice": notice[:200],
                    "url": f"{CS}/reservation?price_search=&search_date={d:%Y-%m}&day={d:%d}", "home": f"{CS}/"})
    return out


def _cs_mkdate(md, year, month):
    mo, dd = int(md.group(1)), int(md.group(2))
    yy = year + (1 if mo < month - 6 else 0) - (1 if mo > month + 6 else 0)
    try:
        d = date(yy, mo, dd)
    except ValueError:
        return None
    if md.group(3) and WEEK[d.weekday()] != md.group(3):
        return None
    return d


CS_TR_SPLIT = re.compile(r"<tr[\s>]", re.I)
CS_LP_RE = re.compile(r"class=[\"'][^\"']*left_person[^\"']*[\"'][^>]*>(.*?)</td>", re.I | re.S)
CS_STRONG_RE = re.compile(r"<strong[^>]*>(.*?)</strong>", re.I | re.S)
CS_DN_RE = re.compile(r"data-dn_date=[\"'](\d{4}-\d{2}-\d{2})[\"']", re.I)
CS_DESC_RE = re.compile(r"class=[\"']desc[\"'][^>]*>(.*?)</div>", re.I | re.S)
CS_TIDE_RE = re.compile(r">\s*(\d{1,2}\s*물|조금|한조금|무시|한객기)\s*<")
CS_N_RE = re.compile(r"^\s*(\d{1,3})\s*명\s*$")


def _cs_txt(frag):
    return _norm(re.sub(r"<[^>]+>", " ", frag).replace("&nbsp;", " "))


CS_CLOSED = {"예약마감", "예약완료", "마감"}
@st.cache_resource(show_spinner=False)
def _cs_closed_store():
    return {}


CS_CLOSED_COUNT = _cs_closed_store()                     # 날짜 → 예약마감 배 척수 (안내 문구용)


def parse_clubsea_simple(html, year, month):
    """표의 줄(<tr>)마다 날짜·배 이름·남은인원 칸을 읽어, 예약마감(예약완료)이 아닌 배를 모두 가져옴.
    마감된 배는 날짜별 척수만 CS_CLOSED_COUNT에 기록. 예약자 이름 목록은 읽지 않음."""
    out, cur, tide, ctime, closed = [], None, "", {}, {}
    for chunk in CS_TR_SPLIT.split(html)[1:]:
        lp = CS_LP_RE.search(chunk)
        head = chunk[:lp.start()] if lp else chunk
        head_wo_desc = CS_DESC_RE.sub(" ", head)
        md = CS_DATE_RE2.search(_cs_txt(head_wo_desc))   # 날짜 칸(또는 날짜 제목 줄)
        if md:
            cur = _cs_mkdate(md, year, month) or cur
            mt = CS_TIDE_RE.search(head_wo_desc)
            tide = re.sub(r"\s+", "", mt.group(1)) if mt else ""
        if not lp:
            continue
        ms = CS_STRONG_RE.search(head)
        name = _cs_txt(ms.group(1)) if ms else ""
        if name == "공지" and cur is not None:          # 그날 공통 공지의 '출항 6시10분'
            tg = CS_TIME_RE.search(_cs_txt(chunk[:lp.start()]))
            if tg:
                ctime[cur] = f"{int(tg.group(1)):02d}:{int(tg.group(2) or 0):02d} 출항"
        lp_txt = _cs_txt(lp.group(1))
        if not lp_txt or lp_txt == "-":
            continue
        mn = CS_N_RE.match(lp_txt)
        mdn0 = CS_DN_RE.search(chunk)
        d0 = date.fromisoformat(mdn0.group(1)) if mdn0 else cur
        if (not mn and re.search(r"마\s*감|완\s*료", lp_txt)) or (mn and int(mn.group(1)) == 0):
            if d0 is not None:
                closed.setdefault(d0, set()).add(name)
            continue                                     # 예약마감은 제외, 나머지는 모두 표시
        if not name or name == "공지" or CS_DATE_RE2.search(name):
            continue
        mdn = CS_DN_RE.search(chunk)
        d = date.fromisoformat(mdn.group(1)) if mdn else cur
        if d is None:
            continue
        mdesc = CS_DESC_RE.search(chunk)
        desc = _cs_txt(mdesc.group(1)) if mdesc else ""
        tm = CS_TIME_RE.search(desc)
        species = re.split(r"\s+-\s+|\s*[\"“(]", desc)[0].strip()
        remain = int(mn.group(1)) if mn else None
        out.append({**ship_cols(CS_SHIP), "date": d, "tide": tide if (mdn is None or d == cur) else "",
                    "boat": name, "species": species or desc[:30],
                    "time": f"{int(tm.group(1)):02d}:{int(tm.group(2) or 0):02d} 출항" if tm else ctime.get(d, ""),
                    "price": "", "remain": remain,
                    "status": "예약가능" if mn else re.sub(r"\s+", "", lp_txt),
                    "notice": desc[len(species):].strip(" -")[:200] if species else "", "url": f"{CS}/reservation?price_search=&search_date={d:%Y-%m}&day={d:%d}",
                    "home": f"{CS}/"})
    for d_, names in closed.items():
        CS_CLOSED_COUNT[d_] = len(names)
    uniq = {}
    for r in out:
        uniq.setdefault((r["date"], r["boat"]), r)
    return list(uniq.values())


def parse_clubsea(html, year, month, stats=None):
    """클럽씨피싱 예약 페이지 → 일정 목록 (배마다 한 줄). 예약자 이름 목록은 읽지 않음."""
    simple = parse_clubsea_simple(html, year, month)
    if simple:
        if stats is not None:
            stats.update(dates=len({r["date"] for r in simple}), boat_rows=len(simple), chars=len(html))
        return simple
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("td.left_person"):
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        marked = parse_clubsea_marked(soup, year, month)
        if stats is not None:
            stats.update(dates=len({r["date"] for r in marked}), boat_rows=len(marked), chars=len(html))
        if marked:
            # 물때·공통 출항시간은 일반 방식으로 보충
            extra = {(r["date"], r["boat"]): r for r in _parse_clubsea_generic(soup, year, month)}
            uniq = {}
            for r in marked:
                g = extra.get((r["date"], r["boat"]))
                if g:
                    r["tide"] = r["tide"] or g["tide"]
                    r["time"] = r["time"] or g["time"]
                uniq.setdefault((r["date"], r["boat"]), r)
            return list(uniq.values())
    return _parse_clubsea_generic(soup, year, month, stats, html_len=len(html))


def _parse_clubsea_generic(soup, year, month, stats=None, html_len=0):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    events = []
    for el, t in _smallest(soup, lambda t: bool(CS_DATE_RE2.search(t)), 30):
        md = CS_DATE_RE2.search(t)
        mo, dd = int(md.group(1)), int(md.group(2))
        yy = year + (1 if mo < month - 6 else 0) - (1 if mo > month + 6 else 0)
        try:
            d = date(yy, mo, dd)
        except ValueError:
            continue
        if md.group(3) and WEEK[d.weekday()] != md.group(3):
            continue
        rest = t[md.end():].strip(" ),")
        mt = CS_TIDE_RE.match(rest) if rest else None
        events.append((_pos(el), "date", (d, mt.group(1).replace(" ", "") if mt else "")))
    for el, t in _smallest(soup, lambda t: bool(CS_TIDE_RE.match(t)), 6):
        if el.find_parent("tr") is not None and _cs_boat_cells(el.find_parent("tr")):
            continue
        events.append((_pos(el), "tide", CS_TIDE_RE.match(t).group(1).replace(" ", "")))
    for el, t in _smallest(soup, lambda t: bool(CS_TIME_RE.search(t)), 80):
        if el.find_parent("tr") is not None and _cs_boat_cells(el.find_parent("tr")):
            continue
        tm = CS_TIME_RE.search(t)
        events.append((_pos(el), "time", f"{int(tm.group(1)):02d}:{int(tm.group(2) or 0):02d} 출항"))
    n_rows = 0
    for tr in soup.find_all("tr"):
        tds = _cs_boat_cells(tr)
        if tds:
            n_rows += 1
            events.append((_pos(tr), "boat", tds))
    events.sort(key=lambda e: e[0])
    if stats is not None:
        stats.update(dates=sum(1 for e in events if e[1] == "date"), boat_rows=n_rows, chars=html_len)

    out, cur, tide, day_time = [], None, "", ""
    for _, kind, val in events:
        if kind == "date":
            cur, tide, day_time = val[0], val[1], ""
            continue
        if cur is None:
            continue
        if kind == "tide":
            tide = tide or val
            continue
        if kind == "time":
            day_time = day_time or val
            continue
        tds = val
        name_el = tds[0].find(["strong", "b"])
        src_el = name_el if name_el else tds[0]
        for btn in src_el.find_all(["button", "a"]):
            if "예약하기" in btn.get_text():
                btn.extract()
        name = _norm(re.sub(r"예약하기", " ", src_el.get_text("")))   # 줄바꿈으로 쪼개진 이름은 붙여서
        detail = [l for l in _cs_lines(tds[1]) if "님" not in l and not l.startswith("/")
                  and l not in ("공지", "예약확정", "예약", "미정", "예약하기")]
        detail = [re.sub(r"^공지\s*", "", l) for l in detail]
        # 같은 줄에 붙은 예약 상태 표시(예약확정·예약·미정)와 그 뒤 내용은 잘라냄
        detail = [re.split(r"\s*(?:예약확정|예약대기|(?<![가-힣])예약(?![가-힣])|(?<![가-힣])미정(?![가-힣]))", l)[0].strip()
                  for l in detail]
        detail = [l for l in detail if l]
        species = next((l for l in detail if "낚시" in l), detail[0] if detail else "")
        notice = " ".join(l for l in detail if l != species)
        tm = CS_TIME_RE.search(notice) or CS_TIME_RE.search(species)
        when = f"{int(tm.group(1)):02d}:{int(tm.group(2) or 0):02d} 출항" if tm else day_time
        rm = CS_REMAIN_RE.match(_norm(tds[-1].get_text(" ")))
        if rm and rm.group(1) is not None:
            remain = int(rm.group(1))
            status = "예약가능" if remain > 0 else "마감"
        elif rm and rm.group(2):
            remain, status = 0, "마감"
        elif rm and rm.group(3):
            remain, status = 0, re.sub(r"\s+", "", rm.group(3))
        else:
            remain, status = None, "확인필요"
        out.append({**ship_cols(CS_SHIP), "date": cur, "tide": tide, "boat": name, "species": species,
                    "time": when, "price": "", "remain": remain, "status": status, "notice": notice[:200],
                    "url": f"{CS}/reservation?price_search=&search_date={cur:%Y-%m}&day={cur:%d}",
                    "home": f"{CS}/"})
    uniq = {}
    for r in out:
        uniq.setdefault((r["date"], r["boat"]), r)
    return list(uniq.values())


@st.cache_data(ttl=180, show_spinner=False)
def cs_page(dstr, _ver=CACHE_VER + 2):
    d = date.fromisoformat(dstr)
    tries = [(f"{CS}/reservation?price_search=&search_date={d:%Y-%m}&day={d:%d}", None),
             (f"{CS}/reservation", None),
             (f"{CS}/reservation?price_search=&search_date={d:%Y-%m}&day={d:%d}",
              {**MOBILE_HEADERS, "Referer": f"{CS}/"})]
    notes = []
    for url, hdr in tries:
        try:
            html = fetch_html(url, headers=hdr, tries=2)
        except Exception as ex:
            notes.append(f"접속 실패({type(ex).__name__}: {str(ex)[:80]})")
            continue
        stats = {}
        rows = parse_clubsea(html, d.year, d.month, stats)
        if rows:
            opened = {}
            for r in rows:
                opened[r["date"]] = opened.get(r["date"], 0) + 1
            CS_CLOSED_COUNT.setdefault("_pages", {})[dstr] = {
                "chars": len(html), "open": opened, "at": kst_now().strftime("%H:%M:%S")}
            return rows
        head = " ".join(clean_lines(html))[:120]
        notes.append(f"글자 {stats.get('chars', len(html)):,}자·배 줄 {stats.get('boat_rows', 0)}개 · 앞부분: {head}")
    raise RuntimeError("클럽씨피싱 예약 페이지를 읽지 못함 — " + " / ".join(notes))


def cs_ship(ship_t, days_t):
    """선택한 날짜들을 덮을 때까지 그 날짜부터 시작하는 페이지를 읽음 (한 페이지에 약 열흘치)"""
    need = sorted(set(days_t))
    got = {}
    for d in need:
        if d in got:
            continue
        for r in cs_page(d.isoformat()):
            got.setdefault(r["date"], []).append(r)
        got.setdefault(d, [])
    return [r for d in need for r in got.get(d, [])]


def cs_catalog(_ver=CACHE_VER):
    return [dict(CS_SHIP)]


# ---------------------------------------------------------------- 라마르호 (lamar.totb.kr, 충남 홍성 남당항)
# 월별 달력(index.asp?stype=M&ndate=YYYY-MM-01). 날짜 칸 글자 예: '26 쭈갑, 7물 쭈갑-9만원(잔여17)' / '31 쭈갑, 12물 쭈갑-9만원(완료)'
# 칸 안의 예약자 목록('- 이름(1명) 입금확인')은 읽지도 저장하지도 않음.
LM = "https://lamar.totb.kr"
LM_SHIP = {"site": "lm", "id": 1, "name": "라마르호", "sea": "west", "sido": "충남", "sigungu": "홍성",
           "port": "남당항", "hint": "쭈갑 주꾸미 갑오징어"}
LM_DAY_RE = re.compile(r"^\s*(\d{1,2})(?=\s|$)")
LM_PROD_RE = re.compile(r"([가-힣A-Za-z0-9·/&]+(?:\s*-\s*[\d,.]+\s*만?\s*원)?)\s*\(\s*(완료|마감|예약\s*마감|예약\s*불가|"
                        r"잔여\s*(\d{1,3})\s*(?:명|석)?)\s*\)")
LM_MUL_RE = re.compile(r"(\d{1,2}\s*물|조금|무시|한객기)")


def lm_cell_text(td):
    """날짜 칸 글자에서 예약자 목록 부분을 잘라냄('- 이름(N명)' 앞까지만 사용)"""
    t = _norm(td.get_text(" "))
    return re.split(r"\s-\s*\S+?\(\s*\d+\s*명\s*\)", t, maxsplit=1)[0]


def parse_lamar(html, y, m):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    out, seen = [], set()
    for td in soup.find_all("td"):
        if td.find("td"):                                   # 바깥 칸은 건너뛰고 가장 안쪽 칸만
            continue
        t = lm_cell_text(td)
        md = LM_DAY_RE.match(t)
        if not md:
            continue
        try:
            d = date(y, m, int(md.group(1)))
        except ValueError:
            continue
        head = t[:t.find("(")] if "(" in t else t
        mm = LM_MUL_RE.search(head)
        for pm in LM_PROD_RE.finditer(t):
            prod = _norm(pm.group(1))
            if (d, prod) in seen:
                continue
            seen.add((d, prod))
            st_ = re.sub(r"\s+", "", pm.group(2))
            if pm.group(3) is not None:
                remain = int(pm.group(3))
                status = "예약가능" if remain > 0 else "마감"
            elif "불가" in st_:
                remain, status = 0, "예약불가"
            else:
                remain, status = 0, "마감"
            name, _, price = prod.partition("-")
            out.append({**ship_cols(LM_SHIP), "date": d, "tide": re.sub(r"\s+", "", mm.group(1)) if mm else "",
                        "boat": "라마르호", "species": name.strip(), "time": "",
                        "price": price.strip(), "remain": remain, "status": status, "notice": "",
                        "url": f"{LM}/index.asp?stype=M&ndate={y}-{m:02d}-01", "home": f"{LM}/"})
    return out


@st.cache_data(ttl=180, show_spinner=False)
def lm_month(yyyymm, _ver=CACHE_VER):
    y, m = int(yyyymm[:4]), int(yyyymm[4:])
    html = fetch_html(f"{LM}/index.asp?stype=M&ndate={y}-{m:02d}-01", timeout=30)
    rows = parse_lamar(html, y, m)
    if not rows and "잔여" not in html and "완료" not in html:
        head = " ".join(clean_lines(html))[:150]
        raise RuntimeError(f"{m}월 달력을 읽지 못함 — 글자 {len(html):,}자 · 앞부분: {head}")
    return rows


def lm_ship(ship_t, days_t):
    need = set(days_t)
    out = []
    for ym in sorted({f"{d.year}{d.month:02d}" for d in need}):
        out += [r for r in lm_month(ym) if r["date"] in need]
    return out


def lm_catalog(_ver=CACHE_VER):
    return [dict(LM_SHIP)]


# ---------------------------------------------------------------- 공통
def ship_cols(ship):
    return {"site": ship["site"], "ship_id": ship["id"], "ship": ship["name"], "sea": ship["sea"],
            "sido": ship["sido"], "sigungu": ship["sigungu"], "port": ship.get("port", "")}


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def fish_options(_ver=CACHE_VER):
    fish = []
    try:
        soup = BeautifulSoup(fetch_html(f"{SS_APP}/ship/list?area=all"), "html.parser")
        anchor = soup.find(string=re.compile(r"^\s*전체어종\s*$"))
        node = anchor.parent if anchor else None
        while node is not None and len(node.find_all(["a", "li", "button"])) < 15:
            node = node.parent
        if node is not None:
            for el in node.find_all(["a", "li", "button", "span"]):
                t = el.get_text(strip=True)
                if t and t not in fish and t not in ("전체어종", "전체", "거리순", "베스트조황", "출조안내") \
                        and re.fullmatch(r"[가-힣]{2,8}", t):
                    fish.append(t)
    except Exception:
        pass
    if len(fish) < 20:
        fish = list(SS_FISH)
    for f in TF_FISH:
        if f not in fish:
            fish.append(f)
    # '쭈갑'(주꾸미+갑오징어)은 주꾸미 바로 위에
    fish = [f for f in fish if f != "쭈갑"]
    at = next((i for i, f in enumerate(fish) if f in ("주꾸미", "쭈꾸미")), 0)
    fish.insert(at, "쭈갑")
    return fish


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def resolve_manual(token):
    """직접 추가: 선상24 배번호/홈페이지(ss:2174, gamsung) 또는 더피싱 uid(tf:6198)"""
    t = token.strip()
    if t.lower().startswith("tf:") and t[3:].isdigit():
        return {"site": "tf", "id": int(t[3:]), "name": f"더피싱 {t[3:]}", "sea": "", "sido": "직접추가",
                "sigungu": "직접추가", "port": "", "hint": ""}
    if t.lower().startswith("ss:"):
        t = t[3:]
    if t.isdigit():
        return {"site": "ss", "id": int(t), "name": f"선상24 {t}", "sea": "", "sido": "직접추가",
                "sigungu": "직접추가", "port": "", "hint": ""}
    host = re.sub(r"^https?://", "", t).split("/")[0]
    if not host.endswith(".sunsang24.com"):
        host += ".sunsang24.com"
    try:
        html = fetch_html(f"https://{host}/")
    except Exception:
        return None
    m = re.search(r"/ship/schedule(?:_fleet)?/(\d+)", html)
    if not m:
        return None
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True).split(",")[0] if soup.title else host
    return {"site": "ss", "id": int(m.group(1)), "name": title, "sea": "", "sido": "직접추가",
            "sigungu": "직접추가", "port": "", "hint": ""}


def freeze(ship):
    return tuple(sorted(ship.items()))


# ================================================================ 화면
st.set_page_config(page_title="선상낚시 예약조회", page_icon="🎣", layout="wide")
ACCENT = "#FFD43B"        # 강조색(부표 노랑) — 예약가능·선택·조회 버튼에 공통으로 씀
INK = "#12304A"           # 깊은 바다색 — 머리띠·표 머리글
SEA = "#2F7FC1"           # 바다 파랑 — 체크·선택 표시
st.markdown(f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp td, .stApp th,
.stApp h1, .stApp h2, .stApp h3, .stApp [data-baseweb="select"] div, .stApp summary {{
  font-family: "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif !important;
}}
.block-container {{padding-top: 3.6rem !important; max-width: 1320px;}}
.stApp [data-baseweb="tag"], .stApp [data-tag] {{background:{ACCENT} !important; color:{INK} !important; font-weight:700;}}
.stApp [data-baseweb="tag"] *, .stApp [data-tag] * {{color:{INK} !important; fill:{INK} !important;}}
.stApp [data-testid="stCheckbox"] label[data-selected="true"] > div:not([data-testid]),
.stApp [data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {{
  background:{SEA} !important; border-color:{SEA} !important;}}
/* ---------- 머리띠 ---------- */
.hero {{display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap;
  background:{INK}; color:#fff; border-radius:14px; padding:22px 26px 20px; margin-bottom:14px;
  border-bottom:5px solid {ACCENT};}}
.hero-t {{font-size:1.9rem; font-weight:800; letter-spacing:-.02em; line-height:1.2;}}
.hero-s {{font-size:.95rem; opacity:.82; margin-top:4px;}}
.hero-v {{font-size:.75rem; opacity:.6; white-space:nowrap;}}
/* ---------- 단계 제목 ---------- */
.step {{display:flex; align-items:center; gap:10px; margin:1.1rem 0 .45rem; flex-wrap:wrap;}}
.step-n {{width:1.75rem; height:1.75rem; border-radius:50%; background:{ACCENT}; color:{INK}; font-weight:800;
  display:inline-flex; align-items:center; justify-content:center; font-size:.95rem; flex:none;}}
.step-t {{font-size:1.2rem; font-weight:800; letter-spacing:-.01em;}}
.step-h {{font-size:.85rem; opacity:.62;}}
.res-head {{font-size:1.45rem; font-weight:800; letter-spacing:-.02em; margin:1.6rem 0 .5rem;
  padding-top:1.1rem; border-top:2px solid rgba(128,128,128,.25);}}
.st-key-filters {{border:1px solid rgba(128,128,128,.28); border-radius:12px; padding:10px 14px 12px;
  background:rgba(128,128,128,.05);}}
/* ---------- 휴대폰: 지역·어종·날짜 요약 버튼과 팝업 ---------- */
.st-key-m_region button, .st-key-m_fish button, .st-key-m_days button {{
  min-height: 3.4rem; justify-content: flex-start !important; width: 100%; text-align: left; border-radius: 12px !important;
  border: 1.5px solid rgba(128,128,128,.4) !important; padding: 0 16px !important;}}
.st-key-m_region button p, .st-key-m_fish button p, .st-key-m_days button p {{
  font-size: 1.05rem !important; font-weight: 700 !important; white-space: normal; text-align: left;}}
[data-testid="stDialog"] button[data-variant="pills"] {{min-height: 2.75rem; padding: 0 16px !important;
  border-radius: 999px !important;}}
[data-testid="stDialog"] button[data-variant="pills"] p {{font-size: 1.02rem !important; font-weight: 600 !important;}}
[data-testid="stDialog"] button[data-variant="pills"][data-selected="true"] {{background: {ACCENT} !important;
  border-color: {ACCENT} !important;}}
[data-testid="stDialog"] button[data-variant="pills"][data-selected="true"] p {{color: {INK} !important; font-weight: 800 !important;}}
[data-testid="stDialog"] .st-key-quick [data-testid="stHorizontalBlock"],
[data-testid="stDialog"] .st-key-pk_fish_bar [data-testid="stHorizontalBlock"] {{flex-wrap: wrap !important; gap: 8px !important;}}
[data-testid="stDialog"] .st-key-quick [data-testid="stColumn"],
[data-testid="stDialog"] .st-key-pk_fish_bar [data-testid="stColumn"] {{min-width: calc(50% - 8px) !important;
  flex: 1 1 calc(50% - 8px) !important; width: auto !important;}}
[data-testid="stDialog"] .st-key-cal {{max-width: none; padding: 8px 4px 6px;}}
[data-testid="stDialog"] .st-key-cal [data-testid="stHorizontalBlock"] {{gap: 3px !important;}}
/* ---------- 달력 카드 ---------- */
.st-key-cal {{
  max-width: 560px; border: 1px solid rgba(128,128,128,.28); border-radius: 18px;
  padding: 14px 14px 10px; background: rgba(128,128,128,.06);
}}
.st-key-cal [data-testid="stHorizontalBlock"] {{flex-wrap: nowrap !important; gap: 6px !important;}}
.st-key-cal [data-testid="stColumn"] {{min-width: 0 !important; flex: 1 1 0 !important; width: auto !important;}}
.st-key-cal .stButton, .st-key-cal [data-testid="stButton"] {{width: 100% !important;}}
.st-key-cal .stButton button {{
  width: 100% !important; min-height: 2.75rem; padding: 0 !important; border-radius: 12px !important;
  border: 1px solid transparent !important; background: transparent !important;
  font-size: 1.02rem; font-weight: 600; transition: all .12s ease;
}}
.st-key-cal .stButton button:hover:not(:disabled) {{
  background: rgba(255,212,59,.18) !important; border-color: rgba(255,212,59,.7) !important;
}}
.st-key-cal .stButton button p {{font-size: 1.08rem !important; font-weight: 700 !important;}}
.st-key-cal div.st-key-calnav_prev button p, .st-key-cal div.st-key-calnav_next button p {{font-size: 1.6rem !important;
  line-height: 1 !important; margin-top: -3px;}}
.st-key-cal .stButton button:disabled {{opacity: .28;}}
.st-key-cal .cal-title {{text-align:center; font-size:1.3rem; font-weight:800; margin:.35rem 0 0; letter-spacing:.02em;}}
.st-key-cal .cal-sub {{text-align:center; font-size:.82rem; opacity:.7; margin:0 0 .2rem;}}
.st-key-cal .wk {{text-align:center; font-size:.8rem; font-weight:700; opacity:.85; padding:.2rem 0 .1rem;
  border-bottom: 1px solid rgba(128,128,128,.25); margin-bottom: .2rem;}}
.st-key-cal div.st-key-calnav_prev button, .st-key-cal div.st-key-calnav_next button {{
  border-radius: 50% !important; width: 2.6rem !important; min-height: 2.6rem !important;
  border: 1px solid rgba(128,128,128,.45) !important; font-size: 1.5rem !important; line-height: 1;
}}
.st-key-cal div.st-key-calnav_prev, .st-key-cal div.st-key-calnav_next {{width: auto !important;}}
.st-key-cal div.st-key-calnav_next {{margin-left: auto;}}
/* ---------- 조회 버튼 ---------- */
button[kind="primary"] {{background: {ACCENT} !important; border-color: {ACCENT} !important;
  color: {INK} !important; font-weight: 800 !important; min-height: 3.2rem; border-radius: 12px !important;
  box-shadow: 0 3px 0 #C9A21A;}}
button[kind="primary"] p {{font-size: 1.12rem !important; font-weight: 800 !important;}}
button[kind="primary"]:hover:not(:disabled) {{filter: brightness(1.04);}}
button[kind="primary"]:active:not(:disabled) {{transform: translateY(2px); box-shadow: 0 1px 0 #C9A21A;}}
button[kind="primary"]:disabled {{opacity: .45;}}
/* ---------- 빠른 선택 버튼 ---------- */
.st-key-quick {{max-width: 560px;}}
.st-key-quick .stButton button {{border-radius: 999px !important; font-size: .88rem;}}
.chips {{max-width:560px; display:flex; flex-wrap:wrap; gap:6px; margin:.3rem 0 .2rem;}}
.chip {{background:{ACCENT}; color:{INK}; font-weight:700; font-size:.85rem; padding:3px 11px; border-radius:999px;}}
.chip.we {{background:#FFE8A3;}}
</style>""", unsafe_allow_html=True)
st.markdown(f"""<div class='hero'>
  <div class='hero-l'><div class='hero-t'>선상낚시 예약조회</div>
  <div class='hero-s'>선상24, 더피싱, 클럽씨피싱, 라마르호의 남은 자리를 날짜별로 한 화면에서 봅니다</div></div>
  <div class='hero-v'>{htmlmod.escape(APP_VERSION)}</div></div>""", unsafe_allow_html=True)


def step_head(n, title, hint=""):
    st.markdown(f"<div class='step'><span class='step-n'>{n}</span><span class='step-t'>{title}</span>"
                f"<span class='step-h'>{hint}</span></div>", unsafe_allow_html=True)

today = kst_today()
ss = st.session_state
ss.setdefault("sel_days", set())
if ss.get("app_ver") != APP_VERSION:
    # 앱이 새 버전으로 바뀌면 이전 버전이 계산해 둔 조회 결과(조류세기 포함)를 버림 → 새 계산식으로 다시 조회
    had_rows = "rows" in ss
    for k in ("rows", "errors", "tide", "probes", "queried", "fetched"):
        ss.pop(k, None)
    ss.sel_days = set()                                  # 이전 버전에서 미리 골라져 있던 날짜도 해제
    ss.app_ver = APP_VERSION
    if had_rows:
        st.toast(f"새 버전({APP_VERSION})이 적용되어 이전 조회 결과를 지웠습니다. 다시 조회해 주세요.")
ss.setdefault("cal_ym", (today.year, today.month))

site_sel = st.multiselect("조회할 사이트", list(SITES.values()), default=list(SITES.values()))
site_codes = [k for k, v in SITES.items() if v in site_sel]

SNAP_SLUG = data_repo_slug()
SNAP = None
if SNAP_SLUG:
    try:
        SNAP = load_snapshot(SNAP_SLUG)
    except Exception:
        SNAP = None                                       # 아직 사전조회가 한 번도 안 돈 경우 등
CATALOG_FN = {"ss": ss_catalog, "tf": tf_catalog, "cs": cs_catalog, "lm": lm_catalog}
catalog, counts = [], {}
with st.spinner("배 목록을 불러오는 중... (처음 한 번만 1~2분 걸립니다)"):
    for code in site_codes:
        pkey = f"partial_{code}"
        if pkey in ss:                                   # 이번 접속에서 이미 실패했던 사이트는 모은 만큼 사용
            part = ss[pkey]["rows"]
            st.warning(f"⚠️ {ss[pkey]['msg']} — 불러온 {len(part)}척으로 조회합니다. "
                       f"아래 [배 목록 다시 불러오기]로 재시도할 수 있습니다.")
        else:
            try:
                part = CATALOG_FN[code]()
            except CatalogError as ex:
                ss[pkey] = {"rows": ex.rows, "msg": str(ex)}
                part = ex.rows
                st.warning(f"⚠️ {ex} — 불러온 {len(part)}척으로 조회합니다. "
                           f"아래 [배 목록 다시 불러오기]로 재시도할 수 있습니다.")
            except Exception as ex:
                ss[pkey] = {"rows": [], "msg": f"{SITES[code]} 목록 오류: {ex}"}
                part = []
                st.error(f"{SITES[code]} 배 목록을 불러오지 못했습니다: {ex}")
        if code == "ss":                                 # 사전조회 목록 + 배경 수집으로 찾은 배 합치기
            have = {r["id"] for r in part}
            for extra in (snapshot_ships(SNAP), ss_bg_rows()):
                add = [r for r in extra if r["id"] not in have]
                part = part + add
                have |= {r["id"] for r in add}
        counts[code] = len(part)
        catalog += part
with st.expander("배 목록 · 다시 불러오기 · CSV 받기"):
    lc1, lc2 = st.columns([3, 1], vertical_alignment="center")
    bg_note = ""
    if "ss" in site_codes:
        _bs = ss_bg_state()
        with _bs["lock"]:
            _pg = dict(_bs["page"]); _rd = _bs["rounds"]
        if not _rd:
            bg_note = (" · 선상24 배 목록 확장 중(게시판 " + ", ".join(f"{SEAS[k]} {v}p" for k, v in _pg.items())
                       + ") — 몇 분 뒤 다시 조회하면 더 많은 배가 나옵니다")
    snap_note = ""
    if "ss" in site_codes:
        snap_note = (f" · 선상24 사전조회: 배 {len(SNAP['ships'])}척, 일정 {SNAP['generated']} 기준" if SNAP
                     else " · 선상24 사전조회 데이터 없음(아직 첫 실행 전)")
    lc1.caption("배 목록: " + " · ".join(f"{SITES[k]} {n}척" for k, n in counts.items()) + snap_note + bg_note)
    if lc2.button("🔄 배 목록 다시 불러오기", width="stretch"):
        for code, fn in CATALOG_FN.items():
            if hasattr(fn, "clear"):
                fn.clear()
            ss.pop(f"partial_{code}", None)
        st.rerun()

    def catalog_csv(code):
        rows_ = [s for s in catalog if s["site"] == code]
        df_ = pd.DataFrame([{
            "사이트": SITES[code], "번호": s["id"], "배": s["name"], "바다": SEAS.get(s["sea"], s["sea"]),
            "시도": s["sido"], "시군": s["sigungu"], "항구": s["port"],
            "목록 어종/소개": s.get("hint", ""),
            "예약페이지": (f"{SS_APP}/ship/schedule_fleet/{s['id']}" if code == "ss"
                        else f"{CS}/reservation" if code == "cs"
                    else f"{LM}/" if code == "lm"
                        else f"{TF}/reservation/list.php?uid={s['id']}"),
        } for s in sorted(rows_, key=lambda s: (s["sea"], s["sido"], s["sigungu"], s["port"], s["name"]))])
        return df_.to_csv(index=False).encode("utf-8-sig"), len(rows_)


    dcols = st.columns(max(2, len(site_codes)) + 1)
    for col, code in zip(dcols, site_codes):
        data_, n_ = catalog_csv(code)
        col.download_button(f"📥 {SITES[code]} 배 목록 CSV다운로드 ({n_}척)", data_, width="stretch",
                            file_name=f"{SITES[code]}_배목록_{kst_today():%Y%m%d}.csv", mime="text/csv",
                            key=f"dl_cat_{code}")
    if "ss" in site_codes and bg_note:
        st.caption("선상24 목록은 배경 수집이 끝날 때까지 계속 늘어납니다. 전체 목록이 필요하면 10~20분 뒤에 받으세요.")
fish_list = fish_options()

# ----- 휴대폰이면 지역·어종·날짜를 팝업으로 고름 (주소 끝에 ?view=m / ?view=pc 로 강제 가능)
def is_phone():
    v = st.query_params.get("view", "")
    if v in ("m", "pc"):
        return v == "m"
    try:
        ua = st.context.headers.get("User-Agent", "") or ""
    except Exception:
        ua = ""
    return bool(re.search(r"iPhone|iPod|Android.+Mobile|Mobile Safari|Windows Phone", ua))


PHONE = is_phone()
ss.setdefault("region", {"sea": "전체", "sido": "전체", "sgg": "전체", "port": "전체"})
ss.setdefault("fish_v", [])
fish_list_set = set(fish_list)
ss.fish_v = [f for f in ss.fish_v if f in fish_list_set]


def region_pool(rg):
    """지역 선택값 → (해당 배 목록, 정리된 선택값, 각 단계 선택지)"""
    sea = rg.get("sea", "전체") if rg.get("sea") in ["전체"] + list(SEAS.values()) else "전체"
    sea_code = next((k for k, v in SEAS.items() if v == sea), "all")
    p_ = [s_ for s_ in catalog if sea_code == "all" or s_["sea"] == sea_code]
    sidos = ["전체"] + sorted({s_["sido"] for s_ in p_}, key=lambda x: (x == "기타", x))
    sido_ = rg.get("sido") if rg.get("sido") in sidos else "전체"
    p_ = [s_ for s_ in p_ if sido_ == "전체" or s_["sido"] == sido_]
    sggs = ["전체"] + sorted({s_["sigungu"] for s_ in p_})
    sgg_ = rg.get("sgg") if rg.get("sgg") in sggs else "전체"
    p_ = [s_ for s_ in p_ if sgg_ == "전체" or s_["sigungu"] == sgg_]
    ports_ = ["전체"] + sorted({s_["port"] for s_ in p_ if s_["port"]})
    port_ = rg.get("port") if rg.get("port") in ports_ else "전체"
    p_ = [s_ for s_ in p_ if port_ == "전체" or s_["port"] == port_]
    return p_, {"sea": sea, "sido": sido_, "sgg": sgg_, "port": port_}, (sidos, sggs, ports_)


def region_text(rg):
    parts = [v for v in (rg["sea"], rg["sido"], rg["sgg"], rg["port"]) if v != "전체"]
    return " › ".join(parts) if parts else "전체 지역"


def render_calendar(scope="app"):
    """달력 + 빠른 선택. scope='fragment'면 팝업 안에서 팝업을 닫지 않고 다시 그림"""
    y, m = ss.cal_ym
    month_days = [d for wk in calendar.Calendar(6).monthdatescalendar(y, m) for d in wk if d.month == m]
    rules = []                                           # 일=빨강, 토=파랑, 오늘=테두리, 선택=노랑
    for d in month_days:
        k = f".st-key-cal div.st-key-d{d.isoformat()} button"
        if d in ss.sel_days:
            rules.append(f"{k}{{background:{ACCENT} !important;color:{INK} !important;"
                         f"border-color:{ACCENT} !important;box-shadow:0 2px 8px rgba(255,212,59,.35);}}")
        elif d.weekday() == 6:
            rules.append(f"{k}{{color:#FF6B6B !important;}}")
        elif d.weekday() == 5:
            rules.append(f"{k}{{color:#4DABF7 !important;}}")
        if d == today:
            rules.append(f"{k}{{outline:2px solid {ACCENT};outline-offset:-2px;}}")
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)
    with st.container(key="cal"):
        n1, n2, n3 = st.columns([1, 4, 1], vertical_alignment="center")
        with n1:
            if st.button("‹", key="calnav_prev", disabled=(y, m) <= (today.year, today.month)):
                ss.cal_ym = (y - 1, 12) if m == 1 else (y, m - 1)
                st.rerun(scope=scope)
        sel_in_month = sum(1 for d in ss.sel_days if (d.year, d.month) == (y, m))
        n2.markdown(f"<p class='cal-title'>{y}. {m:02d}</p>"
                    f"<p class='cal-sub'>이 달 {sel_in_month}일 선택</p>", unsafe_allow_html=True)
        with n3:
            if st.button("›", key="calnav_next"):
                ss.cal_ym = (y + 1, 1) if m == 12 else (y, m + 1)
                st.rerun(scope=scope)
        for col, wd in zip(st.columns(7), ["일", "월", "화", "수", "목", "금", "토"]):
            c = "#FF6B6B" if wd == "일" else "#4DABF7" if wd == "토" else "inherit"
            col.markdown(f"<div class='wk' style='color:{c}'>{wd}</div>", unsafe_allow_html=True)
        for week in calendar.Calendar(firstweekday=6).monthdatescalendar(y, m):
            for col, d in zip(st.columns(7), week):
                if d.month != m:
                    col.markdown("<div style='min-height:2.75rem'></div>", unsafe_allow_html=True)
                    continue
                if col.button(str(d.day), key=f"d{d.isoformat()}", disabled=d < today, width="stretch",
                              help=f"{d.month}월 {d.day}일 ({WEEK[d.weekday()]})"):
                    ss.sel_days.symmetric_difference_update({d})
                    st.rerun(scope=scope)
    with st.container(key="quick"):
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("이번 주말", width="stretch"):
            sat = today + timedelta(days=(5 - today.weekday()) % 7)
            ss.sel_days = {d for d in (sat - timedelta(days=1) if today.weekday() == 6 else sat,
                                       sat + timedelta(days=1)) if d >= today}
            st.rerun(scope=scope)
        if b2.button("앞으로 7일", width="stretch"):
            ss.sel_days = {today + timedelta(days=i) for i in range(7)}
            st.rerun(scope=scope)
        if b3.button("이 달 주말", width="stretch"):
            ss.sel_days = {d for d in month_days if d >= today and d.weekday() >= 5}
            st.rerun(scope=scope)
        if b4.button("선택 해제", width="stretch"):
            ss.sel_days = set()
            st.rerun(scope=scope)


def day_chips():
    ds = sorted(ss.sel_days)
    if ds:
        chips = "".join(f"<span class='chip{' we' if d.weekday() >= 5 else ''}'>"
                        f"{d.month}/{d.day} {WEEK[d.weekday()]}</span>" for d in ds)
        st.markdown(f"<div class='chips'>{chips}</div>", unsafe_allow_html=True)
    else:
        st.caption("선택한 날짜가 없습니다 — 달력에서 날짜를 눌러주세요.")


def _pick(label, options, cur, key):
    v = st.pills(label, options, default=cur if cur in options else "전체", key=key)
    return v or "전체"


@st.dialog("지역 선택")
def dlg_region():
    t = ss.region
    sea = _pick("바다", ["전체"] + list(SEAS.values()), t["sea"], "pk_sea")
    _, rg1, (sidos, _, _) = region_pool({"sea": sea})
    sido_ = _pick("시·도", sidos, t["sido"] if sea == t["sea"] else "전체", f"pk_sido_{sea}")
    _, rg2, (_, sggs, _) = region_pool({"sea": sea, "sido": sido_})
    sgg_ = _pick("시·군", sggs, t["sgg"] if (sea, sido_) == (t["sea"], t["sido"]) else "전체", f"pk_sgg_{sea}_{sido_}")
    pool_, rg3, (_, _, ports_) = region_pool({"sea": sea, "sido": sido_, "sgg": sgg_})
    port_ = "전체"
    if len(ports_) > 1:
        port_ = _pick("항구", ports_, t["port"] if (sea, sido_, sgg_) == (t["sea"], t["sido"], t["sgg"]) else "전체",
                      f"pk_port_{sea}_{sido_}_{sgg_}")
    pool_, rg, _ = region_pool({"sea": sea, "sido": sido_, "sgg": sgg_, "port": port_})
    st.caption(f"선택: {region_text(rg)} · 배 {len(pool_)}척")
    if st.button(f"이 지역으로 선택 (배 {len(pool_)}척)", type="primary", width="stretch", key="pk_ok"):
        ss.region = rg
        st.rerun()


@st.dialog("어종 선택")
def dlg_fish():
    cur = ss.get("pk_fish", ss.fish_v) or []
    with st.container(key="pk_fish_bar"):                 # 목록이 길어서 완료 버튼을 위에 둠
        a1, a2 = st.columns(2)
        if a1.button("전체 어종", width="stretch", key="pk_fish_all"):
            ss.fish_v = []
            st.rerun()
        if a2.button(f"선택 완료 ({len(cur)}종)" if cur else "선택 완료", type="primary", width="stretch",
                     key="pk_fish_ok"):
            ss.fish_v = list(cur)
            st.rerun()
    st.pills("여러 개 고를 수 있고, 비워 두면 전체 어종입니다", fish_list, selection_mode="multi",
             default=ss.fish_v, key="pk_fish")


@st.dialog("날짜 선택")
def dlg_days():
    render_calendar("fragment")
    day_chips()
    if st.button(f"선택 완료 ({len(ss.sel_days)}일)", type="primary", width="stretch", key="pk_days_ok"):
        st.rerun()


if PHONE:
    pool, ss.region, _ = region_pool(ss.region)
    step_head(1, "지역")
    if st.button(f"📍 {region_text(ss.region)}  ·  배 {len(pool)}척", key="m_region", width="stretch"):
        dlg_region()
    step_head(2, "어종")
    if st.button("🐟 " + (", ".join(ss.fish_v) if ss.fish_v else "전체 어종"), key="m_fish", width="stretch"):
        dlg_fish()
    step_head(3, "날짜")
    ds_ = sorted(ss.sel_days)
    lab = ", ".join(f"{d.month}/{d.day}({WEEK[d.weekday()]})" for d in ds_[:6]) + (f" 외 {len(ds_) - 6}일" if len(ds_) > 6 else "")
    if st.button("📅 " + (lab or "날짜를 고르세요"), key="m_days", width="stretch"):
        dlg_days()
    with st.expander(f"선택 지역의 배 {len(pool)}척 보기 · 직접 추가"):
        if pool:
            st.dataframe(pd.DataFrame([{"사이트": SITES[s["site"]], "배": s["name"], "항구": s["port"] or s["sigungu"]}
                                       for s in pool]), hide_index=True, width="stretch", height=220)
        manual_text = st.text_input("목록에 없는 배 추가 (쉼표로 여러 개)",
                                    placeholder="선상24: 2174 또는 gamsung / 더피싱: tf:6198")
    fish_sel = list(ss.fish_v)
else:
    left_col, right_col = st.columns([1.05, 1], gap="large")
    with left_col:
        # ----- ① 지역
        step_head(1, "지역", "바다 → 시·도 → 시·군 → 항구 순서로 좁혀 보세요")
        c1, c2 = st.columns(2)
        c3, c4 = st.columns(2)
        _, rg0, (sidos, sggs, ports_) = region_pool(ss.region)
        seas_ = ["전체"] + list(SEAS.values())
        sea_name = c1.selectbox("바다", seas_, index=seas_.index(rg0["sea"]))
        _, rg0, (sidos, _, _) = region_pool({**rg0, "sea": sea_name})
        sido = c2.selectbox("시·도", sidos, index=sidos.index(rg0["sido"]))
        _, rg0, (_, sggs, _) = region_pool({**rg0, "sido": sido})
        sigungu = c3.selectbox("시·군", sggs, index=sggs.index(rg0["sgg"]))
        _, rg0, (_, _, ports_) = region_pool({**rg0, "sgg": sigungu})
        port = c4.selectbox("항구", ports_, index=ports_.index(rg0["port"]), disabled=len(ports_) < 2)
        pool, ss.region, _ = region_pool({**rg0, "port": port})

        with st.expander(f"선택 지역의 배 {len(pool)}척 보기 · 직접 추가"):
            if pool:
                st.dataframe(pd.DataFrame([{"사이트": SITES[s["site"]], "배": s["name"], "시·도": s["sido"],
                                            "시·군": s["sigungu"], "항구": s["port"], "번호": s["id"]} for s in pool]),
                             hide_index=True, width="stretch", height=220)
            manual_text = st.text_input("목록에 없는 배 추가 (쉼표로 여러 개)",
                                        placeholder="선상24: 2174 또는 gamsung / 더피싱: tf:6198")

        # ----- ② 어종
        step_head(2, "어종", "비워 두면 모든 어종을 조회합니다")
        fish_sel = st.multiselect("어종", fish_list, default=ss.fish_v, placeholder="전체 어종",
                                  label_visibility="collapsed")
        ss.fish_v = list(fish_sel)

    with right_col:
        # ----- ③ 날짜 (달력)
        step_head(3, "날짜", "여러 날을 함께 고를 수 있습니다")
        render_calendar("app")
        day_chips()
manual = [r for r in (resolve_manual(t) for t in manual_text.split(",") if t.strip()) if r]
days = sorted(ss.sel_days)
month_days = [d for wk in calendar.Calendar(6).monthdatescalendar(*ss.cal_ym) for d in wk if d.month == ss.cal_ym[1]]

# ----- 조회
targets = {(s["site"], s["id"]): s for s in pool + manual}
go = st.button(f"조회 (배 {len(targets)}척)", type="primary", width="stretch",
               disabled=not (days and targets))
if go:
    ss_month.clear()                                     # 조회할 때마다 저장된 결과를 버리고 지금 시각 기준으로 새로 가져옴
    tf_ship.clear()
    cs_page.clear()
    lm_month.clear()
    ships = list(targets.values())
    if fish_sel:   # 선상24만 목록상 정보로 1차 압축 (더피싱 목록은 '외 N종'으로 잘려 있어 제외하면 안 됨)
        ships = [s for s in ships if s["site"] != "ss" or not s["hint"] or fish_match(s["hint"], fish_sel)]
    overflow = []
    if len(ships) > MAX_SHIPS:
        # 사이트별로 번갈아 담아 한쪽 사이트만 잘리지 않게
        by = {k: [s for s in ships if s["site"] == k] for k in SITES}
        mixed = []
        while len(mixed) < MAX_SHIPS and any(by.values()):
            for k in SITES:
                if by[k] and len(mixed) < MAX_SHIPS:
                    mixed.append(by[k].pop(0))
        overflow = [s for s in ships if s not in mixed]
        n_snap = sum(1 for s in overflow if s["site"] == "ss" and SNAP and str(s["id"]) in SNAP["sched"])
        st.warning(f"배가 {len(ships)}척이라 {MAX_SHIPS}척은 실시간으로 조회하고"
                   + (f", 나머지 중 선상24 {n_snap}척은 사전조회 결과({SNAP['generated']} 기준)로 보여줍니다."
                      if n_snap else " 나머지는 생략합니다.")
                   + " 시·도나 시·군을 좁히면 전부 실시간으로 조회됩니다.")
        ships = mixed
    ss.queried = {k: sum(1 for s in ships if s["site"] == k) for k in SITES}
    months = tuple(sorted({f"{d.year}{d.month:02d}" for d in days}))
    jobs = [("ss", s, ym) for s in ships if s["site"] == "ss" for ym in months] + \
           [("tf", s, months) for s in ships if s["site"] == "tf"] + \
           [("cs", s, tuple(days)) for s in ships if s["site"] == "cs"] + \
           [("lm", s, tuple(days)) for s in ships if s["site"] == "lm"]
    rows, errors, probes = [], [], []
    bar = st.progress(0.0, text="예약현황을 가져오는 중...")

    def work(job):
        kind, s, arg = job
        try:
            if kind == "ss":
                res = ss_month(freeze(s), arg)
                if not res["rows"] and res["probe"]:
                    fb = snapshot_rows(SNAP, s, arg)       # 실시간으로 못 읽으면 사전조회 결과로 대신
                    if fb:
                        return fb, None
                    probes.append((s["name"], res["probe"]))
                return res["rows"], None
            if kind == "cs":
                return cs_ship(freeze(s), arg), None
            if kind == "lm":
                return lm_ship(freeze(s), arg), None
            return tf_ship(freeze(s), arg), None
        except Exception as ex:
            if kind == "ss":
                fb = snapshot_rows(SNAP, s, arg)
                if fb:
                    return fb, None
            return [], f"[{SITES[kind]}] {s['name']}: {ex}"

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, (items, err) in enumerate(ex.map(work, jobs), 1):
            rows.extend(items)
            if err:
                errors.append(err)
            bar.progress(i / max(1, len(jobs)), text=f"예약현황 가져오는 중... {i}/{len(jobs)}")
    bar.empty()
    for s in overflow:                                    # 실시간 조회 한도를 넘은 선상24 배 → 사전조회 결과
        if s["site"] == "ss":
            for ym in months:
                rows.extend(snapshot_rows(SNAP, s, ym))
    ss.queried["ss"] = ss.queried.get("ss", 0) + sum(1 for s in overflow if s["site"] == "ss"
                                                     and SNAP and str(s["id"]) in SNAP["sched"])
    tide, need_m = {}, set()
    for ym in months:                                     # 앞뒤 7일 계산을 위해 이웃 달도 함께
        y_, m_ = int(ym[:4]), int(ym[4:])
        for k in (-1, 0, 1):
            yy, mm = y_ + (m_ + k - 1) // 12, (m_ + k - 1) % 12 + 1
            need_m.add(f"{yy}{mm:02d}")
    for ym in sorted(need_m):
        try:
            tide.update(tide_month(ym))
        except Exception as ex:
            if ym in months:
                errors.append(f"[조류세기] {TIDE_PORT_NAME} {ym[4:]}월 물때표: {ex}")
    ss.tide = tide_with_strength(tide)
    openmeteo_fc.clear()                                 # 조회할 때마다 가장 최근 예보로
    openmeteo_waves.clear()
    try:
        ss.temps, ss.winds = openmeteo_fc()
    except Exception as ex:
        ss.temps, ss.winds = {}, {}
        errors.append(f"[기온·바람] {ex}")
    try:
        ss.waves, ss.wave_area = openmeteo_waves()
    except Exception as ex:
        ss.waves, ss.wave_area = {}, ""
        errors.append(f"[파고] {ex}")
    try:
        ss.weather, ss.weather_area = tide_weather()
    except Exception as ex:
        ss.weather, ss.weather_area = {}, "바다날씨"
        errors.append(f"[날씨] {TIDE_PORT_NAME} 바다날씨: {ex}")
    ss.rows, ss.errors = rows, errors
    ss.fetched = kst_now().strftime("%Y-%m-%d %H:%M:%S")
    ss.probes = probes

# ----- 연결 점검
with st.expander("🔧 연결 점검 (조회가 안 될 때 눌러서 화면을 캡처해 보내주세요)"):
    if st.button("점검 실행", key="diag"):
        st.markdown("**[선상24]**")
        try:
            found = _ss_board_page("west", 1)
            st.write(f"① 조황정보 목록(서해 1페이지): 배 {len(found) if found is not None else '실패'}척 인식")
            ss_pool = [s for s in pool if s["site"] == "ss"] or [
                {"site": "ss", "id": 2174, "name": "여수 감성피싱", "sea": "south", "sido": "전남",
                 "sigungu": "여수", "port": "", "hint": ""}]
            sh = ss_pool[0]
            ym = f"{today.year}{today.month:02d}"
            h = fetch_html(f"{SS_APP}/ship/schedule_fleet/{sh['id']}/{ym}")
            srows = ss_parse(h, today.year, today.month, sh)
            st.write(f"② {sh['name']}(번호 {sh['id']}) 예약 페이지: 글자 {len(h):,}자, 일정 {len(srows)}건 인식 "
                     f"(남은자리 확인 {sum(1 for r in srows if r['remain'] is not None)}건)")
            if not srows:
                lines = clean_lines(h)
                st.code("\n".join(lines[:40]) or "(본문 없음)")
        except Exception as ex:
            st.write(f"선상24 점검 실패: {ex}")
        st.markdown("**[더피싱]**")
        try:
            h = fetch_html(f"{TF}/reservation/list.php?page=1")
            items, last = _tf_list_page(1)
            st.write(f"① 목록 페이지: 글자 {len(h):,}자, 배 {len(items or {})}척 인식, 마지막 페이지 {last}")
            st.write("예시:", list((items or {}).items())[:3])
        except Exception as ex:
            st.write(f"① 목록 페이지 실패: {ex}")
        tf_pool = [s for s in pool if s["site"] == "tf"] or [
            {"site": "tf", "id": 6198, "name": "골드스타1호", "sea": "west", "sido": "충남",
             "sigungu": "서천", "port": "홍원항", "hint": ""}]
        sh = tf_pool[0]
        try:
            h = fetch_html(f"{TF}/reservation/list.php?uid={sh['id']}")
            prow, home = tf_parse_calendar(h, today.year, today.month, sh)
            known = [r for r in prow if r["status"] != "확인필요"]
            st.write(f"② {sh['name']}(uid {sh['id']}) 예약 페이지: 글자 {len(h):,}자, 날짜 {len(prow)}개 인식 "
                     f"(상태 확인 {len(known)}개), 홈페이지: {home}")
            lines = clean_lines(h)
            idx = next((i for i, l in enumerate(lines) if re.fullmatch(r"\d{1,2}", l)), 0)
            st.code("\n".join(lines[idx: idx + 40]) or "(본문 없음)")
            if home:
                hh = fetch_html(f"{home}/index.php?mid=bk")
                hrows = tf_parse_home(hh, sh)
                st.write(f"③ 홈페이지 예약현황: 글자 {len(hh):,}자, 날짜 {len(hrows)}개 인식")
                st.write([(str(r["date"]), r["status"], r["remain"]) for r in hrows[:8]])
        except Exception as ex:
            st.write(f"② 예약 페이지 실패: {ex}")

rows = ss.get("rows")
if rows is None:
    st.info("사이트·지역·날짜·어종을 고르고 [조회]를 누르세요.")
    st.stop()

st.markdown("<div class='res-head'>조회 결과</div>", unsafe_allow_html=True)
q0 = ss.get("queried", {})
if "ss" in site_codes and q0 and not q0.get("ss"):
    st.error("선상24 배를 한 척도 조회하지 못했습니다 — 선상24 배 목록을 불러오지 못했거나 선택한 지역에 선상24 배가 없습니다. "
             "화면 위쪽 '배 목록' 줄의 선상24 척수를 확인하고, 0척이면 [🔄 배 목록 다시 불러오기]를 눌러주세요.")
if q0.get("ss") and not any(r["site"] == "ss" for r in rows):
    pr = ss.get("probes", [])
    msg = [f"**선상24 배 {q0['ss']}척을 조회했지만 일정을 하나도 읽지 못했습니다.** "
           f"아래는 서버가 선상24에서 실제로 받은 화면입니다. 이 상자를 캡처해서 보내주시면 바로 고칠 수 있습니다."]
    for name, plist in pr[:2]:
        msg.append(f"\n**{name}**")
        for p_ in plist:
            msg.append(f"- `{p_['url']}` → {p_['result']}" + (f"  \n  앞부분: {p_['head']}" if p_.get("head") else ""))
    if not pr:
        msg.append("\n(각 배의 해당 월에 출조 일정이 등록되어 있지 않은 것으로 읽혔습니다.)")
    st.error("\n".join(msg))
if ss.errors:
    with st.expander(f"⚠️ {len(ss.errors)}건은 불러오지 못했습니다"):
        st.write("\n".join(f"- {e}" for e in ss.errors[:30]))

with st.container(key="filters"):
    f1, f2, f3, f4 = st.columns([1, 1, 1.3, 1.7], vertical_alignment="bottom")
    only_open = f1.checkbox("예약 가능한 것만", value=True)
    need = f2.number_input("최소 남은자리", min_value=1, max_value=30, value=1)
    sort_by = f3.radio("정렬", ["날짜순", "남은자리 많은순"], horizontal=True)
    name_q = f4.text_input("🔍 배 이름으로 검색", placeholder="예: 동백호, 골드스타")

day_set = set(days)


def row_fish_ok(r):
    if r["site"] == "cs":                                # 클럽씨피싱은 어종과 상관없이 예약마감 외 모든 배 표시
        return True
    if fish_match(f"{r['species']} {r['notice']} {r['boat']}", fish_sel):
        return True
    # 더피싱 목록의 어종이 '…외 N종'으로 잘려 있으면 확인 불가 → 보여주고 표시
    return r["site"] == "tf" and bool(re.search(r"외\s*\d+\s*종", r["species"]))


def name_ok(r):
    if not name_q.strip():
        return True
    hay = re.sub(r"\s+", "", f"{r['ship']} {r['boat']}").lower()
    return all(t in hay for t in re.sub(r"\s+", " ", name_q.strip().lower()).split(" "))


in_scope = [r for r in rows if r["date"] in day_set and r["site"] in site_codes and row_fish_ok(r) and name_ok(r)]
view = [r for r in in_scope if not only_open or r["site"] == "cs"          # 클럽씨피싱은 예약마감 외 전부 표시
        or (r["remain"] is not None and r["remain"] >= need)]
view.sort(key=(lambda r: (r["date"], r["sido"], r["sigungu"], r["ship"])) if sort_by == "날짜순"
          else (lambda r: (-(r["remain"] or 0), r["date"])))
q = ss.get("queried", {})
st.caption(f"🕒 {ss.fetched} (한국시간) 실시간 조회 결과 — 다시 조회하면 그 시각의 최신 현황으로 바뀝니다"
           + (f" · 배 이름 '{name_q.strip()}' 검색 중" if name_q.strip() else ""))

need_home = list({r["ship_id"] for r in view if r["site"] == "ss" and (r["remain"] or 0) > 0})[:80]
if need_home:
    with ThreadPoolExecutor(max_workers=4) as ex:
        homes = dict(zip(need_home, ex.map(ss_home, need_home)))
    for r in view:
        if r["site"] == "ss":
            r["home"] = homes.get(r["ship_id"]) or r["url"]

st.markdown(f"""
<style>
.rtbl-wrap {{max-height: 640px; overflow: auto; border: 1px solid rgba(128,128,128,.32); border-radius: 12px;}}
.rtbl {{width: 100%; border-collapse: collapse; font-size: .92rem;}}
.rtbl th {{position: sticky; top: 0; z-index: 2; background: {INK}; color: #fff; text-align: left;
  padding: 10px 12px; font-weight: 700; font-size: .82rem; white-space: nowrap;}}
.rtbl td {{padding: 9px 12px; border-top: 1px solid rgba(128,128,128,.2); vertical-align: middle;}}
.rtbl th.c-남은자리, .rtbl td.c-남은자리 {{text-align: right;}}
.rtbl td.c-남은자리 {{font-size: 1.08rem; font-weight: 800; font-variant-numeric: tabular-nums; white-space: nowrap;}}
.rtbl td.c-배 {{min-width: 190px;}}
.rtbl td.c-지역, .rtbl td.c-출항, .rtbl td.c-상태, .rtbl td.c-가격 {{white-space: nowrap;}}
.rtbl td.c-어종 {{min-width: 110px; max-width: 220px;}}
.rtbl td.c-공지 {{font-weight: 500 !important;}}
.rtbl td.c-공지 .nt {{max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}}
.rtbl a.bn {{color: inherit !important; text-decoration: none; font-weight: 700;}}
.rtbl a.bn:hover {{text-decoration: underline;}}
.rtbl tr.ok {{background: {ACCENT};}}
.rtbl tr.ok td {{background: {ACCENT} !important; color: #111 !important; font-weight: 700;}}
.rtbl tr.ok td.c-남은자리 {{color: {INK} !important;}}
.rtbl tr.ok td a.hp {{color: #111 !important; background: rgba(255,255,255,.55); padding: 3px 10px; border-radius: 999px;
  border: 1.5px solid #111; text-decoration: none; white-space: nowrap;}}
.rtbl tr.ok td a.hp:hover {{background: #fff;}}
.rtbl tr.no td {{opacity: .62;}}
.rtbl tr.grp td {{background: rgba(110,140,170,.16); padding: 9px 12px; border-top: 2px solid rgba(110,140,170,.45);
  position: sticky; top: 37px; z-index: 1; backdrop-filter: blur(6px);}}
.rtbl .g {{display: flex; align-items: center; flex-wrap: wrap; gap: 6px 16px;}}
.rtbl .gd {{font-size: 1.12rem; font-weight: 800; letter-spacing: -.01em; min-width: 76px;}}
.rtbl .gd small {{font-size: .82rem; margin-left: 2px; font-weight: 700;}}
.rtbl .gd.sun {{color: #E8484C;}}
.rtbl .gd.sat {{color: #3B8FE8;}}
.rtbl .gf {{font-size: .88rem; white-space: nowrap;}}
.rtbl .gk {{font-size: .74rem; opacity: .6; margin-right: 5px;}}
.rtbl .gc {{margin-left: auto; font-size: .82rem; font-weight: 700; opacity: .8; white-space: nowrap;}}
.rtbl .wxi {{display:inline-block; background:#fff; color:#111; border:1px solid rgba(0,0,0,.12); border-radius:7px;
  padding:0 4px; margin-right:4px; line-height:1.4;}}
.rtbl .wxa {{opacity:.55; margin:0 3px;}}
.rtbl .seaw {{overflow-x: auto; margin-top: 6px;}}
.rtbl table.sea {{border-collapse: collapse; font-size: .8rem; font-variant-numeric: tabular-nums;}}
.rtbl table.sea th, .rtbl table.sea td {{position: static; background: transparent; color: inherit; padding: 2px 8px;
  border: 0; text-align: center; font-weight: 600; white-space: nowrap;}}
.rtbl table.sea th {{opacity: .6; font-size: .72rem; font-weight: 700;}}
.rtbl table.sea th.rk {{text-align: left; padding-left: 0; opacity: .85; font-size: .78rem;}}
.rtbl table.sea th.rk small {{margin-left: 4px; font-size: .68rem; opacity: .7; font-weight: 600;}}
.rtbl table.sea th.loc {{opacity: 1; font-weight: 800;}}
.rtbl table.sea th.loc small {{display: block; margin-left: 0;}}
.rtbl table.sea td.hi {{color: #E8484C; font-weight: 800;}}
.site-head {{display:flex; align-items:center; flex-wrap:wrap; gap:10px; margin:1.5rem 0 .55rem;
  padding-left:12px; border-left:5px solid {ACCENT};}}
.site-head .nm {{font-size:1.3rem; font-weight:800; letter-spacing:-.01em;}}
.site-head .badge {{background:{ACCENT}; color:#111; font-weight:800; border-radius:999px; padding:3px 12px; font-size:.86rem;}}
.site-head .badge.zero {{background:rgba(128,128,128,.22); color:inherit;}}
.site-head .sub {{opacity:.65; font-size:.85rem;}}
@media (max-width: 640px) {{
  .hero {{padding:16px 16px 14px;}} .hero-t {{font-size:1.45rem;}}
  /* 휴대폰: 표 대신 카드처럼 한 배씩 — 배 이름과 남은자리가 첫 줄 */
  .rtbl-wrap {{max-height:none; overflow:visible; border:0;}}
  .rtbl, .rtbl tbody {{display:block; width:100%;}}
  .rtbl thead {{display:none;}}
  .rtbl tr.grp {{display:block; margin-top:10px;}}
  .rtbl tr.grp td {{display:block; position:static; border-radius:10px 10px 0 0; border-top:0;}}
  .rtbl .gc {{margin-left:0;}}
  .rtbl tr.ok, .rtbl tr.no {{display:grid; grid-template-columns:1fr auto; column-gap:8px;
    border-top:1px solid rgba(128,128,128,.25); padding:8px 0 10px;}}
  .rtbl tr.no {{background:rgba(128,128,128,.06);}}
  .rtbl tr td {{border:0 !important; padding:2px 12px; background:transparent !important; white-space:normal !important;
    max-width:none !important; min-width:0 !important;}}
  .rtbl td.c-배 {{grid-column:1; grid-row:1; font-size:1rem; padding-top:4px;}}
  .rtbl td.c-남은자리 {{grid-column:2; grid-row:1; font-size:1.25rem; padding-top:2px;}}
  .rtbl td.c-지역, .rtbl td.c-어종, .rtbl td.c-출항, .rtbl td.c-가격, .rtbl td.c-공지 {{grid-column:1 / -1; font-size:.86rem;
    font-weight:600 !important;}}
  .rtbl td.c-공지 {{opacity:.8;}}
  .rtbl td.c-공지 .nt {{max-width:none; white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;}}
  .rtbl td.c-상태 {{grid-column:1 / -1; padding-top:6px;}}
  .rtbl td:empty {{display:none;}}
  .rtbl table.sea td, .rtbl table.sea th {{display: table-cell !important; padding: 2px 5px !important;}}
}}
</style>""", unsafe_allow_html=True)


def boat_label(r):
    b, sh = (r.get("boat") or "").strip(), r["ship"]
    if r["site"] == "cs" and b:                          # 클럽씨피싱은 선사 이름이 사이트 이름과 같아 생략
        return b
    if not b or b in sh:
        return sh
    return f"{b} ({sh})"


def dedupe(rs):
    """같은 날짜·같은 지역·같은 배는 한 줄만 — 남은자리가 가장 많은 일정을 대표로, 나머지 회차 수는 표시"""
    groups, order = {}, []
    for r in rs:
        key = (r["date"], r["sigungu"], re.sub(r"\s+", "", (r.get("boat") or r["ship"])).lower())
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    out = []
    for key in order:
        g = groups[key]
        best = dict(max(g, key=lambda r: (r["remain"] if r["remain"] is not None else -1)))
        times = sorted({r["time"] for r in g if r["time"]})
        if len(times) > 1:
            best["time"] = f"{best['time'] or times[0]} 외 {len(times) - 1}회"
        out.append(best)
    return out


def render_site(code):
    srows = dedupe([r for r in view if r["site"] == code])
    sscope = dedupe([r for r in in_scope if r["site"] == code])
    n_ok = sum(1 for r in srows if (r["remain"] or 0) > 0)
    n_q = len({r['boat'] for r in sscope}) if code == 'cs' else q.get(code, 0)
    st.markdown(f"<div class='site-head s-{code}'><span class='nm'>{SITES[code]}</span>"
                f"<span class='badge{' zero' if not n_ok else ''}'>예약가능 {n_ok}건</span>"
                f"<span class='sub'>배 {n_q}척 조회, 표시 {len(srows)}건 / 해당 일정 {len(sscope)}건</span></div>",
                unsafe_allow_html=True)
    site_errs = [e for e in ss.get("errors", []) if e.startswith(f"[{SITES[code]}]")]
    if site_errs and not sscope:
        st.error(f"{SITES[code]} 조회 실패 — 서버가 받은 내용: " + site_errs[0][len(SITES[code]) + 2:][:400]
                 + "  \n이 상자를 캡처해서 보내주세요.")
    if code == "cs" and q.get("cs"):
        pages = CS_CLOSED_COUNT.get("_pages", {})
        diag = []
        for d in sorted(day_set):
            n_open = max((p_["open"].get(d, 0) for p_ in pages.values()), default=0)
            diag.append(f"{d.month}/{d.day}({WEEK[d.weekday()]}) 예약가능·기타 {n_open}척 / 예약마감 {CS_CLOSED_COUNT.get(d, 0)}척")
        raw_n = sum(1 for r in (rows or []) if r["site"] == "cs" and r["date"] in day_set)
        st.caption("클럽씨피싱 사이트에서 읽은 내용 — " + " · ".join(diag)
                   + (f" · 받은 페이지 {len(pages)}개" if pages else ""))
        if raw_n and not sscope:
            st.warning(f"클럽씨피싱 배 {raw_n}건을 읽었지만 [배 이름 검색] 조건 때문에 모두 빠졌습니다.")
    if code == "cs" and not sscope and not site_errs and q.get("cs") and not any(
            r["site"] == "cs" and r["date"] in day_set for r in (rows or [])):
        shut = [f"{d.month}/{d.day}({WEEK[d.weekday()]}) {CS_CLOSED_COUNT[d]}척"
                for d in sorted(day_set) if CS_CLOSED_COUNT.get(d)]
        st.info("클럽씨피싱 예약 페이지를 정상으로 읽었습니다. 선택한 날짜는 모든 배가 예약마감입니다."
                + (f" (예약마감: {', '.join(shut)})" if shut else ""))
    if not srows:
        if sscope:
            st.caption("남은자리가 있는 일정이 없습니다. [예약 가능한 것만]을 끄면 마감된 일정도 볼 수 있습니다.")
        else:
            st.caption("선택한 조건에 해당하는 일정이 없습니다.")
        return
    # 물때표에 없는 날은 같은 날 다른 사이트(선상24 등) 일정에 적힌 물때를 씀
    mul_any = {}
    for r_ in (rows or []):
        if r_.get("tide") and re.fullmatch(r"\d{1,2}물|조금|무시|한객기|한조금", r_["tide"]):
            mul_any.setdefault(r_["date"], r_["tide"])
    df = pd.DataFrame([{
        "날짜": f"{r['date']:%m.%d}({WEEK[r['date'].weekday()]})",
        "지역": " ".join(x for x in (r["sido"], r["sigungu"], r["port"]) if x),
        "물때": r["tide"] or (ss.get("tide", {}).get(r["date"], {}) or {}).get("mul", "") or mul_any.get(r["date"], ""),
        f"조류세기({TIDE_PORT_NAME})": tide_label(r["date"]),
        "날씨": ss.get("weather", {}).get(r["date"], "예보 전" if r["date"] > kst_today() + timedelta(days=6) else ""),
        "기온": temp_label(r["date"]), "바람": wind_label(r["date"]), "파고": wave_label(r["date"]),
        "배": boat_label(r),
        "어종": r["species"], "출항": r["time"], "가격": r["price"],
        "남은자리": "" if r["remain"] is None else f"{r['remain']}명",
        "상태": r["status"] + (f" ({r['snap']} 기준)" if r.get("snap") else ""), "공지": r["notice"], "예약": r["url"],
        "홈페이지": r.get("home") or "", "_ok": (r["remain"] or 0) > 0,
    } for r in srows])
    # 날짜별로 묶어서 그림: 날짜 줄에 물때·조류·날씨·기온을 한 번만, 그 아래에 배 목록
    # (예약가능 = 노란 바탕 + 검은 굵은 글씨, 다크/라이트 모드 동일)
    cols = ["배", "지역", "어종", "출항", "가격", "남은자리", "상태", "공지"]
    if code in ("ss", "cs", "lm") and not any(r["price"] for r in srows):
        cols.remove("가격")                               # 선상24·클럽씨피싱은 가격 칸이 없음
    head = "".join(f"<th class='c-{c}'>{c}</th>" for c in cols)
    esc = lambda v: htmlmod.escape(str(v))
    body, by_date = [], {}
    for r, (_, dr) in zip(srows, df.iterrows()):
        by_date.setdefault(r["date"], []).append(dr)
    for d in sorted(by_date):
        g = by_date[d]
        dr0 = dict(g[0])
        for k_ in ("물때", f"조류세기({TIDE_PORT_NAME})", "기온", "날씨"):   # 첫 배에 없으면 같은 날 다른 배 값으로
            dr0[k_] = next((x[k_] for x in g if x[k_]), "")
        n_ok_d = sum(1 for x in g if x["_ok"])
        wx = ""
        if dr0["날씨"]:
            parts = []
            for seg in str(dr0["날씨"]).split(" → "):
                ic, _, txt = seg.partition(" ")
                if txt and not re.search(r"[가-힣A-Za-z0-9]", ic):     # 앞 글자가 날씨 아이콘일 때만 상자에 넣음
                    parts.append(f"<span class='wxi'>{esc(ic)}</span>{esc(txt)}")
                else:                                                # '예보 전' 같은 글자는 그대로
                    parts.append(esc(seg))
            wx = " <span class='wxa'>→</span> ".join(parts)
        we = " sun" if d.weekday() == 6 else " sat" if d.weekday() == 5 else ""
        facts = [("물때", dr0["물때"]), ("조류", dr0[f"조류세기({TIDE_PORT_NAME})"]), ("기온", dr0["기온"])]
        facts_html = "".join(f"<span class='gf'><span class='gk'>{k}</span>{esc(v)}</span>" for k, v in facts if v)
        body.append(
            f"<tr class='grp'><td colspan='{len(cols)}'><div class='g'>"
            f"<span class='gd{we}'>{d.month}.{d.day}<small>({WEEK[d.weekday()]})</small></span>"
            f"{facts_html}" + (f"<span class='gf gw'>{wx}</span>" if wx else "") +
            f"<span class='gc'>예약가능 {n_ok_d}척 / {len(g)}척</span></div>"
            f"<div class='seaw'>{sea_grid_html(d)}</div></td></tr>")
        for r in g:
            cells = []
            for c in cols:
                v = r[c]
                if c == "배":
                    cells.append(f"<td class='c-배'><a class='bn' href='{esc(r['예약'])}' target='_blank' "
                                 f"title='예약 페이지 열기'>{esc(v)}</a></td>")
                elif c == "남은자리":
                    cells.append(f"<td class='c-남은자리'>{esc(v) if v else '–'}</td>")
                elif c == "상태" and r["_ok"] and r["홈페이지"]:
                    cells.append(f"<td class='c-상태'><a class='hp' href='{esc(r['홈페이지'])}' target='_blank' "
                                 f"title='선사 홈페이지 열기'>{esc(v)} ↗</a></td>")
                elif c == "공지":
                    cells.append(f"<td class='c-공지' title='{esc(v)}'><div class='nt'>{esc(v)}</div></td>")
                else:
                    cells.append(f"<td class='c-{c}'>{esc(v)}</td>")
            body.append(f"<tr class='{'ok' if r['_ok'] else 'no'}'>{''.join(cells)}</tr>")
    st.markdown(f"<div class='rtbl-wrap'><table class='rtbl'><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table></div>", unsafe_allow_html=True)
    st.download_button(f"{SITES[code]} 결과 CSV 다운로드",
                       df.drop(columns=["_ok"]).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{SITES[code]}_예약_{today:%Y%m%d}.csv", mime="text/csv", key=f"dl_res_{code}")


for code in site_codes:
    render_site(code)

st.caption("물때·조류세기·날씨: 바다타임 남당항 · 기온·바람: Open-Meteo 최신 예보(남당항 위치) · 파고: Open-Meteo 해양 예보"
           + (f"({ss.get('wave_area')})" if ss.get("wave_area") else "")
           + " · 조회할 때마다 새로 받음 · 바람 16Kts 이상, 파고 1.5m 이상은 빨간 글씨")

with st.expander(f"🌊 조류세기 계산 근거 ({TIDE_PORT_NAME}, 바다타임 물때표)"):
    td = ss.get("tide", {})
    if not td:
        st.caption("물때표를 불러오지 못했습니다.")
    else:
        show = sorted({d + timedelta(days=k) for d in days for k in range(-7, 8)} & set(td))
        st.caption("조류세기 = 바다타임 '물흐름'과 같은 눈금. 하루 ▲/▼ 높이 변화 평균이 201cm면 0%(최소), 732cm면 100%.")
        st.dataframe(pd.DataFrame([{
            "날짜": f"{d:%m.%d}({WEEK[d.weekday()]})" + (" ◀" if d in day_set else ""), "물때": td[d]["mul"],
            "만조·간조 높이(cm)": ", ".join(str(h) for h in td[d].get("heights", [])),
            "물흐름 지표(▲▼ 평균 cm)": td[d].get("flow"), "조류세기": tide_label(d),
        } for d in show]), hide_index=True, width="stretch")
