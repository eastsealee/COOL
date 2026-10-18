"""라마르호 예상 조과 분석 (2018~2026년 9~12월)
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

APP_VERSION = "v40"
APP_DATE = "2026-10-17"
CHANGELOG = [
    ("v40", "10월 분위기 % 가중치를 조과 50% · 본문 30% · 날씨 20%로 변경"),
    ("v39", "블로그 자동 갱신 시각을 매일 자정(오전 0시)으로 변경"),
    ("v38", "제목 아래 '2018~2026년 9~12월' 문구 삭제"),
    ("v37", "예상 갑오징어 아래 '2026 가중치 ×… 적용' 표시 삭제 (가중치 계산은 그대로)"),
    ("v36", "24시간 그래프 입질 확률을 쭈갑물때 모델로 계산 + 블로그 오전·오후 조황 보정, 주꾸미·갑오징어 오늘 점수·추천·최적 시간대"),
    ("v35", "2026·2027 예상: 물세기 아래에 24시간 물때·입질 확률 그래프(조위·주꾸미/갑오징어 확률·조류 세기·야간 표시)"),
    ("v34", "2026 예상 갑오징어 배율: 11·12월 ×2.0으로 지정 (10월 ×2.7 유지)"),
    ("v33", "마릿수는 '○○님은 주꾸미 N마리, 갑오징어 N마리'처럼 두 어종이 함께 적힌 문장만 사용"),
    ("v32", "블로그 새 조과 글을 매일 1번 자동으로 가져와 분석·반영 (GitHub Actions)"),
    ("v31", "제목을 '라마르호 예상 조과 분석'으로 변경"),
    ("v30", "2026 예상 갑오징어: 10월 배율을 ×2.7로 지정 (11·12월은 데이터 기준 전체 배율)"),
    ("v29", "2026 예상만 갑오징어 마릿수 가중치: 데이터 기준 월별 배율 자동 적용(9월 ×1.9, 10월 ×3.1 …), 직접 입력도 가능"),
    ("v28", "🔮 2026 예상 탭 추가: 2026-10-18 ~ 12-31 예상 달력(2027과 같은 방식, 같은 달 과거 기록 기준)"),
    ("v27", "2027 예상·추천: 9월은 9월 기록만, 10월은 10월 기록만… 같은 달 과거 기록으로만 분석"),
    ("v26", "추천일: 기본 9~12월 전체 10일, 물세기 30% 이하인 날 추천 점수 가중(+15%), 범위·일수·가중치 사이드바 조절"),
    ("v25", "2027 예상 달력: 추천일(달마다 예상 분위기 상위 N일) 날짜 숫자에 빨간 실선 원, 추천일 목록"),
    ("v24", "🔘 2027 버튼 달력 탭 삭제 (버튼 달력은 🔮 2027 예상 탭에 그대로)"),
    ("v23", "버튼 달력 테마 선택(기본: 눈 편한 어두운 달력 / 밝은 달력), 날짜 버튼이 칸 전체를 채우도록 수정"),
    ("v22", "'물세기 20% 미만인 날'을 '물세기 30% 이하인 날'로 변경 (목록·2027 달력 강조·예상표)"),
    ("v21", "버튼 달력: 물세기 0~20% 노란 실선, 21~30% 파란 실선이 칸 테두리를 따라 움직이는 애니메이션, 선택한 날짜를 검은 칸으로 표시"),
    ("v20", "물세기 분석: 주꾸미·갑오징어 중앙값을 한 곡선 그래프(양쪽 눈금)로, 점 그래프를 범위 띠+중앙값 선으로 대체"),
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

st.set_page_config(page_title=f"라마르호 예상 조과 분석 : {APP_VERSION}", page_icon="🦑", layout="wide")


MUL_ORDER = ["1물", "2물", "3물", "4물", "5물", "6물", "7물", "8물", "9물",
             "10물", "11물", "12물", "13물", "조금", "무시"]
TIDE_CYCLE = ["7물", "8물", "9물", "10물", "11물", "12물", "13물", "조금", "무시",
              "1물", "2물", "3물", "4물", "5물", "6물"]
WD = "월화수목금토일"
KST_TZ = dt.timezone(dt.timedelta(hours=9))
SEGS = [("am", "오전"), ("pre_lunch", "점심 전"), ("post_lunch", "점심 후"), ("pm", "오후"), ("lt", "라마르타임")]


def seg_label(v):
    if v is None or pd.isna(v):
        return "-"
    return "🟢 잘 나옴" if v >= 60 else ("🔴 안 나옴" if v <= 40 else "🟡 보통")




# ------------------------------------------------------------ 데이터
DATA_FILE = BASE / "data" / "lamar_days.json"
# 월별 분위기 % 가중치: (조과, 본문 분위기, 날씨)
WEIGHTS = {9: (0.60, 0.30, 0.10), 10: (0.50, 0.30, 0.20), 11: (0.40, 0.40, 0.20), 12: (0.30, 0.50, 0.20)}


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
st.sidebar.caption(f"블로그 데이터: {len(df)}일 · 마지막 조과 {df['date'].max()} (매일 자정 자동 갱신)")
CAL_THEME = st.sidebar.radio("예상 달력 테마", ["🌙 눈 편한 어두운 달력", "☀️ 밝은 달력"], index=0, horizontal=False,
                             key="cal_theme")
def gg26_ratios(d_):
    """2026년 갑오징어(날마다 중앙값의 평균) ÷ 다른 해 같은 달 평균 — 월별 배율과 전체 배율"""
    t = d_.dropna(subset=["gg_med"])
    out, rows = {}, []
    a_all = t[(t["연도"] == 2026)]
    b_all = t[(t["연도"] < 2026) & t["월"].isin(a_all["월"].unique())]
    overall = a_all["gg_med"].mean() / b_all["gg_med"].mean() if len(a_all) >= 5 and len(b_all) else 1.0
    for m in (9, 10, 11, 12):
        a = t[(t["연도"] == 2026) & (t["월"] == m)]["gg_med"]
        b = t[(t["연도"] < 2026) & (t["월"] == m)]["gg_med"]
        if len(a) >= 5 and len(b) >= 5:
            out[m] = a.mean() / b.mean()
            rows.append((f"{m}월", f"{a.mean():.1f} ({len(a)}일)", f"{b.mean():.1f} ({len(b)}일)", f"×{out[m]:.2f}"))
        else:
            out[m] = overall
            rows.append((f"{m}월", "기록 없음", f"{b.mean():.1f} ({len(b)}일)" if len(b) else "-",
                         f"×{overall:.2f} (전체 배율)"))
    return out, overall, rows


GG26_AUTO, GG26_ALL, GG26_ROWS = gg26_ratios(df)
GG26_FIXED = {10: 2.7, 11: 2.0, 12: 2.0}               # 사용자가 정한 배율 (10월 2.7배, 11·12월 2배)
for _m, _v in GG26_FIXED.items():
    _data_txt = f"데이터 ×{GG26_AUTO[_m]:.2f}" if _m not in (11, 12) else f"전체 배율 ×{GG26_ALL:.2f}"
    GG26_ROWS = [(r[0], r[1], r[2], f"×{_v:.2f} (지정 · {_data_txt})") if r[0] == f"{_m}월" else r
                 for r in GG26_ROWS]
    GG26_AUTO[_m] = _v
with st.sidebar.expander("🦑 2026 갑오징어 가중치", expanded=False):
    gg_mode = st.radio("적용 방식", ["📊 데이터 기준 (자동)", "✍️ 직접 입력"], index=0, key="gg26_mode")
    if gg_mode.startswith("📊"):
        GG26 = dict(GG26_AUTO)
        st.dataframe(pd.DataFrame(GG26_ROWS, columns=["월", "2026년", "다른 해", "배율"]), hide_index=True,
                     width="stretch")
        st.caption("날마다 갑오징어 중앙값의 평균을 같은 달끼리 비교. 10월은 2.7배, 11·12월은 2배로 지정했어요.")
    else:
        mval = st.slider("2026 예상 갑오징어 배율", 1.0, 4.0, round(GG26_ALL, 1), step=0.1, key="gg26_manual")
        GG26 = {m: mval for m in (9, 10, 11, 12)}
    st.caption("2026 예상의 갑오징어 마릿수에만 적용되고, 2027 예상에는 적용되지 않아요.")
with st.sidebar.expander("🔴 추천일 기준 (2026·2027 예상)", expanded=False):
    st.radio("고르는 범위", ["기간 전체에서", "달마다"], index=0, key="rec_scope", horizontal=True)
    st.slider("추천일 수", 3, 20, 10, key="rec_n")
    st.slider("물세기 30% 이하 가중치 (+%)", 0, 40, 15, step=5, key="rec_bonus",
              help="추천 점수 = 예상 분위기 × (1 + 가중치). 물세기 30% 이하인 날만 가중치를 받아요.")
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
st.title(f"🦑 라마르호 예상 조과 분석 : {APP_VERSION}")
st.caption(f"남당항 라마르호 '오늘의 조과' {len(df)}일 · 블로그 본문 분석 · "
           f"물때·조석·물세기는 바다타임 {bt.PORT_NAME} 기준")

tab1, tab8, tab5, tab6, tab2, tab3, tab4 = st.tabs(["📅 날짜별 조회", "🔮 2026 예상", "🔮 2027 예상", "🗓️ 2027 달력",
                                                    "📋 전체 목록", "📊 물때·시기 분석", "ℹ️ 산출 방식"])



# ------------------------------------------------------------ 24시간 물때 · 입질 확률 그래프
def _gauss(x, mu, sd):
    return math.exp(-0.5 * ((x - mu) / sd) ** 2)


def chart24(d: dt.date, am=None, pm=None):
    """조위 곡선 + 주꾸미·갑오징어 입질 확률(추정) + 조류 세기 — 어두운 24시간 그래프"""
    evs = []
    for k in (-1, 0, 1):                                  # 0시·24시 끝까지 곡선을 이으려고 앞뒤 날 물때도 사용
        dd = d + dt.timedelta(days=k)
        inf = tide_info(dd)
        if inf and inf.get("events"):
            evs += [(kind, dt.datetime.combine(dd, dt.time.fromisoformat(t if len(t) == 5 else "0" + t)), h)
                    for kind, t, h in inf["events"]]
    evs.sort(key=lambda x: x[1])
    if len(evs) < 3:
        st.caption("물때표가 없어 24시간 그래프를 그릴 수 없어요.")
        return
    t0 = dt.datetime.combine(d, dt.time())
    grid = [t0 + dt.timedelta(minutes=10 * i) for i in range(24 * 6 + 1)]

    def h_at(t):
        for (k1, a, h1), (k2, b, h2) in zip(evs, evs[1:]):
            if a <= t <= b:
                f = (t - a) / (b - a)
                return h1 + (h2 - h1) * (1 - math.cos(math.pi * f)) / 2
        return None

    H = [h_at(t) for t in grid]
    if any(v is None for v in H):
        st.caption("물때표가 부족해 24시간 그래프를 그릴 수 없어요.")
        return
    # --- 입질 확률: 쭈갑물때 모델(커뮤니티 물때 기준 점수화)을 그대로 옮김, 남당항(보령 대비 높이비 1.028) 선상 기준
    flow = [abs((H[min(i + 3, len(H) - 1)] - H[max(i - 3, 0)])) for i in range(len(H))]   # 1시간 조위 변화(막대용)
    fmax = max(flow) or 1
    _, _, rise, sett = sun.fishing_window(d)
    sr = rise.hour + rise.minute / 60
    ss = sett.hour + sett.minute / 60
    day_evs = [e for e in evs if e[1].date() == d]
    ext_h = [((e[1] - t0).total_seconds() / 3600, e[2], e[0] == "만조") for e in evs]
    rs = [abs(ext_h[i][1] - ext_h[i - 1][1]) for i in range(1, len(ext_h)) if ext_h[i][0] > -3 and ext_h[i - 1][0] < 27]
    day_range = sum(rs) / len(rs) if rs else 0
    RR = 1.028                                             # 남당항 높이비 (쭈갑물때 지역표)
    q = day_range / (700 * RR)
    r_ref = 175 * RR
    SEASON = {"jj": [0.4, 0.3, 0.75, 0.85, 0.6, 0, 0, 0, 1, 1, 0.8, 0.55],
              "gg": [0.2, 0.2, 0.35, 0.6, 0.75, 0.7, 0.55, 0.7, 0.9, 1, 0.7, 0.35]}
    sig = lambda v: 1 / (1 + math.exp(-v))
    gs = lambda v, m_, s_: math.exp(-((v - m_) ** 2) / (2 * s_ * s_))
    # 블로그 기록으로 예상한 오전·오후 조황으로 살짝 보정 (50% = 보정 없음, ±20%까지)
    am_f = max(0.8, min(1.2, 1 + ((am if am is not None else 50) - 50) / 125))
    pm_f = max(0.8, min(1.2, 1 + ((pm if pm is not None else 50) - 50) / 125))
    jj, gg, hourly = [], [], {}
    for i, t in enumerate(grid):
        x = i / 6
        rate = (h_at(t + dt.timedelta(minutes=1)) - h_at(t - dt.timedelta(minutes=1))) * 30 \
            if 0 < i < len(grid) - 1 else (H[min(i + 1, len(H) - 1)] - H[max(i - 1, 0)]) * 3
        c = abs(rate) / r_ref
        w = max((math.exp(-(((x - et - 0.6) / 1.4) ** 2)) for et, _, _ in ext_h), default=0)
        dl = sig((x - sr) / 0.35) * sig((ss - x) / 0.35)
        tw = max(gs(x, sr, 0.7), gs(x, ss, 0.7))
        eve = gs(x, ss + 2.2, 1.3)
        seg = am_f if x < 12 else pm_f
        out = {}
        for sp in ("jj", "gg"):
            if sp == "jj":
                day_p = 0.35 + 0.65 * gs(q, 0.40, 0.25)
                flow_p = 0.3 + 0.7 * gs(c, 0.28, 0.2)
                light = 0.3 + 0.7 * dl + 0.18 * tw
            else:
                day_p = 0.4 + 0.6 * gs(q, 0.62, 0.3)
                flow_p = 0.3 + 0.7 * gs(c, 0.45, 0.25)
                light = 0.42 + 0.48 * dl + 0.2 * tw + 0.12 * eve * (1 - dl)
            season = SEASON[sp][d.month - 1]
            raw = season * day_p * flow_p * (0.7 + 0.4 * w) * light * seg
            out[sp] = max(2 if season else 0, min(95, round(100 * raw / 1.12)))
        jj.append(out["jj"])
        gg.append(out["gg"])
        if i < len(grid) - 1:
            hourly.setdefault(int(x), []).append((out["jj"], out["gg"], dl))
    hours = [{"H": hh, "jj": round(sum(v[0] for v in vals) / len(vals)), "gg": round(sum(v[1] for v in vals) / len(vals)),
              "day": sum(v[2] for v in vals) / len(vals)} for hh, vals in sorted(hourly.items())]

    def day_score(sp):
        arr = sorted((o[sp] for o in hours if sp == "gg" or o["day"] > 0.5), reverse=True)[:3]
        return round(sum(arr) / len(arr)) if arr else 0

    def best_window(sp):
        mx = max(o[sp] for o in hours)
        if mx <= 2:
            return None
        thr = max(mx - 8, mx * 0.85)
        best = cur = None
        for o in hours:
            if o[sp] >= thr:
                cur = {"s": o["H"], "e": o["H"] + 1, "pk": max(o[sp], cur["pk"]) if cur else o[sp]} if not cur else \
                    {"s": cur["s"], "e": o["H"] + 1, "pk": max(cur["pk"], o[sp])}
            elif cur:
                if not best or cur["pk"] > best["pk"]:
                    best = cur
                cur = None
        if cur and (not best or cur["pk"] > best["pk"]):
            best = cur
        return best

    def verdict(sc):
        return ("추천", "#4FB97E") if sc >= 60 else (("조건부", "#E0A934") if sc >= 40 else ("비추천", "#E06464"))

    cards = []
    for sp, nm, col in (("jj", "주꾸미", "#EC7C5C"), ("gg", "갑오징어", "#9397EA")):
        sc = day_score(sp)
        vt, vc = verdict(sc)
        bw = best_window(sp)
        bw_txt = f"최적 <b>{bw['s']:02d}~{bw['e']:02d}시</b> · 최고 {bw['pk']}%" if bw else "-"
        cards.append(f"<div style='flex:1;min-width:220px;border-top:3px solid {col};padding:8px 4px 4px 4px'>"
                     f"<div style='display:flex;justify-content:space-between;align-items:center;font-weight:700'>{nm}"
                     f"<span style='font-size:12px;padding:1px 9px;border-radius:999px;border:1.5px solid {vc};color:{vc}'>{vt}</span></div>"
                     f"<div><span style='font-size:28px;font-weight:700;color:{col}'>{sc}</span>"
                     f"<span style='color:#8DA0A9'> / 100 오늘 점수</span></div>"
                     f"<div style='font-size:13.5px'>{bw_txt}</div></div>")
    st.markdown("<div style='display:flex;gap:14px;flex-wrap:wrap;background:#14181d;color:#E2EBEE;padding:10px 14px;"
                "border-radius:8px 8px 0 0'>" + "".join(cards) + "</div>", unsafe_allow_html=True)

    df24 = pd.DataFrame({"시각": grid, "조위": H, "주꾸미": jj, "갑오징어": gg})
    X = alt.X("시각:T", scale=alt.Scale(domain=[t0, t0 + dt.timedelta(hours=24)]),
              axis=alt.Axis(format="%-H시", tickCount=8, title=None, labelColor="#adb5bd", grid=False))
    night = pd.DataFrame([{"s": t0, "e": rise}, {"s": sett, "e": t0 + dt.timedelta(hours=24)}])
    shade = alt.Chart(night).mark_rect(color="#000000", opacity=0.35).encode(x="s:T", x2="e:T")
    now = dt.datetime.now(KST_TZ).replace(tzinfo=None)
    now_df = pd.DataFrame({"t": [now], "l": ["지금"]})
    now_layer = (alt.Chart(now_df).mark_rule(color="#ffffff", strokeDash=[5, 4]).encode(x="t:T")
                 if now.date() == d else None)
    now_txt = (alt.Chart(now_df).mark_text(y=-6, color="#ffffff", fontSize=12, fontWeight="bold").encode(x="t:T", text="l:N")
               if now.date() == d else None)
    XN = alt.X("시각:T", scale=alt.Scale(domain=[t0, t0 + dt.timedelta(hours=24)]),
               axis=alt.Axis(labels=False, ticks=False, title=None, grid=False, domain=False))
    W = 760

    # ① 조위
    ev_df = pd.DataFrame([{"시각": e[1], "조위": e[2], "라벨": ("▲" if e[0] == "만조" else "▼") + f"{e[1]:%H:%M} {e[2]:.0f}",
                           "dy": -12 if e[0] == "만조" else 14} for e in day_evs])
    tide = alt.Chart(df24).mark_area(line={"color": "#66b2d6", "strokeWidth": 3}, color="#66b2d6", opacity=0.18,
                                     interpolate="monotone").encode(
        x=XN, y=alt.Y("조위:Q", title="조위 cm", axis=alt.Axis(labelColor="#adb5bd", titleColor="#adb5bd",
                                                              gridColor="#2b3038")))
    tide_pts = alt.Chart(ev_df).mark_circle(size=70, color="#66b2d6").encode(x="시각:T", y="조위:Q")
    tide_lbl_hi = alt.Chart(ev_df[ev_df["dy"] < 0]).mark_text(dy=-12, color="#e9ecef", fontSize=12,
                                                            fontWeight="bold").encode(x="시각:T", y="조위:Q", text="라벨:N")
    tide_lbl_lo = alt.Chart(ev_df[ev_df["dy"] > 0]).mark_text(dy=16, color="#e9ecef", fontSize=12,
                                                            fontWeight="bold").encode(x="시각:T", y="조위:Q", text="라벨:N")
    top_layers = [shade, tide, tide_pts, tide_lbl_hi, tide_lbl_lo] + ([now_layer, now_txt] if now_layer is not None else [])
    top = alt.layer(*top_layers).properties(width=W, height=190)

    # ② 입질 확률
    long = df24.melt(id_vars=["시각"], value_vars=["주꾸미", "갑오징어"], var_name="어종", value_name="확률")
    pk = []
    for sp, key in (("주꾸미", "jj"), ("갑오징어", "gg")):
        i = int(pd.Series(df24[sp]).idxmax())
        bw = best_window(key)
        s_, e_ = ((t0 + dt.timedelta(hours=bw["s"]), t0 + dt.timedelta(hours=bw["e"])) if bw
                  else (grid[i] - dt.timedelta(minutes=60), grid[i] + dt.timedelta(minutes=60)))
        pk.append({"시각": grid[i], "확률": df24[sp][i], "어종": sp, "라벨": f"{df24[sp][i]:.0f}%", "s": s_, "e": e_})
    pk_df = pd.DataFrame(pk)
    colors = alt.Scale(domain=["주꾸미", "갑오징어"], range=["#ff8a5b", "#9b8cff"])
    peak_band = alt.Chart(pk_df).mark_rect(opacity=0.13).encode(x="s:T", x2="e:T",
                                                                color=alt.Color("어종:N", scale=colors, legend=None))
    lines = alt.Chart(long).mark_line(strokeWidth=3, interpolate="monotone").encode(
        x=XN, y=alt.Y("확률:Q", scale=alt.Scale(domain=[0, 100]), title="입질 확률 %",
                     axis=alt.Axis(values=[0, 25, 50, 75, 100], labelColor="#adb5bd", titleColor="#adb5bd",
                                   gridColor="#2b3038")),
        color=alt.Color("어종:N", scale=colors, legend=alt.Legend(orient="top-right", title=None, labelColor="#dee2e6",
                                                                  fillColor="#171c22", padding=6,
                                                                  labelExpr="datum.label + ' 확률'")),
        tooltip=[alt.Tooltip("시각:T", format="%H:%M"), "어종", alt.Tooltip("확률:Q", format=".0f")])
    pk_pts = alt.Chart(pk_df).mark_circle(size=90).encode(x="시각:T", y="확률:Q",
                                                         color=alt.Color("어종:N", scale=colors, legend=None))
    pk_lbl = alt.Chart(pk_df).mark_text(dy=-13, fontSize=13, fontWeight="bold").encode(
        x="시각:T", y="확률:Q", text="라벨:N", color=alt.Color("어종:N", scale=colors, legend=None))
    sun_df = pd.DataFrame([{"t": rise, "l": f"일출 {rise:%H:%M}"}, {"t": sett, "l": f"일몰 {sett:%H:%M}"}])
    sun_lbl = alt.Chart(sun_df).mark_text(y=6, color="#adb5bd", fontSize=11).encode(x="t:T", text="l:N")
    mid_layers = [shade, peak_band, lines, pk_pts, pk_lbl, sun_lbl] + ([now_layer] if now_layer is not None else [])
    mid = alt.layer(*mid_layers).properties(width=W, height=210)

    # ③ 조류 세기 (1시간 막대)
    hours = [t0 + dt.timedelta(hours=h) for h in range(24)]
    fl = pd.DataFrame({"s": hours, "e": [h + dt.timedelta(minutes=50) for h in hours],
                       "조류": [min(1.0, sum(flow[h * 6:(h + 1) * 6]) / 6 / r_ref) * 100 for h in range(24)]})
    bars = alt.Chart(fl).mark_rect(color="#56636e").encode(
        x=alt.X("s:T", scale=alt.Scale(domain=[t0, t0 + dt.timedelta(hours=24)]),
                axis=alt.Axis(format="%-H시", tickCount=8, title=None, labelColor="#adb5bd", grid=False)),
        x2="e:T", y=alt.Y("조류:Q", title="조류", axis=alt.Axis(labels=False, ticks=False, titleColor="#adb5bd",
                                                              grid=False)),
        tooltip=[alt.Tooltip("s:T", format="%H시", title="시각"), alt.Tooltip("조류:Q", format=".0f", title="조류 세기 %")])
    bot_layers = [shade, bars] + ([now_layer] if now_layer is not None else [])
    bot = alt.layer(*bot_layers).properties(width=W, height=70)

    chart = (alt.vconcat(top, mid, bot, spacing=6)
             .resolve_scale(color="independent")
             .properties(title=alt.TitleParams("24시간 물때 · 입질 확률 그래프", anchor="start", color="#f1f3f5",
                                               fontSize=15))
             .configure(background="#14181d")
             .configure_view(stroke=None, fill="#171c22")
             .configure_axis(domainColor="#495057", tickColor="#495057"))
    st.altair_chart(chart, width="stretch")
    sw = "display:inline-block;width:22px;height:4px;border-radius:2px;vertical-align:middle;margin:0 6px 0 14px;"
    st.markdown(
        "<div style='background:#14181d;color:#dee2e6;padding:6px 10px;border-radius:0 0 8px 8px;font-size:0.85rem;"
        "margin-top:-14px'>"
        f"<span style='{sw}background:#66b2d6'></span>조위(cm)"
        f"<span style='{sw}background:#ff8a5b'></span>주꾸미 확률"
        f"<span style='{sw}background:#9b8cff'></span>갑오징어 확률"
        f"<span style='{sw}height:10px;width:14px;background:#56636e'></span>조류 세기"
        "<span style='margin-left:14px;color:#868e96'>어두운 바탕 = 야간</span></div>", unsafe_allow_html=True)
    st.caption("입질 확률·오늘 점수는 쭈갑물때 모델(커뮤니티 물때 기준을 점수화: 하루 조차, 시간별 조류 세기, 물돌이 직후, "
               "일출·일몰, 시즌)을 남당항 선상 기준으로 계산하고, 블로그 기록으로 예상한 오전·오후 조황으로 ±20% 안에서 보정한 추정치예요.")


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
    """같은 달의 과거 출조일 중 물세기가 비슷한 날(±12%p, 물세기를 모르면 같은 물때)의 가중 평균
    — 9월은 9월 기록만, 10월은 10월 기록만 사용. 같은 달 안에서 날짜가 가까울수록 비중 큼"""
    d = c["date"]
    h = df[df["월"] == d.month].copy()                 # 같은 달 기록만
    h["_dd"] = (pd.to_datetime(h["date"]).dt.day - d.day).abs()
    if c["pct"] is not None and h["물세기(%)"].notna().any():
        h["_dp"] = (h["물세기(%)"] - c["pct"]).abs()
        near = h[h["_dp"] <= 12].copy()
        near["_w"] = (1 - near["_dd"] / 40) * (1 - near["_dp"] / 15)
        basis = f"{d.month}월 기록만 · 물세기 {c['pct']:.0f}%±12"
    else:
        near = h[h["mul"] == c["mul"]].copy()
        near["_w"] = 1 - near["_dd"] / 40
        basis = f"{d.month}월 기록만 · 같은 물때({c['mul']})"
    if len(near) < 5:                                  # 표본이 적으면 같은 달 전체로 넓힘
        near = h.copy()
        near["_w"] = 1 - near["_dd"] / 40
        basis = f"{d.month}월 기록 전체 (비슷한 물세기 표본 부족)"
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
    if d.year == 2026:                                 # 2026년만 갑오징어 가중치
        f = GG26.get(d.month, 1.0)
        for k in ("gg", "gg_max"):
            if out.get(k) is not None:
                out[k] = out[k] * f
        out["gg_boost"] = f
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


HOLIDAYS = {
    # 2026 (10/18 이후 예상 기간: 성탄절)
    "2026-10-03": "개천절", "2026-10-05": "대체공휴일", "2026-10-09": "한글날", "2026-12-25": "성탄절",
    # 2027
    "2027-09-14": "추석 연휴", "2027-09-15": "추석", "2027-09-16": "추석 연휴",
    "2027-10-03": "개천절", "2027-10-04": "대체공휴일",
    "2027-10-09": "한글날", "2027-10-11": "대체공휴일",
    "2027-12-25": "성탄절", "2027-12-27": "대체공휴일",
}
HOLIDAYS_2027 = {k: v for k, v in HOLIDAYS.items() if k.startswith("2027")}
WD_SUN = ["일", "월", "화", "수", "목", "금", "토"]


def button_calendar(P, prefix, year, months, state_key, start, end, note="날짜를 누르면 아래에 상세가 나와요."):
    """예상 기간 날짜 버튼 달력 — 흰 달력, 일요일 시작, 음력·공휴일 표시, 토·일·공휴일 빨강
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
        return "yellow" if p <= 20 else ("blue" if p <= 30 else "")

    dark = str(st.session_state.get("cal_theme", "🌙")).startswith("🌙")
    T = (dict(bg="#1f2329", line="#343a40", head="#868e96", text="#e9ecef", sub="#adb5bd", red="#ff8787",
              hover="#2b3038", sel_bg="#e9ecef", sel_txt="#1f2329", sel_red="#e03131", edge="#2b3038")
         if dark else
         dict(bg="#ffffff", line="#e9ecef", head="#343a40", text="#212529", sub="#868e96", red="#e03131",
              hover="#f8f9fa", sel_bg="#212529", sel_txt="#ffffff", sel_red="#ff8787", edge="#f1f3f5"))
    css = ["""
    /* 테두리를 따라 실선이 도는 애니메이션 (회전하는 원뿔 그라데이션) */
    @property --lamarAng { syntax:'<angle>'; inherits:false; initial-value:0deg; }
    @keyframes lamarRun { to { --lamarAng: 360deg; } }
    .run-yellow, .run-blue { border:3px solid transparent !important; animation: lamarRun 2.2s linear infinite; }
    .run-yellow { background: linear-gradient(BG,BG) padding-box,
        conic-gradient(from var(--lamarAng), #fcc419 0deg 110deg, #fff3bf 110deg 140deg, transparent 140deg 360deg) border-box !important; }
    .run-blue { background: linear-gradient(BG,BG) padding-box,
        conic-gradient(from var(--lamarAng), #1c7ed6 0deg 110deg, #d0ebff 110deg 140deg, transparent 140deg 360deg) border-box !important; }
    .lg { padding:2px 8px; border-radius:6px; font-size:0.85em; white-space:nowrap; display:inline-block; }
    .lg-bar { display:inline-block; width:46px; height:6px; border-radius:3px; vertical-align:middle;
              background:linear-gradient(90deg,#fa5252,#fab005,#37b24d); }
    .cal-title { text-align:center; font-size:2.1rem; font-weight:800; color:TXT; margin:6px 0 10px 0; }
    .cal-wd { text-align:center; font-size:0.95rem; font-weight:700; color:SUB; padding:4px 0 8px 0; }
    .cal-wd.red { color:RED; }
    .cal-empty { height:72px; }
    div[class*="st-key-PFX_m"] { background:BG !important; border-radius:14px; padding:4px 10px 6px 10px;
                                 border:1px solid EDGE; color:TXT; }
    div[class*="st-key-PFX_m"] [data-testid="stHorizontalBlock"] { gap:2px !important; }
    div[class*="st-key-PFX_m"] [data-testid="stColumn"] { min-width:0 !important; }
    div[class*="st-key-PFX_m"] [data-testid="stElementContainer"] { margin-bottom:0 !important; }
    div[class*="st-key-PFX_2"], div[class*="st-key-PFX_2"] > div, div[class*="st-key-PFX_2"] [data-testid="stTooltipHoverTarget"]
        { width:100% !important; }
    div[class*="st-key-PFX_hd"] { border-bottom:2px solid HEAD; margin-bottom:2px; }
    div[class*="st-key-PFX_wk"] { border-bottom:1px solid LINE; padding:2px 0; }
    div[class*="st-key-PFX_2"] button { width:100% !important; height:72px; padding:4px 0 6px 0 !important; border-radius:8px;
        background:transparent !important; border:none !important; box-shadow:none; color:TXT !important;
        line-height:1.2; }
    div[class*="st-key-PFX_2"] button p { font-size:0.72rem; margin:0; color:RED; }
    div[class*="st-key-PFX_2"] button p strong { font-size:1.55rem; font-weight:800; color:TXT; }
    div[class*="st-key-PFX_2"] button:hover { background:HOVER !important; }
    """.replace("PFX", prefix).replace("TXT", T["text"]).replace("SUB", T["sub"]).replace("RED", T["red"])
        .replace("BG", T["bg"]).replace("EDGE", T["edge"]).replace("HEAD", T["head"]).replace("LINE", T["line"])
        .replace("HOVER", T["hover"])]
    sel_iso = st.session_state[state_key].isoformat()
    rec_n = int(st.session_state.get("rec_n", 10))
    bonus = int(st.session_state.get("rec_bonus", 15)) / 100
    per_month = st.session_state.get("rec_scope", "기간 전체에서") == "달마다"
    R = P.dropna(subset=["예상 분위기"]).copy()
    R["추천 점수"] = R["예상 분위기"] * R["물세기"].apply(lambda v: 1 + bonus if pd.notna(v) and v <= 30 else 1.0)
    R = R.sort_values(["추천 점수", "주꾸미"], ascending=False)
    REC = set((R.groupby("월").head(rec_n) if per_month else R.head(rec_n))["date"])
    REC_SCORE = dict(zip(R["date"], R["추천 점수"]))
    for _, r in P.iterrows():
        kc = f"st-key-{prefix}_{r['date'].replace('-', '_')}"
        k = f"div.{kc}.{kc} button"          # 기본 버튼 스타일보다 우선 적용되도록 선택자를 강하게
        bar = f"inset 0 -5px 0 {_score_color(r['예상 분위기'])}"       # 칸 아래 분위기 막대
        rule = [f"box-shadow:{bar} !important;"]
        band = _band(r["물세기"])
        selected = r["date"] == sel_iso
        inner = T["sel_bg"] if selected else T["bg"]               # 선택한 날 = 반전 색 칸
        if band in ("yellow", "blue"):
            line_c, glow_c = ("#fcc419", "#fff3bf") if band == "yellow" else ("#1c7ed6", "#d0ebff")
            rule.append("border:3px solid transparent !important; animation: lamarRun 2.2s linear infinite;")
            rule.append(f"background: linear-gradient({inner},{inner}) padding-box, conic-gradient(from var(--lamarAng), "
                        f"{line_c} 0deg 110deg, {glow_c} 110deg 140deg, transparent 140deg 360deg) border-box !important;")
        elif selected:
            rule.append(f"background:{inner} !important;")
        if selected:
            rule.append("transform:scale(1.04); z-index:3;")
        css.append(k + " {" + " ".join(rule) + "}")
        d_ = dt.date.fromisoformat(r["date"])
        red_day = d_.weekday() >= 5 or r["date"] in HOLIDAYS      # 토·일·공휴일 빨강
        if selected:
            css.append(k + " p, " + k + " p strong { color:" + (T["sel_red"] if red_day else T["sel_txt"]) + " !important; }")
        elif red_day:
            css.append(k + " p strong { color:" + T["red"] + " !important; }")
        if r["date"] in REC:                                       # 추천일 = 숫자에 빨간 실선 원
            css.append(k + " p strong { display:inline-flex; align-items:center; justify-content:center; "
                           "width:2.0em; height:2.0em; border:2.5px solid #f03e3e; border-radius:50%; "
                           "line-height:1; margin-bottom:1px; }")
    st.markdown("<style>" + "\n".join(css) + "</style>", unsafe_allow_html=True)

    st.markdown(
        "<div style='line-height:2.2'>칸 아래 막대 = 예상 분위기 <span class='lg-bar'></span> (빨강 낮음 → 초록 좋음)"
        " · <span style='display:inline-flex;width:1.7em;height:1.7em;border:2.5px solid #f03e3e;border-radius:50%;"
        "align-items:center;justify-content:center;font-weight:800'>7</span> 추천일"
        " · 물세기 <span class='lg run-yellow'>0~20% 노란 실선</span> "
        f"<span class='lg run-blue'>21~30% 파란 실선</span> (테두리를 따라 움직여요) · {note}</div>",
        unsafe_allow_html=True)

    def _pick(iso):
        st.session_state[state_key] = dt.date.fromisoformat(iso)
        st.session_state[state_key + "_input"] = st.session_state[state_key]

    for pair in [months[i:i + 2] for i in range(0, len(months), 2)]:
        outer = st.columns(2, gap="medium")
        for oc, m in zip(outer, pair):
            with oc, st.container(key=f"{prefix}_m{m}"):
                st.markdown(f"<div class='cal-title'>{year}년 {m}월</div>", unsafe_allow_html=True)
                with st.container(key=f"{prefix}_hd{m}"):
                    hdr = st.columns(7)
                    for i, (hc, w) in enumerate(zip(hdr, WD_SUN)):
                        cls = "red" if i in (0, 6) else ""
                        hc.markdown(f"<div class='cal-wd {cls}'>{w}</div>", unsafe_allow_html=True)
                first = dt.date(year, m, 1)
                days_in = (dt.date(year + (m == 12), m % 12 + 1, 1) - first).days
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
                            d_ = dt.date(year, m, day)
                            iso = d_.isoformat()
                            hol = HOLIDAYS.get(iso)
                            if not (start <= d_ <= end):          # 예상 기간 밖(지난 날)은 흐리게만 표시
                                rc.markdown(f"<div style='height:72px;text-align:center;padding-top:6px;opacity:0.3;"
                                            f"font-size:1.55rem;font-weight:800'>{day}</div>", unsafe_allow_html=True)
                                continue
                            r = P[P["date"] == iso].iloc[0]
                            label = f"**{day}**" + (f"  \n{hol}" if hol else "  \n\u00a0")
                            pct_txt = f"{r['물세기']:.0f}%" if pd.notna(r["물세기"]) else "-"
                            rc.button(label, key=f"{prefix}_{iso.replace('-', '_')}", on_click=_pick, args=(iso,), width="stretch",
                                      help=f"{iso} ({WD[d_.weekday()]}){' · ' + hol if hol else ''} · {r['물때']} · "
                                           f"물세기 {pct_txt} · 예상 분위기 {r['예상 분위기']}% · "
                                           f"주꾸미 약 {r['주꾸미']:.0f}마리")

    rec_rows = P[P["date"].isin(REC)].sort_values("date")
    if len(rec_rows):
        scope_txt = f"달마다 {rec_n}일" if per_month else f"{months[0]}~{months[-1]}월 전체 {rec_n}일"
        st.markdown(f"**🔴 추천하는 날** ({scope_txt} · 물세기 30% 이하 +{bonus:.0%} 가중) · " + " ".join(
            f"`{r['월']}/{r['일']}({r['요일']}) 추천 {REC_SCORE[r['date']]:.0f}점`" for _, r in rec_rows.iterrows()))
    low_days = P[P["물세기"].notna() & (P["물세기"] <= 30)]
    if len(low_days):
        st.markdown("**물세기 30% 이하인 날** · " + " ".join(
            f"`{r['월']}/{r['일']}({r['요일']}) {r['물세기']:.0f}%`" for _, r in low_days.iterrows()))


