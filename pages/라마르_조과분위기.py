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
import lamar_sun as sun      # noqa: E402
import lamar_tide as hm      # noqa: E402  (바다타임 조회가 안 될 때 쓰는 조화상수 계산)

APP_VERSION = "v19"
APP_DATE = "2026-10-17"
CHANGELOG = [
    ("v19", "버튼 달력을 흰 달력 모양으로: 일요일 시작, 공휴일 표시, 토·일·공휴일 빨강, 칸 아래 분위기 막대"),
    ("v18", "버튼 달력 바탕을 검은색으로, 예상 주꾸미·갑오징어에 중앙값 / 최고 마릿수 나란히 표시"),
    ("v17", "버튼 달력을 실제 달력처럼: 월 제목 띠, 요일 머리줄(토 파랑·일 빨강), 고른 칸 크기, 좁은 간격, 빈 칸 표시"),
    ("v16", "🔘 2027 버튼 달력 탭 추가: 깜빡임·진하게·약하게 버튼 달력과 선택한 날 예상 요약"),
    ("v15", "🗓️ 2027 달력 탭 추가: 깜빡임 없는 색칠 달력(물세기 20% 미만 파란 테두리), 예상 상위 10일"),
    ("v14", "2027 예상 달력을 날짜 버튼으로 변경: 물세기 0~9% 깜빡임, 10~19% 진하게, 20~30% 약하게 표시, 누르면 바로 선택"),
    ("v13", "2027 예상 제목 옆에 '가장 비슷했던 과거 출조일 평균' 노란 표시"),
    ("v12", "2027 예상 달력: 물세기 20% 미만인 날을 파란 굵은 테두리·●·굵은 글씨로 강조, 해당 날짜 목록 표시"),
    ("v11", "2027 예상 달력: 날짜 칸을 누르면 그 날짜 상세가 바로 표시되도록 수정"),
    ("v10", "🔮 2027 예상 탭: 2027년 9~12월 달력, 날짜별 예상 분위기·마릿수·오전/오후 조황·물때·조석"),
    ("v9", "전체 목록: 만조·간조는 시각만 표시하고 조위(cm)는 삭제, 고저차는 유지"),
    ("v8", "물때·시기 분석의 막대그래프를 곡선그래프로 변경 (물때별·물세기 구간별·월별)"),
    ("v7", "물세기 구간별 갑오징어 중앙값 그래프와 물세기-갑오징어 점 그래프 따로 추가"),
    ("v6", "물때·시기 분석: 물세기 구간별 분위기·마릿수·오전/오후 조황 그래프, 물세기-분위기 점 그래프와 추세선"),
    ("v5", "월별 분위기 % 가중치 적용 (9월 조과 60% … 12월 본문 50%)"),
    ("v4", "낚시 시간 = 남당항 일출 5분 전 ~ 일몰 20분 전, 주꾸미·갑오징어 중앙값 추가"),
    ("v3", "오전·점심 전·점심 후·오후·라마르타임 시간대별 조황 평가, 데이터 캐시 자동 갱신"),
    ("v2", "바다타임 남당항 물때표로 물때·만조·간조·고저차·물세기 %, 주꾸미·갑오징어 최고/최저"),
    ("v1", "블로그 본문 분석 586일, 날짜별 분위기 % 조회"),
]

st.set_page_config(page_title=f"라마르호 조과 분위기 조회 : {APP_VERSION}", page_icon="🦑", layout="wide")


MUL_ORDER = ["1물", "2물", "3물", "4물", "5물", "6물", "7물", "8물", "9물",
             "10물", "11물", "12물", "13물", "조금", "무시"]
TIDE_CYCLE = ["7물", "8물", "9물", "10물", "11물", "12물", "13물", "조금", "무시",
              "1물", "2물", "3물", "4물", "5물", "6물"]
WD = "월화수목금토일"
SEGS = [("am", "오전"), ("pre_lunch", "점심 전"), ("post_lunch", "점심 후"), ("pm", "오후"), ("lt", "라마르타임")]


def seg_label(v):
    if v is None or pd.isna(v):
        return "-"
    return "🟢 잘 나옴" if v >= 60 else ("🔴 안 나옴" if v <= 40 else "🟡 보통")




# ------------------------------------------------------------ 데이터
DATA_FILE = BASE / "data" / "lamar_days.json"
# 월별 분위기 % 가중치: (조과, 본문 분위기, 날씨)
WEIGHTS = {9: (0.60, 0.30, 0.10), 10: (0.50, 0.25, 0.15), 11: (0.40, 0.40, 0.20), 12: (0.30, 0.50, 0.20)}


def mood_score(r):
    """월별 가중치로 분위기 % 계산. 본문 분위기 = 본문 표현 점수와 오전·오후 조황 점수의 평균"""
    if r.get("basis") == "제목만" or pd.isna(r.get("sent")):
        return r["score"]
    wc, wb, ww = WEIGHTS.get(int(r["월"]), (0.5, 0.3, 0.2))
    body = r["sent"] if pd.isna(r.get("seg_avg")) else (r["sent"] + r["seg_avg"]) / 2
    if pd.isna(r.get("catch_pct")):          # 마릿수 기록이 없으면 조과 몫을 본문·날씨에 비율대로 나눔
        wb, ww, wc = wb / (wb + ww), ww / (wb + ww), 0
        return round(wb * body + ww * r["weather"])
    return round(wc * r["catch_pct"] + wb * body + ww * r["weather"])
NEED_COLS = ["gg_med", "am", "pre_lunch", "post_lunch", "pm", "lt", "seg_avg", "jj_min", "jj_max", "gg_min", "gg_max", "jj_med", "catch_pct", "stats", "key", "tags"]


@st.cache_data
def load_days(stamp):
    """stamp(파일 수정시각·크기)가 바뀌면 캐시를 버리고 새 데이터를 읽음"""
    rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    for c in NEED_COLS:  # 예전 데이터 파일이어도 멈추지 않도록 빈 열 채움
        if c not in df.columns:
            df[c] = None
    df["날짜"] = pd.to_datetime(df["date"]).dt.date
    df["연도"] = pd.to_datetime(df["date"]).dt.year
    df["월"] = pd.to_datetime(df["date"]).dt.month
    df["날씨"] = df["tags"].apply(lambda t: ", ".join(t))
    df["score"] = df.apply(mood_score, axis=1)
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
    return " / ".join(t for t, _ in lst) if lst else ""


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


_st = DATA_FILE.stat()
# ------------------------------------------------------------ 낚시 시간대 (남당항 출항 기준)
def _t(d, hhmm):
    h, m = map(int, hhmm.split(":"))
    return dt.datetime.combine(d, dt.time(h, m))


def start_time(d: dt.date):
    """낚시 시작 = 남당항 일출 5분 전"""
    st_dt = sun.fishing_window(d)[0]
    return st_dt, f"{st_dt:%H:%M}"


def end_time(d: dt.date):
    """낚시 종료 = 남당항 일몰 20분 전"""
    return sun.fishing_window(d)[1]


def _evt(d, events):
    return sorted(((k, _t(d, t if len(t) == 5 else "0" + t)) for k, t, _ in events), key=lambda x: x[1])


