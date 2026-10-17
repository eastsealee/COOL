"""조화상수(M2, S2, K1, O1)로 만조·간조 시각과 고저차를 계산하는 모듈.

- 국립해양조사원 '기준항 조화상수' CSV(공공데이터포털 15145395)를 읽습니다.
- 지각(위상)은 동경 135°(한국 표준시) 기준으로 가정합니다.
- 4개 분조만 쓰므로 시각은 ±30분, 높이는 수십 cm 정도 오차가 있을 수 있습니다.
"""
import io
import math
import datetime as dt

import pandas as pd

CONST = ["M2", "S2", "K1", "O1"]
NAMDANG = (36.538, 126.463)  # 남당항 (위도, 경도)


# ---------------------------------------------------------------- CSV 읽기
def _read_any(data: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            continue
    # 깨진 바이트가 조금 섞인 경우: UTF-8로 읽고 깨진 글자만 버림
    return pd.read_csv(io.StringIO(data.decode("utf-8", errors="ignore")))


def _find(cols, *keys, exclude=()):
    for c in cols:
        s = str(c).replace(" ", "")
        if all(k in s for k in keys) and not any(e in s for e in exclude):
            return c
    return None


def load_constants(data: bytes):
    """CSV 바이트 → 관측소별 조화상수 dict 목록"""
    df = _read_any(data)
    cols = list(df.columns)
    c_name = _find(cols, "관측소", "명") or _find(cols, "관측소") or cols[0]
    c_lat = _find(cols, "위도")
    c_lon = _find(cols, "경도")
    c_z0 = _find(cols, "평균해수면")
    amp, pha = {}, {}
    for k in CONST:
        amp[k] = _find(cols, k, "진폭")
        pha[k] = _find(cols, k, "지각") or _find(cols, k, "위상", exclude=("진폭",))
    missing = [k for k in CONST if amp[k] is None or pha[k] is None]
    if missing:
        raise ValueError(f"CSV에서 {', '.join(missing)} 진폭/지각 열을 찾지 못했습니다. 열 이름: {cols}")
    out = []
    for _, row in df.iterrows():
        try:
            C = {k: (float(row[amp[k]]), float(row[pha[k]])) for k in CONST}
        except (TypeError, ValueError):
            continue
        st = {
            "name": str(row[c_name]).strip(),
            "lat": float(row[c_lat]) if c_lat and pd.notna(row[c_lat]) else None,
            "lon": float(row[c_lon]) if c_lon and pd.notna(row[c_lon]) else None,
            "z0": float(row[c_z0]) if c_z0 and pd.notna(row[c_z0]) else 0.0,
            "C": C,
        }
        out.append(st)
    return out


def nearest(stations, lat=NAMDANG[0], lon=NAMDANG[1]):
    best, bd = None, 1e9
    for s in stations:
        if s["lat"] is None or s["lon"] is None:
            continue
        d = math.hypot(s["lat"] - lat, (s["lon"] - lon) * math.cos(math.radians(lat)))
        if d < bd:
            best, bd = s, d
    return best, bd * 111.0  # km 근사


# ---------------------------------------------------------------- 조석 계산
def _args(t: dt.datetime):
    j2000 = dt.datetime(2000, 1, 1, 12)
    T = (t - j2000).total_seconds() / 86400 / 36525
    s = 218.3165 + 481267.8813 * T
    h = 280.4661 + 36000.7698 * T
    N = 125.0445 - 1934.1363 * T
    hr = t.hour + t.minute / 60 + t.second / 3600
    Tm = 180 + 15 * hr
    Nr = math.radians(N)
    V = {"M2": 2 * Tm - 2 * s + 2 * h, "S2": 2 * Tm, "K1": Tm + h - 90, "O1": Tm - 2 * s + h + 90}
    f = {"M2": 1 - 0.037 * math.cos(Nr), "S2": 1.0,
         "K1": 1.006 + 0.115 * math.cos(Nr), "O1": 1.009 + 0.187 * math.cos(Nr)}
    u = {"M2": -2.1 * math.sin(Nr), "S2": 0.0, "K1": -8.9 * math.sin(Nr), "O1": 10.8 * math.sin(Nr)}
    return V, f, u


def height(t: dt.datetime, st) -> float:
    """t: 한국 표준시(KST) 시각 → 조위(cm, 평균해수면 z0 더함)"""
    V, f, u = _args(t)
    return st["z0"] + sum(f[k] * a * math.cos(math.radians(V[k] + u[k] - g)) for k, (a, g) in st["C"].items())


def day_curve(day: dt.date, st, step_min=10):
    t0 = dt.datetime.combine(day, dt.time())
    return [(t0 + dt.timedelta(minutes=step_min * i), height(t0 + dt.timedelta(minutes=step_min * i), st))
            for i in range(int(24 * 60 / step_min) + 1)]


def day_extrema(day: dt.date, st, step_min=2):
    t0 = dt.datetime.combine(day, dt.time()) - dt.timedelta(minutes=step_min)
    n = int(24 * 60 / step_min) + 2
    pts = [t0 + dt.timedelta(minutes=step_min * i) for i in range(n + 1)]
    hs = [height(t, st) for t in pts]
    ev = []
    for i in range(1, len(pts) - 1):
        if pts[i].date() != day:
            continue
        if hs[i] > hs[i - 1] and hs[i] >= hs[i + 1]:
            ev.append(("만조", pts[i], hs[i]))
        elif hs[i] < hs[i - 1] and hs[i] <= hs[i + 1]:
            ev.append(("간조", pts[i], hs[i]))
    return ev


def day_range(day: dt.date, st):
    """그날 최대 고저차(cm): 연속한 만조·간조 쌍 중 가장 큰 차이"""
    ev = day_extrema(day, st)
    if len(ev) < 2:
        return None, ev
    rng = max(abs(ev[i][2] - ev[i + 1][2]) for i in range(len(ev) - 1))
    return rng, ev
