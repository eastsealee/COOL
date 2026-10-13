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
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
SS_APP = "https://app.sunsang24.com"
TF = "https://thefishing.kr"
SEAS = {"west": "서해", "east": "동해", "south": "남해", "jeju": "제주"}
SITES = {"ss": "선상24", "tf": "더피싱"}
SS_BOARD_MAX_PAGES = 12
TF_LIST_MAX_PAGES = 40
MAX_SHIPS = 150
WORKERS = 8
WEEK = "월화수목금토일"

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
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


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


def fish_match(text, selected):
    if not selected:
        return True
    return any(alias in text for f in selected for alias in FISH_ALIAS.get(f, [f]))


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
    r"|(기상\s*악화|출조\s*취소|배\s*정비일?|정비일|예약을?\s*받지\s*않|휴\s*무|휴\s*항|출조\s*없음)")
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
            "예약받지않": "예약중단"}.get(word, word)
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
            stm = STATUS_RE.search(block, tm.end() if tm else lab.end(), nxt)
            remain, status = status_of(stm)
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
                        "url": f"{SS_APP}/ship/schedule_fleet/{ship['id']}/{yr}{mo:02d}"})
            prev_end = end
    return out


def _ss_board_page(sea, page):
    try:
        html = fetch_html(f"{SS_APP}/ship/board?area={sea}&page={page}")
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
            break
        new = {k: v for k, v in found.items() if k not in ships}
        ships.update(new)
        streak = 0 if new else streak + 1
        if streak >= 2:
            break
        time.sleep(0.3)
    return sea, ships


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def ss_catalog():
    rows, seen = [], set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for sea, ships in ex.map(_ss_crawl_sea, list(SEAS)):
            for sid, name in ships.items():
                if sid in seen:
                    continue
                seen.add(sid)
                sido, sgg, port = ss_locate(name, sea)
                rows.append({"site": "ss", "id": sid, "name": name, "sea": sea, "sido": sido,
                             "sigungu": sgg, "port": port, "hint": ""})
    return rows


@st.cache_data(ttl=180, show_spinner=False)
def ss_month(ship_t, yyyymm):
    ship = dict(ship_t)
    html = fetch_html(f"{SS_APP}/ship/schedule_fleet/{ship['id']}/{yyyymm}")
    return ss_parse(html, int(yyyymm[:4]), int(yyyymm[4:]), ship)


# ---------------------------------------------------------------- 더피싱
TF_PATH_RE = re.compile(r"(서해권|남해권|동해권)((?:\s*>\s*(?:영흥도 진두항|제주 [가-힣]+항|[가-힣·/]+)){1,3})")


def _tf_list_page(page):
    try:
        html = fetch_html(f"{TF}/reservation/list.php?page={page}")
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
def tf_catalog():
    first, last = _tf_list_page(1)
    if first is None:
        return []
    pages = range(2, min(last, TF_LIST_MAX_PAGES) + 1)
    allitems = dict(first)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for items, _ in ex.map(_tf_list_page, pages):
            for uid, v in (items or {}).items():
                allitems.setdefault(uid, v)
    rows = []
    for uid, (name, path, hint) in allitems.items():
        sea, sido, sgg, port = tf_region(path)
        rows.append({"site": "tf", "id": uid, "name": name or f"더피싱 {uid}", "sea": sea, "sido": sido,
                     "sigungu": sgg, "port": port, "hint": hint})
    return rows


def tf_parse_calendar(html, year, month, ship):
    """thefishing.kr/reservation/list.php?uid=… 의 달력(이번 달) → 일정"""
    full = "\n".join(clean_lines(html))
    home = re.search(r"https?://([a-z0-9\-]+)\.thefishing\.kr", html)
    dates = line_start_dates(full, DATE_RE)

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
                   "boat": ship["name"], "species": ship.get("hint", ""),
                   "time": (f"{tm.group(1)}~{tm.group(2)}" if tm and tm.re is TIME_RE else
                            (f"{tm.group(1)} 출항" if tm else "")),
                   "price": pm.group(1) if pm else "", "remain": remain, "status": status,
                   "notice": notice, "url": f"{TF}/reservation/list.php?uid={ship['id']}"}
    return list(days.values()), (home.group(1) if home else None)


