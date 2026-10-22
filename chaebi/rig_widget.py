"""채비 계산기 화면 컴포넌트 등록 (메뉴 페이지 안에서는 등록할 수 없어 별도 모듈로 둠)"""
from pathlib import Path

import streamlit.components.v1 as components

rig = components.declare_component("chaebi_rig", path=str(Path(__file__).parent / "rig_component"))
