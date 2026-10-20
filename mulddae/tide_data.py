"""물때 데이터 — 물때 시계(dial.py)에서 씀

데이터
- 물때(만조·간조·물때·일출몰·월출몰): 바다타임닷컴 월간 물때표 (인증키 불필요)
- 날씨·바람: Open-Meteo Forecast API (무료, 인증키 불필요)
- 파고·수온: Open-Meteo Marine API (무료, 인증키 불필요)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")
HERE = Path(__file__).parent
UA = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 이름: (바다타임 ID, 위도, 경도)  — 좌표는 날씨·파고 조회용 근사값
PORTS: dict[str, tuple[int, float, float]] = {
    "남당항 (홍성)": (356, 36.538, 126.452),
    "홍성죽도 (홍성)": (181, 36.535, 126.433),
    "궁리항 (홍성)": (1392, 36.585, 126.436),
    "오천항 (보령)": (355, 36.443, 126.519),
    "대천항 (보령)": (126, 36.329, 126.512),
    "무창포항 (보령)": (236, 36.249, 126.537),
    "원산도 (보령)": (353, 36.383, 126.430),
    "삽시도 (보령)": (352, 36.330, 126.360),
    "녹도항 (보령)": (350, 36.272, 126.255),
    "외연도항 (보령)": (125, 36.226, 126.084),
    "홍원항 (서천)": (523, 36.155, 126.502),
    "서천마량 (서천)": (123, 36.128, 126.505),
    "영목항 (태안)": (354, 36.400, 126.427),
    "드르니항 (태안)": (1399, 36.531, 126.351),
    "백사장항 (태안)": (175, 36.585, 126.316),
    "방포항 (태안)": (358, 36.491, 126.344),
    "마검포방파제 (태안)": (1400, 36.605, 126.297),
    "안흥항 (태안)": (1410, 36.676, 126.137),
    "안흥신진도 (태안)": (132, 36.675, 126.130),
    "모항항 (태안)": (134, 36.765, 126.140),
    "만리포항 (태안)": (631, 36.787, 126.143),
    "학암포 (태안)": (136, 36.896, 126.199),
    "간월도항 (서산)": (129, 36.605, 126.410),
    "삼길포항 (서산)": (144, 37.000, 126.453),
    "장고항 (당진)": (370, 37.004, 126.546),
    "왜목항 (당진)": (180, 37.033, 126.528),
    "궁평항 (화성)": (466, 37.115, 126.680),
    "전곡항 (화성)": (618, 37.188, 126.652),
    "영흥도 (옹진)": (151, 37.255, 126.495),
    "인천": (158, 37.450, 126.590),
    "비응항 (군산)": (118, 35.938, 126.527),
    "선유도 (군산)": (115, 35.808, 126.414),
    "어청도 (군산)": (124, 36.117, 125.983),
    "격포항 (부안)": (430, 35.622, 126.467),
    "곰소항 (부안)": (188, 35.588, 126.610),
    "위도 (부안)": (112, 35.616, 126.300),
    "구시포항 (고창)": (343, 35.440, 126.430),
    "목포": (105, 34.780, 126.380),
    "진도항 (진도)": (1229, 34.375, 126.310),
}

# ---------------------------------------------------------------- 물때 파싱
ROW_RE = re.compile(r"(?<![가-힣\w])([일월화수목금토])\s+(\d{1,2})\s+(\d{1,2})\.(\d{1,2})\s+(무시|조금|\d{1,2}\s*물)")
TIDE_RE = re.compile(r"(\d{1,2}:\d{2})\s*\(\s*(-?\d+)\s*\)\s*([▲▼])\s*([+-]?\d+)")
PAIR_RE = re.compile(r"(\d{1,2}:\d{2})?\s*/\s*(\d{1,2}:\d{2})?")


def _hm(s: str | None) -> str | None:
    if not s:
        return None
    h, m = s.split(":")
    return f"{int(h):02d}:{m}"


def parse_month(text: str, year: int, month: int) -> dict[str, dict]:
    """바다타임 월간 물때표 페이지의 텍스트에서 날짜별 물때를 뽑는다."""
    text = re.sub(r"\s+", " ", text)
    matches = list(ROW_RE.finditer(text))
    days: dict[str, dict] = {}
    for i, m in enumerate(matches):
        day = int(m.group(2))
        if not 1 <= day <= 31:
            continue
        chunk = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else m.end() + 400]
        tides = []
        for t in TIDE_RE.finditer(chunk):
            tides.append({
                "t": _hm(t.group(1)),
                "h": int(t.group(2)),
                "type": "high" if t.group(3) == "▲" else "low",
                "diff": int(t.group(4)),
            })
        if not tides:
            continue
        rest = TIDE_RE.sub(" ", chunk)
        pairs = [p for p in PAIR_RE.finditer(rest) if p.group(1) or p.group(2)]
        sun = pairs[0] if pairs else None
        moon = pairs[1] if len(pairs) > 1 else None
        try:
            key = datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
        if key in days:  # 같은 날짜가 페이지에 두 번 나오면 첫 번째(표)를 쓴다
            continue
        tides.sort(key=lambda e: e["t"])
        days[key] = {
            "lunar": f"{int(m.group(3))}.{int(m.group(4))}",
            "mul": m.group(5).replace(" ", ""),
            "tides": tides,
            "sunrise": _hm(sun.group(1)) if sun else None,
            "sunset": _hm(sun.group(2)) if sun else None,
            "moonrise": _hm(moon.group(1)) if moon else None,
            "moonset": _hm(moon.group(2)) if moon else None,
        }
    return days


# 조류세기 — 선상낚시 예약조회(sunsang24/streamlit_app.py)의 tide_with_strength와 같은 계산
# ▲/▼ 뒤 숫자(직전 물때와의 높이 변화 cm)의 하루 평균 = 바다타임 '물흐름'과 비례하는 지표
# 남당항(356)은 바다타임 물흐름%와 대조해 맞춘 기준값, 다른 항구는 불러온 석 달 안에서 최약 0% ~ 최강 100%
FLOW_ZERO, FLOW_FULL = 201.0, 732.0           # 사리 → 조금 (물살이 약해지는 기간)
FLOW_ZERO_UP, FLOW_FULL_UP = 234.0, 727.0     # 조금 → 사리 (물살이 세지는 기간)
FLOW_CALIBRATED = {356}


def add_flow(days: dict[str, dict], code: int) -> None:
    for d in days.values():
        deltas = [abs(e["diff"]) for e in d["tides"]][:4]
        d["_flow"] = round(sum(deltas) / len(deltas), 1) if deltas else None
    flows = [d["_flow"] for d in days.values() if d["_flow"] is not None]
    fmin, fmax = (min(flows), max(flows)) if flows else (0, 0)
    for key in sorted(days):
        d, f = days[key], days[key]["_flow"]
        if f is None:
            pct = None
        elif code not in FLOW_CALIBRATED:
            pct = round((f - fmin) / (fmax - fmin) * 100) if fmax > fmin else None
        else:
            prev_key = (datetime.strptime(key, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            prev = days.get(prev_key, {}).get("_flow")
            rising = prev is not None and f > prev and len(d["tides"]) >= 4
            z, full = (FLOW_ZERO_UP, FLOW_FULL_UP) if rising else (FLOW_ZERO, FLOW_FULL)
            pct = round((f - z) / (full - z) * 100)
        d["flow"] = 0 if pct is None else max(0, min(100, pct))
    for d in days.values():
        d.pop("_flow", None)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_month(pid: int, year: int, month: int) -> dict[str, dict]:
    url = f"https://www.badatime.com/{pid}-{year}-{month:02d}-01.html"
    r = requests.get(url, headers={**UA, "Referer": "https://www.badatime.com/"}, timeout=15)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
        r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    return parse_month(soup.get_text(" "), year, month)


# ---------------------------------------------------------------- 날씨·파고
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_weather(lat: float, lon: float, past_days: int = 1, forecast_days: int = 7) -> list[dict]:
    common = {"latitude": lat, "longitude": lon, "timezone": "Asia/Seoul",
              "past_days": past_days, "forecast_days": forecast_days}
    f = requests.get("https://api.open-meteo.com/v1/forecast", params={
        **common,
        "hourly": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation,is_day",
        "wind_speed_unit": "ms",
    }, timeout=15).json()["hourly"]
    try:
        mr = requests.get("https://marine-api.open-meteo.com/v1/marine", params={
            **common, "hourly": "wave_height,wave_period,wave_direction,sea_surface_temperature",
        }, timeout=15).json().get("hourly", {})
    except Exception:
        mr = {}
    marine = {t: i for i, t in enumerate(mr.get("time", []))}

    def mv(name, t):
        i = marine.get(t)
        vals = mr.get(name) or []
        return vals[i] if i is not None and i < len(vals) else None

    out = []
    for i, t in enumerate(f["time"]):
        out.append({
            "time": t,
            "temp": f["temperature_2m"][i],
            "hum": f["relative_humidity_2m"][i],
            "wcode": f["weather_code"][i],
            "wspd": f["wind_speed_10m"][i],
            "wdir": f["wind_direction_10m"][i],
            "precip": f["precipitation"][i],
            "is_day": f["is_day"][i],
            "wave": mv("wave_height", t),
            "wper": mv("wave_period", t),
            "sst": mv("sea_surface_temperature", t),
        })
    return out


def load_days(pid: int, around: datetime, span_days: int = 11) -> tuple[dict[str, dict], list[str]]:
    """around 날짜 앞뒤 span_days일이 들어가는 달의 물때표를 모아 조류세기까지 계산"""
    months = sorted({((around + timedelta(days=k)).year, (around + timedelta(days=k)).month)
                     for k in (-span_days - 31, -span_days, 0, span_days)})
    days: dict[str, dict] = {}
    errors = []
    for y, m in months:
        try:
            days.update(fetch_month(pid, y, m))
        except Exception as e:  # 한 달이 실패해도 나머지는 보여준다
            errors.append(f"{y}년 {m}월: {e}")
    if days:
        add_flow(days, pid)
    return days, errors
