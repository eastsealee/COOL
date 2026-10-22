"""갑오징어·쭈꾸미 채비 계산기 — 선속·조류·봉돌·원줄로 가짓줄 길이와 봉돌 단차 추천

- 계산과 GPS는 모두 휴대폰 안(rig_component)에서 돌아감: 배 위에서 GPS가 1초마다 바뀌어도 바로 다시 계산
- 계산 모델: rig_component/model.js (궁디피싱 채비 과학 영상 3편의 방식·수치로 보정)
- 나중에 쭈갑물때(물때 시계)에 합칠 때: rig(data={"cur": 그날 조류 노트}) 처럼 조류값만 넘기면 화면이 받아 씀
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from rig_widget import rig  # noqa: E402

st.set_page_config(page_title="채비 계산기", layout="centered")
st.markdown("<style>.block-container{padding-top:3.6rem;padding-bottom:1rem;max-width:560px}</style>",
            unsafe_allow_html=True)

rig(data={}, key="rig", default=None)

st.caption("계산 근거: 궁디피싱 채비 과학 영상(채비 3D 시뮬레이션 · 1,340마리 조과 분석 · 55명 채비 분석). "
           "정적 모델이라 정확한 값이 아니라 경향을 보는 용도입니다.")
