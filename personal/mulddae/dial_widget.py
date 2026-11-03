"""물때 시계 원형 화면 컴포넌트 등록 (메뉴 페이지 안에서는 등록할 수 없어 별도 모듈로 둠)"""
from pathlib import Path

import streamlit.components.v1 as components

dial = components.declare_component("mulddae_dial", path=str(Path(__file__).parent / "dial_component"))
