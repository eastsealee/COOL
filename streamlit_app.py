# -*- coding: utf-8 -*-
"""
선상24 실시간예약 조회 — 웹 버전 (Streamlit)
- 날짜 / 지역 / 어종 선택: 지역·어종 목록은 선상24 목록 페이지에서 읽어옴
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




# ---------------------------------------------------------------- 선상24 필터 목록 (지역/어종)
import pandas as pd
import streamlit as st
from datetime import timedelta

FILTER_PAGE = "https://app.sunsang24.com/ship/list?area=all"
# 사이트에서 못 읽을 때 쓰는 기본값 (2026-10 기준 app.sunsang24.com 목록 페이지와 동일)
FALLBACK_AREAS = {"전체": "all", "서해": "west", "동해": "east", "남해": "south", "제주": "jeju"}
FALLBACK_FISH = ["참돔", "광어", "우럭", "참우럭", "감성돔", "문어", "무늬오징어", "주꾸미", "갑오징어",
                 "한치", "오징어", "낙지", "호래기", "화살촉오징어", "부시리", "삼치", "갈치", "열기",
                 "노래미", "황열기", "볼락", "벤자리", "전갱이", "민어", "농어", "백조기", "수조기",
                 "도다리", "대구", "어구가자미", "참가자미", "붉바리", "방어", "돌돔", "붕장어", "쥐치",
                 "벵에돔", "옥돔", "쏨뱅이", "고등어", "망둥어", "홍감펭", "임연수어", "참치", "상어",
                 "뿔돔", "꽃게", "홍어"]
NOT_FISH = {"전체어종", "시즌어종", "기타", "베스트조황", "체험낚시", "갯바위", "좌대유터",
            "해루질", "탐사", "출조안내", "전체", "거리순"}
FISH_ALIAS = {"주꾸미": ["주꾸미", "쭈꾸미", "쭈갑"], "갑오징어": ["갑오징어", "쭈갑", "갑오"],
              "우럭": ["우럭", "조피볼락"], "광어": ["광어", "넙치"], "백조기": ["백조기", "조기"],
              "무늬오징어": ["무늬오징어", "에깅"], "오징어": ["오징어"], "문어": ["문어", "돌문어", "대문어"]}


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def load_filter_options():
    """선상24 목록 페이지에서 지역(area)과 어종 목록을 읽어옴. 실패하면 기본값."""
    areas, fish, src = {}, [], "기본값"
    try:
        soup = BeautifulSoup(fetch_html(FILTER_PAGE), "html.parser")
        for a in soup.find_all("a", href=True):
            m = re.search(r"[?&]area=([a-z]+)", a["href"])
            name = a.get_text(strip=True)
            if m and name and len(name) <= 6:
                areas.setdefault(name, m.group(1))
        anchor = soup.find(string=re.compile(r"^\s*전체어종\s*$"))
        node = anchor.parent if anchor else None
        while node is not None and len(node.find_all(["a", "li", "button"])) < 15:
            node = node.parent
        if node is not None:
            for el in node.find_all(["a", "li", "button", "span"]):
                t = el.get_text(strip=True)
                if t and 1 < len(t) <= 8 and t not in NOT_FISH and t not in fish \
                        and re.fullmatch(r"[가-힣]+", t):
                    fish.append(t)
        if areas and len(fish) >= 10:
            src = "선상24"
    except Exception:
        pass
    if not areas or len(fish) < 10:
        return FALLBACK_AREAS, FALLBACK_FISH, "기본값(사이트 응답 없음)"
    return areas, fish, src


# ---------------------------------------------------------------- 배 지역 판별
AREA_BY_PLACE = [
    ("jeju", ["제주", "서귀포"]),
    ("east", ["강원", "속초", "양양", "강릉", "동해시", "삼척", "울진", "영덕", "포항", "경주",
              "울산", "경북"]),
    ("west", ["인천", "경기", "옹진", "화성", "평택", "안산", "시흥", "김포", "충남", "태안", "보령",
              "서산", "당진", "홍성", "서천", "전북", "군산", "부안", "고창", "영광", "목포", "신안",
              "무안", "함평"]),
    ("south", ["부산", "경남", "거제", "통영", "남해", "사천", "창원", "마산", "고성군", "전남", "여수",
               "고흥", "완도", "진도", "해남", "장흥", "강진", "보성", "광양"]),
]


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def detect_ship_info(ship):
    """배 홈페이지에서 이름과 주소를 읽고 지역 코드를 추정"""
    try:
        soup = BeautifulSoup(fetch_html(f"https://{ship}.sunsang24.com/"), "html.parser")
    except Exception:
        return {"title": ship, "address": "", "area": ""}
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    title = soup.title.get_text(strip=True).split(",")[0] if soup.title else ship
    m = re.search(r"오시는\s*길\s*:?\s*([가-힣0-9\- ]{4,40})", text)
    addr = m.group(1).strip() if m else ""
    hay = addr or text[:3000]
    area = ""
    # 시/군 단위(구체적) 먼저 확인
    for code, places in AREA_BY_PLACE:
        if any(p in hay for p in places if len(p) >= 2 and p not in ("경북", "경남", "전남", "전북",
                                                                      "충남", "경기", "강원")):
            area = code
            break
    if not area:
        for code, places in AREA_BY_PLACE:
            if any(p in hay for p in places):
                area = code
                break
    return {"title": title, "address": addr, "area": area}


def fish_match(species_text, selected):
    if not selected:
        return True
    for f in selected:
        for alias in FISH_ALIAS.get(f, [f]):
            if alias in species_text:
                return True
    return False


# ---------------------------------------------------------------- 화면
st.set_page_config(page_title="선상24 예약조회", page_icon="🎣", layout="wide")
st.title("🎣 선상24 실시간예약 조회")

@st.cache_data(ttl=180, show_spinner=False)
def load_month(ship, y, m):
    html = fetch_html(schedule_url(ship, f"{y}{m:02d}"))
    return parse_schedule(html, y, ship)


areas, fish_list, filter_src = load_filter_options()
area_names = list(areas.keys())
code_to_name = {v: k for k, v in areas.items()}
today = date.today()

qp = st.query_params
default_ships = qp.get("ships", "gamsung")

with st.expander("⚓ 조회할 배 목록", expanded=not qp.get("ships")):
    st.caption("배 홈페이지 주소의 앞부분을 쉼표로 넣으세요. 예: gamsung.sunsang24.com → gamsung")
    ships_text = st.text_area("선박 ID", value=default_ships, height=70, label_visibility="collapsed")
ships = [s for s in (normalize_ship_id(x) for x in ships_text.replace("\n", ",").split(",")) if s]

st.subheader("예약 조회")
with st.form("search"):
    c1, c2, c3 = st.columns([2, 1, 2])
    period = c1.date_input("날짜 선택 (시작일 ~ 종료일)", value=(today, today + timedelta(days=13)),
                           min_value=today, max_value=today + timedelta(days=365), format="YYYY.MM.DD")
    area_sel = c2.selectbox("지역 선택", area_names,
                            index=area_names.index(code_to_name.get("all", area_names[0])))
    fish_sel = c3.multiselect("어종 선택", fish_list, placeholder="전체 어종")
    o1, o2, o3 = st.columns([1, 1, 2])
    need = o1.number_input("최소 남은자리", min_value=1, max_value=30, value=1)
    only_open = o2.checkbox("예약 가능한 것만", value=True)
    weekend = o3.checkbox("주말만")
    submitted = st.form_submit_button("조회", type="primary", width="stretch")
st.caption(f"지역·어종 목록 출처: {filter_src}")

if submitted:
    st.query_params["ships"] = ",".join(ships)
    if isinstance(period, (tuple, list)):
        d_from = period[0]
        d_to = period[1] if len(period) > 1 else period[0]
    else:
        d_from = d_to = period
    months, y, m = [], d_from.year, d_from.month
    while (y, m) <= (d_to.year, d_to.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    rows, errors, info = [], [], {}
    want_area = areas.get(area_sel, "all")
    with st.spinner("선상24에서 일정을 가져오는 중..."):
        for ship in ships:
            info[ship] = detect_ship_info(ship)
            if want_area != "all" and info[ship]["area"] and info[ship]["area"] != want_area:
                continue  # 다른 지역 배는 조회 생략
            for (yy, mm) in months:
                try:
                    items = load_month(ship, yy, mm)
                    if not items:
                        errors.append(f"{ship} {yy}.{mm}: 일정 없음 또는 페이지 형식이 다름")
                    rows.extend(items)
                except Exception as ex:
                    errors.append(f"{ship} {yy}.{mm}: {ex}")
                time.sleep(0.3)
    for r in rows:
        r["area"] = code_to_name.get(info[r["ship_id"]]["area"], "미확인")
        r["port"] = info[r["ship_id"]]["address"]
    st.session_state.update(rows=rows, errors=errors, fetched=time.strftime("%H:%M:%S"),
                            crit=(d_from, d_to, want_area, fish_sel, need, only_open, weekend))

rows = st.session_state.get("rows")
if rows is None:
    st.info("날짜·지역·어종을 고르고 [조회]를 누르세요.")
    st.stop()

for e in st.session_state.get("errors", [])[:5]:
    st.warning(e)

d_from, d_to, want_area, fish_sel_c, need_c, only_open_c, weekend_c = st.session_state["crit"]
view = []
for r in rows:
    d = date.fromisoformat(r["date"][:10])
    if not (d_from <= d <= d_to):
        continue
    if want_area != "all" and r["area"] not in (code_to_name.get(want_area), "미확인"):
        continue
    if not fish_match(r["species"] + " " + r["boat"], fish_sel_c):
        continue
    if only_open_c and not (r["remain"] is not None and r["remain"] >= need_c):
        continue
    if weekend_c and not r["date"].endswith(("(토)", "(일)")):
        continue
    view.append(r)

st.caption(f"{st.session_state.get('fetched')} 기준 · {len(view)}건")

if view:
    df = pd.DataFrame(view)[["date", "tide", "area", "boat", "species", "time", "remain",
                             "booked", "status", "port", "notice", "url"]]
    df.columns = ["날짜", "물때", "지역", "배", "어종", "운항시간", "남은자리", "예약", "상태",
                  "주소", "공지", "예약페이지"]

    def color(row):
        v = row["남은자리"]
        ok = v is not None and v == v and v > 0
        return ["background-color: #e8f6ec" if ok else "color: #999"] * len(row)

    st.dataframe(
        df.style.apply(color, axis=1), width="stretch", hide_index=True, height=560,
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
