"""라마르호 조과 분위기 조회 (2018~2026년 9~12월)
물때·만조·간조·고저차·물세기(%)는 예약조회 앱과 같은 바다타임 남당항 물때표 기준.
"""
import json
import math
import sys
import datetime as dt
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from korean_lunar_calendar import KoreanLunarCalendar

BASE = Path(__file__).resolve().parent.parent  # 저장소 최상위
sys.path.insert(0, str(BASE))
import lamar_badatime as bt  # noqa: E402
import lamar_tide as hm      # noqa: E402  (바다타임 조회가 안 될 때 쓰는 조화상수 계산)

st.set_page_config(page_title="라마르호 조과 분위기 조회", page_icon="🦑", layout="wide")

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


@st.cache_data(ttl=None, show_spinner="바다타임 남당항 물때표 불러오는 중… (처음 한 번만 걸려요)")
def badatime_days(ym_list: tuple, _ver=1):
    days, errs = bt.fetch_many(list(ym_list))
    return {d.isoformat(): v for d, v in days.items()}, errs


def tide_info(d: dt.date):
    """그날 물때·물세기·만조·간조·고저차 dict (바다타임 우선, 없으면 조화상수 추산)"""
    v = BT.get(d.isoformat())
    if v:
        return {"src": "바다타임", "mul": v["mul"], "pct": v.get("pct"), "range": v["range"],
                "hi": [(t, h) for k, t, h in v["events"] if k == "만조"],
                "lo": [(t, h) for k, t, h in v["events"] if k == "간조"],
                "events": [(k, t, h) for k, t, h in v["events"]]}
    if HM_STATION:
        rng, ev = hm.day_range(d, HM_STATION)
        return {"src": f"조화상수 추산({HM_STATION['name']})", "mul": lunar_mul(d)[1], "pct": None,
                "range": round(rng) if rng else None,
                "hi": [(t.strftime("%H:%M"), round(h)) for k, t, h in ev if k == "만조"],
                "lo": [(t.strftime("%H:%M"), round(h)) for k, t, h in ev if k == "간조"],
                "events": [(k, t.strftime("%H:%M"), round(h)) for k, t, h in ev]}
    return None


def fmt_ev(lst):
    return " / ".join(f"{t}({h})" for t, h in lst) if lst else ""


def curve_from_events(d: dt.date, events):
    """만조·간조 점을 코사인 곡선으로 이어 24시간 조위 그래프용 점 생성"""
    pts = sorted((dt.datetime.combine(d, dt.time.fromisoformat(t if len(t) == 5 else "0" + t)), h)
                 for _, t, h in events)
    out = []
    for (t1, h1), (t2, h2) in zip(pts, pts[1:]):
        for i in range(20):
            f = i / 20
            out.append((t1 + (t2 - t1) * f, h1 + (h2 - h1) * (1 - math.cos(math.pi * f)) / 2))
    if pts:
        out.append(pts[-1])
    return out


df = load_days()

# ------------------------------------------------------------ 물때표 불러오기
need = tuple(bt.months_for(sorted(set(df["날짜"]))))
try:
    BT, BT_ERRS = badatime_days(need)
except Exception as ex:
    BT, BT_ERRS = {}, [str(ex)]
BT = dict(BT)  # 캐시 원본을 건드리지 않도록 복사

st.sidebar.header("🌊 물때·조석")
st.sidebar.caption(f"바다타임 {bt.PORT_NAME} 물때표 · {len(BT)}일 확보")
if BT_ERRS:
    with st.sidebar.expander(f"못 읽은 달 {len(BT_ERRS)}개"):
        st.write("\n".join(f"- {e}" for e in BT_ERRS[:40]))
if st.sidebar.button("물때표 다시 불러오기"):
    badatime_days.clear()
    st.rerun()

