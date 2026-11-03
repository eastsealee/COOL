"""스토어 버전 입질 확률 보정용 '라마르호 예상 오전·오후 조황' — 개인 버전 personal/mulddae/bite.py 의 predictions()와 같은 방식
(라마르호 블로그 조과 기록 사용 — 허락 받음)
차이: 물때(만조·간조)를 바다타임 대신 해양조사원 조석예보(보령 DT_0025, 남당항과 가장 가까운 조석예보 지점)로 계산
- 같은 달 출조 기록 중 물세기가 ±12%p 안쪽인 날을 날짜·물세기 차이로 가중 평균 (물세기를 모르면 같은 물때)
- 오전·오후 물흐름 유형(만조 끼임 등)이 같은 날이 5일 이상이면 그 날들로 다시 평균
- 물세기(조류세기%)는 선상낚시 예약조회와 같은 계산: ▲▼ 변화량 하루 평균, 남당항 기준값(사리→조금 201~732cm, 조금→사리 234~727cm)
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "personal" / "lamar"))
import lamar_sun as lsun  # noqa: E402

RECORDS = ROOT / "personal" / "lamar" / "data" / "lamar_days.json"
LUNCH = dt.time(12, 0)
FLOW_ZERO, FLOW_FULL, FLOW_ZERO_UP, FLOW_FULL_UP = 201.0, 732.0, 234.0, 727.0


def pct_of(days_ex):
    """{date: [(datetime, h, 'high'|'low', diff)]} → {date: 물세기%} (남당항 기준값)"""
    flows = {}
    for d, ev in days_ex.items():
        ds = [abs(e[3]) for e in ev][:4]
        flows[d] = sum(ds) / len(ds) if ds else None
    out = {}
    for d in sorted(flows):
        f = flows[d]
        if f is None:
            out[d] = None
            continue
        prev = flows.get(d - dt.timedelta(days=1))
        rising = prev is not None and f > prev and len(days_ex[d]) >= 4
        z, full = (FLOW_ZERO_UP, FLOW_FULL_UP) if rising else (FLOW_ZERO, FLOW_FULL)
        out[d] = max(0, min(100, round((f - z) / (full - z) * 100)))
    return out


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


def _kind(text):
    if text in ("-", None):
        return None
    if "만조" in text and "간조" in text:
        return "물돌이 2회"
    if "만조" in text:
        return "만조 끼임(들→날)"
    if "간조" in text:
        return "간조 끼임(날→들)"
    return text + " 내내"


def _wmean(rows, key):
    v = [(r[key], r["_w"]) for r in rows if r.get(key) is not None and r["_w"] > 0]
    tw = sum(w for _, w in v)
    return sum(x * w for x, w in v) / tw if tw > 0 else None


def predictions(targets, ex, mul_of):
    """targets: [date], ex: {date: [(datetime, h, type, diff)]}(보령 조석예보), mul_of(date)→물때 이름
    → {YYYY-MM-DD: {am, pm, n}}"""
    recs = json.loads(RECORDS.read_text(encoding="utf-8"))
    pct = pct_of(ex)

    def cond(d):
        c = {"pct": pct.get(d), "am": None, "pm": None}
        evs = [("만조" if e[2] == "high" else "간조", e[0]) for e in ex.get(d, [])]
        if evs:
            start, end, _, _ = lsun.fishing_window(d)
            lunch = dt.datetime.combine(d, LUNCH)
            c["am"], c["pm"] = _kind(_window_flow(evs, start, lunch)), _kind(_window_flow(evs, lunch, end))
        return c

    months = {t.month for t in targets}
    rows = []
    for r in recs:
        d = dt.date.fromisoformat(r["date"])
        if d.month not in months:
            continue
        c = cond(d)
        rows.append({**r, "_d": d, "pct": c["pct"], "mul": r.get("mul") or mul_of(d), "am_kind": c["am"], "pm_kind": c["pm"]})
    out = {}
    for d in targets:
        c = cond(d)
        h = [x for x in rows if x["_d"].month == d.month]
        if not h:
            continue
        for x in h:
            x["_dd"] = abs(x["_d"].day - d.day)
        near = []
        if c["pct"] is not None and any(x["pct"] is not None for x in h):
            near = [{**x, "_w": (1 - x["_dd"] / 40) * (1 - abs(x["pct"] - c["pct"]) / 15)}
                    for x in h if x["pct"] is not None and abs(x["pct"] - c["pct"]) <= 12]
        else:
            near = [{**x, "_w": 1 - x["_dd"] / 40} for x in h if x["mul"] == mul_of(d)]
        if len(near) < 5:
            near = [{**x, "_w": 1 - x["_dd"] / 40} for x in h]
        res = {"am": _wmean(near, "am"), "pm": _wmean(near, "pm"), "n": len(near)}
        for seg in ("am", "pm"):
            if c[seg]:
                same = [x for x in near if x[f"{seg}_kind"] == c[seg]]
                if sum(1 for x in same if x.get(seg) is not None) >= 5:
                    res[seg] = _wmean(same, seg)
        out[d.isoformat()] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in res.items()}
    return out