def flow_at(evs, t):
    """t 시각의 물 흐름: 다음 물때가 만조면 들물, 간조면 날물 (전후 25분 이내면 정조)"""
    for k, et in evs:
        if abs((et - t).total_seconds()) <= 25 * 60:
            return "만조 정조" if k == "만조" else "간조 정조"
    nxt = next(((k, et) for k, et in evs if et > t), None)
    if nxt:
        return "들물" if nxt[0] == "만조" else "날물"
    prv = [k for k, et in evs if et <= t]
    if prv:
        return "날물" if prv[-1] == "만조" else "들물"
    return "-"


def window_flow(evs, t0, t1):
    """구간의 물 흐름 요약: '들물', '날물', '들물→만조→날물' 등"""
    if t1 <= t0:
        return "-"
    inside = [(k, et) for k, et in evs if t0 < et < t1]
    nxt = next((k for k, et in evs if et > t0), None)
    if nxt:
        first = "들물" if nxt == "만조" else "날물"
    else:
        prv = [k for k, et in evs if et <= t0]
        first = ("날물" if prv[-1] == "만조" else "들물") if prv else "-"
    if not inside:
        return first
    parts = [first]
    for k, et in inside:
        parts.append(f"{k} {et:%H:%M}")
        parts.append("날물" if k == "만조" else "들물")
    return "→".join(parts)


def flow_kind(text):
    """구간 요약 → 분석용 분류"""
    if text in ("-", None) or not isinstance(text, str):
        return None
    if "만조" in text and "간조" in text:
        return "물돌이 2회"
    if "만조" in text:
        return "만조 끼임(들→날)"
    if "간조" in text:
        return "간조 끼임(날→들)"
    return text + " 내내"


df = load_days(f"{_st.st_mtime_ns}-{_st.st_size}")

# ------------------------------------------------------------ 물때표 불러오기
need = tuple(bt.months_for(sorted(set(df["날짜"]))))
try:
    BT, BT_ERRS = badatime_days(need)
except Exception as ex:
    BT, BT_ERRS = {}, [str(ex)]
BT = dict(BT)  # 캐시 원본을 건드리지 않도록 복사

st.sidebar.markdown(f"**라마르 조과분위기 {APP_VERSION}** · {APP_DATE}")
st.sidebar.header("🌊 물때·조석")
with st.sidebar.expander("⏰ 낚시 시간 (남당항 일출·일몰 기준)", expanded=False):
    st.caption("시작 = 남당항 일출 5분 전 · 종료 = 일몰 20분 전 (날짜마다 자동 계산)")
    LUNCH_T = st.time_input("오전/오후 기준 (점심)", dt.time(12, 0), step=1800)
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

for k, nm in SEGS:
    df[nm + " 평가"] = df[k].apply(seg_label)

# 날짜별 물때 정보를 목록에 붙이기 (바다타임 물때가 있으면 그것을 씀)
infos = {d: tide_info(d) for d in df["날짜"]}
df["mul"] = [(infos[d] or {}).get("mul") or m for d, m in zip(df["날짜"], df["mul"])]
df["물세기(%)"] = [(infos[d] or {}).get("pct") for d in df["날짜"]]
df["만조"] = [fmt_ev((infos[d] or {}).get("hi")) for d in df["날짜"]]
df["간조"] = [fmt_ev((infos[d] or {}).get("lo")) for d in df["날짜"]]
df["고저차(cm)"] = [(infos[d] or {}).get("range") for d in df["날짜"]]


def fishing_flows(d):
    info = infos.get(d) if d in infos else tide_info(d)
    st_dt, st_txt = start_time(d)
    if not info or not info.get("events"):
        return st_txt, "-", "-", "-"
    evs = _evt(d, info["events"])
    lunch, end = dt.datetime.combine(d, LUNCH_T), end_time(d)
    return st_txt, flow_at(evs, st_dt), window_flow(evs, st_dt, lunch), window_flow(evs, lunch, end)


_ff = [fishing_flows(d) for d in df["날짜"]]
df["시작"] = [x[0] for x in _ff]
df["종료"] = [f"{end_time(d):%H:%M}" for d in df["날짜"]]
df["시작 물흐름"] = [x[1] for x in _ff]
df["오전 물흐름"] = [x[2] for x in _ff]
df["오후 물흐름"] = [x[3] for x in _ff]

# ------------------------------------------------------------ 본문
st.title(f"🦑 라마르호 조과 분위기 조회 : {APP_VERSION}")
st.caption(f"남당항 라마르호 '오늘의 조과' {len(df)}일 · 2018~2026년 9~12월 · 블로그 본문 분석 · "
           f"물때·조석·물세기는 바다타임 {bt.PORT_NAME} 기준")

tab1, tab5, tab7, tab6, tab2, tab3, tab4 = st.tabs(["📅 날짜별 조회", "🔮 2027 예상", "🔘 2027 버튼 달력",
                                                    "🗓️ 2027 달력", "📋 전체 목록", "📊 물때·시기 분석", "ℹ️ 산출 방식"])


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
        st_dt, st_txt = start_time(d)
        lunch, end = dt.datetime.combine(d, LUNCH_T), end_time(d)
        band = pd.DataFrame([{"s": st_dt, "e": lunch, "구간": "오전 낚시"}, {"s": lunch, "e": end, "구간": "오후 낚시"}])
        bands = alt.Chart(band).mark_rect(opacity=0.12).encode(
            x="s:T", x2="e:T", color=alt.Color("구간:N", scale=alt.Scale(
                domain=["오전 낚시", "오후 낚시"], range=["#f59f00", "#7048e8"]), legend=alt.Legend(title=None)))
        st.altair_chart((bands + line + dots).properties(height=230), width="stretch")
        evs = _evt(d, info["events"])
        _, _, rise, sett = sun.fishing_window(d)
        st.markdown(f"**낚시 {st_txt} ~ {end:%H:%M}** (일출 {rise:%H:%M} · 일몰 {sett:%H:%M}) · 시작 때 **{flow_at(evs, st_dt)}**  \n"
                    f"오전: {window_flow(evs, st_dt, lunch)}  \n오후: {window_flow(evs, lunch, end)}")
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
            c3.metric("주꾸미 (최저~최고)", rng_text(r["jj_min"], r["jj_max"]),
                      f"중앙값 {r['jj_med']:g}마리" if pd.notna(r["jj_med"]) else None, delta_color="off")
            c4.metric("갑오징어 (최저~최고)", rng_text(r["gg_min"], r["gg_max"]),
                      f"중앙값 {r['gg_med']:g}마리" if pd.notna(r["gg_med"]) else None, delta_color="off")
            st.progress(int(r["score"]) / 100, text=f"분위기 {r['score']}%")
            st.markdown("**시간대별 조황**")
            sc = st.columns(len(SEGS))
            for col, (k, nm) in zip(sc, SEGS):
                v = r[k]
                col.metric(nm, f"{int(v)}%" if pd.notna(v) else "-", seg_label(v) if pd.notna(v) else None,
                           delta_color="off")
            if r["stats"]:
                st.markdown(f"**조과** · {r['stats']}")
            if r["tags"]:
                st.markdown("**날씨·바다** · " + " ".join(f"`{t}`" for t in r["tags"]))
            if r["key"]:
                st.markdown("**그날 분위기 (본문 발췌)**")
                for s in r["key"]:
                    st.markdown(f"> {s}")
            wc, wb, ww = WEIGHTS.get(int(r["월"]), (0.5, 0.3, 0.2))
            st.caption(f"{int(r['월'])}월 가중치 조과 {wc:.0%} · 본문 {wb:.0%} · 날씨 {ww:.0%} · "
                       f"본문 표현 {r['sent']}% · 날씨 점수 {r['weather']}%")
        else:
            history_hint(sel, mul)
        st.divider()
        tide_block(sel)