def day_range(start, end):
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


@st.cache_data(show_spinner="예상 계산 중…")
def all_predictions(stamp, bt_keys, lunch, start_iso, end_iso, gg_boost=""):
    rows = []
    for d in day_range(dt.date.fromisoformat(start_iso), dt.date.fromisoformat(end_iso)):
        c = pred_conditions(d)
        p_ = predict(c)
        rows.append({"date": d.isoformat(), "월": d.month, "일": d.day, "요일": WD[d.weekday()],
                     "주": (d.day + d.replace(day=1).weekday() - 1) // 7, "물때": c["mul"],
                     "물세기": c["pct"], "예상 분위기": round(p_["score"]) if p_["score"] is not None else None,
                     "주꾸미": p_["jj"], "갑오징어": p_["gg"]})
    return pd.DataFrame(rows)


def forecast_tab(year, start, end, prefix, state_key):
    """예상 탭 한 개: 버튼 달력 + 선택한 날 상세 + 전체 예상표 (같은 달 과거 기록으로 분석)"""
    days = day_range(start, end)
    months = sorted({d.month for d in days})
    if state_key not in st.session_state:
        st.session_state[state_key] = start
    try:                                               # 그 기간 물때표 받아두기 (없으면 과거 평균으로 추정)
        BT.update(badatime_days(tuple(bt.months_for(days)))[0])
    except Exception:
        pass
    P_ = all_predictions(_st.st_mtime_ns, len([k for k in BT if k.startswith(str(year))]), str(LUNCH_T),
                         start.isoformat(), end.isoformat(),
                         str(sorted(GG26.items())) if year == 2026 else "")
    period = f"{start.month}월 {start.day}일 ~ {end.month}월 {end.day}일"
    st.subheader(f"{year}년 {period} 예상 달력")
    button_calendar(P_, prefix, year, months, state_key, start, end)

    in_key = state_key + "_input"
    if in_key not in st.session_state:
        st.session_state[in_key] = st.session_state[state_key]
    dsel = st.date_input(f"날짜 선택 ({year}년 {period})", min_value=start, max_value=end,
                         format="YYYY-MM-DD", key=in_key)
    st.session_state[state_key] = dsel

    c = pred_conditions(dsel)
    p_ = predict(c)
    st.divider()
    st.markdown(
        f"<h3 style='margin-bottom:0.3rem'>{dsel:%Y-%m-%d} ({WD[dsel.weekday()]}) 예상 · 음력 {c['lunar']} · "
        f"{c['mul']} : <span style='background:#ffe066;color:#000;padding:2px 10px;border-radius:6px;"
        f"font-size:0.8em'>가장 비슷했던 과거 출조일 평균</span></h3>", unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("예상 분위기", f"{p_['score']:.0f}%" if p_["score"] is not None else "-")
    m2.metric("예상 주꾸미 (중앙값 / 최고)", fish_txt(p_["jj"], p_["jj_max"], 0), help=MAX_HELP)
    m3.metric("예상 갑오징어 (중앙값 / 최고)", fish_txt(p_["gg"], p_["gg_max"], 1), help=MAX_HELP)
    m4.metric("물세기", f"{c['pct']:.0f}%" if c["pct"] is not None else "-", c["pct_src"], delta_color="off")
    if p_["score"] is not None:
        st.progress(min(1.0, p_["score"] / 100), text=f"예상 분위기 {p_['score']:.0f}%")
    chart24(dsel, p_.get("am"), p_.get("pm"))

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
        tide_block(dsel)
    else:
        st.info(f"{year}년 바다타임 물때표를 받지 못해 만조·간조 시각은 비어 있어요. "
                "물때는 음력으로, 물세기는 과거 같은 물때 평균으로 추정했어요.")

    st.caption(f"예상 근거: {p_['basis']} · 비슷한 과거 출조일 {p_['n']}일의 가중 평균 "
               "(같은 달 안에서 날짜가 가깝고 물세기가 비슷할수록 비중 큼)")
    sim = p_["similar"][["date", "mul", "물세기(%)", "score", "jj_med", "gg_med", "오전 평가", "오후 평가", "title", "link"]]
    st.markdown("**가장 비슷했던 과거 출조일**")
    st.dataframe(sim.rename(columns={"date": "날짜", "mul": "물때", "score": "분위기", "jj_med": "주꾸미 중앙값",
                                     "gg_med": "갑오징어 중앙값", "title": "제목", "link": "링크"}),
                 hide_index=True, width="stretch",
                 column_config={"분위기": st.column_config.ProgressColumn("분위기", format="%d%%", min_value=0, max_value=100),
                                "링크": st.column_config.LinkColumn("링크", display_text="원문")})

    st.markdown(f"**{year}년 {period} 전체 예상표**")
    P_show = P_.drop(columns=["주", "일"]).rename(columns={"date": "날짜"})
    P_show.insert(4, "물세기 30% 이하", P_["물세기"].apply(lambda v: "🔵" if pd.notna(v) and v <= 30 else ""))
    st.dataframe(P_show, hide_index=True, width="stretch",
                 height=360, column_config={
                     "예상 분위기": st.column_config.ProgressColumn("예상 분위기", format="%d%%", min_value=0, max_value=100),
                     "물세기": st.column_config.NumberColumn("물세기 %", format="%d"),
                     "주꾸미": st.column_config.NumberColumn("예상 주꾸미", format="%d"),
                     "갑오징어": st.column_config.NumberColumn("예상 갑오징어", format="%.1f")})
    st.download_button(f"{year} 예상표 CSV", P_.drop(columns=["주"]).to_csv(index=False).encode("utf-8-sig"),
                       f"lamar_{year}_예상_{APP_VERSION}.csv", "text/csv", key=f"dl_{prefix}")
    st.caption("예상치는 과거 블로그 기록의 평균이라 실제 조황·날씨와 다를 수 있어요. 날씨는 예측에 들어가지 않아요.")
    return P_


MUL_PCT = mul_pct_table(_st.st_mtime_ns, df)

with tab5:
    P = forecast_tab(2027, PRED_START, PRED_END, "c27", "pred_day")

with tab8:
    TODAY = dt.date(2026, 10, 18)
    forecast_tab(2026, TODAY, dt.date(2026, 12, 31), "c26", "pred_day26")


# ---------------- 탭6: 2027 달력 (깜빡임 없는 색칠 달력)
with tab6:
    st.subheader("2027년 9~12월 달력")
    st.markdown(
        "칸 색 = 예상 분위기 % (초록일수록 좋음) · "
        "<span style='border:3px solid #1864ab;padding:0 6px;border-radius:4px;font-weight:700;color:#1864ab'>"
        "파란 굵은 테두리·● = 물세기 30% 이하</span> · 칸에 마우스를 올리면 상세가 보여요. "
        "날짜별 상세는 🔮 2027 예상 탭에서 확인하세요.", unsafe_allow_html=True)
    cal_cols = st.columns(4)
    for col, m in zip(cal_cols, [9, 10, 11, 12]):
        sub = P[P["월"] == m]
        base = alt.Chart(sub).encode(
            x=alt.X("요일:N", sort=list(WD), title=None, axis=alt.Axis(orient="top", labelAngle=0)),
            y=alt.Y("주:O", title=None, axis=None))
        low = "datum['물세기'] != null && datum['물세기'] <= 30"
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
    low_days6 = P[P["물세기"].notna() & (P["물세기"] <= 30)]
    if len(low_days6):
        st.markdown("**물세기 30% 이하인 날** · " + " ".join(
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
    st.caption("주꾸미·갑오징어 최고/중앙값/최저는 '주꾸미 N마리, 갑오징어 N마리'가 함께 적힌 손님 3명 이상인 날만 계산해요.")

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
            ).properties(height=280), width="stretch")
        with k2:
            st.markdown("**주꾸미·갑오징어 중앙값 평균 (마리)**")
            fb = alt.Chart(g).encode(x=alt.X("물세기 구간:N", sort=order, title=None))
            jj_line = fb.mark_line(color="#e8590c", interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
                y=alt.Y("주꾸미:Q", title="주꾸미 (마리)", axis=alt.Axis(titleColor="#e8590c")),
                tooltip=["물세기 구간", alt.Tooltip("주꾸미:Q", format=".0f"), alt.Tooltip("갑오징어:Q", format=".1f"), "일수"])
            jj_txt = fb.mark_text(dy=-14, color="#e8590c").encode(y="주꾸미:Q", text=alt.Text("주꾸미:Q", format=".0f"))
            gg_line = fb.mark_line(color="#1971c2", strokeDash=[6, 3], interpolate="monotone", point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=3).encode(
                y=alt.Y("갑오징어:Q", title="갑오징어 (마리)", axis=alt.Axis(titleColor="#1971c2", orient="right")),
                tooltip=["물세기 구간", alt.Tooltip("주꾸미:Q", format=".0f"), alt.Tooltip("갑오징어:Q", format=".1f"), "일수"])
            gg_txt = fb.mark_text(dy=16, color="#1971c2").encode(y="갑오징어:Q", text=alt.Text("갑오징어:Q", format=".1f"))
            st.altair_chart(alt.layer(jj_line + jj_txt, gg_line + gg_txt).resolve_scale(y="independent")
                            .properties(height=280), width="stretch")
            st.caption("주황 실선 = 주꾸미(왼쪽 눈금) · 파랑 점선 = 갑오징어(오른쪽 눈금)")

        # 날짜별 값을 점으로 찍던 그래프 → 물세기 10% 단위 범위 띠(가운데 50%)와 중앙값 선으로 대체
        t["물세기10"] = (t["물세기(%)"] // 10 * 10).clip(upper=90) + 5

        def band_df(col):
            q = t.dropna(subset=[col]).groupby("물세기10")[col].agg(
                하위=lambda x: x.quantile(0.25), 중앙=lambda x: x.median(), 상위=lambda x: x.quantile(0.75),
                일수="size").reset_index()
            return q[q["일수"] >= 3]

        def band_chart(q, color, ytitle, fmt=".0f"):
            bb = alt.Chart(q).encode(x=alt.X("물세기10:Q", scale=alt.Scale(domain=[0, 100]), title="물세기 %"))
            area = bb.mark_area(opacity=0.25, color=color, interpolate="monotone").encode(
                y=alt.Y("하위:Q", title=ytitle), y2="상위:Q")
            line = bb.mark_line(color=color, strokeWidth=3, interpolate="monotone").encode(
                y="중앙:Q", tooltip=[alt.Tooltip("물세기10:Q", title="물세기 %(구간 가운데)"),
                                    alt.Tooltip("하위:Q", format=fmt, title="하위 25%"),
                                    alt.Tooltip("중앙:Q", format=fmt, title="중앙값"),
                                    alt.Tooltip("상위:Q", format=fmt, title="상위 25%"), "일수"])
            return area + line

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
                tooltip=["물세기 구간", "시간대", alt.Tooltip("조황:Q", format=".0f")]).properties(height=280),
                width="stretch")
        with k4:
            st.markdown("**물세기별 분위기 범위**")
            st.altair_chart(band_chart(band_df("score"), "#0b7285", "분위기 %").properties(height=280),
                            width="stretch")
            st.caption("띠 = 그 물세기에서 분위기가 나온 가운데 50% 범위 · 선 = 중앙값")

        k5, k6 = st.columns(2)
        with k5:
            st.markdown("**물세기별 주꾸미 범위 (그날 중앙값 기준)**")
            st.altair_chart(band_chart(band_df("jj_med"), "#e8590c", "주꾸미 (마리)").properties(height=280),
                            width="stretch")
        with k6:
            st.markdown("**물세기별 갑오징어 범위 (그날 중앙값 기준)**")
            st.altair_chart(band_chart(band_df("gg_med"), "#1971c2", "갑오징어 (마리)", ".1f").properties(height=280),
                            width="stretch")
        st.caption("물세기를 10% 단위로 묶어, 기록이 3일 이상인 구간만 표시해요.")

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
| 10월 | 50% | 30% | 20% |
| 11월 | 40% | 40% | 20% |
| 12월 | 30% | 50% | 20% |

- **조과**: "○○님은 주꾸미 123마리, 갑오징어 28마리"처럼 **두 어종이 함께 적힌 문장만** 마릿수로 쓰고, 그날 주꾸미 중앙값을 구해
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