HM_STATION = None
with st.sidebar.expander("바다타임 조회가 안 될 때 (조화상수 CSV)"):
    up = st.file_uploader("국립해양조사원 기준항 조화상수 CSV", type=["csv"])
    raw = up.getvalue() if up else None
    bundled = BASE / "data" / "lamar_tide_constants.csv"
    if raw is None and bundled.exists():
        raw = bundled.read_bytes()
    if raw:
        try:
            stations = hm.load_constants(raw)
            HM_STATION, km = hm.nearest(stations)
            st.caption(f"{HM_STATION['name']} (남당항에서 약 {km:.0f} km) 기준으로 빈 날을 채웁니다.")
        except Exception as e:
            st.error(f"CSV를 읽지 못했어요: {e}")

# 날짜별 물때 정보를 목록에 붙이기 (바다타임 물때가 있으면 그것을 씀)
infos = {d: tide_info(d) for d in df["날짜"]}
df["mul"] = [(infos[d] or {}).get("mul") or m for d, m in zip(df["날짜"], df["mul"])]
df["물세기(%)"] = [(infos[d] or {}).get("pct") for d in df["날짜"]]
df["만조"] = [fmt_ev((infos[d] or {}).get("hi")) for d in df["날짜"]]
df["간조"] = [fmt_ev((infos[d] or {}).get("lo")) for d in df["날짜"]]
df["고저차(cm)"] = [(infos[d] or {}).get("range") for d in df["날짜"]]

# ------------------------------------------------------------ 본문
st.title("🦑 라마르호 조과 분위기 조회")
st.caption(f"남당항 라마르호 '오늘의 조과' {len(df)}일 · 2018~2026년 9~12월 · 블로그 본문 분석 · "
           f"물때·조석·물세기는 바다타임 {bt.PORT_NAME} 기준")

tab1, tab2, tab3, tab4 = st.tabs(["📅 날짜별 조회", "📋 전체 목록", "📊 물때·시기 분석", "ℹ️ 산출 방식"])


def tide_block(d: dt.date):
    info = tide_info(d)
    if not info:
        st.caption("이 날짜의 물때표를 불러오지 못했어요.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("물세기", f"{info['pct']}%" if info["pct"] is not None else "-")
    c2.metric("고저차", f"{info['range']} cm" if info["range"] else "-")
    c3.metric("만조", " / ".join(t for t, _ in info["hi"]) or "-")
    c4.metric("간조", " / ".join(t for t, _ in info["lo"]) or "-")
    if info["pct"] is not None:
        st.progress(info["pct"] / 100, text=f"물세기 {info['pct']}%")
    curve = pd.DataFrame(curve_from_events(d, info["events"]), columns=["시각", "조위(cm)"])
    pts = pd.DataFrame([(dt.datetime.combine(d, dt.time.fromisoformat(t if len(t) == 5 else "0" + t)), h, k)
                        for k, t, h in info["events"]], columns=["시각", "조위(cm)", "구분"])
    if len(curve) > 1:
        line = alt.Chart(curve).mark_line(color="#2b7bb9").encode(
            x=alt.X("시각:T", axis=alt.Axis(format="%H:%M", title=None)), y=alt.Y("조위(cm):Q"))
        dots = alt.Chart(pts).mark_point(filled=True, size=70).encode(
            x="시각:T", y="조위(cm):Q",
            color=alt.Color("구분:N", scale=alt.Scale(domain=["만조", "간조"], range=["#d9480f", "#1c7ed6"])),
            tooltip=[alt.Tooltip("시각:T", format="%H:%M"), "구분", "조위(cm)"])
        st.altair_chart((line + dots).properties(height=220), width="stretch")
    st.caption(f"출처: {info['src']} · 괄호 안은 조위(cm)")


def history_hint(d: dt.date, mul: str):
    same = df[(df["mul"] == mul) & (df["월"] == d.month)]
    allm = df[df["mul"] == mul]
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{d.month}월 · {mul} 과거 평균 분위기",
              f"{same['score'].mean():.0f}%" if len(same) else "-", help=f"표본 {len(same)}일")
    c2.metric(f"{mul} 전체 평균 분위기", f"{allm['score'].mean():.0f}%" if len(allm) else "-",
              help=f"표본 {len(allm)}일")
    jj = same["jj_med"].dropna()
    c3.metric(f"{d.month}월 · {mul} 주꾸미 중앙값 평균", f"{jj.mean():.0f}마리" if len(jj) else "-",
              help=f"마릿수 기록 있는 {len(jj)}일")


