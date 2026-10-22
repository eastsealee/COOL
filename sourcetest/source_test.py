"""데이터 출처 비교 테스트 — 지금 앱이 쓰는 정보 vs 국립해양조사원·기상청 API

GitHub Actions(.github/workflows/source_test.yml)에서 실행합니다. 인증키는 저장소 Secret DATA_GO_KR_KEY.
결과: sourcetest/out/report.md (요약), sourcetest/out/raw/ (원본 응답 일부), sourcetest/out/archive/ (매일 쌓는 예보)

A. 물때(조석) — 보령 조위관측소 기준, 지난 14일
   실제 = 해양조사원 실측 조위에서 찾은 만조·간조
   비교 = ① 바다타임 보령(127) 예측  ② 해양조사원 조석예보(고·저조)
   + 남당항: 바다타임(356) vs 해양조사원 TideBED(남당항 좌표) 만조·간조 차이
A-2. 해양조사원 '조위관측소 실측·예측 조위 조회'(한 번에 실측+예측) — 보령 지난 7일

B. 바람 — 기상청 보령 관측소(ASOS 235) 실측 기준
   비교 = ① 기상청 단기예보 API(동네예보 격자) ② Open-Meteo 기상청 모델 ③ Open-Meteo 기본 모델 ④ GFS(윈드파인더 무료 예보)
   Open-Meteo는 '하루 전에 낸 예보'(previous_day1)를 지난 14일치 받아 바로 비교,
   기상청 단기예보 API는 지난 예보를 주지 않아 매일 실행하며 쌓은 예보로 비교 (며칠 지나야 표본이 생김)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import statistics
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RAW = OUT / "raw"
ARC = OUT / "archive"
for p in (OUT, RAW, ARC):
    p.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE.parent / "mulddae"))

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
TODAY = NOW.date()
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())   # 인코딩 키를 넣어도 동작하도록 한 번 풀어줌
UA = {"User-Agent": "Mozilla/5.0 (COOL source test)"}

KHOA_OBS = "DT_0025"                         # 보령 조위관측소
BORYEONG = (36.406, 126.486)
NAMDANG = (36.5333, 126.4667)
ASOS_ID, ASOS_POS = 235, (36.3272, 126.5574)  # 보령 ASOS
WONSAN = (36.38, 126.42)

report: list[str] = []
OBSPRE: list[dict] = []
log: list[str] = []


def say(s=""):
    print(s)
    report.append(s)


def note(s):
    print("  ·", s)
    log.append(s)


def mask(text):
    text = str(text)
    if KEY:
        for k in (KEY, quote(KEY, safe=""), quote_plus(KEY), quote(KEY)):
            text = text.replace(k, "***")
    return re.sub(r"(serviceKey=)[^&\s]+", r"\1***", text)


def dump(name, text):
    (RAW / f"{name}.txt").write_text(mask(text)[:6000], encoding="utf-8")


# ------------------------------------------------------------------ 공통 요청
def get(url, params=None, name=None, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if name:
                dump(name, f"{r.status_code} {r.url}\n\n{r.text}")
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def items_of(js):
    """공공데이터포털 응답에서 항목 목록 꺼내기 (구조가 조금씩 달라서 넓게 찾음)"""
    if isinstance(js, list):
        return js
    if not isinstance(js, dict):
        return []
    for path in (("response", "body", "items", "item"), ("body", "items", "item"), ("body", "items"),
                 ("response", "body", "items"), ("items", "item"), ("items",), ("data",), ("result", "data")):
        cur = js
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, list):
            return cur
        if isinstance(cur, dict) and cur:
            return [cur]
    for v in js.values():                    # 마지막 수단: 안쪽 어딘가의 dict 목록
        if isinstance(v, (dict, list)):
            got = items_of(v)
            if got:
                return got
    return []


def result_msg(text):
    m = re.search(r"<returnAuthMsg>(.*?)</returnAuthMsg>|<resultMsg>(.*?)</resultMsg>|\"resultMsg\"\s*:\s*\"(.*?)\"", text)
    return next((g for g in m.groups() if g), "") if m else ""


# ------------------------------------------------------------------ 해양조사원 API 주소 찾기
FALLBACK = {   # 공공데이터포털 영문 상세 페이지에서 확인한 주소 (2026-10-22)
    "15156018": ["https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"],   # 조석예보(고·저조)
    "15142507": ["https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService"],  # 실측·예측 조위
    "15156002": ["https://apis.data.go.kr/1192136/surveyTideLevel/GetSurveyTideLevelApiService"],  # (같은 것 사용)
    "15156026": ["https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService"],                 # TideBED
}


_DISC: dict = {}
_WORKS: dict = {}


def discover(ds_id):
    if ds_id in _DISC:
        return _DISC[ds_id]
    urls = []
    if ds_id in FALLBACK:
        _DISC[ds_id] = FALLBACK[ds_id]
        return FALLBACK[ds_id]
    try:
        for page in (f"https://www.data.go.kr/data/{ds_id}/openapi.do",
                     f"https://www.data.go.kr/catalog/{ds_id}/openapi.json"):
            t = requests.get(page, headers=UA, timeout=30).text
            dump(f"page_{ds_id}_{'json' if page.endswith('json') else 'do'}",
                 "\n".join(m.group(0) for m in re.finditer(r".{0,200}(apis\.data\.go\.kr|basePath|swagger|1192136).{0,200}", t)) or t[:3000])
            urls += re.findall(r"https?://apis\.data\.go\.kr/1192136/[A-Za-z0-9_/]+", t)
            # swagger 안에 basePath + path 로 나뉘어 있는 경우
            for base in re.findall(r"\"basePath\"\s*:\s*\"(/1192136/[^\"]+)\"", t):
                for path in re.findall(r"\"(/[A-Za-z0-9_]+)\"\s*:\s*\{\s*\"get\"", t):
                    urls.append("https://apis.data.go.kr" + base.rstrip("/") + path)
    except Exception as e:  # noqa: BLE001
        note(f"{ds_id} 상세 페이지 읽기 실패: {e}")
    seen, out = set(), []
    for u in urls + FALLBACK.get(ds_id, []):
        u = u.rstrip("/")
        if u not in seen:
            seen.add(u)
            out.append(u)
    note(f"{ds_id} 후보 주소: {out}")
    _DISC[ds_id] = out
    return out


def khoa_call(ds_id, label, extra):
    """후보 주소 × 변수 이름 조합을 차례로 시도해 항목이 나오는 첫 응답을 씀"""
    variants = [
        {"type": "json", "pageNo": 1, "numOfRows": 300, **extra},   # 한 번에 최대 300건
        {"type": "json", "pageNo": 1, "numOfRows": 300, **{k: v for k, v in extra.items() if k != "min"}},
    ]
    combos = [(ui, url, vi, v) for ui, url in enumerate(discover(ds_id)) for vi, v in enumerate(variants)]
    if ds_id in _WORKS:                      # 한 번 성공한 조합이 있으면 그것만
        combos = [c for c in combos if (c[0], c[2]) == _WORKS[ds_id]]
    for ui, url, vi, v in combos:
        if True:
            try:
                r = get(url, {"serviceKey": KEY, **v}, name=f"khoa_{label}_{ui}{vi}")
            except Exception as e:  # noqa: BLE001
                note(f"{label} 요청 실패 {url}: {e}")
                continue
            try:
                its = items_of(r.json())
            except ValueError:
                its = []
            if its:
                if ds_id not in _WORKS:
                    note(f"{label}: {url} {list(v)[0]} → {len(its)}건, 필드 {list(its[0])}, 예: {its[0]}")
                _WORKS[ds_id] = (ui, vi)
                return its
            if ds_id not in _WORKS:
                note(f"{label}: {url} ({r.status_code}) 항목 없음 {result_msg(r.text)[:80]} {r.text[:120]!r}")
    return []


# ------------------------------------------------------------------ 값 꺼내기 (필드 이름을 몰라도 되도록)
def _parse_time(v):
    s = re.sub(r"[^0-9]", "", str(v))
    for fmt, n in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d%H", 10)):
        if len(s) >= n:
            try:
                return dt.datetime.strptime(s[:n], fmt)
            except ValueError:
                pass
    return None


def pick_time(it):
    for k, v in it.items():
        if re.search(r"(dt|tm|time|date)", k, re.I):
            t = _parse_time(v)
            if t and t.year > 2000:
                if t.hour == 0 and t.minute == 0 and len(re.sub(r"[^0-9]", "", str(v))) <= 8:
                    continue
                return t
    return None


def pick_level(it):
    best = None
    for k, v in it.items():
        if re.search(r"(hgt|lvl|level|tdlv|tph|height|val)", k, re.I):
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if -200 < x < 1500:
                if re.search(r"(pred|fcst|bsc|tdlv|hgt)", k, re.I):
                    return x
                best = x if best is None else best
    return best


def pick_kind(it):
    for k, v in it.items():
        s = str(v)
        if re.search(r"(extr|hl|type|se|kind)", k, re.I):
            if re.search(r"(고조|만조|high|^H$|^1$|^3$)", s, re.I):
                return "high"
            if re.search(r"(저조|간조|low|^L$|^2$|^4$)", s, re.I):
                return "low"
    return None


def series(items):
    out = []
    for it in items:
        t, h = pick_time(it), pick_level(it)
        if t and h is not None:
            out.append((t, h, pick_kind(it)))
    out.sort()
    return out


def extremes_from_series(sr, gap_h=3.0):
    """실측 시계열 → 만조·간조 (40분 이동평균 후 앞뒤 2시간 안 최고·최저)"""
    if len(sr) < 20:
        return []
    ts = [t for t, _, _ in sr]
    hs = [h for _, h, _ in sr]
    step = max(1, round(statistics.median((ts[i + 1] - ts[i]).total_seconds() / 60 for i in range(len(ts) - 1))))
    w = max(1, round(20 / step))
    sm = [statistics.mean(hs[max(0, i - w): i + w + 1]) for i in range(len(hs))]
    span = max(2, round(120 / step))
    ex = []
    for i in range(span, len(sm) - span):
        win = sm[i - span: i + span + 1]
        if sm[i] == max(win) and (not ex or (ts[i] - ex[-1][0]).total_seconds() / 3600 > gap_h or ex[-1][2] != "high"):
            ex.append((ts[i], sm[i], "high"))
        elif sm[i] == min(win) and (not ex or (ts[i] - ex[-1][0]).total_seconds() / 3600 > gap_h or ex[-1][2] != "low"):
            ex.append((ts[i], sm[i], "low"))
    return ex


def badatime_extremes(pid, days_back=15, days_fwd=0):
    import tide_data as td
    months = sorted({((TODAY - dt.timedelta(days=k)).year, (TODAY - dt.timedelta(days=k)).month)
                     for k in range(-days_fwd, days_back + 1)})
    out = []
    for y, m in months:
        for day, v in td.fetch_month(pid, y, m).items():
            d = dt.date.fromisoformat(day)
            if TODAY - dt.timedelta(days=days_back) <= d <= TODAY + dt.timedelta(days=days_fwd):
                for e in v["tides"]:
                    hh, mm = map(int, e["t"].split(":"))
                    out.append((dt.datetime(d.year, d.month, d.day, hh, mm), float(e["h"]), e["type"]))
    out.sort()
    return out


def match(pred, truth, max_h=2.5):
    """예측 만조·간조마다 같은 종류의 가장 가까운 실제와 짝지어 (시간 오차 분, 높이 오차 cm)"""
    pairs = []
    for t, h, k in pred:
        cands = [(abs((t - tt).total_seconds()), tt, hh) for tt, hh, kk in truth if kk == k]
        if not cands:
            continue
        sec, tt, hh = min(cands)
        if sec <= max_h * 3600:
            pairs.append(((t - tt).total_seconds() / 60, h - hh))
    return pairs


def stat_line(name, pairs, bias_fix=False):
    if not pairs:
        return f"| {name} | – | – | – | – | 0 |"
    tm = [abs(a) for a, _ in pairs]
    hs = [b for _, b in pairs]
    bias = statistics.mean(hs)
    hm = statistics.mean(abs(b - (bias if bias_fix else 0)) for b in hs)
    return (f"| {name} | {statistics.mean(tm):.0f}분 | {max(tm):.0f}분 | {hm:.0f}cm | {bias:+.0f}cm | {len(pairs)} |")


# ------------------------------------------------------------------ A. 물때
def test_tide():
    say("## A. 물때(만조·간조) — 보령 조위관측소 실측 기준, 지난 14일")
    start = TODAY - dt.timedelta(days=14)
    obs_items, fc_items = [], []
    for k in range(15):
        d = start + dt.timedelta(days=k)
        if d >= TODAY:
            break
        ds = d.strftime("%Y%m%d")
        got = khoa_call("15142507", f"obs_{ds}", {"obsCode": KHOA_OBS, "reqDate": ds, "min": 10})
        OBSPRE.extend(got)
        obs_items += got
        fc_items += khoa_call("15156018", f"hl_{ds}", {"obsCode": KHOA_OBS, "reqDate": ds})
        if k == 0 and not obs_items and not fc_items:
            note("첫날 두 API 모두 응답 없음 → 나머지 날짜 생략")
            break
    sp = split_obs_pred(obs_items)
    obs = [(t, o, None) for t, o, _ in sp] if sp else series(obs_items)
    truth = extremes_from_series(obs)
    khoa_fc = [(t, h, k) for t, h, k in series(fc_items) if k]
    (OUT / "khoa_boryeong.json").write_text(json.dumps({
        "truth_extremes": [(t.isoformat(), round(h), k) for t, h, k in truth],
        "khoa_hl_forecast": [(t.isoformat(), h, k) for t, h, k in khoa_fc],
        "sample_obs_item": obs_items[:2], "sample_hl_item": fc_items[:2]}, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        bada = [e for e in badatime_extremes(127) if start <= e[0].date() < TODAY]
    except Exception as e:  # noqa: BLE001
        bada = []
        note(f"바다타임 보령 실패: {e}")
    note(f"실측 {len(obs)}점 → 만조·간조 {len(truth)}개 / 해양조사원 예보 {len(khoa_fc)} / 바다타임 {len(bada)}")
    if not truth:
        say("실측 조위를 받지 못해 비교 불가 (raw/khoa_obs_* 확인)")
    else:
        say("| 예측 출처 | 시간 오차(평균) | 시간 오차(최대) | 높이 오차(평균) | 높이 치우침 | 비교 수 |")
        say("|---|---|---|---|---|---|")
        say(stat_line("바다타임 보령(지금 앱)", match(bada, truth)))
        say(stat_line("해양조사원 조석예보", match(khoa_fc, truth)))
        say("")
        say("※ 높이는 관측소 기준면이 서로 다를 수 있어 '치우침'이 크면 기준면 차이, 평균 오차에서 치우침을 뺀 값이 실제 정확도")
        b2, k2 = match(bada, truth), match(khoa_fc, truth)
        if b2 and k2:
            say(f"- 치우침 뺀 높이 오차: 바다타임 {statistics.mean(abs(b - statistics.mean(x for _, x in b2)) for _, b in b2):.0f}cm · "
                f"해양조사원 {statistics.mean(abs(b - statistics.mean(x for _, x in k2)) for _, b in k2):.0f}cm")
    # 조류세기(물세기)용 ▲▼ 변화량이 같은지
    if bada and khoa_fc:
        def daily_flow(ex):
            by = {}
            for i in range(1, len(ex)):
                by.setdefault(ex[i][0].date(), []).append(abs(ex[i][1] - ex[i - 1][1]))
            return {d: statistics.mean(v[:4]) for d, v in by.items()}
        fb, fk = daily_flow(bada), daily_flow(khoa_fc)
        common = sorted(set(fb) & set(fk))
        if common:
            diffs = [fb[d] - fk[d] for d in common]
            say(f"- 하루 평균 ▲▼ 변화량(조류세기 계산값) 차이: 평균 {statistics.mean(abs(x) for x in diffs):.0f}cm "
                f"(바다타임−해양조사원 {statistics.mean(diffs):+.0f}cm, {len(common)}일)")
    say("")

    # 남당항: 관측소가 없어 실측 비교는 불가 → 바다타임 vs 해양조사원 TideBED 예측 차이만
    say("### 남당항 — 바다타임(356) vs 해양조사원 TideBED(남당항 좌표) 예측 차이, 오늘부터 7일")
    tb = []
    for k in range(7):
        ds = (TODAY + dt.timedelta(days=k)).strftime("%Y%m%d")
        tb += khoa_call("15156026", f"bed_{ds}", {"lat": NAMDANG[0], "lot": NAMDANG[1], "reqDate": ds, "min": 10})
        if k == 0 and not tb:
            break
    (OUT / "khoa_tidebed_namdang.json").write_text(json.dumps(tb[:1200], ensure_ascii=False), encoding="utf-8")
    sr = series(tb)
    bed_ex = extremes_from_series(sr) if len(sr) > 20 else [(t, h, k) for t, h, k in sr if k]
    try:
        bada_n = [e for e in badatime_extremes(356, days_back=0, days_fwd=6) if e[0].date() >= TODAY]
    except Exception as e:  # noqa: BLE001
        bada_n = []
        note(f"바다타임 남당 실패: {e}")
    if bed_ex and bada_n:
        say("| 비교 | 시간 차이(평균) | 시간 차이(최대) | 높이 차이(평균) | 높이 치우침 | 비교 수 |")
        say("|---|---|---|---|---|---|")
        say(stat_line("바다타임 − TideBED", match(bada_n, bed_ex)))
    else:
        say(f"TideBED {len(bed_ex)} · 바다타임 {len(bada_n)} — 비교 불가 (raw/khoa_bed_* 확인)")
    say("")


def split_obs_pred(items):
    """한 항목 안에 실측·예측 조위가 같이 있을 때 → [(시각, 실측, 예측)]"""
    out = []
    for it in items:
        t = pick_time(it)
        o = p = None
        for k, v in it.items():
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if not -200 < x < 1500 or re.search(r"(lat|lot|lon|cd|code)", k, re.I):
                continue
            if re.search(r"(pre|prd|fcst|est)", k, re.I):
                p = x if p is None else p
            elif re.search(r"(obs|srv|real|msr|hgt|lvl|tdlv|val)", k, re.I):
                o = x if o is None else o
        if t and o is not None and p is not None:
            out.append((t, o, p))
    out.sort()
    return out


def test_obs_pred():
    say("## A-2. 해양조사원 실측·예측 동시 조회 — 보령, 지난 7일")
    cut = dt.datetime.combine(TODAY - dt.timedelta(days=7), dt.time())
    rows = [r for r in split_obs_pred(OBSPRE) if r[0] >= cut]
    if not rows:
        say("받지 못함 (raw/khoa_obspre_*, raw/page_15142507_* 확인)")
        say("")
        return
    diff = [o - p for _, o, p in rows]
    bias = statistics.mean(diff)
    say(f"- {len(rows)}개 시각 비교: 실측−예측 평균 {bias:+.0f}cm, 치우침 뺀 평균 오차 "
        f"{statistics.mean(abs(x - bias) for x in diff):.0f}cm, 가장 크게 틀린 값 {max(abs(x) for x in diff):.0f}cm")
    truth = extremes_from_series([(t, o, None) for t, o, _ in rows])
    pred = extremes_from_series([(t, p, None) for t, _, p in rows])
    say("| 비교 | 시간 오차(평균) | 시간 오차(최대) | 높이 오차(평균) | 높이 치우침 | 비교 수 |")
    say("|---|---|---|---|---|---|")
    say(stat_line("해양조사원 예측 만조·간조", match(pred, truth)))
    try:
        bada = [e for e in badatime_extremes(127, days_back=8) if TODAY - dt.timedelta(days=7) <= e[0].date() < TODAY]
        say(stat_line("바다타임 보령 만조·간조", match(bada, truth)))
    except Exception as e:  # noqa: BLE001
        note(f"바다타임 보령 실패: {e}")
    say("")


# ------------------------------------------------------------------ B. 바람
def kma_grid(lat, lon):
    """위경도 → 기상청 동네예보 격자 (nx, ny)"""
    RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    DEG = math.pi / 180.0
    re_ = RE / GRID
    s1, s2, ol, oa = SLAT1 * DEG, SLAT2 * DEG, OLON * DEG, OLAT * DEG
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(math.tan(math.pi * 0.25 + s2 * 0.5) / math.tan(math.pi * 0.25 + s1 * 0.5))
    sf = math.tan(math.pi * 0.25 + s1 * 0.5) ** sn * math.cos(s1) / sn
    ro = re_ * sf / math.tan(math.pi * 0.25 + oa * 0.5) ** sn
    ra = re_ * sf / math.tan(math.pi * 0.25 + lat * DEG * 0.5) ** sn
    th = lon * DEG - ol
    th = (th + 2 * math.pi) % (2 * math.pi)
    th = th - 2 * math.pi if th > math.pi else th
    th *= sn
    return int(ra * math.sin(th) + XO + 0.5), int(ro - ra * math.cos(th) + YO + 0.5)


def kma_vilage(lat, lon, label):
    """기상청 단기예보: 가장 최근 발표분 (02,05,08,11,14,17,20,23시 발표, 10분 뒤부터 조회)"""
    nx, ny = kma_grid(lat, lon)
    t = NOW - dt.timedelta(minutes=15)
    base = None
    for k in range(0, 30):
        c = t - dt.timedelta(hours=k)
        if c.hour in (2, 5, 8, 11, 14, 17, 20, 23):
            base = c.replace(minute=0)
            break
    r = get("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
            {"serviceKey": KEY, "pageNo": 1, "numOfRows": 2000, "dataType": "JSON",
             "base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H00"), "nx": nx, "ny": ny},
            name=f"kma_vilage_{label}")
    try:
        its = items_of(r.json())
    except ValueError:
        its = []
    rows = {}
    for it in its:
        key = f"{it.get('fcstDate')}{it.get('fcstTime')}"
        rows.setdefault(key, {})[it.get("category")] = it.get("fcstValue")
    note(f"단기예보 {label} 격자 {nx},{ny} 발표 {base:%m-%d %H시} → {len(rows)}시간 {result_msg(r.text)[:60]}")
    return {"base": base.strftime("%Y%m%d%H"), "nx": nx, "ny": ny, "rows": rows}


def asos_hourly(days=14):
    """보령 ASOS 시간자료 (어제까지만 제공)"""
    end = TODAY - dt.timedelta(days=1)
    st_ = TODAY - dt.timedelta(days=days)
    r = get("https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList",
            {"serviceKey": KEY, "pageNo": 1, "numOfRows": 999, "dataType": "JSON", "dataCd": "ASOS", "dateCd": "HR",
             "startDt": st_.strftime("%Y%m%d"), "startHh": "00", "endDt": end.strftime("%Y%m%d"), "endHh": "23",
             "stnIds": ASOS_ID}, name="kma_asos")
    try:
        its = items_of(r.json())
    except ValueError:
        its = []
    out = {}
    for it in its:
        try:
            out[it["tm"][:13].replace(" ", "T")] = (float(it["ws"]), float(it["wd"]))
        except (KeyError, TypeError, ValueError):
            pass
    note(f"보령 ASOS {len(out)}시간 {result_msg(r.text)[:60]}")
    return out


def om_previous(lat, lon, days=14):
    models = "kma_gdps,kma_ldps,best_match,gfs_seamless"
    r = get("https://previous-runs-api.open-meteo.com/v1/forecast",
            {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m_previous_day1,wind_direction_10m_previous_day1",
             "models": models, "past_days": days, "forecast_days": 1, "wind_speed_unit": "ms", "timezone": "Asia/Seoul"},
            name="om_previous")
    h = r.json().get("hourly", {})
    out = {}
    for m in models.split(","):
        s, d = h.get(f"wind_speed_10m_previous_day1_{m}") or [], h.get(f"wind_direction_10m_previous_day1_{m}") or []
        out[m] = {t[:13]: (s[i], d[i]) for i, t in enumerate(h.get("time", [])) if i < len(s) and s[i] is not None}
    note("Open-Meteo 하루 전 예보: " + ", ".join(f"{m} {len(v)}시간" for m, v in out.items()))
    return out


def om_now(lat, lon):
    r = get("https://api.open-meteo.com/v1/forecast",
            {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,wind_direction_10m",
             "models": "kma_seamless,best_match,gfs_seamless", "forecast_days": 3, "wind_speed_unit": "ms",
             "timezone": "Asia/Seoul"}, name="om_now")
    return r.json().get("hourly", {})


def adiff(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def wind_line(name, fc, obs):
    """fc, obs: {'YYYY-MM-DDTHH': (속도, 방향)}"""
    common = [t for t in obs if t in fc and fc[t][0] is not None]
    if not common:
        return f"| {name} | – | – | – | – | 0 |"
    sp = [abs(fc[t][0] - obs[t][0]) for t in common]
    bias = statistics.mean(fc[t][0] - obs[t][0] for t in common)
    dirs = [adiff(fc[t][1], obs[t][1]) for t in common if obs[t][0] >= 2 and fc[t][1] is not None]
    hit = sum(1 for x in dirs if x <= 45) / len(dirs) * 100 if dirs else float("nan")
    return (f"| {name} | {statistics.mean(sp):.1f} m/s | {bias:+.1f} m/s | "
            f"{(statistics.mean(dirs) if dirs else float('nan')):.0f}° | {hit:.0f}% | {len(common)} |")


def test_wind():
    say("## B. 바람 — 기상청 보령 관측소(ASOS 235) 실측 기준")
    obs = asos_hourly()
    # 오늘 받은 예보 저장 (기상청 단기예보는 지난 예보를 주지 않아 매일 쌓아서 비교)
    snap = {"made": NOW.isoformat()}
    for label, (la, lo) in (("asos", ASOS_POS), ("wonsando", WONSAN), ("namdang", NAMDANG)):
        try:
            snap[f"kma_{label}"] = kma_vilage(la, lo, label)
        except Exception as e:  # noqa: BLE001
            note(f"단기예보 {label} 실패: {e}")
    try:
        snap["om_asos"] = om_now(*ASOS_POS)
    except Exception as e:  # noqa: BLE001
        note(f"Open-Meteo 현재 예보 실패: {e}")
    (ARC / f"fc_{NOW:%Y%m%d_%H%M}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    # 쌓인 기상청 단기예보 중 '하루 전(18~30시간 앞)' 예보로 실측 비교
    kma_fc = {}
    for f in sorted(ARC.glob("fc_*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            made = dt.datetime.fromisoformat(s["made"])
        except Exception:  # noqa: BLE001
            continue
        for key, v in (s.get("kma_asos") or {}).get("rows", {}).items():
            t = dt.datetime.strptime(key, "%Y%m%d%H%M").replace(tzinfo=KST)
            lead = (t - made).total_seconds() / 3600
            if 12 <= lead <= 36 and "WSD" in v and "VEC" in v:
                kma_fc[t.strftime("%Y-%m-%dT%H")] = (float(v["WSD"]), float(v["VEC"]))
    om_arc = {m: {} for m in ("kma_seamless", "best_match", "gfs_seamless")}
    for f in sorted(ARC.glob("fc_*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            made = dt.datetime.fromisoformat(s["made"])
        except Exception:  # noqa: BLE001
            continue
        h = s.get("om_asos") or {}
        for m in om_arc:
            sp_, dr_ = h.get(f"wind_speed_10m_{m}") or [], h.get(f"wind_direction_10m_{m}") or []
            for i, t in enumerate(h.get("time", [])):
                lead = (dt.datetime.fromisoformat(t).replace(tzinfo=KST) - made).total_seconds() / 3600
                if 12 <= lead <= 36 and i < len(sp_) and sp_[i] is not None:
                    om_arc[m][t[:13]] = (sp_[i], dr_[i] if i < len(dr_) else None)
    try:
        om = om_previous(*ASOS_POS)
    except Exception as e:  # noqa: BLE001
        om = {}
        note(f"Open-Meteo 하루 전 예보 실패: {e}")
    if not obs:
        say("보령 ASOS 실측을 받지 못해 비교 불가 (raw/kma_asos 확인)")
        say("")
        return
    say("하루 전에 낸 예보 vs 실제 (방향은 실측 2m/s 이상일 때만, '방향 적중' = 45° 안)")
    say("")
    say("**바로 비교 (Open-Meteo가 보관한 지난 14일 '하루 전 예보')**")
    say("")
    say("| 예보 출처 | 풍속 오차(평균) | 풍속 치우침 | 방향 오차(평균) | 방향 적중 | 비교 시간 |")
    say("|---|---|---|---|---|---|")
    say(wind_line("기상청 전구모델 GDPS (Open-Meteo)", om.get("kma_gdps", {}), obs))
    say(wind_line("기상청 국지모델 LDPS (Open-Meteo)", om.get("kma_ldps", {}), obs))
    say(wind_line("Open-Meteo 기본 모델 (예전 앱)", om.get("best_match", {}), obs))
    say(wind_line("GFS (윈드파인더 무료 예보)", om.get("gfs_seamless", {}), obs))
    say("")
    say("**매일 쌓은 예보로 비교 (며칠 지나야 숫자가 생김)**")
    say("")
    say("| 예보 출처 | 풍속 오차(평균) | 풍속 치우침 | 방향 오차(평균) | 방향 적중 | 비교 시간 |")
    say("|---|---|---|---|---|---|")
    say(wind_line("기상청 단기예보 API (직접)", kma_fc, obs))
    say(wind_line("Open-Meteo 기상청 모델 (지금 앱 v10.21)", om_arc["kma_seamless"], obs))
    say(wind_line("Open-Meteo 기본 모델 (예전 앱)", om_arc["best_match"], obs))
    say(wind_line("GFS (윈드파인더 무료 예보)", om_arc["gfs_seamless"], obs))
    say("")
    say(f"- 기상청 단기예보 API는 매일 쌓은 예보로만 비교 가능 — 현재 쌓인 비교 {sum(1 for t in obs if t in kma_fc)}시간, "
        "며칠 더 돌리면 늘어남")
    w = snap.get("kma_wonsando", {}).get("rows", {})
    if w:
        k0 = sorted(w)[0]
        say(f"- 참고: 기상청 단기예보에는 파고(WAV)도 있음 — 원산도 격자 {k0[4:6]}/{k0[6:8]} {k0[8:10]}시 "
            f"풍속 {w[k0].get('WSD')}m/s 풍향 {w[k0].get('VEC')}° 파고 {w[k0].get('WAV')}m")
    say("")


def test_mid():
    say("## C. 기상청 중기 해상예보 (3~10일 뒤) — 받아지는지만 확인")
    base = NOW.replace(hour=6 if NOW.hour >= 6 else 18, minute=0)
    if NOW.hour < 6:
        base -= dt.timedelta(days=1)
    elif NOW.hour >= 18:
        base = base.replace(hour=18)
    try:
        r = get("https://apis.data.go.kr/1360000/MidFcstInfoService/getMidSeaFcst",
                {"serviceKey": KEY, "pageNo": 1, "numOfRows": 10, "dataType": "JSON", "regId": "12A20000",
                 "tmFc": base.strftime("%Y%m%d%H00")}, name="kma_midsea")
        its = items_of(r.json())
        if its:
            it = its[0]
            say("서해중부 해상: " + ", ".join(f"{k}={v}" for k, v in list(it.items())[:14]))
        else:
            say(f"응답 없음: {result_msg(r.text)}")
    except Exception as e:  # noqa: BLE001
        say(f"실패: {e}")
    say("")


def main():
    say(f"# 데이터 출처 비교 테스트 — {NOW:%Y-%m-%d %H:%M} KST")
    say("")
    if not KEY:
        say("**DATA_GO_KR_KEY Secret이 없습니다.** 저장소 Settings → Secrets and variables → Actions 에 넣어 주세요.")
    for fn in (test_tide, test_obs_pred, test_wind, test_mid):
        try:
            fn()
        except Exception:  # noqa: BLE001
            say(f"**{fn.__name__} 오류**")
            say("```")
            say(traceback.format_exc()[-1500:])
            say("```")
    say("## 진행 기록")
    for s in log:
        say(f"- {mask(s)}")
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
