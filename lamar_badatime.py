"""바다타임 남당항 물때표로 물때·만조·간조·고저차·물세기(%) 구하기.

선상24 예약조회 앱(streamlit_app.py)의 '조류세기' 계산과 같은 방식입니다.
- 페이지: https://www.badatime.com/356-YYYY-MM-01.html (남당항)
- 하루 블록의 '시각 (높이)'에서 만조·간조 시각과 높이를 읽음
- ▲/▼ 뒤 숫자(직전 물때와의 높이 변화)의 하루 평균으로 물세기 % 환산
  (남당항 기준값: 사리→조금 201~732cm, 조금→사리 234~727cm = 0~100%)
"""
import re
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import requests

PORT_CODE, PORT_NAME = 356, "남당항"
WEEK = "월화수목금토일"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DAY_RE = re.compile(r"(?m)^([월화수목금토일])\s+(\d{1,2})(?=\s|$)")
EVENT_RE = re.compile(r"(\d{1,2}:\d{2})\s*\(\s*(\d{1,4})\s*\)")
FLOW_ZERO, FLOW_FULL = 201.0, 732.0          # 사리 → 조금
FLOW_ZERO_UP, FLOW_FULL_UP = 234.0, 727.0    # 조금 → 사리


def fetch_html(url, tries=3, timeout=20):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(1.5 * (i + 1))
                continue
            r.raise_for_status()
            raw = r.content
            try:
                return raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                loose = raw.decode("utf-8", errors="replace")
                if loose.count("�") <= max(20, len(raw) // 2000):
                    return loose
                return raw.decode("cp949", errors="replace")
        except requests.RequestException as ex:
            last = ex
            time.sleep(1.5 * (i + 1))
    raise last or RuntimeError("페이지를 가져오지 못했습니다")


def clean_lines(html):
    try:
        import lxml.html
        root = lxml.html.document_fromstring(html)
        for el in root.xpath("//script|//style|//noscript"):
            el.drop_tree()
        text = "\n".join(root.itertext())
    except Exception:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
    out = []
    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw).strip()
        if s:
            out.append(s)
    return out


def parse_month(html, y, m):
    """물때표 텍스트 → {날짜: {mul, events[(구분, 'HH:MM', 높이)], range, flow, heights}}"""
    full = "\n".join(clean_lines(html))
    heads = list(DAY_RE.finditer(full))
    days = {}
    for i, mt in enumerate(heads):
        block = full[mt.end(): heads[i + 1].start() if i + 1 < len(heads) else len(full)]
        try:
            d = dt.date(y, m, int(mt.group(2)))
        except ValueError:
            continue
        if WEEK[d.weekday()] != mt.group(1) or d in days:
            continue
        ev = [(t, int(h)) for t, h in EVENT_RE.findall(block)][:4]
        heights = [h for _, h in ev]
        if len(heights) < 2 or max(heights) - min(heights) < 50:
            continue
        mid = sum(heights) / len(heights)
        events = [("만조" if h > mid else "간조", t, h) for t, h in ev]
        highs = [h for h in heights if h > mid] or [max(heights)]
        lows = [h for h in heights if h <= mid] or [min(heights)]
        mul = re.search(r"(\d{1,2}\s*물|조금|무시)", block)
        deltas = [abs(int(x)) for x in re.findall(r"[▲▼]\s*([+-]?\d{1,4})", block)][:4]
        days[d] = {
            "mul": mul.group(1).replace(" ", "") if mul else "",
            "events": events,
            "heights": heights,
            "range": round(sum(highs) / len(highs) - sum(lows) / len(lows)),
            "flow": round(sum(deltas) / len(deltas), 1) if deltas else None,
        }
    return days


def month(y, m, code=PORT_CODE):
    return parse_month(fetch_html(f"https://www.badatime.com/{code}-{y}-{m:02d}-01.html"), y, m)


def with_strength(all_days):
    """물세기 % 추가 (남당항 바다타임 '물흐름 %' 환산 기준)"""
    out = {}
    for d, v in all_days.items():
        pct = None
        if v.get("flow") is not None:
            prev = all_days.get(d - dt.timedelta(days=1), {}).get("flow")
            rising = prev is not None and v["flow"] > prev and len(v.get("heights", [])) >= 4
            z, f = (FLOW_ZERO_UP, FLOW_FULL_UP) if rising else (FLOW_ZERO, FLOW_FULL)
            pct = round((v["flow"] - z) / (f - z) * 100)
        else:
            win = [all_days[d + dt.timedelta(days=k)]["range"] for k in range(-7, 8)
                   if d + dt.timedelta(days=k) in all_days]
            lo, hi = min(win), max(win)
            pct = round((v["range"] - lo) / (hi - lo) * 100) if hi > lo else None
        out[d] = {**v, "pct": None if pct is None else max(0, min(100, pct))}
    return out


def months_for(dates):
    """날짜 목록에 필요한 (연, 월) — 각 달의 첫날 물세기 계산을 위해 전달도 포함"""
    need = set()
    for d in dates:
        need.add((d.year, d.month))
        p = d.replace(day=1) - dt.timedelta(days=1)
        need.add((p.year, p.month))
    return sorted(need)


def fetch_many(ym_list, workers=6):
    """여러 달을 동시에 받기 → (날짜별 결과, 오류 목록)"""
    days, errs = {}, []

    def one(ym):
        try:
            return ym, month(*ym), None
        except Exception as ex:
            return ym, {}, str(ex)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ym, res, err in ex.map(one, ym_list):
            if err or len(res) < 20:
                errs.append(f"{ym[0]}-{ym[1]:02d}: {err or f'{len(res)}일만 인식'}")
            days.update(res)
    return with_strength(days), errs