def tf_parse_home(html, ship):
    """<선박>.thefishing.kr/index.php?mid=bk… 예약현황 → 이 배의 일정"""
    full = "\n".join(clean_lines(html))
    heads = line_start_dates(full, FULL_DATE_RE)
    out = []
    name = ship["name"]
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
                    "notice": notice, "url": f"{TF}/reservation/list.php?uid={ship['id']}"})
    return out


@st.cache_data(ttl=180, show_spinner=False)
def tf_ship(ship_t, months):
    """더피싱 한 척: 이번 달은 예약 페이지 달력, 나머지 달은 선박 홈페이지 예약현황"""
    ship = dict(ship_t)
    today = date.today()
    html = fetch_html(f"{TF}/reservation/list.php?uid={ship['id']}")
    rows, home = tf_parse_calendar(html, today.year, today.month, ship)
    got = {f"{r['date'].year}{r['date'].month:02d}" for r in rows if r["status"] != "확인필요"}
    for ym in months:
        if ym in got or not home:
            continue
        try:
            h = fetch_html(f"https://{home}.thefishing.kr/index.php?mid=bk&year={ym[:4]}&month={ym[4:]}&day=01")
            rows += [r for r in tf_parse_home(h, ship) if f"{r['date'].year}{r['date'].month:02d}" == ym]
        except Exception:
            pass
    return rows


# ---------------------------------------------------------------- 공통
def ship_cols(ship):
    return {"site": ship["site"], "ship_id": ship["id"], "ship": ship["name"], "sea": ship["sea"],
            "sido": ship["sido"], "sigungu": ship["sigungu"], "port": ship.get("port", "")}


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def fish_options():
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
st.markdown("""
<style>
.st-key-cal [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 4px !important;}
.st-key-cal [data-testid="stColumn"] {min-width: 0 !important; flex: 1 1 0 !important; width: auto !important;}
.st-key-cal button {padding: 0.15rem 0 !important; min-height: 2.3rem; width: 100%;}
.st-key-cal .wk p {text-align: center; font-weight: 600; margin: 0;}
</style>""", unsafe_allow_html=True)
st.title("🎣 선상낚시 통합 예약조회")
st.caption("선상24 · 더피싱 예약현황을 한 번에 조회합니다.")

today = date.today()
ss = st.session_state
ss.setdefault("sel_days", {today + timedelta(days=i) for i in range(7)})
ss.setdefault("cal_ym", (today.year, today.month))

site_sel = st.multiselect("조회할 사이트", list(SITES.values()), default=list(SITES.values()))
site_codes = [k for k, v in SITES.items() if v in site_sel]

catalog, load_err = [], []
with st.spinner("배 목록을 불러오는 중... (처음 한 번만 1~2분 걸립니다)"):
    if "ss" in site_codes:
        part = ss_catalog()
        catalog += part
        if not part:
            load_err.append("선상24")
    if "tf" in site_codes:
        part = tf_catalog()
        catalog += part
        if not part:
            load_err.append("더피싱")
for name in load_err:
    st.error(f"{name} 배 목록을 불러오지 못했습니다. 잠시 후 새로고침 해주세요. "
             f"계속 안 되면 {name}가 이 서버의 접속을 막고 있을 수 있습니다.")
fish_list = fish_options()

# ----- ① 지역
st.subheader("① 지역 선택")
c1, c2, c3, c4 = st.columns(4)
sea_name = c1.selectbox("바다", ["전체"] + list(SEAS.values()))
sea_code = next((k for k, v in SEAS.items() if v == sea_name), "all")
pool = [s for s in catalog if sea_code == "all" or s["sea"] == sea_code]
sido = c2.selectbox("시·도", ["전체"] + sorted({s["sido"] for s in pool}, key=lambda x: (x == "기타", x)))
pool = [s for s in pool if sido == "전체" or s["sido"] == sido]
sigungu = c3.selectbox("시·군", ["전체"] + sorted({s["sigungu"] for s in pool}))
pool = [s for s in pool if sigungu == "전체" or s["sigungu"] == sigungu]
ports = sorted({s["port"] for s in pool if s["port"]})
port = c4.selectbox("항구", ["전체"] + ports, disabled=not ports)
pool = [s for s in pool if port == "전체" or s["port"] == port]

