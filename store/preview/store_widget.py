"""플레이스토어 버전 화면(store/web)을 개인 웹 메뉴 안에서 그대로 미리 보기 위한 등록 (화면 파일은 수정 없이 그대로 씀)"""
from pathlib import Path

import streamlit.components.v1 as components

store_web = components.declare_component("store_web", path=str(Path(__file__).resolve().parent.parent / "web"))