def rng_text(lo, hi, unit="마리"):
    if pd.isna(hi):
        return "-"
    return f"{int(lo)}~{int(hi)}{unit}" if not pd.isna(lo) and lo != hi else f"{int(hi)}{unit}"


# ---------------- 탭1: 날짜별 조회
with tab1:
    dates = sorted(df["날짜"])
    left, right = st.columns([1, 2])
    with left:
        sel = st.date_input("날짜 선택", value=dates[-1], min_value=dt.date(2018, 1, 1),
                            max_value=dt.date(2030, 12, 31), format="YYYY-MM-DD")
        if sel.isoformat() not in BT:  # 저장된 달 밖의 날짜(내년 등)는 그 달 물때표를 따로 받음
            try:
                BT.update(badatime_days(tuple(bt.months_for([sel])))[0])
            except Exception:
                pass
        info = tide_info(sel)
        lunar, lmul = lunar_mul(sel)
        mul = (info or {}).get("mul") or lmul
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
            c3.metric("주꾸미 (최저~최고)", rng_text(r["jj_min"], r["jj_max"]))
            c4.metric("갑오징어 (최저~최고)", rng_text(r["gg_min"], r["gg_max"]))
            st.progress(int(r["score"]) / 100, text=f"분위기 {r['score']}%")
            if r["stats"]:
                st.markdown(f"**조과** · {r['stats']}")
            if r["tags"]:
                st.markdown("**날씨·바다** · " + " ".join(f"`{t}`" for t in r["tags"]))
            if r["key"]:
                st.markdown("**그날 분위기 (본문 발췌)**")
                for s in r["key"]:
                    st.markdown(f"> {s}")
            st.caption(f"산출 근거: {r['basis']} · 본문 분위기 {r['sent']}% · 날씨 점수 {r['weather']}%")
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
    g1, g2 = st.columns([3, 1])
    alltags = sorted({t for ts in df["tags"] for t in ts})
    tagsel = g1.multiselect("날씨·바다 조건 포함 (선택 시 해당 조건이 있는 날만)", alltags)
    plo, phi = g2.slider("물세기 %", 0, 100, (0, 100))
    q = st.text_input("제목 검색", "")
    v = df[df["연도"].isin(years) & df["월"].isin(months) & df["mul"].isin(muls)
           & df["score"].between(lo, hi)]
    if (plo, phi) != (0, 100):
        v = v[v["물세기(%)"].between(plo, phi)]
    if tagsel:
        v = v[v["tags"].apply(lambda ts: all(t in ts for t in tagsel))]
    if q:
        v = v[v["title"].str.contains(q, case=False, na=False)]
    cols = ["date", "wd", "mul", "물세기(%)", "만조", "간조", "고저차(cm)", "score",
            "jj_max", "jj_min", "gg_max", "gg_min", "title", "날씨", "link"]
    show = v[cols].rename(columns={
        "date": "날짜", "wd": "요일", "mul": "물때", "score": "분위기",
        "jj_max": "주꾸미 최고", "jj_min": "주꾸미 최저", "gg_max": "갑오징어 최고", "gg_min": "갑오징어 최저",
        "title": "제목", "link": "링크"})
    st.caption(f"{len(show)}일 · 평균 분위기 {show['분위기'].mean():.0f}%" if len(show) else "해당 없음")
    st.dataframe(
        show.sort_values("날짜", ascending=False), hide_index=True, width="stretch", height=600,
        column_config={
            "분위기": st.column_config.ProgressColumn("분위기", format="%d%%", min_value=0, max_value=100),
            "물세기(%)": st.column_config.ProgressColumn("물세기", format="%d%%", min_value=0, max_value=100,
                                                      help="바다타임 남당항 물흐름 % 기준"),
            "만조": st.column_config.TextColumn("만조 시각(조위cm)"),
            "간조": st.column_config.TextColumn("간조 시각(조위cm)"),
            "주꾸미 최고": st.column_config.NumberColumn("주꾸미 최고", format="%d"),
            "주꾸미 최저": st.column_config.NumberColumn("주꾸미 최저", format="%d"),
            "갑오징어 최고": st.column_config.NumberColumn("갑오징어 최고", format="%d"),
            "갑오징어 최저": st.column_config.NumberColumn("갑오징어 최저", format="%d"),
            "링크": st.column_config.LinkColumn("링크", display_text="원문"),
            "제목": st.column_config.TextColumn("제목", width="large")})
    st.download_button("CSV 다운로드", show.to_csv(index=False).encode("utf-8-sig"),
                       "lamar_분위기_목록.csv", "text/csv")
    st.caption("주꾸미·갑오징어 최고/최저는 본문에 마릿수가 적힌 손님 기준입니다(주꾸미는 3명 이상 기록된 날만).")

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
    best = m.dropna().sort_values("분위기", ascending=False).head(3)["mul"].tolist()
    st.caption(f"분위기가 가장 좋았던 물때: {', '.join(best)}")

    t = df.dropna(subset=["물세기(%)"]).copy()
    if len(t):
        st.subheader("물세기와 분위기")
        t["물세기 구간"] = pd.cut(t["물세기(%)"], bins=[-1, 20, 40, 60, 80, 100],
                              labels=["0~20%", "21~40%", "41~60%", "61~80%", "81~100%"])
        g = t.groupby("물세기 구간", observed=False).agg(
            분위기=("score", "mean"), 주꾸미=("jj_med", "mean"), 일수=("score", "size")).reset_index()
        cc1, cc2 = st.columns([2, 1])
        cc1.altair_chart(alt.Chart(g).mark_bar(color="#0b7285").encode(
            x=alt.X("물세기 구간:N", sort=None), y=alt.Y("분위기:Q", scale=alt.Scale(domain=[0, 100]),
                                                    title="평균 분위기 %"),
            tooltip=["물세기 구간", alt.Tooltip("분위기:Q", format=".0f"),
                     alt.Tooltip("주꾸미:Q", format=".0f"), "일수"]).properties(height=260), width="stretch")
        cc2.dataframe(g.round(1), hide_index=True, width="stretch")

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

