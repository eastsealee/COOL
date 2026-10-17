"""라마르호 조과 분위기 조회 (2018~2026년 9~12월)
실행: streamlit run app.py
"""
import json
import datetime as dt
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from korean_lunar_calendar import KoreanLunarCalendar

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lamar_tide as tidemod

st.set_page_config(page_title="라마르호 조과 분위기 조회", page_icon="🦑", layout="wide")

BASE = Path(__file__).resolve().parent.parent  # 저장소 최상위
MUL_ORDER = ["1물", "2물", "3물", "4물", "5물", "6물", "7물", "8물", "9물",
             "10물", "11물", "12물", "13물", "조금", "무시"]
TIDE_CYCLE = ["7물", "8물", "9물", "10물", "11물", "12물", "13물", "조금", "무시",
              "1물", "2물", "3물", "4물", "5물", "6물"]
WD = "월화수목금토일"


# ------------------------------------------------------------ 데이터
@st.cache_data
def load_days():
    rows = json.loads((BASE / "data" / "lamar_days.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["날짜"] = pd.to_datetime(df["date"]).dt.date
    df["연도"] = pd.to_datetime(df["date"]).dt.year
    df["월"] = pd.to_datetime(df["date"]).dt.month
    df["날씨"] = df["tags"].apply(lambda t: ", ".join(t))
    return df


def lunar_mul(d: dt.date):
    c = KoreanLunarCalendar()
    c.setSolarDate(d.year, d.month, d.day)
    return f"{c.lunarMonth}/{c.lunarDay}", TIDE_CYCLE[(c.lunarDay - 1) % 15]


def score_color(v):
    if v is None:
        return "gray"
    return "green" if v >= 70 else ("orange" if v >= 45 else "red")


@st.cache_data(show_spinner="조석 계산 중…")
def tide_table(dates: tuple, st_key: str, _station):
    out = {}
    for d in dates:
        rng, ev = tidemod.day_range(d, _station)
        hi = " / ".join(t.strftime("%H:%M") for k, t, h in ev if k == "만조")
        lo = " / ".join(t.strftime("%H:%M") for k, t, h in ev if k == "간조")
        out[d] = (round(rng) if rng is not None else None, hi, lo)
    return out


df = load_days()

# ------------------------------------------------------------ 사이드바: 조화상수
st.sidebar.header("🌊 조석 설정")
station = None
up = st.sidebar.file_uploader("조화상수 CSV (국립해양조사원)", type=["csv"],
                              help="공공데이터포털 '기준항 조화상수' CSV를 올리면 만조·간조·고저차가 계산됩니다.")
raw = up.getvalue() if up else None
bundled = BASE / "data" / "lamar_tide_constants.csv"
if raw is None and bundled.exists():
    raw = bundled.read_bytes()
if raw:
    try:
        stations = tidemod.load_constants(raw)
        near, km = tidemod.nearest(stations)
        names = [s["name"] for s in stations]
        default = names.index(near["name"]) if near else 0
        pick = st.sidebar.selectbox("관측소", names, index=default,
                                    help="기본값은 남당항에서 가장 가까운 관측소입니다.")
        station = stations[names.index(pick)]
        if near and pick == near["name"]:
            st.sidebar.caption(f"남당항에서 약 {km:.0f} km")
    except Exception as e:
        st.sidebar.error(f"CSV를 읽지 못했어요: {e}")
else:
    st.sidebar.info("조화상수 CSV를 올리면 만조·간조 시각과 고저차가 함께 표시됩니다.")
    st.sidebar.markdown("[CSV 받기 (공공데이터포털)](https://www.data.go.kr/data/15145395/fileData.do)")

st_key = f"{station['name']}{station['C']}" if station else ""
tides = tide_table(tuple(df["날짜"]), st_key, station) if station else {}
if station:
    df["고저차(cm)"] = df["날짜"].map(lambda d: tides[d][0])
    df["만조"] = df["날짜"].map(lambda d: tides[d][1])
    df["간조"] = df["날짜"].map(lambda d: tides[d][2])

# ------------------------------------------------------------ 본문
st.title("🦑 라마르호 조과 분위기 조회")
st.caption(f"남당항 라마르호 '오늘의 조과' {len(df)}일 · 2018~2026년 9~12월 · 블로그 본문 분석")

tab1, tab2, tab3, tab4 = st.tabs(["📅 날짜별 조회", "📋 전체 목록", "📊 물때·시기 분석", "ℹ️ 산출 방식"])


def tide_block(d: dt.date):
    if not station:
        st.caption("조석: 왼쪽에서 조화상수 CSV를 올리면 표시됩니다.")
        return
    rng, ev = tidemod.day_range(d, station)
    c1, c2, c3 = st.columns(3)
    c1.metric("고저차", f"{rng:.0f} cm" if rng else "-")
    c2.metric("만조", " / ".join(t.strftime("%H:%M") for k, t, h in ev if k == "만조") or "-")
    c3.metric("간조", " / ".join(t.strftime("%H:%M") for k, t, h in ev if k == "간조") or "-")
    curve = pd.DataFrame(tidemod.day_curve(d, station), columns=["시각", "조위(cm)"])
    pts = pd.DataFrame([(t, h, k) for k, t, h in ev], columns=["시각", "조위(cm)", "구분"])
    line = alt.Chart(curve).mark_line(color="#2b7bb9").encode(
        x=alt.X("시각:T", axis=alt.Axis(format="%H:%M", title=None)),
        y=alt.Y("조위(cm):Q"))
    dots = alt.Chart(pts).mark_point(filled=True, size=70).encode(
        x="시각:T", y="조위(cm):Q", color=alt.Color("구분:N", scale=alt.Scale(
            domain=["만조", "간조"], range=["#d9480f", "#1c7ed6"])),
        tooltip=[alt.Tooltip("시각:T", format="%H:%M"), "구분", alt.Tooltip("조위(cm):Q", format=".0f")])
    st.altair_chart((line + dots).properties(height=220), width="stretch")
    st.caption(f"관측소: {station['name']} · 4대 분조 추산(시각 ±30분 오차 가능)")


def history_hint(d: dt.date, mul: str):
    same = df[(df["mul"] == mul) & (df["월"] == d.month)]
    allm = df[df["mul"] == mul]
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{d.month}월 · {mul} 과거 평균 분위기",
              f"{same['score'].mean():.0f}%" if len(same) else "-", help=f"표본 {len(same)}일")
    c2.metric(f"{mul} 전체 평균 분위기", f"{allm['score'].mean():.0f}%", help=f"표본 {len(allm)}일")
    jj = same["jj_med"].dropna()
    c3.metric(f"{d.month}월 · {mul} 주꾸미 중앙값 평균", f"{jj.mean():.0f}마리" if len(jj) else "-",
              help=f"마릿수 기록 있는 {len(jj)}일")


# ---------------- 탭1: 날짜별 조회
with tab1:
    dates = sorted(df["날짜"])
    left, right = st.columns([1, 2])
    with left:
        sel = st.date_input("날짜 선택", value=dates[-1], min_value=dt.date(2018, 1, 1),
                            max_value=dt.date(2030, 12, 31), format="YYYY-MM-DD")
        lunar, mul = lunar_mul(sel)
        st.markdown(f"**{sel:%Y-%m-%d} ({WD[sel.weekday()]})** · 음력 {lunar} · **{mul}**")
        hit = df[df["날짜"] == sel]
        if hit.empty:
            st.info("이 날짜는 조과 기록이 없어요. 같은 물때의 과거 기록으로 참고 정보를 보여드려요.")
            near = df.iloc[(pd.to_datetime(df["date"]) - pd.Timestamp(sel)).abs().argsort()[:5]]
            st.markdown("**가까운 기록일**")
            for _, r in near.sort_values("date").iterrows():
                st.markdown(f"- {r['date']} ({r['wd']}) · {r['mul']} · **{r['score']}%**")
    with right:
        if not hit.empty:
            r = hit.iloc[0]
            st.subheader(r["title"])
            st.markdown(f"[블로그 원문 보기]({r['link']})")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("분위기", f"{r['score']}%")
            c2.metric("조과 백분위", f"{r['catch_pct']:.0f}%" if pd.notna(r["catch_pct"]) else "-",
                      help="같은 달 다른 출조일과 비교한 주꾸미 중앙값 순위")
            c3.metric("본문 분위기", f"{r['sent']}%")
            c4.metric("날씨 점수", f"{r['weather']}%")
            st.progress(int(r["score"]) / 100)
            if r["stats"]:
                st.markdown(f"**조과** · {r['stats']}")
            if r["tags"]:
                st.markdown("**날씨·바다** · " + " ".join(f"`{t}`" for t in r["tags"]))
            if r["key"]:
                st.markdown("**그날 분위기 (본문 발췌)**")
                for s in r["key"]:
                    st.markdown(f"> {s}")
            st.caption(f"산출 근거: {r['basis']}")
        else:
            history_hint(sel, mul)
        st.divider()
        tide_block(sel)

# ---------------- 탭2: 전체 목록
with tab2:
    f1, f2, f3, f4 = st.columns(4)
    years = f1.multiselect("연도", sorted(df["연도"].unique()), default=sorted(df["연도"].unique()))
    months = f2.multiselect("월", [9, 10, 11, 12], default=[9, 10, 11, 12])
    muls = f3.multiselect("물때", MUL_ORDER, default=MUL_ORDER)
    lo, hi = f4.slider("분위기 %", 0, 100, (0, 100))
    alltags = sorted({t for ts in df["tags"] for t in ts})
    tagsel = st.multiselect("날씨·바다 조건 포함 (선택 시 해당 조건이 있는 날만)", alltags)
    q = st.text_input("제목 검색", "")
    v = df[df["연도"].isin(years) & df["월"].isin(months) & df["mul"].isin(muls)
           & df["score"].between(lo, hi)]
    if tagsel:
        v = v[v["tags"].apply(lambda ts: all(t in ts for t in tagsel))]
    if q:
        v = v[v["title"].str.contains(q, case=False, na=False)]
    cols = ["date", "wd", "mul", "lunar", "score", "title", "jj_med", "jj_max", "gg_max", "날씨"]
    if station:
        cols[4:4] = ["고저차(cm)", "만조", "간조"]
    cols.append("link")
    show = v[cols].rename(columns={"date": "날짜", "wd": "요일", "mul": "물때", "lunar": "음력",
                                   "score": "분위기", "title": "제목", "jj_med": "주꾸미 중앙값",
                                   "jj_max": "주꾸미 최고", "gg_max": "갑오징어 최고", "link": "링크"})
    st.caption(f"{len(show)}일 · 평균 분위기 {show['분위기'].mean():.0f}%" if len(show) else "해당 없음")
    st.dataframe(show.sort_values("날짜", ascending=False), hide_index=True, width="stretch",
                 height=560, column_config={
                     "분위기": st.column_config.ProgressColumn("분위기", format="%d%%", min_value=0, max_value=100),
                     "링크": st.column_config.LinkColumn("링크", display_text="원문"),
                     "제목": st.column_config.TextColumn("제목", width="large")})
    st.download_button("CSV 다운로드", show.to_csv(index=False).encode("utf-8-sig"),
                       "lamar_분위기_목록.csv", "text/csv")

# ---------------- 탭3: 분석
with tab3:
    m = df.groupby("mul").agg(분위기=("score", "mean"), 일수=("score", "size"),
                              주꾸미=("jj_med", "mean")).reindex(MUL_ORDER).reset_index()
    m["분위기"] = m["분위기"].round(1)
    st.subheader("물때별 평균 분위기")
    st.altair_chart(alt.Chart(m).mark_bar(color="#2b7bb9").encode(
        x=alt.X("mul:N", sort=MUL_ORDER, title="물때"),
        y=alt.Y("분위기:Q", title="평균 분위기 %", scale=alt.Scale(domain=[0, 100])),
        tooltip=["mul", "분위기", "일수", alt.Tooltip("주꾸미:Q", format=".0f")]
    ).properties(height=280), width="stretch")
    best = m.sort_values("분위기", ascending=False).head(3)["mul"].tolist()
    st.caption(f"분위기가 가장 좋았던 물때: {', '.join(best)}")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("월별")
        mm = df.groupby("월").agg(분위기=("score", "mean"), 주꾸미=("jj_med", "mean"),
                                 일수=("score", "size")).reset_index()
        st.altair_chart(alt.Chart(mm).mark_bar(color="#5c940d").encode(
            x="월:O", y=alt.Y("주꾸미:Q", title="주꾸미 중앙값 평균(마리)"),
            tooltip=["월", alt.Tooltip("분위기:Q", format=".0f"), alt.Tooltip("주꾸미:Q", format=".0f"), "일수"]
        ).properties(height=240), width="stretch")
    with c2:
        st.subheader("연도별")
        yy = df.groupby("연도").agg(분위기=("score", "mean"), 일수=("score", "size")).reset_index()
        st.altair_chart(alt.Chart(yy).mark_line(point=True, color="#e8590c").encode(
            x="연도:O", y=alt.Y("분위기:Q", scale=alt.Scale(domain=[0, 100])),
            tooltip=["연도", alt.Tooltip("분위기:Q", format=".0f"), "일수"]
        ).properties(height=240), width="stretch")

    if station:
        st.subheader("고저차와 분위기")
        t = df.dropna(subset=["고저차(cm)"]).copy()
        t["고저차 구간"] = pd.cut(t["고저차(cm)"], bins=6).astype(str)
        g = t.groupby("고저차 구간", sort=False).agg(분위기=("score", "mean"), 일수=("score", "size")).reset_index()
        cc1, cc2 = st.columns(2)
        cc1.altair_chart(alt.Chart(t).mark_circle(opacity=0.5).encode(
            x=alt.X("고저차(cm):Q"), y=alt.Y("score:Q", title="분위기 %"),
            tooltip=["date", "mul", "고저차(cm)", "score", "title"]).properties(height=260),
            width="stretch")
        cc2.dataframe(g.round(1), hide_index=True, width="stretch")
    else:
        st.info("조화상수 CSV를 올리면 고저차와 분위기의 관계도 분석됩니다.")

# ---------------- 탭4: 산출 방식
with tab4:
    st.markdown("""
**분위기 %** (0~100)
- **조과 50%**: 본문의 손님별 마릿수("○○님은 주꾸미 127마리…")에서 그날 주꾸미 중앙값을 구하고,
  **같은 달** 다른 해 출조일과 비교한 백분위. (손님 3명 이상 기록된 날만)
- **본문 분위기 35%**: "잘 나와, 폭발, 손맛, 꾸준히" 같은 긍정 표현과 "안 나와, 고전, 뜸, 아쉬" 같은 부정 표현의 비율. 제목은 2배 가중.
- **날씨 15%**: 강풍·파도·비·안개·물색 탁함 언급은 감점, 잔잔·화창은 가점.
- 마릿수 기록이 없는 날은 본문 75% + 날씨 25%, 본문이 비어 있는 2018년 일부는 제목만으로 산출.

**물때**: 음력 날짜 기준 서해 7물때식(음력 1일=7물, 8일=조금, 9일=무시, 10일=1물).

**조석·고저차**: 국립해양조사원 기준항 조화상수의 4대 분조(M2·S2·K1·O1) 추산.
시각 ±30분, 높이 수십 cm 오차가 있을 수 있어 실제 출조 판단은 바다타임·국립해양조사원 예보를 함께 보세요.

**본문 발췌**: 날씨·물때·활성도 관련 문장을 자동으로 골랐습니다. 전체 내용은 원문 링크에서 확인하세요.
""")