# ---------------- 탭5: 2027 예상
PRED_START, PRED_END = dt.date(2027, 9, 1), dt.date(2027, 12, 31)
PRED_DAYS = [PRED_START + dt.timedelta(days=i) for i in range((PRED_END - PRED_START).days + 1)]


@st.cache_data(show_spinner=False)
def mul_pct_table(stamp, _df):
    """과거 기록에서 (월, 물때)별 물세기 % 중앙값 — 2027 물때표가 없을 때 물세기 추정용"""
    t = _df.dropna(subset=["물세기(%)"])
    return t.groupby(["월", "mul"])["물세기(%)"].median().to_dict(), t.groupby("mul")["물세기(%)"].median().to_dict()


def pred_conditions(d: dt.date):
    """2027 날짜의 조건: 물때, 물세기, 만조·간조, 낚시시간, 오전·오후 물흐름"""
    info = tide_info(d)
    lunar, lmul = lunar_mul(d)
    mul = (info or {}).get("mul") or lmul
    pct = (info or {}).get("pct")
    pct_src = "바다타임"
    if pct is None:
        by_m, by_all = MUL_PCT
        pct = by_m.get((d.month, mul), by_all.get(mul))
        pct_src = "과거 같은 물때 평균(추정)"
    st_dt, st_txt = start_time(d)
    end = end_time(d)
    lunch = dt.datetime.combine(d, LUNCH_T)
    am_flow = pm_flow = start_flow = "-"
    if info and info.get("events"):
        evs = _evt(d, info["events"])
        start_flow, am_flow, pm_flow = flow_at(evs, st_dt), window_flow(evs, st_dt, lunch), window_flow(evs, lunch, end)
    return dict(date=d, lunar=lunar, mul=mul, pct=pct, pct_src=pct_src, info=info, start=st_txt, end=f"{end:%H:%M}",
                start_flow=start_flow, am_flow=am_flow, pm_flow=pm_flow)


def _wmean(sub, col):
    v = sub[[col, "_w"]].dropna()
    return (v[col] * v["_w"]).sum() / v["_w"].sum() if len(v) and v["_w"].sum() > 0 else None


def predict(c):
    """비슷한 과거 출조일(같은 달 ±20일, 물세기 ±12%p 또는 같은 물때)의 가중 평균"""
    d = c["date"]
    h = df.copy()
    doy = pd.to_datetime(h["date"]).dt.dayofyear
    tdoy = d.timetuple().tm_yday
    h["_dd"] = (doy - tdoy).abs()
    h = h[h["_dd"] <= 20]
    if c["pct"] is not None and h["물세기(%)"].notna().any():
        h["_dp"] = (h["물세기(%)"] - c["pct"]).abs()
        near = h[h["_dp"] <= 12].copy()
        near["_w"] = (1 - near["_dd"] / 25) * (1 - near["_dp"] / 15)
        basis = f"같은 시기(±20일) · 물세기 {c['pct']:.0f}%±12"
    else:
        near = h[h["mul"] == c["mul"]].copy()
        near["_w"] = 1 - near["_dd"] / 25
        basis = f"같은 시기(±20일) · 같은 물때({c['mul']})"
    if len(near) < 5:                                  # 표본이 적으면 같은 달 전체로 넓힘
        near = df[df["월"] == d.month].copy()
        near["_w"] = 1.0
        basis = f"{d.month}월 전체 (비슷한 조건 표본 부족)"
    out = {k: _wmean(near, col) for k, col in
           [("score", "score"), ("jj", "jj_med"), ("gg", "gg_med"), ("jj_max", "jj_max"), ("gg_max", "gg_max"),
            ("am", "am"), ("pm", "pm"), ("lt", "lt")]}
    # 오전·오후 조황은 같은 물흐름 유형(만조 끼임 등)인 날이 충분하면 그 날들로 보정
    for seg, col_flow, key in (("am", "오전 물흐름", "am_flow"), ("pm", "오후 물흐름", "pm_flow")):
        kind = flow_kind(c[key])
        if kind:
            same = near[near[col_flow].apply(flow_kind) == kind]
            if same[seg].notna().sum() >= 5:
                out[seg] = _wmean(same, seg)
    out["n"] = len(near)
    out["basis"] = basis
    out["similar"] = near.assign(_rank=near["_w"]).sort_values("_rank", ascending=False).head(6)
    return out


MAX_HELP = "최고 = 비슷했던 과거 출조일들의 '그날 1등 마릿수' 평균"


def fish_txt(med, mx, nd=0):
    if med is None or pd.isna(med):
        return "-"
    m_txt = f"{med:.{nd}f}"
    return f"{m_txt} / {mx:.0f}마리" if mx is not None and not pd.isna(mx) else f"{m_txt}마리"


HOLIDAYS_2027 = {
    "2027-09-14": "추석 연휴", "2027-09-15": "추석", "2027-09-16": "추석 연휴",
    "2027-10-03": "개천절", "2027-10-04": "대체공휴일",
    "2027-10-09": "한글날", "2027-10-11": "대체공휴일",
    "2027-12-25": "성탄절", "2027-12-27": "대체공휴일",
}
WD_SUN = ["일", "월", "화", "수", "목", "금", "토"]


def lunar_dot(d: dt.date):
    c = KoreanLunarCalendar()
    c.setSolarDate(d.year, d.month, d.day)
    return f"{c.lunarMonth}.{c.lunarDay}"


