# -*- coding: utf-8 -*-
"""
선상24 실시간예약 조회 — 웹 버전 (Streamlit)
로컬 실행:  pip install -r requirements.txt  →  streamlit run streamlit_app.py
"""
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

APP_TITLE = "선상24 실시간예약 조회기"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
REQUEST_DELAY = 0.7  # 배 여러 척 조회 시 요청 간격(초) — 사이트 부담 줄이기

DATE_RE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*\(([월화수목금토일])\)")
TIDE_RE = re.compile(r"(\d{1,2}물|조금|무시)")
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})")
REMAIN_RE = re.compile(r"남은자리\s*(\d+)\s*명")
BOOKED_RE = re.compile(r"예약\s*/\s*(\d+)\s*명")
BUTTON_WORDS = ("바로예약", "대기하기", "예약하기", "전화예약")
STATUS_NOISE = ("예약완료", "입금대기", "취소대기", "취소완료", "예약대기", "출조대기")


# ---------------------------------------------------------------- 파싱
def normalize_ship_id(text):
    """'gamsung', 'gamsung.sunsang24.com', 'https://gamsung.sunsang24.com/...' → 'gamsung'"""
    t = text.strip()
    if not t:
        return ""
    t = re.sub(r"^https?://", "", t)
    host = t.split("/")[0]
    if host.endswith(".sunsang24.com"):
        return host[: -len(".sunsang24.com")]
    return host


def schedule_url(ship_id, yyyymm):
    return f"https://{ship_id}.sunsang24.com/ship/schedule_fleet/{yyyymm}"


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def _clean_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # 예약대기 팝업 등 본문 외 영역은 날짜 블록 밖이라 자연히 무시됨
    lines = []
    for raw in soup.get_text("\n").split("\n"):
        s = re.sub(r"\s+", " ", raw).strip()
        if s:
            lines.append(s)
    return lines


def _is_name_candidate(line):
    if not line or len(line) > 30:
        return False
    if DATE_RE.search(line) or TIDE_RE.fullmatch(line):
        return False
    if re.fullmatch(r"\(일정-?\d*\)", line):
        return False
    if any(w in line for w in BUTTON_WORDS + STATUS_NOISE):
        return False
    if REMAIN_RE.search(line) or BOOKED_RE.search(line) or "예약마감" in line:
        return False
    if re.fullmatch(r"[\d명/ ]+", line) or line in ("|", "-", ":"):
        return False
    if ":" in line:
        return False
    return True


def parse_schedule(html, year, ship_id=""):
    """실시간예약 페이지 HTML → 일정 dict 리스트"""
    lines = _clean_lines(html)
    results = []
    cur_date = None
    cur_tide = ""
    cur = None          # 현재 작성 중인 배 일정
    name_buf = []       # 버튼 직전 줄들(배 이름 후보)
    field = None        # 다음 줄이 무슨 값인지 ('species', 'notice')

    def finish():
        nonlocal cur
        # 예약대기 팝업의 '대기하기' 버튼처럼 내용 없는 항목은 버림
        if cur and (cur["species"].strip() or cur["time"] or cur["remain"] is not None):
            cur["species"] = cur["species"].strip(" /")
            cur["notice"] = cur["notice"].strip()
            results.append(cur)
        cur = None

    for line in lines:
        m = DATE_RE.search(line)
        if m and not line.startswith("공지"):
            finish()
            mo, dd, wd = int(m.group(1)), int(m.group(2)), m.group(3)
            cur_date = f"{year}-{mo:02d}-{dd:02d}({wd})"
            t = TIDE_RE.search(line[m.end():])
            cur_tide = t.group(1) if t else ""
            rest = line[m.end():]
            name_buf = []
            # "10물 | 감성피싱" 처럼 같은 줄에 배 이름이 붙은 경우
            for part in re.split(r"[|]", rest):
                part = TIDE_RE.sub("", part).strip()
                if _is_name_candidate(part):
                    name_buf.append(part)
            field = None
            continue
        if cur_date is None:
            continue

        if not cur_tide and TIDE_RE.fullmatch(line):
            cur_tide = line
            continue

        # 배 하나의 시작 = 예약 버튼
        btn = next((w for w in BUTTON_WORDS if w in line), None)
        if btn and not line.startswith("공지"):
            finish()
            before = line.split(btn)[0].strip(" |")
            before = re.sub(r"\(일정-?\d*\)", "", before).strip()
            name = before if _is_name_candidate(before) else (name_buf[-1] if name_buf else "")
            cur = {
                "ship_id": ship_id, "date": cur_date, "tide": cur_tide, "boat": name,
                "button": btn, "species": "", "time": "", "remain": None,
                "booked": None, "status": "", "notice": "",
                "url": schedule_url(ship_id, cur_date[:7].replace("-", "")) if ship_id else "",
            }
            name_buf = []
            field = None
            continue

        if cur is None:
            if _is_name_candidate(line):
                name_buf.append(line)
            continue

        # 상세 항목
        if line.startswith("공지사항"):
            field = "notice"
            v = line.split(":", 1)[1] if ":" in line else ""
            cur["notice"] += v.strip() + " "
            continue
        if line.startswith("어종"):
            field = "species"
            v = line.split(":", 1)[1] if ":" in line else ""
            cur["species"] += v.strip() + " "
            continue
        if "운항시간" in line or TIME_RE.search(line):
            t = TIME_RE.search(line)
            if t:
                cur["time"] = f"{t.group(1)}~{t.group(2)}"
                field = None
                continue
            field = "time"
            continue
        if field == "time" and TIME_RE.search(line):
            t = TIME_RE.search(line)
            cur["time"] = f"{t.group(1)}~{t.group(2)}"
            field = None
            continue

        r = REMAIN_RE.search(line)
        if r:
            cur["remain"] = int(r.group(1))
            cur["status"] = "예약가능" if cur["remain"] > 0 else "마감"
        if "예약마감" in line:
            cur["remain"] = 0
            cur["status"] = "마감"
        b = BOOKED_RE.search(line)
        if b:
            cur["booked"] = int(b.group(1))
        if r or b or "예약마감" in line:
            field = None
            continue
        if any(w == line for w in STATUS_NOISE):
            field = None
            continue

        if field == "species":
            cur["species"] += line + " "
        elif field == "notice":
            cur["notice"] += line + " "
        elif _is_name_candidate(line):
            # 상태까지 다 읽은 뒤 나오는 짧은 줄 = 다음 배 이름일 가능성
            if cur["status"]:
                name_buf.append(line)

    finish()
    for it in results:
        if not it["status"]:
            it["status"] = "대기만 가능" if it["button"] == "대기하기" else "확인필요"
    return results




