"""COOL — 낚시 도구 모음, 개인 버전 메뉴 (플레이스토어 버전은 store/ 폴더, Streamlit을 쓰지 않음)

각 프로그램은 자기 폴더에 있습니다.
- personal/sunsang24/  선상낚시 예약조회 (선상24·더피싱)
- personal/lamar/      라마르호 예상 조과 분석
- personal/mulddae/    물때 시계 (dial.py)
- personal/chaebi/     갑오징어·쭈꾸미 채비 계산기 (calc.py)

Streamlit Cloud의 Main file은 계속 이 파일(streamlit_app.py)이라 앱 주소는 그대로입니다.
"""
import streamlit as st

pages = [
    st.Page("personal/sunsang24/streamlit_app.py", title="선상낚시 예약조회", icon=":material/sailing:",
            url_path="sunsang24", default=True),
    st.Page("personal/lamar/streamlit_app.py", title="라마르호 예상 조과 분석", icon=":material/set_meal:",
            url_path="lamar"),
    st.Page("personal/mulddae/dial.py", title="물때 시계", icon=":material/schedule:", url_path="mulddae-clock"),
    st.Page("personal/chaebi/calc.py", title="채비 계산기", icon=":material/straighten:", url_path="chaebi"),
]
st.navigation(pages, position="sidebar").run()