def button_calendar(P, prefix, note="날짜를 누르면 아래에 상세가 나와요."):
    """2027년 9~12월 날짜 버튼 달력 — 흰 달력, 일요일 시작, 음력·공휴일 표시, 토·일·공휴일 빨강
    물세기 0~9% 깜빡임 · 10~19% 진하게 · 20~30% 약하게, 칸 아래 색 막대 = 예상 분위기"""

    def _score_color(v):
        if v is None or pd.isna(v):
            return "#dee2e6"
        x = max(0.0, min(1.0, (v - 35) / 35))
        stops = [(0.0, (250, 82, 82)), (0.5, (250, 176, 5)), (1.0, (55, 178, 77))]
        for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
            if x <= x1:
                f = (x - x0) / (x1 - x0)
                r, g, b = (round(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
                return f"#{r:02x}{g:02x}{b:02x}"
        return "#37b24d"

    def _band(p):
        if p is None or pd.isna(p):
            return ""
        return "blink" if p < 10 else ("strong" if p < 20 else ("weak" if p <= 30 else ""))

    css = ["""
    @keyframes lamarBlink { 0%,100% { background:#a5d8ff; } 50% { background:#ffffff; } }
    .lg { padding:2px 8px; border-radius:6px; font-size:0.85em; white-space:nowrap; }
    .lg-blink { background:#a5d8ff; animation: lamarBlink 1s infinite; font-weight:800; color:#1864ab; }
    .lg-strong { background:#a5d8ff; font-weight:800; color:#1864ab; }
    .lg-weak { background:#e7f5ff; color:#339af0; }
    .lg-bar { display:inline-block; width:46px; height:6px; border-radius:3px; vertical-align:middle;
              background:linear-gradient(90deg,#fa5252,#fab005,#37b24d); }
    .cal-title { text-align:center; font-size:2.1rem; font-weight:800; color:#212529; margin:6px 0 2px 0; }
    .cal-note { text-align:right; font-size:0.78rem; color:#868e96; margin-top:-30px; margin-bottom:8px; }
    .cal-wd { text-align:center; font-size:0.95rem; font-weight:700; color:#868e96; padding:4px 0 8px 0; }
    .cal-wd.red { color:#e03131; }
    .cal-empty { height:72px; }
    div[class*="st-key-PFX_m"] { background:#ffffff !important; border-radius:14px; padding:4px 10px 6px 10px;
                                 border:1px solid #f1f3f5; color:#212529; }
    div[class*="st-key-PFX_m"] [data-testid="stHorizontalBlock"] { gap:2px !important; }
    div[class*="st-key-PFX_m"] [data-testid="stColumn"] { min-width:0 !important; }
    div[class*="st-key-PFX_m"] [data-testid="stElementContainer"] { margin-bottom:0 !important; }
    div[class*="st-key-PFX_hd"] { border-bottom:2px solid #343a40; margin-bottom:2px; }
    div[class*="st-key-PFX_wk"] { border-bottom:1px solid #e9ecef; padding:2px 0; }
    div[class*="st-key-PFX_2"] button { width:100%; height:72px; padding:4px 0 6px 0 !important; border-radius:8px;
        background:transparent !important; border:none !important; box-shadow:none; color:#212529 !important;
        line-height:1.15; }
    div[class*="st-key-PFX_2"] button p { font-size:0.72rem; margin:0; color:#e03131; }
    div[class*="st-key-PFX_2"] button p strong { font-size:1.55rem; font-weight:800; color:#212529; }
    div[class*="st-key-PFX_2"] button:hover { background:#f8f9fa !important; }
    """.replace("PFX", prefix)]
    sel_iso = st.session_state.pred_day.isoformat()
    for _, r in P.iterrows():
        k = f".st-key-{prefix}_{r['date'].replace('-', '_')} button"
        rule = [f"border-bottom:5px solid {_score_color(r['예상 분위기'])} !important;"]
        band = _band(r["물세기"])
        if band == "blink":
            rule.append("background:#a5d8ff !important; animation: lamarBlink 1s infinite;")
        elif band == "strong":
            rule.append("background:#a5d8ff !important;")
        elif band == "weak":
            rule.append("background:#e7f5ff !important;")
        if r["date"] == sel_iso:
            rule.append("outline:2px solid #212529; outline-offset:-2px;")
        css.append(k + " {" + " ".join(rule) + "}")
        d_ = dt.date.fromisoformat(r["date"])
        if d_.weekday() >= 5 or r["date"] in HOLIDAYS_2027:      # 토·일·공휴일 빨강
            css.append(k + " p strong { color:#e03131 !important; }")
    st.markdown("<style>" + "\n".join(css) + "</style>", unsafe_allow_html=True)

    st.markdown(
        "<div style='line-height:2.2'>칸 아래 막대 = 예상 분위기 <span class='lg-bar'></span> (빨강 낮음 → 초록 좋음)"
        " · 물세기 <span class='lg lg-blink'>0~9% 깜빡임</span> "
        "<span class='lg lg-strong'>10~19% 진하게</span> "
        f"<span class='lg lg-weak'>20~30% 약하게</span> · {note}</div>", unsafe_allow_html=True)

    def _pick(iso):
        st.session_state.pred_day = dt.date.fromisoformat(iso)
        st.session_state.pred_date_input = st.session_state.pred_day

    for pair in ((9, 10), (11, 12)):
        outer = st.columns(2, gap="medium")
        for oc, m in zip(outer, pair):
            with oc, st.container(key=f"{prefix}_m{m}"):
                st.markdown(f"<div class='cal-title'>2027년 {m}월</div>", unsafe_allow_html=True)
                with st.container(key=f"{prefix}_hd{m}"):
                    hdr = st.columns(7)
                    for i, (hc, w) in enumerate(zip(hdr, WD_SUN)):
                        cls = "red" if i in (0, 6) else ""
                        hc.markdown(f"<div class='cal-wd {cls}'>{w}</div>", unsafe_allow_html=True)
                first = dt.date(2027, m, 1)
                days_in = (dt.date(2027 + (m == 12), m % 12 + 1, 1) - first).days
                lead = (first.weekday() + 1) % 7                   # 일요일 시작
                cells = [None] * lead + list(range(1, days_in + 1))
                cells += [None] * (-len(cells) % 7)
                for wk in range(0, len(cells), 7):
                    with st.container(key=f"{prefix}_wk{m}_{wk // 7}"):
                        row = st.columns(7)
                        for rc, day in zip(row, cells[wk:wk + 7]):
                            if day is None:
                                rc.markdown("<div class='cal-empty'></div>", unsafe_allow_html=True)
                                continue
                            d_ = dt.date(2027, m, day)
                            iso = d_.isoformat()
                            r = P[P["date"] == iso].iloc[0]
                            hol = HOLIDAYS_2027.get(iso)
                            label = f"**{day}**" + (f"  \n{hol}" if hol else "  \n\u00a0")
                            pct_txt = f"{r['물세기']:.0f}%" if pd.notna(r["물세기"]) else "-"
                            rc.button(label, key=f"{prefix}_{iso.replace('-', '_')}", on_click=_pick, args=(iso,),
                                      help=f"{iso} ({WD[d_.weekday()]}){' · ' + hol if hol else ''} · {r['물때']} · "
                                           f"물세기 {pct_txt} · 예상 분위기 {r['예상 분위기']}% · "
                                           f"주꾸미 약 {r['주꾸미']:.0f}마리")

    low_days = P[P["물세기"].notna() & (P["물세기"] < 20)]
    if len(low_days):
        st.markdown("**물세기 20% 미만인 날** · " + " ".join(
            f"`{r['월']}/{r['일']}({r['요일']}) {r['물세기']:.0f}%`" for _, r in low_days.iterrows()))

with tab5:
    MUL_PCT = mul_pct_table(_st.st_mtime_ns, df)
    if "pred_day" not in st.session_state:
        st.session_state.pred_day = PRED_START
    # 2027 물때표 받아두기 (없으면 과거 평균으로 추정)
    need27 = tuple(bt.months_for(PRED_DAYS))
    try:
        BT.update(badatime_days(need27)[0])
    except Exception:
        pass

    @st.cache_data(show_spinner="2027년 예상 계산 중…")
    def all_predictions(stamp, bt_keys, lunch):
        rows = []
        for d in PRED_DAYS:
            c = pred_conditions(d)
            p_ = predict(c)
            rows.append({"date": d.isoformat(), "월": d.month, "일": d.day, "요일": WD[d.weekday()],
                         "주": (d.day + d.replace(day=1).weekday() - 1) // 7, "물때": c["mul"],
                         "물세기": c["pct"], "예상 분위기": round(p_["score"]) if p_["score"] is not None else None,
                         "주꾸미": p_["jj"], "갑오징어": p_["gg"]})
        return pd.DataFrame(rows)

    P = all_predictions(_st.st_mtime_ns, len([k for k in BT if k.startswith("2027")]), str(LUNCH_T))

    st.subheader("2027년 9~12월 예상 달력")
    button_calendar(P, "c27")

    if "pred_date_input" not in st.session_state:
        st.session_state.pred_date_input = st.session_state.pred_day
    d27 = st.date_input("날짜 선택 (2027년 9월 1일 ~ 12월 31일)", min_value=PRED_START, max_value=PRED_END,
                        format="YYYY-MM-DD", key="pred_date_input")
    st.session_state.pred_day = d27

    c = pred_conditions(d27)
    p_ = predict(c)
    st.divider()
    st.markdown(
        f"<h3 style='margin-bottom:0.3rem'>{d27:%Y-%m-%d} ({WD[d27.weekday()]}) 예상 · 음력 {c['lunar']} · "
        f"{c['mul']} : <span style='background:#ffe066;color:#000;padding:2px 10px;border-radius:6px;"
        f"font-size:0.8em'>가장 비슷했던 과거 출조일 평균</span></h3>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("예상 분위기", f"{p_['score']:.0f}%" if p_["score"] is not None else "-")
    m2.metric("예상 주꾸미 (중앙값 / 최고)", fish_txt(p_["jj"], p_["jj_max"], 0), help=MAX_HELP)
    m3.metric("예상 갑오징어 (중앙값 / 최고)", fish_txt(p_["gg"], p_["gg_max"], 1), help=MAX_HELP)
    m4.metric("물세기", f"{c['pct']:.0f}%" if c["pct"] is not None else "-", c["pct_src"], delta_color="off")
    if p_["score"] is not None:
        st.progress(min(1.0, p_["score"] / 100), text=f"예상 분위기 {p_['score']:.0f}%")

    st.markdown("**시간대별 예상 조황**")
    s1, s2, s3 = st.columns(3)
    for col, k, nm in ((s1, "am", "오전"), (s2, "pm", "오후"), (s3, "lt", "라마르타임")):
        v = p_[k]
        col.metric(nm, f"{v:.0f}%" if v is not None else "-", seg_label(v) if v is not None else None,
                   delta_color="off")

    st.markdown(f"**낚시 {c['start']} ~ {c['end']}** · 시작 때 **{c['start_flow']}**  \n"
                f"오전: {c['am_flow']}  \n오후: {c['pm_flow']}")
    if c["info"]:
        t1, t2, t3 = st.columns(3)
        t1.metric("만조", " / ".join(t for t, _ in c["info"]["hi"]) or "-")
        t2.metric("간조", " / ".join(t for t, _ in c["info"]["lo"]) or "-")
        t3.metric("고저차", f"{c['info']['range']} cm" if c["info"]["range"] else "-")
        tide_block(d27)
    else:
        st.info("2027년 바다타임 물때표를 아직 받지 못해 만조·간조 시각은 비어 있어요. "
                "물때는 음력으로, 물세기는 과거 같은 물때 평균으로 추정했어요.")

    st.caption(f"예상 근거: {p_['basis']} · 비슷한 과거 출조일 {p_['n']}일의 가중 평균 "
               "(날짜가 가깝고 물세기가 비슷할수록 비중 큼)")
    sim = p_["similar"][["date", "mul", "물세기(%)", "score", "jj_med", "gg_med", "오전 평가", "오후 평가", "title", "link"]]
    st.markdown("**가장 비슷했던 과거 출조일**")
    st.dataframe(sim.rename(columns={"date": "날짜", "mul": "물때", "score": "분위기", "jj_med": "주꾸미 중앙값",
                                     "gg_med": "갑오징어 중앙값", "title": "제목", "link": "링크"}),
                 hide_index=True, width="stretch",
                 column_config={"분위기": st.column_config.ProgressColumn("분위기", format="%d%%", min_value=0, max_value=100),
                                "링크": st.column_config.LinkColumn("링크", display_text="원문")})

    st.markdown("**2027년 9~12월 전체 예상표**")
    P_show = P.drop(columns=["주", "일"]).rename(columns={"date": "날짜"})
    P_show.insert(4, "물세기 20% 미만", P["물세기"].apply(lambda v: "🔵" if pd.notna(v) and v < 20 else ""))
    st.dataframe(P_show, hide_index=True, width="stretch",
                 height=360, column_config={
                     "예상 분위기": st.column_config.ProgressColumn("예상 분위기", format="%d%%", min_value=0, max_value=100),
                     "물세기": st.column_config.NumberColumn("물세기 %", format="%d"),
                     "주꾸미": st.column_config.NumberColumn("예상 주꾸미", format="%d"),
                     "갑오징어": st.column_config.NumberColumn("예상 갑오징어", format="%.1f")})
    st.download_button("2027 예상표 CSV", P.drop(columns=["주"]).to_csv(index=False).encode("utf-8-sig"),
                       f"lamar_2027_예상_{APP_VERSION}.csv", "text/csv")
    st.caption("예상치는 과거 블로그 기록의 평균이라 실제 조황·날씨와 다를 수 있어요. 날씨는 예측에 들어가지 않아요.")


# ---------------- 탭7: 2027 버튼 달력
with tab7:
    st.subheader("2027년 9~12월 버튼 달력")
    button_calendar(P, "b27", "날짜를 누르면 바로 아래에 그날 예상이 나와요.")
    d7 = st.session_state.pred_day
    c7 = pred_conditions(d7)
    p7 = predict(c7)
    st.divider()
    st.markdown(
        f"<h3 style='margin-bottom:0.3rem'>{d7:%Y-%m-%d} ({WD[d7.weekday()]}) 예상 · 음력 {c7['lunar']} · "
        f"{c7['mul']} : <span style='background:#ffe066;color:#000;padding:2px 10px;border-radius:6px;"
        f"font-size:0.8em'>가장 비슷했던 과거 출조일 평균</span></h3>", unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("예상 분위기", f"{p7['score']:.0f}%" if p7["score"] is not None else "-")
    q2.metric("예상 주꾸미 (중앙값 / 최고)", fish_txt(p7["jj"], p7["jj_max"], 0), help=MAX_HELP)
    q3.metric("예상 갑오징어 (중앙값 / 최고)", fish_txt(p7["gg"], p7["gg_max"], 1), help=MAX_HELP)
    q4.metric("물세기", f"{c7['pct']:.0f}%" if c7["pct"] is not None else "-", c7["pct_src"], delta_color="off")
    w1, w2, w3 = st.columns(3)
    for col, k, nm in ((w1, "am", "오전"), (w2, "pm", "오후"), (w3, "lt", "라마르타임")):
        v = p7[k]
        col.metric(nm, f"{v:.0f}%" if v is not None else "-", seg_label(v) if v is not None else None,
                   delta_color="off")
    hi7 = " / ".join(t for t, _ in c7["info"]["hi"]) if c7["info"] else "-"
    lo7 = " / ".join(t for t, _ in c7["info"]["lo"]) if c7["info"] else "-"
    st.markdown(f"**낚시 {c7['start']} ~ {c7['end']}** · 시작 때 **{c7['start_flow']}** · 만조 {hi7} · 간조 {lo7}  \n"
                f"오전: {c7['am_flow']}  \n오후: {c7['pm_flow']}")
    st.caption("조위 그래프·비슷했던 과거 출조일 목록은 🔮 2027 예상 탭에서 같은 날짜로 볼 수 있어요.")

# ---------------- 탭6: 2027 달력 (깜빡임 없는 색칠 달력)
with tab6:
    st.subheader("2027년 9~12월 달력")
    st.markdown(
        "칸 색 = 예상 분위기 % (초록일수록 좋음) · "
        "<span style='border:3px solid #1864ab;padding:0 6px;border-radius:4px;font-weight:700;color:#1864ab'>"
        "파란 굵은 테두리·● = 물세기 20% 미만</span> · 칸에 마우스를 올리면 상세가 보여요. "
        "날짜별 상세는 🔮 2027 예상 탭에서 확인하세요.", unsafe_allow_html=True)
    cal_cols = st.columns(4)
    for col, m in zip(cal_cols, [9, 10, 11, 12]):
        sub = P[P["월"] == m]
        base = alt.Chart(sub).encode(
            x=alt.X("요일:N", sort=list(WD), title=None, axis=alt.Axis(orient="top", labelAngle=0)),
            y=alt.Y("주:O", title=None, axis=None))
        low = "datum['물세기'] != null && datum['물세기'] < 20"
        norm = f"!({low})"
        rect = base.mark_rect(cornerRadius=4).encode(
            color=alt.Color("예상 분위기:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[35, 70]), legend=None),
            stroke=alt.condition(low, alt.value("#1864ab"), alt.value("white")),
            strokeWidth=alt.condition(low, alt.value(4), alt.value(2)),
            tooltip=[alt.Tooltip("date:N", title="날짜"), "요일", "물때", alt.Tooltip("물세기:Q", format=".0f"),
                     alt.Tooltip("예상 분위기:Q", title="예상 분위기 %"),
                     alt.Tooltip("주꾸미:Q", format=".0f", title="예상 주꾸미"),
                     alt.Tooltip("갑오징어:Q", format=".1f", title="예상 갑오징어")])
        txt = (base.transform_filter(norm).mark_text(fontSize=11, dy=-4).encode(text="일:Q")
               + base.transform_filter(low).mark_text(fontSize=12, dy=-4, fontWeight="bold").encode(text="일:Q"))
        txt2 = (base.transform_filter(norm).mark_text(fontSize=8, dy=8, opacity=0.85).encode(text="물때:N")
                + base.transform_filter(low).mark_text(fontSize=8, dy=8, fontWeight="bold", color="#1864ab"
                                                       ).encode(text="물때:N"))
        dot = base.transform_filter(low).mark_text(fontSize=10, dx=13, dy=-12, color="#1864ab").encode(
            text=alt.value("●"))
        with col:
            st.markdown(f"**2027년 {m}월**")
            st.altair_chart((rect + txt + txt2 + dot).properties(height=230), width="stretch")
    low_days6 = P[P["물세기"].notna() & (P["물세기"] < 20)]
    if len(low_days6):
        st.markdown("**물세기 20% 미만인 날** · " + " ".join(
            f"`{r['월']}/{r['일']}({r['요일']}) {r['물세기']:.0f}%`" for _, r in low_days6.iterrows()))
    best = P.dropna(subset=["예상 분위기"]).sort_values("예상 분위기", ascending=False).head(10)
    st.markdown("**예상 분위기 상위 10일**")
    st.dataframe(best.drop(columns=["주", "일"]).rename(columns={"date": "날짜"}), hide_index=True, width="stretch",
                 column_config={
                     "예상 분위기": st.column_config.ProgressColumn("예상 분위기", format="%d%%", min_value=0, max_value=100),
                     "물세기": st.column_config.NumberColumn("물세기 %", format="%d"),
                     "주꾸미": st.column_config.NumberColumn("예상 주꾸미", format="%d"),
                     "갑오징어": st.column_config.NumberColumn("예상 갑오징어", format="%.1f")})


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
    s1, s2 = st.columns(2)
    am_sel = s1.multiselect("오전 조황", ["🟢 잘 나옴", "🟡 보통", "🔴 안 나옴", "-"],
                            default=["🟢 잘 나옴", "🟡 보통", "🔴 안 나옴", "-"])
    pm_sel = s2.multiselect("오후 조황", ["🟢 잘 나옴", "🟡 보통", "🔴 안 나옴", "-"],
                            default=["🟢 잘 나옴", "🟡 보통", "🔴 안 나옴", "-"])
    v = v[v["오전 평가"].isin(am_sel) & v["오후 평가"].isin(pm_sel)]
    cols = ["date", "wd", "mul", "물세기(%)", "시작", "종료", "시작 물흐름", "오전 물흐름", "오후 물흐름",
            "만조", "간조", "고저차(cm)", "score",
            "오전 평가", "am", "점심 전 평가", "점심 후 평가", "오후 평가", "pm", "라마르타임 평가",
            "jj_max", "jj_med", "jj_min", "gg_max", "gg_med", "gg_min", "title", "날씨", "link"]
    show = v[cols].rename(columns={
        "date": "날짜", "wd": "요일", "mul": "물때", "score": "분위기",
        "am": "오전%", "pm": "오후%",
        "jj_max": "주꾸미 최고", "jj_med": "주꾸미 중앙값", "jj_min": "주꾸미 최저", "gg_med": "갑오징어 중앙값", "gg_max": "갑오징어 최고", "gg_min": "갑오징어 최저",
        "title": "제목", "link": "링크"})
    st.caption(f"{len(show)}일 · 평균 분위기 {show['분위기'].mean():.0f}%" if len(show) else "해당 없음")
    st.dataframe(
        show.sort_values("날짜", ascending=False), hide_index=True, width="stretch", height=600,
        column_config={
            "분위기": st.column_config.ProgressColumn("분위기", format="%d%%", min_value=0, max_value=100),
            "물세기(%)": st.column_config.ProgressColumn("물세기", format="%d%%", min_value=0, max_value=100,
                                                      help="바다타임 남당항 물흐름 % 기준"),
            "오전%": st.column_config.ProgressColumn("오전%", format="%d%%", min_value=0, max_value=100),
            "오후%": st.column_config.ProgressColumn("오후%", format="%d%%", min_value=0, max_value=100),
            "만조": st.column_config.TextColumn("만조 시각"),
            "간조": st.column_config.TextColumn("간조 시각"),
            "주꾸미 최고": st.column_config.NumberColumn("주꾸미 최고", format="%d"),
            "주꾸미 최저": st.column_config.NumberColumn("주꾸미 최저", format="%d"),
            "주꾸미 중앙값": st.column_config.NumberColumn("주꾸미 중앙값", format="%g"),
            "갑오징어 중앙값": st.column_config.NumberColumn("갑오징어 중앙값", format="%g"),
            "갑오징어 최고": st.column_config.NumberColumn("갑오징어 최고", format="%d"),
            "갑오징어 최저": st.column_config.NumberColumn("갑오징어 최저", format="%d"),
            "링크": st.column_config.LinkColumn("링크", display_text="원문"),
            "제목": st.column_config.TextColumn("제목", width="large")})
    st.download_button("CSV 다운로드", show.to_csv(index=False).encode("utf-8-sig"),
                       f"lamar_분위기_목록_{APP_VERSION}.csv", "text/csv")
    st.caption("주꾸미·갑오징어 최고/중앙값/최저는 본문에 마릿수가 적힌 손님 기준입니다(주꾸미는 3명 이상 기록된 날만).")

# ---------------- 탭3: 분석
with tab3:
    m = df.groupby("mul").agg(분위기=("score", "mean"), 일수=("score", "size"),
                              주꾸미=("jj_med", "mean")).reindex(MUL_ORDER).reset_index()
    m["분위기"] = m["분위기"].round(1)
    st.subheader("물때별 평균 분위기")
    st.altair_chart(alt.Chart(m).mark_line(color="#2b7bb9", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
        x=alt.X("mul:N", sort=MUL_ORDER, title="물때"),
        y=alt.Y("분위기:Q", title="평균 분위기 %", scale=alt.Scale(domain=[0, 100])),
        tooltip=["mul", "분위기", "일수", alt.Tooltip("주꾸미:Q", format=".0f")]
    ).properties(height=280), width="stretch")
    best = m.dropna().sort_values("분위기", ascending=False).head(3)["mul"].tolist()
    st.caption(f"분위기가 가장 좋았던 물때: {', '.join(best)}")

    t = df.dropna(subset=["물세기(%)"]).copy()
    if len(t):
        st.subheader("물세기와 분위기")
        st.caption("물세기 % = 바다타임 남당항 물흐름 % 기준 (0%에 가까울수록 조금, 100%에 가까울수록 사리)")
        BIN_LABELS = ["0~20%", "21~40%", "41~60%", "61~80%", "81~100%"]
        t["물세기 구간"] = pd.cut(t["물세기(%)"], bins=[-1, 20, 40, 60, 80, 100], labels=BIN_LABELS).astype(str)
        g = t.groupby("물세기 구간").agg(
            분위기=("score", "mean"), 주꾸미=("jj_med", "mean"), 갑오징어=("gg_med", "mean"),
            오전=("am", "mean"), 오후=("pm", "mean"), 일수=("score", "size")).reindex(BIN_LABELS).dropna(
            subset=["분위기"]).reset_index()
        order = g["물세기 구간"].tolist()

        k1, k2 = st.columns(2)
        with k1:
            st.markdown("**평균 분위기 %**")
            base = alt.Chart(g).encode(x=alt.X("물세기 구간:N", sort=order, title=None))
            st.altair_chart((base.mark_line(color="#0b7285", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
                y=alt.Y("분위기:Q", scale=alt.Scale(domain=[0, 100]), title="평균 분위기 %"),
                tooltip=["물세기 구간", alt.Tooltip("분위기:Q", format=".0f"), "일수"])
                + base.mark_text(dy=-14).encode(y="분위기:Q", text=alt.Text("분위기:Q", format=".0f"))
            ).properties(height=260), width="stretch")
        with k2:
            st.markdown("**주꾸미 중앙값 평균 (마리)**")
            jb = alt.Chart(g.dropna(subset=["주꾸미"])).encode(x=alt.X("물세기 구간:N", sort=order, title=None))
            st.altair_chart((jb.mark_line(color="#e8590c", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
                y=alt.Y("주꾸미:Q", title="평균 마리"),
                tooltip=["물세기 구간", alt.Tooltip("주꾸미:Q", format=".0f"), "일수"])
                + jb.mark_text(dy=-14).encode(y="주꾸미:Q", text=alt.Text("주꾸미:Q", format=".0f"))
            ).properties(height=260), width="stretch")

        gcnt = t.dropna(subset=["gg_med"]).groupby("물세기 구간").agg(
            갑오징어=("gg_med", "mean"), 갑오징어최고=("gg_max", "mean"), 기록일수=("gg_med", "size")
        ).reindex(order).dropna(subset=["갑오징어"]).reset_index()
        k5, k6 = st.columns(2)
        with k5:
            st.markdown("**갑오징어 중앙값 평균 (마리)**")
            gb = alt.Chart(gcnt).encode(x=alt.X("물세기 구간:N", sort=order, title=None))
            st.altair_chart((gb.mark_line(color="#1971c2", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
                y=alt.Y("갑오징어:Q", title="평균 마리"),
                tooltip=["물세기 구간", alt.Tooltip("갑오징어:Q", format=".1f"),
                         alt.Tooltip("갑오징어최고:Q", format=".1f", title="최고 평균"), "기록일수"])
                + gb.mark_text(dy=-14).encode(y="갑오징어:Q", text=alt.Text("갑오징어:Q", format=".1f"))
            ).properties(height=260), width="stretch")
        with k6:
            st.markdown("**날짜별 물세기와 갑오징어 (중앙값)**")
            tg = t.dropna(subset=["gg_med"])
            gp = alt.Chart(tg).mark_circle(opacity=0.45, size=40, color="#1971c2").encode(
                x=alt.X("물세기(%):Q", scale=alt.Scale(domain=[0, 100]), title="물세기 %"),
                y=alt.Y("gg_med:Q", title="갑오징어 중앙값(마리)"),
                tooltip=["date", "mul", "물세기(%)", alt.Tooltip("gg_med:Q", title="중앙값"),
                         alt.Tooltip("gg_max:Q", title="최고"), "title"])
            gt = alt.Chart(tg).transform_loess("물세기(%)", "gg_med", bandwidth=0.6).mark_line(
                color="#c92a2a", size=3).encode(x="물세기(%):Q", y="gg_med:Q")
            st.altair_chart((gp + gt).properties(height=260), width="stretch")
        st.caption("갑오징어는 본문에 갑오징어 마릿수가 적힌 날만 집계해요. 빨간 선 = 추세")

        k3, k4 = st.columns(2)
        with k3:
            st.markdown("**오전·오후 조황 %**")
            seg = g.melt(id_vars=["물세기 구간"], value_vars=["오전", "오후"], var_name="시간대",
                         value_name="조황").dropna()
            st.altair_chart(alt.Chart(seg).mark_line(interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
                x=alt.X("물세기 구간:N", sort=order, title=None),
                y=alt.Y("조황:Q", scale=alt.Scale(domain=[0, 100]), title="평균 조황 %"),
                color=alt.Color("시간대:N", scale=alt.Scale(domain=["오전", "오후"], range=["#f59f00", "#7048e8"]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["물세기 구간", "시간대", alt.Tooltip("조황:Q", format=".0f")]).properties(height=260),
                width="stretch")
        with k4:
            st.markdown("**날짜별 물세기와 분위기**")
            pts = alt.Chart(t).mark_circle(opacity=0.45, size=40, color="#0b7285").encode(
                x=alt.X("물세기(%):Q", scale=alt.Scale(domain=[0, 100]), title="물세기 %"),
                y=alt.Y("score:Q", scale=alt.Scale(domain=[0, 100]), title="분위기 %"),
                tooltip=["date", "mul", "물세기(%)", alt.Tooltip("score:Q", title="분위기"), "title"])
            trend = alt.Chart(t).transform_loess("물세기(%)", "score", bandwidth=0.5).mark_line(
                color="#c92a2a", size=3).encode(x="물세기(%):Q", y="score:Q")
            st.altair_chart((pts + trend).properties(height=260), width="stretch")
            st.caption("빨간 선 = 추세")

        st.dataframe(g.round(1), hide_index=True, width="stretch")

    st.subheader("낚시 시간의 물 흐름과 조황")
    st.caption("남당항 출항 시각부터 오전/오후 구간에 들물·날물, 만조·간조가 언제 끼었는지에 따른 평균 조황 %")
    fa, fb = st.columns(2)
    for col, seg_k, flow_col, nm in ((fa, "am", "오전 물흐름", "오전"), (fb, "pm", "오후 물흐름", "오후")):
        tmp = df[[seg_k, flow_col]].copy()
        tmp["분류"] = tmp[flow_col].apply(flow_kind)
        g = tmp.dropna().groupby("분류").agg(평균=(seg_k, "mean"), 일수=(seg_k, "size")).reset_index()
        col.markdown(f"**{nm} 조황**")
        col.altair_chart(alt.Chart(g).mark_bar(color="#f59f00" if nm == "오전" else "#7048e8").encode(
            x=alt.X("평균:Q", scale=alt.Scale(domain=[0, 100]), title="평균 %"),
            y=alt.Y("분류:N", sort="-x", title=None),
            tooltip=["분류", alt.Tooltip("평균:Q", format=".0f"), "일수"]).properties(height=200), width="stretch")
    tmp = df[["am", "시작 물흐름"]].dropna()
    g = tmp.groupby("시작 물흐름").agg(오전평균=("am", "mean"), 일수=("am", "size")).round(0).reset_index()
    st.markdown("**시작할 때 물 흐름별 오전 조황**")
    st.dataframe(g, hide_index=True, width="content")

    st.subheader("시간대별 조황 (물때별 평균 %)")
    seg_long = df.melt(id_vars=["mul"], value_vars=[k for k, _ in SEGS], var_name="seg", value_name="v").dropna()
    seg_long["시간대"] = seg_long["seg"].map(dict(SEGS))
    hm_df = seg_long.groupby(["mul", "시간대"]).agg(평균=("v", "mean"), 일수=("v", "size")).reset_index()
    st.altair_chart(alt.Chart(hm_df).mark_rect().encode(
        x=alt.X("mul:N", sort=MUL_ORDER, title="물때"),
        y=alt.Y("시간대:N", sort=[nm for _, nm in SEGS], title=None),
        color=alt.Color("평균:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[20, 80]), title="평균 %"),
        tooltip=["mul", "시간대", alt.Tooltip("평균:Q", format=".0f"), "일수"]).properties(height=220),
        width="stretch")
    ss_ = seg_long.groupby("시간대").agg(평균=("v", "mean"), 일수=("v", "size")).reindex(
        [nm for _, nm in SEGS]).round(0).reset_index()
    st.dataframe(ss_, hide_index=True, width="content")
    st.caption("라마르타임·점심 전후는 본문에서 직접 언급된 날만 집계돼 표본이 적어요.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("월별")
        mm = df.groupby("월").agg(분위기=("score", "mean"), 주꾸미=("jj_med", "mean"),
                                 일수=("score", "size")).reset_index()
        st.altair_chart(alt.Chart(mm).mark_line(color="#5c940d", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
            x="월:O", y=alt.Y("주꾸미:Q", title="주꾸미 중앙값 평균(마리)"),
            tooltip=["월", alt.Tooltip("분위기:Q", format=".0f"), alt.Tooltip("주꾸미:Q", format=".0f"), "일수"]
        ).properties(height=240), width="stretch")
    with c2:
        st.subheader("연도별")
        yy = df.groupby("연도").agg(분위기=("score", "mean"), 일수=("score", "size")).reset_index()
        st.altair_chart(alt.Chart(yy).mark_line(color="#e8590c", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
            x="연도:O", y=alt.Y("분위기:Q", scale=alt.Scale(domain=[0, 100])),
            tooltip=["연도", alt.Tooltip("분위기:Q", format=".0f"), "일수"]
        ).properties(height=240), width="stretch")

# ---------------- 탭4: 산출 방식
with tab4:
    st.markdown(f"""
**분위기 %** (0~100) — 월별 가중치

| 월 | 조과(마릿수) | 본문 분위기 | 날씨 |
|---|---|---|---|
| 9월 | 60% | 30% | 10% |
| 10월 | 50% | 25% | 15% |
| 11월 | 40% | 40% | 20% |
| 12월 | 30% | 50% | 20% |

- **조과**: 본문의 손님별 마릿수("○○님은 주꾸미 127마리…")에서 그날 주꾸미 중앙값을 구하고,
  **같은 달** 다른 해 출조일과 비교한 백분위. (손님 3명 이상 기록된 날만)
- **본문 분위기**: "잘 나와, 폭발, 손맛, 꾸준히" ↔ "안 나와, 고전, 뜸, 아쉬" 표현 비율(제목 2배 가중)과
  오전·오후 시간대 조황 %의 평균
- **날씨**: 강풍·파도·비·안개·물색 탁함 언급은 감점, 잔잔·화창은 가점
- 마릿수 기록이 없는 날은 조과 몫을 본문·날씨에 비율대로 나눔. 본문이 비어 있는 2018년 일부는 제목만으로 산출.

**낚시 시간 (남당항 일출·일몰 기준)**
- 시작 = 남당항 일출 5분 전, 종료 = 일몰 20분 전 (날짜마다 계산, 오차 ±2분)
- 오전 = 시작~점심(기본 12:00, 사이드바에서 변경), 오후 = 점심~종료
- 물 흐름: 다음 물때가 만조면 들물, 간조면 날물, 만조·간조 전후 25분은 정조
- 구간 안에 만조·간조가 끼면 "들물→만조 08:40→날물"처럼 표시

**시간대별 조황** (오전 / 점심 전 / 점심 후 / 오후 / 라마르타임)
- 글은 시간 순서로 쓰여 있어서, 점심·식사 언급을 기준으로 앞은 오전, 뒤는 오후로 나눔 (언급이 없으면 글의 절반 지점)
- "오전·아침·초반", "오후·후반·막판" 같은 말이 있는 문장은 그 시간대로, 점심 언급 앞뒤 몇 문장은 점심 전/후로, "라마르타임" 언급 문장과 그 뒤 두 문장은 라마르타임으로 분류
- 각 시간대 문장의 "잘 나와, 꾸준히, 폭발, 웃었" ↔ "안 나와, 뜸, 끊겼, 울었" 비율로 % 산출. "터지지 않던"처럼 부정형은 반대로 셈
- "오전엔 웃고 오후에 울었던"처럼 시간대를 직접 평가한 문장과 제목은 가중치를 크게
- **60% 이상 🟢 잘 나옴 · 41~59% 🟡 보통 · 40% 이하 🔴 안 나옴**

**주꾸미·갑오징어 최고/중앙값/최저**: 본문에 마릿수가 적힌 손님들 중 가장 많이 잡은 수, 가운데 값, 가장 적게 잡은 수.

**물때·만조·간조·고저차·물세기**: 예약조회 앱과 같은 **바다타임 {bt.PORT_NAME} 월별 물때표** 기준.
- 만조·간조: 물때표의 시각
- 고저차: 그날 만조 높이 평균 − 간조 높이 평균
- 물세기 %: 물때표 ▲/▼ 변화량의 하루 평균을 바다타임 '물흐름 %'에 맞춘 기준으로 환산
  (사리→조금 201~732cm, 조금→사리 234~727cm = 0~100%)
- 바다타임에서 못 읽은 날은 사이드바에 조화상수 CSV를 올리면 추산값으로 채웁니다(물세기 제외).
""")
    st.divider()
    st.markdown(f"**버전 {APP_VERSION}** ({APP_DATE})")
    st.markdown("\n".join(f"- **{v}** · {t}" for v, t in CHANGELOG))