with st.expander(f"선택 지역의 배 {len(pool)}척 보기 · 직접 추가"):
    if pool:
        st.dataframe(pd.DataFrame([{"사이트": SITES[s["site"]], "배": s["name"], "시·도": s["sido"],
                                    "시·군": s["sigungu"], "항구": s["port"], "번호": s["id"]} for s in pool]),
                     hide_index=True, width="stretch", height=220)
    manual_text = st.text_input("목록에 없는 배 추가 (쉼표로 여러 개)",
                                placeholder="선상24: 2174 또는 gamsung / 더피싱: tf:6198")
manual = [r for r in (resolve_manual(t) for t in manual_text.split(",") if t.strip()) if r]

# ----- ② 날짜 (달력)
st.subheader("② 날짜 선택")
y, m = ss.cal_ym
with st.container(key="cal"):
    n1, n2, n3 = st.columns([1, 3, 1])
    if n1.button("◀", key="prev", disabled=(y, m) <= (today.year, today.month)):
        ss.cal_ym = (y - 1, 12) if m == 1 else (y, m - 1)
        st.rerun()
    n2.markdown(f"<p style='text-align:center;font-size:1.15rem;font-weight:700;margin:.4rem 0'>"
                f"{y}년 {m}월</p>", unsafe_allow_html=True)
    if n3.button("▶", key="next"):
        ss.cal_ym = (y + 1, 1) if m == 12 else (y, m + 1)
        st.rerun()
    for col, wd in zip(st.columns(7), ["일", "월", "화", "수", "목", "금", "토"]):
        color = "#d33" if wd == "일" else "#36c" if wd == "토" else "inherit"
        col.markdown(f"<div class='wk'><p style='color:{color}'>{wd}</p></div>", unsafe_allow_html=True)
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(y, m):
        for col, d in zip(st.columns(7), week):
            if d.month != m:
                col.write("")
                continue
            if col.button(str(d.day), key=f"d{d.isoformat()}", disabled=d < today,
                          type="primary" if d in ss.sel_days else "secondary"):
                ss.sel_days.symmetric_difference_update({d})
                st.rerun()
b1, b2, b3, b4 = st.columns(4)
if b1.button("이번 주말", width="stretch"):
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    ss.sel_days = {d for d in (sat - timedelta(days=1) if today.weekday() == 6 else sat,
                               sat + timedelta(days=1)) if d >= today}
    st.rerun()
if b2.button("앞으로 7일", width="stretch"):
    ss.sel_days = {today + timedelta(days=i) for i in range(7)}
    st.rerun()
if b3.button("이 달 주말 전체", width="stretch"):
    ss.sel_days = {d for wk in calendar.Calendar(6).monthdatescalendar(y, m) for d in wk
                   if d.month == m and d >= today and d.weekday() >= 5}
    st.rerun()
if b4.button("선택 해제", width="stretch"):
    ss.sel_days = set()
    st.rerun()
days = sorted(ss.sel_days)
st.caption("선택한 날짜: " + (", ".join(f"{d.month}/{d.day}({WEEK[d.weekday()]})" for d in days)
                         if days else "없음 — 달력에서 날짜를 눌러주세요"))

# ----- ③ 어종
st.subheader("③ 어종 선택")
fish_sel = st.multiselect("어종", fish_list, placeholder="전체 어종", label_visibility="collapsed")

# ----- 조회
targets = {(s["site"], s["id"]): s for s in pool + manual}
go = st.button(f"조회 (배 {len(targets)}척)", type="primary", width="stretch",
               disabled=not (days and targets))
