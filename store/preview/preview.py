"""플레이스토어 버전 미리보기 — store/web 화면을 그대로 띄움 (앱에 들어갈 화면과 같은 파일)"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from store_widget import store_web  # noqa: E402

st.markdown("<style>.block-container{padding-top:3.2rem;padding-bottom:0;max-width:560px}</style>", unsafe_allow_html=True)
store_web(key="store_web", default=None)
