"""COOL — 낚시 도구 모음 (메뉴만 담당)

각 프로그램은 자기 폴더에 있습니다.
- sunsang24/  선상낚시 예약조회 (선상24·더피싱)
- lamar/      라마르호 예상 조과 분석
- mulddae/    물때 시계 (dial.py)
- chaebi/     갑오징어·쭈꾸미 채비 계산기 (calc.py)

Streamlit Cloud의 Main file은 계속 이 파일(streamlit_app.py)이라 앱 주소는 그대로입니다.
"""
import streamlit as st

pages = [
    st.Page("sunsang24/streamlit_app.py", title="선상낚시 예약조회", icon=":material/sailing:",
            url_path="sunsang24", default=True),
    st.Page("lamar/streamlit_app.py", title="라마르호 예상 조과 분석", icon=":material/set_meal:",
            url_path="lamar"),
    st.Page("mulddae/dial.py", title="물때 시계", icon=":material/schedule:", url_path="mulddae-clock"),
    st.Page("chaebi/calc.py", title="채비 계산기", icon=":material/straighten:", url_path="chaebi"),
]
st.navigation(pages, position="sidebar").run()
