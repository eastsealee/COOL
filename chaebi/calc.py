"""갑오징어·쭈꾸미 채비 계산기 — 선속·조류·봉돌·원줄로 가짓줄 길이와 봉돌 단차 추천

- 계산과 GPS는 모두 휴대폰 안(rig_component)에서 돌아감: 배 위에서 GPS가 1초마다 바뀌어도 바로 다시 계산
- 계산 모델: rig_component/model.js (궁디피싱 채비 과학 영상 3편의 방식·수치로 보정)
- 나중에 쭈갑물때(물때 시계)에 합칠 때: rig(data={"cur": 그날 조류 노트}) 처럼 조류값만 넘기면 화면이 받아 씀
"""
import datetime as dt
import gzip
import json
import sys
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from rig_widget import rig  # noqa: E402

st.set_page_config(page_title="채비 계산기", layout="centered")
st.markdown("<style>.block-container{padding-top:3.6rem;padding-bottom:1rem;max-width:560px}</style>",
            unsafe_allow_html=True)

# ----- 맨 위에 '쭈갑과물때로 돌아가기' (웹·앱 모두 항상 표시)
try:
    _in_app = "MulddaeApp" in (st.context.headers.get("User-Agent", "") or "")
except Exception:
    _in_app = False
if True:                                                # 웹에서 메뉴로 들어와도 항상 돌아갈 수 있게
    st.markdown("""<style>
    .st-key-back_mulddae_rig button{border:2px solid #bff1ff !important;border-radius:999px !important;padding:0.55rem 1.4rem !important;
      background:linear-gradient(100deg,#0b5f7f 0%,#14a3cf 30%,#bff1ff 50%,#14a3cf 70%,#0b5f7f 100%) !important;
      background-size:250% 100% !important;color:#fff !important;
      animation:rShine 2.2s linear infinite, rPulse 1.1s ease-in-out infinite, rRing 1.6s ease-out infinite}
    .st-key-back_mulddae_rig button p{font-size:1.05rem !important;font-weight:800 !important;color:#fff !important;
      text-shadow:0 1px 3px rgba(0,40,60,.8)}
    @keyframes rShine{0%{background-position:100% 0}100%{background-position:-150% 0}}
    @keyframes rPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
    @keyframes rRing{0%{box-shadow:0 0 0 0 rgba(76,195,230,.75)}100%{box-shadow:0 0 0 16px rgba(76,195,230,0)}}
    @media (prefers-reduced-motion:reduce){.st-key-back_mulddae_rig button{animation:none}}
    </style>""", unsafe_allow_html=True)
    if st.button("← 쭈갑과물때로 돌아가기", key="back_mulddae_rig"):
        st.session_state.pop("back_to_mulddae", None)
        st.switch_page("mulddae/dial.py")



# ----- 해양조사원 조류예보(전국 예보점, 30분 간격) — '조류예보 받기' Actions가 매일 currents 브랜치에 올림
CUR_URL = "https://raw.githubusercontent.com/eastsealee/COOL/currents/currents.json.gz"


@st.cache_data(ttl=3600, show_spinner=False)
def load_currents():
    try:
        r = requests.get(CUR_URL, timeout=20)
        r.raise_for_status()
        return json.loads(gzip.decompress(r.content))
    except Exception:  # noqa: BLE001
        return None


def curdb_for(dates):
    """화면에 넘길 만큼만: 예보점 위치 + 고른 날짜(앞뒤 하루 포함)의 유속·유향"""
    db = load_currents()
    if not db:
        return None
    want = set()
    for d in dates:
        for k in (-1, 0, 1):
            want.add((dt.date.fromisoformat(d) + dt.timedelta(days=k)).isoformat())
    want &= set(db.get("days", []))
    return {"updated": db.get("updated"), "dirs": db.get("dirs"), "st": db.get("st", {}),
            "sp": {c: {d: v[d] for d in want if d in v} for c, v in db.get("sp", {}).items()},
            "dr": {c: {d: v[d] for d in want if d in v} for c, v in db.get("dr", {}).items()}}


KST = dt.timezone(dt.timedelta(hours=9))
today = dt.datetime.now(KST).date().isoformat()
ctx = st.session_state.get("chaebi_ctx") or {}
if not st.session_state.get("back_to_mulddae"):        # 물때 시계에서 온 게 아니면 오늘·GPS 기준
    ctx = {}
day = ctx.get("date") or today
rig(data={"curdb": curdb_for(sorted({day, today})), "today": today, "day": day,
          "loc": {"lat": ctx["lat"], "lon": ctx["lon"], "name": ctx.get("port", "")} if ctx.get("lat") else None},
    key="rig", default=None)
