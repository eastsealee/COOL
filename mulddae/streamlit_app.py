"""물때 — '물때와 날씨' 스타일 물때·날씨·바람/파고 조회 (Streamlit)
데이터 수집·조류세기 계산은 tide_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from tide_data import KST, PORTS, add_flow, fetch_month, fetch_weather  # noqa: E402

# ---------------------------------------------------------------- 화면
st.set_page_config(page_title="물때", layout="centered")
st.markdown(
    "<style>.block-container{padding-top:1.2rem;padding-bottom:1rem;max-width:560px}</style>",
    unsafe_allow_html=True,
)

names = list(PORTS)
q = st.query_params.get("port")
default = names.index(q) if q in names else 0
port = st.selectbox("포인트", names, index=default, help="입력해서 검색할 수 있습니다")
st.query_params["port"] = port
pid, lat, lon = PORTS[port]

with st.expander("목록에 없는 포인트"):
    st.caption("badatime.com에서 원하는 항구 페이지를 열면 주소의 숫자가 ID입니다 (예: badatime.com/**356**.html). 날씨는 위에서 고른 포인트 기준으로 표시됩니다.")
    c1, c2 = st.columns([1, 2])
    custom_id = c1.number_input("바다타임 ID", min_value=0, step=1, value=0)
    custom_name = c2.text_input("표시 이름", value="")
    if custom_id:
        pid = int(custom_id)
        port = custom_name or f"포인트 {pid}"

now = datetime.now(KST)
months = []
for delta in (-1, 0, 1):
    y, m = now.year, now.month + delta
    if m == 0:
        y, m = y - 1, 12
    elif m == 13:
        y, m = y + 1, 1
    months.append((y, m))

days: dict[str, dict] = {}
errors = []
with st.spinner("물때 불러오는 중…"):
    for y, m in months:
        try:
            days.update(fetch_month(pid, y, m))
        except Exception as e:  # 한 달이 실패해도 나머지는 보여준다
            errors.append(f"{y}년 {m}월: {e}")

if not days:
    st.error("물때 자료를 가져오지 못했습니다. 잠시 후 새로고침하거나 다른 포인트를 골라 보세요.")
    if errors:
        st.caption(" / ".join(errors))
    st.stop()

add_flow(days, pid)

try:
    weather = fetch_weather(lat, lon)
except Exception:
    weather = []
    st.warning("날씨 정보를 가져오지 못했습니다. 물때만 표시합니다.")

data = {
    "port": port.split(" (")[0],
    "today": now.strftime("%Y-%m-%d"),
    "days": days,
    "weather": weather,
}
html = (HERE / "tide_view.html").read_text(encoding="utf-8")
html = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
components.html(html, height=870, scrolling=False)

st.caption(
    f"물때: [바다타임](https://www.badatime.com/{pid}.html) · 날씨/파고: [Open-Meteo](https://open-meteo.com) · "
    f"조류세기는 선상낚시 예약조회와 같은 계산(▲▼ 변화량 평균) · {now:%m-%d %H:%M} 기준"
)