# ---------------------------------------------------------------- 웹 화면 (Streamlit)
import pandas as pd
import streamlit as st

st.set_page_config(page_title="선상24 예약조회", page_icon="🎣", layout="wide")
st.title("🎣 선상24 실시간예약 조회")
st.caption("배 홈페이지 주소의 앞부분(예: gamsung.sunsang24.com → gamsung)을 넣고 조회하세요.")


@st.cache_data(ttl=180, show_spinner=False)
def load_month(ship, y, m):
    """한 배의 한 달 일정 (3분 캐시 — 사이트 부담 줄이기)"""
    html = fetch_html(schedule_url(ship, f"{y}{m:02d}"))
    return parse_schedule(html, y, ship)


qp = st.query_params
default_ships = qp.get("ships", "gamsung")
today = date.today()

with st.form("search"):
    c1, c2, c3 = st.columns([3, 1, 1])
    ships_text = c1.text_input("선박 ID (쉼표로 여러 개)", value=default_ships)
    start = c2.date_input("조회 시작월", value=today.replace(day=1))
    n_months = c3.selectbox("기간", [1, 2, 3], format_func=lambda x: f"{x}개월")
    submitted = st.form_submit_button("조회", type="primary", width="stretch")

ships = [s for s in (normalize_ship_id(x) for x in ships_text.split(",")) if s]

if submitted:
    st.query_params["ships"] = ",".join(ships)  # 주소창 링크로 즐겨찾기 가능
    rows, errors = [], []
    y, m = start.year, start.month
    months = []
    for _ in range(n_months):
        months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    with st.spinner("선상24에서 일정을 가져오는 중..."):
        for ship in ships:
            for (yy, mm) in months:
                try:
                    items = load_month(ship, yy, mm)
                    if not items:
                        errors.append(f"{ship} {yy}.{mm}: 일정 없음 또는 페이지 형식이 다름")
                    rows.extend(items)
                except Exception as ex:
                    errors.append(f"{ship} {yy}.{mm}: {ex}")
                time.sleep(0.3)
    st.session_state["rows"] = rows
    st.session_state["errors"] = errors
    st.session_state["fetched"] = time.strftime("%H:%M:%S")

rows = st.session_state.get("rows")
if rows is None:
    st.info("조회 버튼을 누르면 결과가 여기에 표시됩니다.")
    st.stop()

for e in st.session_state.get("errors", [])[:5]:
    st.warning(e)

st.subheader("필터")
f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
kw = f1.text_input("어종/배 이름 검색", placeholder="예: 쭈꾸미, 감성돔")
need = f2.number_input("최소 남은자리", min_value=1, max_value=30, value=1)
only_open = f3.checkbox("예약 가능한 것만")
weekend = f4.checkbox("주말만")

view = []
for r in rows:
    if kw and kw not in r["species"] and kw not in r["boat"] and kw not in r["notice"]:
        continue
    if only_open and not (r["remain"] is not None and r["remain"] >= need):
        continue
    if weekend and not r["date"].endswith(("(토)", "(일)")):
        continue
    view.append(r)

st.caption(f"{st.session_state.get('fetched')} 기준 · 전체 {len(rows)}건 중 {len(view)}건 표시")

if view:
    df = pd.DataFrame(view)[["date", "tide", "boat", "species", "time", "remain",
                             "booked", "status", "notice", "url"]]
    df.columns = ["날짜", "물때", "배", "어종", "운항시간", "남은자리", "예약", "상태", "공지", "예약페이지"]

    def color(row):
        ok = row["남은자리"] is not None and row["남은자리"] == row["남은자리"] and row["남은자리"] > 0
        return ["background-color: #e8f6ec" if ok else "color: #999"] * len(row)

    st.dataframe(
        df.style.apply(color, axis=1),
        width="stretch", hide_index=True, height=560,
        column_config={
            "예약페이지": st.column_config.LinkColumn("예약페이지", display_text="열기"),
            "공지": st.column_config.TextColumn("공지", width="medium"),
            "남은자리": st.column_config.NumberColumn("남은자리", format="%d명"),
        },
    )
    st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"선상24_예약_{today:%Y%m%d}.csv", mime="text/csv")
else:
    st.write("조건에 맞는 일정이 없습니다.")
