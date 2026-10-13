# -*- coding: utf-8 -*-
"""
선상24 실시간예약 조회 — 웹 버전 (Streamlit)

- 배 목록: 선상24 조황정보(app.sunsang24.com/ship/board?area=...) 지역별 페이지에서 수집
- 지역 선택: 바다(서해/동해/남해/제주) → 시·도 → 시·군(항구)
- 어종 선택: 선상24 목록 페이지의 어종 전체
- 날짜 선택: 달력에서 날짜를 눌러 여러 날 선택
- 예약현황: app.sunsang24.com/ship/schedule_fleet/<배번호>/<YYYYMM>

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

APP = "https://app.sunsang24.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
SEAS = {"west": "서해", "east": "동해", "south": "남해", "jeju": "제주"}
BOARD_MAX_PAGES = 12   # 지역별 조황정보 몇 페이지까지 훑어 배 목록을 만들지
MAX_SHIPS = 150        # 한 번에 조회할 최대 배 수 (사이트 부담 방지)
WORKERS = 6

# 선상24 어종 목록 (2026-10 기준 app.sunsang24.com 목록 페이지). 실행 시 사이트에서 다시 읽어 갱신.
FALLBACK_FISH = ["참돔", "광어", "우럭", "참우럭", "감성돔", "문어", "무늬오징어", "주꾸미", "갑오징어",
                 "한치", "오징어", "낙지", "호래기", "화살촉오징어", "부시리", "삼치", "갈치", "열기",
                 "노래미", "황열기", "볼락", "벤자리", "전갱이", "민어", "농어", "백조기", "수조기",
                 "도다리", "대구", "어구가자미", "참가자미", "붉바리", "방어", "돌돔", "붕장어", "쥐치",
                 "벵에돔", "옥돔", "쏨뱅이", "고등어", "망둥어", "홍감펭", "임연수어", "참치", "상어",
                 "뿔돔", "꽃게", "홍어", "시즌어종", "기타", "체험낚시", "갯바위", "좌대유터", "해루질",
                 "탐사"]
FISH_ALIAS = {"주꾸미": ["주꾸미", "쭈꾸미", "쭈갑"], "갑오징어": ["갑오징어", "쭈갑", "갑오"],
              "우럭": ["우럭", "조피볼락"], "광어": ["광어", "넙치"], "백조기": ["백조기", "보구치"],
              "무늬오징어": ["무늬오징어", "에깅"], "문어": ["문어", "돌문어", "대문어", "피문어"],
              "열기": ["열기", "불볼락"], "도다리": ["도다리", "문치가자미"], "붕장어": ["붕장어", "아나고"]}

# 배 이름 앞의 항구/지명 → (시·도, 시·군)
PLACES = {
    # 인천
    "인천": ("인천", "인천"), "영종도": ("인천", "중구(영종도)"), "연안부두": ("인천", "중구"),
    "남항": ("인천", "중구"), "영흥도": ("인천", "옹진(영흥도)"), "덕적도": ("인천", "옹진"),
    "강화": ("인천", "강화"), "선재도": ("인천", "옹진"),
    # 경기
    "오이도": ("경기", "시흥(오이도)"), "시흥": ("경기", "시흥"), "전곡항": ("경기", "화성(전곡항)"),
    "궁평항": ("경기", "화성(궁평항)"), "제부도": ("경기", "화성"), "화성": ("경기", "화성"),
    "대부도": ("경기", "안산(대부도)"), "탄도항": ("경기", "안산(탄도항)"), "안산": ("경기", "안산"),
    "평택": ("경기", "평택"), "김포": ("경기", "김포"),
    # 충남
    "당진": ("충남", "당진"), "장고항": ("충남", "당진(장고항)"), "석문": ("충남", "당진"),
    "한진": ("충남", "당진"), "서산": ("충남", "서산"), "삼길포": ("충남", "서산(삼길포)"),
    "태안": ("충남", "태안"), "안면도": ("충남", "태안(안면도)"), "신진도": ("충남", "태안(신진도)"),
    "안흥": ("충남", "태안(안흥)"), "마검포": ("충남", "태안(마검포)"), "영목": ("충남", "태안(영목항)"),
    "영목항": ("충남", "태안(영목항)"), "모항": ("충남", "태안(모항)"), "백사장": ("충남", "태안"),
    "홍성": ("충남", "홍성"), "남당항": ("충남", "홍성(남당항)"), "보령": ("충남", "보령"),
    "오천": ("충남", "보령(오천항)"), "오천항": ("충남", "보령(오천항)"), "대천": ("충남", "보령(대천항)"),
    "대천항": ("충남", "보령(대천항)"), "무창포": ("충남", "보령(무창포)"), "서천": ("충남", "서천"),
    "홍원항": ("충남", "서천(홍원항)"),
    # 전북
    "군산": ("전북", "군산"), "비응항": ("전북", "군산(비응항)"), "야미도": ("전북", "군산"),
    "부안": ("전북", "부안"), "격포": ("전북", "부안(격포)"), "위도": ("전북", "부안(위도)"),
    "고창": ("전북", "고창"),
    # 전남
    "영광": ("전남", "영광"), "목포": ("전남", "목포"), "신안": ("전남", "신안"), "무안": ("전남", "무안"),
    "영암": ("전남", "영암"), "진도": ("전남", "진도"), "해남": ("전남", "해남"), "완도": ("전남", "완도"),
    "여수": ("전남", "여수"), "돌산": ("전남", "여수(돌산)"), "고흥": ("전남", "고흥"),
    "녹동": ("전남", "고흥(녹동)"), "장흥": ("전남", "장흥"), "강진": ("전남", "강진"),
    "보성": ("전남", "보성"), "광양": ("전남", "광양"),
    # 강원
    "속초": ("강원", "속초"), "양양": ("강원", "양양"), "주문진": ("강원", "강릉(주문진)"),
    "강릉": ("강원", "강릉"), "동해": ("강원", "동해"), "묵호": ("강원", "동해(묵호)"),
    "삼척": ("강원", "삼척"), "임원": ("강원", "삼척(임원)"), "대진": ("강원", "고성"),
    "아야진": ("강원", "고성"), "공현진": ("강원", "고성"),
    # 경북
    "울진": ("경북", "울진"), "후포": ("경북", "울진(후포)"), "영덕": ("경북", "영덕"),
    "강구": ("경북", "영덕(강구)"), "축산": ("경북", "영덕(축산)"), "포항": ("경북", "포항"),
    "구룡포": ("경북", "포항(구룡포)"), "경주": ("경북", "경주"), "감포": ("경북", "경주(감포)"),
    # 울산·부산·경남
    "울산": ("울산", "울산"), "정자": ("울산", "북구(정자)"), "부산": ("부산", "부산"),
    "기장": ("부산", "기장"), "다대포": ("부산", "사하(다대포)"), "거제": ("경남", "거제"),
    "통영": ("경남", "통영"), "남해": ("경남", "남해"), "사천": ("경남", "사천"),
    "삼천포": ("경남", "사천(삼천포)"), "진해": ("경남", "창원(진해)"), "마산": ("경남", "창원(마산)"),
    "창원": ("경남", "창원"),
    # 제주
    "제주": ("제주", "제주"), "서귀포": ("제주", "서귀포"), "한림": ("제주", "제주(한림)"),
    "도두": ("제주", "제주(도두)"), "김녕": ("제주", "제주(김녕)"), "차귀도": ("제주", "제주(차귀도)"),
    "모슬포": ("제주", "서귀포(모슬포)"), "성산": ("제주", "서귀포(성산)"), "애월": ("제주", "제주(애월)"),
}


# ---------------------------------------------------------------- 공통
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def clean_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    out = []
    for raw in soup.get_text("\n").split("\n"):
        s = re.sub(r"\s+", " ", raw).strip()
        if s:
            out.append(s)
    return out


def locate(name, sea):
    """배 이름('장고항 군자호', '군산낚시프라자')에서 시·도/시·군 추정"""
    first = name.split()[0] if " " in name else ""
    keys = [first] if first in PLACES else [k for k in sorted(PLACES, key=len, reverse=True)
                                            if name.startswith(k)][:1]
    if first == "고성" or name.startswith("고성"):          # 강원 고성 / 경남 고성 구분
        return ("강원", "고성") if sea == "east" else ("경남", "고성")
    if keys:
        return PLACES[keys[0]]
    return ("기타", first or "기타")


# ---------------------------------------------------------------- 선상24 데이터 수집
@st.cache_data(ttl=12 * 3600, show_spinner=False)
def load_fish_list():
    try:
        soup = BeautifulSoup(fetch_html(f"{APP}/ship/list?area=all"), "html.parser")
        anchor = soup.find(string=re.compile(r"^\s*전체어종\s*$"))
        node = anchor.parent if anchor else None
        while node is not None and len(node.find_all(["a", "li", "button"])) < 15:
            node = node.parent
        fish = []
        if node is not None:
            for el in node.find_all(["a", "li", "button", "span"]):
                t = el.get_text(strip=True)
                if t and t not in fish and t not in ("전체어종", "전체", "거리순", "베스트조황", "출조안내") \
                        and re.fullmatch(r"[가-힣]{2,8}", t):
                    fish.append(t)
        if len(fish) >= 20:
            return fish, "선상24"
    except Exception:
        pass
    return FALLBACK_FISH, "기본 목록"


def _board_page(sea, page):
    try:
        html = fetch_html(f"{APP}/ship/board?area={sea}&page={page}")
    except Exception:
        return None
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"/ship/schedule/(\d+)", a["href"])
        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if m and name and len(name) <= 30:
            found.setdefault(int(m.group(1)), name)
    return found


def _crawl_sea(sea):
    ships, empty_streak = {}, 0
    for page in range(1, BOARD_MAX_PAGES + 1):
        found = _board_page(sea, page)
        if found is None:
            break
        new = {k: v for k, v in found.items() if k not in ships}
        ships.update(new)
        empty_streak = 0 if new else empty_streak + 1
        if empty_streak >= 2:
            break
        time.sleep(0.3)
    return sea, ships


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_catalog():
    """지역별 조황정보 페이지를 훑어 배 목록(번호, 이름, 바다, 시도, 시군) 생성"""
    rows, seen = [], set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for sea, ships in ex.map(_crawl_sea, list(SEAS)):
            for sid, name in ships.items():
                if sid in seen:
                    continue
                seen.add(sid)
                sido, sigungu = locate(name, sea)
                rows.append({"id": sid, "name": name, "sea": sea, "sido": sido, "sigungu": sigungu})
    return sorted(rows, key=lambda r: (r["sea"], r["sido"], r["sigungu"], r["name"]))


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def resolve_manual(token):
    """직접 추가: 배 번호(2174) 또는 홈페이지 주소(gamsung / gamsung.sunsang24.com)"""
    t = token.strip()
    if t.isdigit():
        return {"id": int(t), "name": f"배 {t}", "sea": "", "sido": "직접추가", "sigungu": "직접추가"}
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
    return {"id": int(m.group(1)), "name": title, "sea": "", "sido": "직접추가", "sigungu": "직접추가"}


# ---------------------------------------------------------------- 예약현황 파싱
DATE_RE = re.compile(r"(?:(\d{1,2})[ \t]*월[ \t]*)?(\d{1,2})\s*일\s*\(\s*([월화수목금토일])\s*\)")
TIDE_RE = re.compile(r"(\d{1,2}\s*물|조금|무시)")
SP_LABEL = re.compile(r"(?:대상\s*어종|(?<![가-힣])어\s*종)\s*:?\s*")
TIME_LABEL = re.compile(r"(?:출항\s*시간|운항\s*시간)\s*:?\s*")
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})")
STATUS_RE = re.compile(r"남은\s*자리\s*:?\s*(\d+)\s*명|(예약\s*마감)|(기상\s*악화|출조\s*취소|휴\s*항|휴\s*무)")
BOOKED_RE = re.compile(r"\s*(?:(\d+)\s*명\s*)?예약\s*/\s*(\d+)\s*명|\s*(\d+)\s*명")
NOISE = ("바로예약", "대기하기", "예약하기", "전화예약", "예약완료", "입금대기", "취소대기", "취소완료",
         "예약대기", "출조대기")


def _is_name(line):
    if not line or len(line) > 30 or ":" in line:
        return False
    if DATE_RE.search(line) or TIDE_RE.fullmatch(line) or STATUS_RE.search(line):
        return False
    if any(w in line for w in NOISE) or line.startswith(("공지", "(")):
        return False
    return not re.fullmatch(r"[\d\s명/|\-*]+", line)


def parse_schedule(html, year, month, ship):
    """app.sunsang24.com/ship/schedule_fleet/<id>/<YYYYMM> 페이지 → 일정 목록"""
    full = "\n".join(clean_lines(html))
    dates = []
    for m in DATE_RE.finditer(full):
        line_start = full.rfind("\n", 0, m.start()) + 1
        if full[line_start:m.start()].strip(" -|*") == "":      # 줄 맨 앞의 날짜만 (공지 속 날짜 제외)
            dates.append(m)
    results = []
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
            remain, booked, status = None, None, "확인필요"
            end = stm.end() if stm else (tm.end() if tm else lab.end())
            if stm:
                if stm.group(1) is not None:
                    remain = int(stm.group(1))
                    status = "예약가능" if remain > 0 else "마감"
                elif stm.group(2):
                    remain, status = 0, "마감"
                else:
                    remain, status = 0, re.sub(r"\s+", "", stm.group(3))
                bm = BOOKED_RE.match(block, stm.end())
                if bm and bm.end() - stm.end() < 25:
                    booked = int(bm.group(2) or bm.group(3) or 0) or None
                    end = bm.end()
            pre = [l.strip(" |-*") for l in block[prev_end: lab.start()].split("\n")]
            pre = [re.sub(r"\(일정-?\d*\)", "", l).strip() for l in pre]
            names = [l for l in pre if _is_name(l)]
            boat = names[0] if names else ship["name"]
            notice = " ".join(l for l in pre if l and l != boat and not any(w == l for w in NOISE))
            notice = re.sub(r"^공지사항\s*:?\s*", "", notice).strip()
            results.append({
                "ship_id": ship["id"], "ship": ship["name"], "sido": ship["sido"],
                "sigungu": ship["sigungu"], "date": d, "tide": tide, "boat": boat,
                "species": species, "time": f"{tm.group(1)}~{tm.group(2)}" if tm else "",
                "remain": remain, "booked": booked, "status": status, "notice": notice[:200],
                "url": f"{APP}/ship/schedule_fleet/{ship['id']}/{yr}{mo:02d}",
            })
            prev_end = end
    return results


@st.cache_data(ttl=180, show_spinner=False)
def load_month(ship_id, name, sido, sigungu, yyyymm):
    ship = {"id": ship_id, "name": name, "sido": sido, "sigungu": sigungu}
    html = fetch_html(f"{APP}/ship/schedule_fleet/{ship_id}/{yyyymm}")
    return parse_schedule(html, int(yyyymm[:4]), int(yyyymm[4:]), ship)


def fish_match(text, selected):
    if not selected:
        return True
    return any(alias in text for f in selected for alias in FISH_ALIAS.get(f, [f]))


# ---------------------------------------------------------------- 화면
st.set_page_config(page_title="선상24 예약조회", page_icon="🎣", layout="wide")
st.markdown("""
<style>
.st-key-cal [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 4px !important;}
.st-key-cal [data-testid="stColumn"] {min-width: 0 !important; flex: 1 1 0 !important; width: auto !important;}
.st-key-cal button {padding: 0.15rem 0 !important; min-height: 2.3rem; width: 100%;}
.st-key-cal .wk p {text-align: center; font-weight: 600; margin: 0;}
</style>""", unsafe_allow_html=True)
st.title("🎣 선상24 실시간예약 조회")

today = date.today()
ss = st.session_state
ss.setdefault("sel_days", {today + timedelta(days=i) for i in range(7)})
ss.setdefault("cal_ym", (today.year, today.month))

with st.spinner("선상24 배 목록을 불러오는 중... (처음 한 번만 1분 정도 걸립니다)"):
    catalog = load_catalog()
fish_list, fish_src = load_fish_list()

if not catalog:
    st.error("선상24에서 배 목록을 불러오지 못했습니다. 잠시 후 새로고침 해주세요. "
             "계속 안 되면 선상24가 이 서버의 접속을 막고 있을 수 있습니다.")

# ----- 1) 지역 선택 (바다 → 시·도 → 시·군)
st.subheader("① 지역 선택")
c1, c2, c3 = st.columns(3)
sea_opts = ["전체"] + [SEAS[k] for k in SEAS]
sea_name = c1.selectbox("바다", sea_opts)
sea_code = next((k for k, v in SEAS.items() if v == sea_name), "all")
pool = [s for s in catalog if sea_code == "all" or s["sea"] == sea_code]
sido_opts = ["전체"] + sorted({s["sido"] for s in pool}, key=lambda x: (x == "기타", x))
sido = c2.selectbox("시·도", sido_opts)
pool = [s for s in pool if sido == "전체" or s["sido"] == sido]
sgg_opts = ["전체"] + sorted({s["sigungu"] for s in pool})
sigungu = c3.selectbox("시·군 / 항구", sgg_opts)
pool = [s for s in pool if sigungu == "전체" or s["sigungu"] == sigungu]

with st.expander(f"선택 지역의 배 {len(pool)}척 보기 · 직접 추가"):
    if pool:
        st.dataframe(pd.DataFrame(pool)[["name", "sido", "sigungu", "id"]]
                     .rename(columns={"name": "배", "sido": "시·도", "sigungu": "시·군", "id": "번호"}),
                     hide_index=True, width="stretch", height=220)
    manual_text = st.text_input("목록에 없는 배 추가 (쉼표로 여러 개, 배 번호 또는 홈페이지 주소)",
                                placeholder="예: 2174, gamsung")
manual = [r for r in (resolve_manual(t) for t in manual_text.split(",") if t.strip()) if r]

# ----- 2) 날짜 선택 (달력)
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
    head = st.columns(7)
    for col, wd in zip(head, ["일", "월", "화", "수", "목", "금", "토"]):
        col.markdown(f"<div class='wk'><p style='color:{'#d33' if wd == '일' else '#36c' if wd == '토' else 'inherit'}'>"
                     f"{wd}</p></div>", unsafe_allow_html=True)
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(y, m):
        cols = st.columns(7)
        for col, d in zip(cols, week):
            if d.month != m:
                col.write("")
                continue
            picked = d in ss.sel_days
            if col.button(str(d.day), key=f"d{d.isoformat()}", disabled=d < today,
                          type="primary" if picked else "secondary"):
                ss.sel_days.symmetric_difference_update({d})
                st.rerun()
b1, b2, b3, b4 = st.columns(4)
if b1.button("이번 주말", width="stretch"):
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    ss.sel_days = {sat, sat + timedelta(days=1)} - {today - timedelta(days=1)}
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
st.caption("선택한 날짜: " + (", ".join(f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})" for d in days)
                         if days else "없음 — 달력에서 날짜를 눌러주세요"))

# ----- 3) 어종 선택
st.subheader("③ 어종 선택")
fish_sel = st.multiselect("어종", fish_list, placeholder="전체 어종", label_visibility="collapsed")
st.caption(f"어종 목록 출처: {fish_src}")

# ----- 조회
targets = {s["id"]: s for s in pool + manual}
go = st.button(f"조회 (배 {len(targets)}척)", type="primary", width="stretch",
               disabled=not (days and targets))
if go:
    ships = list(targets.values())
    if len(ships) > MAX_SHIPS:
        st.warning(f"배가 {len(ships)}척이라 앞의 {MAX_SHIPS}척만 조회합니다. 시·도나 시·군을 좁혀주세요.")
        ships = ships[:MAX_SHIPS]
    months = sorted({f"{d.year}{d.month:02d}" for d in days})
    jobs = [(s, ym) for s in ships for ym in months]
    rows, errors = [], []
    bar = st.progress(0.0, text="선상24에서 예약현황을 가져오는 중...")

    def work(job):
        s, ym = job
        try:
            return load_month(s["id"], s["name"], s["sido"], s["sigungu"], ym), None
        except Exception as ex:
            return [], f"{s['name']} {ym}: {ex}"

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, (items, err) in enumerate(ex.map(work, jobs), 1):
            rows.extend(items)
            if err:
                errors.append(err)
            bar.progress(i / len(jobs), text=f"예약현황 가져오는 중... {i}/{len(jobs)}")
    bar.empty()
    ss.rows, ss.errors, ss.fetched = rows, errors, time.strftime("%H:%M:%S")

rows = ss.get("rows")
if rows is None:
    st.info("지역·날짜·어종을 고르고 [조회]를 누르세요.")
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
in_scope = [r for r in rows if r["date"] in day_set and fish_match(r["species"] + " " + r["notice"], fish_sel)]
view = [r for r in in_scope if not only_open or (r["remain"] is not None and r["remain"] >= need)]
view.sort(key=(lambda r: (r["date"], r["sigungu"], r["ship"])) if sort_by == "날짜순"
          else (lambda r: (-(r["remain"] or 0), r["date"])))

st.caption(f"{ss.fetched} 기준 · 선택 날짜/어종 일정 {len(in_scope)}건 중 {len(view)}건 표시")

if view:
    df = pd.DataFrame([{
        "날짜": f"{r['date']:%m.%d}({'월화수목금토일'[r['date'].weekday()]})", "물때": r["tide"],
        "지역": f"{r['sido']} {r['sigungu']}", "배": r["ship"] if r["boat"] in r["ship"] else f"{r['ship']} / {r['boat']}",
        "어종": r["species"], "출항시간": r["time"], "남은자리": r["remain"], "상태": r["status"],
        "공지": r["notice"], "예약": r["url"],
    } for r in view])

    def color(row):
        v = row["남은자리"]
        ok = v is not None and v == v and v > 0
        return ["background-color: #e8f6ec" if ok else "color: #999"] * len(row)

    st.dataframe(df.style.apply(color, axis=1), width="stretch", hide_index=True, height=600,
                 column_config={
                     "예약": st.column_config.LinkColumn("예약", display_text="예약하기"),
                     "공지": st.column_config.TextColumn("공지", width="medium"),
                     "남은자리": st.column_config.NumberColumn("남은자리", format="%d명"),
                 })
    st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"선상24_예약_{today:%Y%m%d}.csv", mime="text/csv")
elif in_scope:
    st.write("선택한 조건에 남은자리가 있는 일정이 없습니다. [예약 가능한 것만]을 끄면 마감된 일정도 볼 수 있습니다.")
else:
    st.write("선택한 날짜·어종에 해당하는 출조 일정이 없습니다.")