if go:
    ships = list(targets.values())
    if fish_sel:   # 어종을 골랐으면 목록상 어종 정보로 1차 압축 (정보 없는 배는 유지)
        ships = [s for s in ships if not s["hint"] or fish_match(s["hint"], fish_sel)] or ships
    if len(ships) > MAX_SHIPS:
        st.warning(f"배가 {len(ships)}척이라 {MAX_SHIPS}척만 조회합니다. 시·도나 시·군을 좁혀주세요.")
        ships = ships[:MAX_SHIPS]
    months = tuple(sorted({f"{d.year}{d.month:02d}" for d in days}))
    jobs = [("ss", s, ym) for s in ships if s["site"] == "ss" for ym in months] + \
           [("tf", s, months) for s in ships if s["site"] == "tf"]
    rows, errors = [], []
    bar = st.progress(0.0, text="예약현황을 가져오는 중...")

    def work(job):
        kind, s, arg = job
        try:
            return (ss_month(freeze(s), arg) if kind == "ss" else tf_ship(freeze(s), arg)), None
        except Exception as ex:
            return [], f"[{SITES[kind]}] {s['name']}: {ex}"

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, (items, err) in enumerate(ex.map(work, jobs), 1):
            rows.extend(items)
            if err:
                errors.append(err)
            bar.progress(i / max(1, len(jobs)), text=f"예약현황 가져오는 중... {i}/{len(jobs)}")
    bar.empty()
    ss.rows, ss.errors, ss.fetched = rows, errors, time.strftime("%H:%M:%S")

rows = ss.get("rows")
if rows is None:
    st.info("사이트·지역·날짜·어종을 고르고 [조회]를 누르세요.")
    st.stop()

st.subheader("조회 결과")
if ss.errors:
    with st.expander(f"⚠️ {len(ss.errors)}건은 불러오지 못했습니다"):
        st.write("\n".join(f"- {e}" for e in ss.errors[:30]))

f1, f2, f3 = st.columns([1, 1, 2])
only_open = f1.checkbox("예약 가능한 것만", value=True)
need = f2.number_input("최소 남은자리", min_value=1, max_value=30, value=1)
sort_by = f3.radio("정렬", ["날짜순", "남은자리 많은순"], horizontal=True)

day_set = set(days)
in_scope = [r for r in rows if r["date"] in day_set and r["site"] in site_codes
            and fish_match(f"{r['species']} {r['notice']} {r['boat']}", fish_sel)]
view = [r for r in in_scope if not only_open or (r["remain"] is not None and r["remain"] >= need)]
view.sort(key=(lambda r: (r["date"], r["sido"], r["sigungu"], r["ship"])) if sort_by == "날짜순"
          else (lambda r: (-(r["remain"] or 0), r["date"])))
st.caption(f"{ss.fetched} 기준 · 선택 날짜/어종 일정 {len(in_scope)}건 중 {len(view)}건 표시")

if view:
    df = pd.DataFrame([{
        "날짜": f"{r['date']:%m.%d}({WEEK[r['date'].weekday()]})", "사이트": SITES[r["site"]],
        "지역": " ".join(x for x in (r["sido"], r["sigungu"], r["port"]) if x), "물때": r["tide"],
        "배": r["ship"] if r["boat"] in r["ship"] else f"{r['ship']} / {r['boat']}",
        "어종": r["species"], "출항": r["time"], "가격": r["price"], "남은자리": r["remain"],
        "상태": r["status"], "공지": r["notice"], "예약": r["url"],
    } for r in view])

    def color(row):
        v = row["남은자리"]
        ok = v is not None and v == v and v > 0
        return ["background-color: #e8f6ec" if ok else "color: #999"] * len(row)

    st.dataframe(df.style.apply(color, axis=1), width="stretch", hide_index=True, height=600,
                 column_config={
                     "예약": st.column_config.LinkColumn("예약", display_text="예약하기"),
                     "공지": st.column_config.TextColumn("공지", width="medium"),
                     "어종": st.column_config.TextColumn("어종", width="medium"),
                     "남은자리": st.column_config.NumberColumn("남은자리", format="%d명"),
                 })
    st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"선상낚시_예약_{today:%Y%m%d}.csv", mime="text/csv")
elif in_scope:
    st.write("선택한 조건에 남은자리가 있는 일정이 없습니다. [예약 가능한 것만]을 끄면 마감된 일정도 볼 수 있습니다.")
else:
    st.write("선택한 날짜·어종에 해당하는 출조 일정이 없습니다.")
