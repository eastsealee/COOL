"""물때 시계 '입질 확률'용 예상 오전·오후 조황 — 라마르호 예상 조과 분석(lamar/streamlit_app.py)의 predict()와 같은 방식

- 라마르호 블로그 기록(lamar/data/lamar_days.json) 중 같은 달의 출조일을 골라
  물세기가 비슷한 날(±12%p, 물세기를 모르면 같은 물때)을 날짜·물세기 차이로 가중 평균
- 오전·오후 물흐름 유형(만조 끼임 등)이 같은 날이 5일 이상이면 그 날들로 다시 평균
- 물세기·물흐름은 라마르 페이지와 같은 바다타임 남당항 물때표(lamar_badatime)로 계산
- 입질 확률 그래프 자체(쭈갑물때 모델)는 dial_component/index.html 에서 계산하고, 여기서 낸 오전·오후 값으로 ±20% 보정
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import streamlit as st

LAMAR = Path(__file__).resolve().parent.parent / "lamar"
if str(LAMAR) not in sys.path:
    sys.path.insert(0, str(LAMAR))
import lamar_badatime as lbt  # noqa: E402
import lamar_sun as lsun  # noqa: E402

DATA = LAMAR / "data" / "lamar_days.json"
REGIONS = {"인천", "경기", "충남"}          # 입질 확률을 보여주는 시·도 (라마르호 남당항 기록 기준이라 서해 중부만)
LUNCH = dt.time(12, 0)                     # 오전/오후 나누는 기준 (라마르 페이지 기본값)


@st.cache_data(ttl=None, show_spinner=False)
def _records(stamp: str) -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _tides(months: tuple) -> dict[str, dict]:
    days, _ = lbt.fetch_many(list(months))
    return {d.isoformat(): v for d, v in days.items()}


def _evt(d: dt.date, events):
    return sorted(((k, dt.datetime.combine(d, dt.time.fromisoformat(t if len(t) == 5 else "0" + t))) for k, t, _ in events),
                  key=lambda x: x[1])


def _flow_at(evs, t):
    for k, et in evs:
        if abs((et - t).total_seconds()) <= 25 * 60:
            return "만조 정조" if k == "만조" else "간조 정조"
    nxt = next(((k, et) for k, et in evs if et > t), None)
    if nxt:
        return "들물" if nxt[0] == "만조" else "날물"
    prv = [k for k, et in evs if et <= t]
    return ("날물" if prv[-1] == "만조" else "들물") if prv else "-"


def _window_flow(evs, t0, t1):
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
        parts += [f"{k} {et:%H:%M}", "날물" if k == "만조" else "들물"]
    return "→".join(parts)


def _flow_kind(text):
    if text in ("-", None) or not isinstance(text, str):
        return None
    if "만조" in text and "간조" in text:
        return "물돌이 2회"
    if "만조" in text:
        return "만조 끼임(들→날)"
    if "간조" in text:
        return "간조 끼임(날→들)"
    return text + " 내내"


def _cond(d: dt.date, info: dict | None) -> dict:
    """그날 물때·물세기·오전/오후 물흐름 (남당항 출항 기준: 일출 5분 전 ~ 일몰 20분 전, 점심 12시)"""
    c = {"mul": (info or {}).get("mul"), "pct": (info or {}).get("pct"), "am_flow": "-", "pm_flow": "-"}
    if info and info.get("events"):
        start, end, _, _ = lsun.fishing_window(d)
        lunch = dt.datetime.combine(d, LUNCH)
        evs = _evt(d, info["events"])
        c["am_flow"], c["pm_flow"] = _window_flow(evs, start, lunch), _window_flow(evs, lunch, end)
    return c


def _wmean(rows, key):
    v = [(r[key], r["_w"]) for r in rows if r.get(key) is not None and r["_w"] > 0]
    tw = sum(w for _, w in v)
    return sum(x * w for x, w in v) / tw if tw > 0 else None


def predictions(dates: list[str]) -> dict[str, dict]:
    """날짜(YYYY-MM-DD) 목록 → {날짜: {am, pm, n}} (같은 달 기록이 없으면 빠짐)"""
    if not DATA.exists() or not dates:
        return {}
    st_ = DATA.stat()
    recs = _records(f"{st_.st_mtime_ns}-{st_.st_size}")
    targets = [dt.date.fromisoformat(x) for x in dates]
    months = {t.month for t in targets}
    recs = [r for r in recs if int(r["date"][5:7]) in months]
    if not recs:
        return {}
    all_dates = [dt.date.fromisoformat(r["date"]) for r in recs] + targets
    try:
        tides = _tides(tuple(lbt.months_for(sorted(set(all_dates)))))
    except Exception:  # noqa: BLE001
        tides = {}
    rows = []
    for r in recs:
        d = dt.date.fromisoformat(r["date"])
        c = _cond(d, tides.get(r["date"]))
        rows.append({**r, "_d": d, "pct": c["pct"], "mul": c["mul"] or r.get("mul"),
                     "am_kind": _flow_kind(c["am_flow"]), "pm_kind": _flow_kind(c["pm_flow"])})
    out = {}
    for d in targets:
        c = _cond(d, tides.get(d.isoformat()))
        h = [x for x in rows if x["_d"].month == d.month]
        if not h:
            continue
        for x in h:
            x["_dd"] = abs(x["_d"].day - d.day)
        near = []
        if c["pct"] is not None and any(x["pct"] is not None for x in h):
            for x in h:
                if x["pct"] is not None and abs(x["pct"] - c["pct"]) <= 12:
                    near.append({**x, "_w": (1 - x["_dd"] / 40) * (1 - abs(x["pct"] - c["pct"]) / 15)})
        else:
            near = [{**x, "_w": 1 - x["_dd"] / 40} for x in h if x["mul"] == c["mul"]]
        if len(near) < 5:                      # 표본이 적으면 같은 달 전체
            near = [{**x, "_w": 1 - x["_dd"] / 40} for x in h]
        res = {"am": _wmean(near, "am"), "pm": _wmean(near, "pm"), "n": len(near)}
        for seg, kind in (("am", _flow_kind(c["am_flow"])), ("pm", _flow_kind(c["pm_flow"]))):
            if kind:
                same = [x for x in near if x[f"{seg}_kind"] == kind]
                if sum(1 for x in same if x.get(seg) is not None) >= 5:
                    res[seg] = _wmean(same, seg)
        out[d.isoformat()] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in res.items()}
    return out
