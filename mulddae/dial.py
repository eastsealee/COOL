"""물때 시계 — 24시간 원형 화면 (물때·조류세기·날씨·바람·수온)

- 물때·일출몰: 바다타임 월간 물때표 / 조류세기: 선상낚시 예약조회와 같은 계산 (tide_data.add_flow)
- 날씨·바람: Open-Meteo Forecast / 수온: Open-Meteo Marine
- 오늘 기준 앞뒤 10일
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from tide_data import KST, PORTS, fetch_weather, load_days  # noqa: E402

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
with st.spinner("물때 불러오는 중…"):
    days, errors = load_days(pid, now)

lo = (now - timedelta(days=11)).strftime("%Y-%m-%d")
hi = (now + timedelta(days=11)).strftime("%Y-%m-%d")
days = {k: v for k, v in days.items() if lo <= k <= hi}
if len(days) < 3:
    st.error("물때 자료를 가져오지 못했습니다. 잠시 후 새로고침하거나 다른 포인트를 골라 보세요.")
    if errors:
        st.caption(" / ".join(errors))
    st.stop()

try:
    weather = fetch_weather(lat, lon, past_days=11, forecast_days=12)
    weather = [w for w in weather if lo <= w["time"][:10] <= hi]
except Exception:
    weather = []
    st.warning("날씨 정보를 가져오지 못했습니다. 물때만 표시합니다.")

data = {"port": port.split(" (")[0], "today": now.strftime("%Y-%m-%d"), "days": days, "weather": weather}
html = (HERE / "dial_view.html").read_text(encoding="utf-8").replace(
    "/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
components.html(html, height=1640, scrolling=True)

st.caption(f"물때: [바다타임](https://www.badatime.com/{pid}.html) · 날씨/수온: [Open-Meteo](https://open-meteo.com) · "
           f"{now:%m-%d %H:%M} 기준")
