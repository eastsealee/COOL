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
import importlib  # noqa: E402

import tide_data  # noqa: E402

# 앱이 켜진 채로 코드가 바뀌면 예전 tide_data가 메모리에 남아 있을 수 있어, 새 항목이 없으면 다시 읽음
if not all(hasattr(tide_data, n) for n in ("DEFAULT_PORT", "PORT_META", "load_days", "port_current")):
    tide_data = importlib.reload(tide_data)
from tide_data import DEFAULT_PORT, KST, PORT_META, PORTS, fetch_weather, load_days  # noqa: E402
from dial_widget import dial  # noqa: E402
import bite as bite_mod  # noqa: E402

st.set_page_config(page_title="물때 시계", layout="centered")
st.markdown("<style>.block-container{padding-top:3.6rem;padding-bottom:1rem;max-width:560px}</style>",
            unsafe_allow_html=True)

# ----- 웹 첫 화면: 앱과 같은 시작 화면(쭈꾸미·갑오징어)을 물때 시계가 그려질 때까지 덮어 둠
#  앱(MulddaeApp)은 자체 시작 화면이 있어 건너뜀. 세션당 처음 한 번만.
SPLASH = HERE.parent / "android" / "app" / "src" / "main" / "assets" / "splash.html"


@st.cache_resource(show_spinner=False)
def splash_html(stamp: float) -> str:
    import re
    t = SPLASH.read_text(encoding="utf-8")
    import base64
    svg = re.search(r"(<svg.*?</svg>)", t, re.S).group(1)
    keys = "".join(re.findall(r"@keyframes (?:bob|rise|shine|flow|fadein)\{.*?\}\}", t, re.S))
    rules = (".bob{transform-box:view-box;animation:bob 3s ease-in-out infinite}.jj{animation-duration:2.6s}"
             ".gg{animation-duration:3.3s;animation-delay:-1.1s}.bub{transform-box:fill-box;animation:rise 8s linear infinite}"
             ".ray{animation:shine 7s ease-in-out infinite}.wave{animation:flow 4s linear infinite}"
             ".title{animation:fadein .9s ease-out both}"
             "text{font-family:'Noto Sans KR','Noto Sans CJK KR','Samsung Sans','Apple SD Gothic Neo',sans-serif}")
    # 스트림릿 글상자는 svg를 지우므로, 애니메이션까지 담은 svg 그림 파일(img)로 넣음
    svg = re.sub(r"(<svg[^>]*>)", lambda m: m.group(1) + f"<style>{keys}{rules}</style>", svg, count=1)
    src = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    css = ""
    return f"""<style>{css}
#mdSplash{{position:fixed;inset:0;z-index:1000000;background:#071520;pointer-events:none;
  animation:mdOut .6s ease 25s forwards}}
#mdSplash img{{position:absolute;inset:0;width:100%;height:100%;display:block;object-fit:cover;max-width:none}}
#mdSplash .wt{{position:absolute;left:0;right:0;bottom:4%;text-align:center;color:#bfe6f2;font:500 14px 'Noto Sans KR',sans-serif;
  letter-spacing:.06em;opacity:0;animation:mdIn .6s ease 2.5s forwards}}
body:has(iframe[title*="mulddae_dial"]) #mdSplash{{animation:mdOut .6s ease 1.8s forwards}}
@keyframes mdOut{{to{{opacity:0;visibility:hidden}}}}
@keyframes mdIn{{to{{opacity:.85}}}}
</style><div id="mdSplash"><img src="{src}" alt=""><div class="wt">물때 불러오는 중…</div></div>"""


try:
    _ua = st.context.headers.get("User-Agent", "") or ""
except Exception:
    _ua = ""
if "MulddaeApp" not in _ua and not st.session_state.get("splash_done") and SPLASH.exists():
    st.session_state["splash_done"] = True
    try:
        st.markdown(splash_html(SPLASH.stat().st_mtime), unsafe_allow_html=True)
    except Exception:  # noqa: BLE001  시작 화면은 없어도 됨
        pass

# 항구: 화면 안 '항구 선택' 버튼으로 고름 (주소의 ?port= 로 기억)
names = list(PORTS)
port = st.session_state.get("dial_port") or st.query_params.get("port")
if port not in PORTS:
    port = DEFAULT_PORT if DEFAULT_PORT in PORTS else names[0]
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
    other = st.selectbox("다른 항구", names, index=names.index(port))
    if other != port:
        st.session_state["dial_port"] = other
        st.rerun()
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