# ---------------- 탭4: 산출 방식
with tab4:
    st.markdown(f"""
**분위기 %** (0~100)
- **조과 50%**: 본문의 손님별 마릿수("○○님은 주꾸미 127마리…")에서 그날 주꾸미 중앙값을 구하고,
  **같은 달** 다른 해 출조일과 비교한 백분위. (손님 3명 이상 기록된 날만)
- **본문 분위기 35%**: "잘 나와, 폭발, 손맛, 꾸준히" 같은 긍정 표현과 "안 나와, 고전, 뜸, 아쉬" 같은 부정 표현의 비율. 제목은 2배 가중.
- **날씨 15%**: 강풍·파도·비·안개·물색 탁함 언급은 감점, 잔잔·화창은 가점.
- 마릿수 기록이 없는 날은 본문 75% + 날씨 25%, 본문이 비어 있는 2018년 일부는 제목만으로 산출.

**주꾸미·갑오징어 최고/최저**: 본문에 마릿수가 적힌 손님들 중 가장 많이·적게 잡은 수.

**물때·만조·간조·고저차·물세기**: 예약조회 앱과 같은 **바다타임 {bt.PORT_NAME} 월별 물때표** 기준.
- 만조·간조: 물때표의 시각과 조위(cm)
- 고저차: 그날 만조 높이 평균 − 간조 높이 평균
- 물세기 %: 물때표 ▲/▼ 변화량의 하루 평균을 바다타임 '물흐름 %'에 맞춘 기준으로 환산
  (사리→조금 201~732cm, 조금→사리 234~727cm = 0~100%)
- 바다타임에서 못 읽은 날은 사이드바에 조화상수 CSV를 올리면 추산값으로 채웁니다(물세기 제외).
""")
