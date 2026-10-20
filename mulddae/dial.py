"""물때 시계 — 24시간 원형 화면 (물때·조류세기·날씨·바람·수온)

- 물때·일출몰: 바다타임 월간 물때표 / 조류세기: 선상낚시 예약조회와 같은 계산 (tide_data.add_flow)
- 날씨·바람: Open-Meteo Forecast / 수온: Open-Meteo Marine (약 3달 전 ~ 16일 뒤까지만 제공)
- 화면(dial_component/index.html)은 양방향 컴포넌트: 달력에서 고른 날짜가 불러온 범위 밖이면
  그 날짜를 돌려보내고, 여기서 그 날짜 앞뒤 물때를 다시 불러와 넘겨줌
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from tide_data import KST, PORTS, fetch_weather, load_days  # noqa: E402
from dial_widget import dial  # noqa: E402

st.set_page_config(page_title="물때 시계", layout="centered")
st.markdown("<style>.block-container{padding-top:1.2rem;padding-bottom:1rem;max-width:560px}</style>",
            unsafe_allow_html=True)

names = list(PORTS)
q = st.query_params.get("port")
port = st.selectbox("포인트", names, index=names.index(q) if q in names else 0,
                    help="입력해서 검색할 수 있습니다")
st.query_params["port"] = port
pid, lat, lon = PORTS[port]

now = datetime.now(KST)
today = now.strftime("%Y-%m-%d")
center_s = st.session_state.get("dial_center", today)
center = datetime.strptime(center_s, "%Y-%m-%d").replace(tzinfo=KST)

with st.spinner("물때 불러오는 중…"):
    days, errors = load_days(pid, center)

if len(days) < 3:
    st.error(f"{center:%Y년 %m월 %d일} 앞뒤 물때 자료를 가져오지 못했습니다. 다른 날짜나 포인트를 골라 보세요.")
    if errors:
        st.caption(" / ".join(errors))
    if center_s != today and st.button("오늘로 돌아가기"):
        st.session_state["dial_center"] = today
        st.rerun()
    st.stop()

# 날씨는 예보 API가 주는 범위(약 90일 전 ~ 15일 뒤)와 기준 날짜 앞뒤 11일이 겹치는 부분만
w_lo = max(center - timedelta(days=11), now - timedelta(days=90)).strftime("%Y-%m-%d")
w_hi = min(center + timedelta(days=11), now + timedelta(days=15)).strftime("%Y-%m-%d")
weather = []
if w_lo <= w_hi:
    try:
        weather = fetch_weather(lat, lon, start=w_lo, end=w_hi)
    except Exception:
        st.warning("날씨 정보를 가져오지 못했습니다. 물때만 표시합니다.")

data = {"port": port.split(" (")[0], "today": today, "center": center_s, "days": days, "weather": weather}
val = dial(data=data, key="dial", default=None)

# 화면에서 범위 밖 날짜를 골랐으면 그 날짜를 기준으로 다시 불러옴
if isinstance(val, dict) and val.get("n") != st.session_state.get("dial_n"):
    st.session_state["dial_n"] = val.get("n")
    picked = str(val.get("date", ""))[:10]
    try:
        datetime.strptime(picked, "%Y-%m-%d")
    except ValueError:
        picked = ""
    if picked and picked != center_s:
        st.session_state["dial_center"] = picked
        st.rerun()

st.caption(f"물때: [바다타임](https://www.badatime.com/{pid}.html) · 날씨/수온: [Open-Meteo](https://open-meteo.com) · "
           f"{now:%m-%d %H:%M} 기준")