# 입질 확률: 인천·경기·충남 항구에서만, 라마르호 기록으로 예상한 그날 오전·오후 조황을 함께 넘김
bite = {"on": False}
if PORT_META.get(port, ("", "", ""))[1] in bite_mod.REGIONS:
    win = sorted(k for k in days if (center - timedelta(days=11)).strftime("%Y-%m-%d") <= k
                 <= (center + timedelta(days=11)).strftime("%Y-%m-%d"))
    try:
        with st.spinner("라마르호 기록으로 예상 조황 계산 중…"):
            bite = {"on": True, "pred": bite_mod.predictions(win)}
    except Exception:  # noqa: BLE001  예상 계산이 안 되면 보정 없이 모델만
        bite = {"on": True, "pred": {}}

try:
    cur_fc = tide_data.port_current(lat, lon, sorted(days)) if hasattr(tide_data, "port_current") else None
except Exception:  # noqa: BLE001
    cur_fc = None
# 브이월드(국토교통부) 지도 인증키: Streamlit Secrets의 VWORLD_KEY, 없으면 data/vworld_key.txt (없으면 OpenStreetMap)
def _vworld_key() -> str:
    try:
        k = str(st.secrets.get("VWORLD_KEY", "") or "").strip()
    except Exception:  # noqa: BLE001  secrets 파일이 없을 때
        k = ""
    f = HERE / "data" / "vworld_key.txt"
    if not k and f.exists():
        k = f.read_text(encoding="utf-8").strip()
    return k


data = {"vworld": _vworld_key(), "cur": cur_fc, "bite": bite, "port": port.split(" (")[0], "portFull": port, "ports": [[k, *PORT_META.get(k, ("", "", "")), round(PORTS[k][1], 4), round(PORTS[k][2], 4)] for k in names], "today": today, "center": center_s, "days": days, "weather": weather}
val = dial(data=data, key="dial", default=None)

# 화면에서 범위 밖 날짜를 골랐으면 그 날짜를 기준으로 다시 불러옴
if isinstance(val, dict) and val.get("n") != st.session_state.get("dial_n"):
    st.session_state["dial_n"] = val.get("n")
    if val.get("goto") == "chaebi":                     # 오늘 카드 '쭈갑 채비계산' → 채비 계산기
        st.session_state["dial_center"] = str(val.get("date", ""))[:10] or center_s
        st.session_state["back_to_mulddae"] = True
        _pi = PORTS.get(port) or (0, None, None)          # 그 항구 근처 조류예보점을 고르도록 위치·날짜를 넘김
        st.session_state["chaebi_ctx"] = {"date": st.session_state["dial_center"], "port": port.split(" (")[0],
                                          "lat": _pi[1], "lon": _pi[2]}
        st.switch_page("chaebi/calc.py")
    if val.get("goto") == "lamar":                      # 8시 방향 '라마르 예상분석' → 보던 날짜로 라마르호 예상 조과 분석
        st.session_state["dial_center"] = str(val.get("date", ""))[:10] or center_s   # 돌아오면 그 날짜로
        st.session_state["lamar_from_mulddae"] = st.session_state["dial_center"]
        st.session_state["back_to_mulddae"] = True        # 라마르 맨 위에 '물때 시계로 돌아가기' 표시
        st.switch_page("lamar/streamlit_app.py")
    if val.get("goto") == "sunsang24":                  # 2시 방향 '예약조회' → 보던 날짜·지역으로 예약조회 열기
        area, sido, sgg = PORT_META.get(port, ("서해", "", ""))
        st.session_state["jump_from_mulddae"] = {"date": str(val.get("date", ""))[:10], "sea": area, "sido": sido,
                                                 "sgg": sgg, "port": port.split(" (")[0]}
        st.session_state["dial_center"] = st.session_state["jump_from_mulddae"]["date"] or center_s   # 돌아오면 그 날짜로
        st.session_state["back_to_mulddae"] = True        # 예약조회 맨 위에 '물때 시계로 돌아가기' 표시
        st.switch_page("sunsang24/streamlit_app.py")
    if val.get("port") in PORTS and val["port"] != port:
        st.session_state["dial_port"] = val["port"]
        st.query_params["port"] = val["port"]
        st.rerun()
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
