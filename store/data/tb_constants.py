"""전국 1,394개 항구의 조석 상수 받기 (해양조사원 TideBED) — Actions '자체 물때 상수 받기' (한 달에 한 번)
- 항구 좌표에서 자료가 없으면(좌표가 육지 쪽) 둘레 바다 쪽 좌표 몇 곳을 차례로 물어봄
- 그래도 없으면 가장 가까운 항구 값을 빌려 씀(borrow 표시)
- 결과: store/data/tb_constants.json  {항구 id: [이름, 위도, 경도, m2진폭, m2위상, s2진폭, s2위상, 평균해면, 빌린 항구 id 또는 0]}
  + 기준항(조석예보 지점) 상수: {"ref": {코드: [...]}}
"""
import datetime as dt, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote
import requests

ROOT = Path(__file__).resolve().parents[2]
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUTF = Path(__file__).resolve().parent / "tb_constants.json"
TB = "https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService"
HL = "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).date()
OFFS = [(0, 0)] + [(r * math.cos(a), r * math.sin(a)) for r in (0.01, 0.025, 0.05) for a in [k * math.pi / 4 for k in range(8)]]


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def get(url, params):
    for k in range(3):
        try:
            r = requests.get(url, params={"serviceKey": KEY, "type": "json", "pageNo": 1, "numOfRows": 3, **params}, timeout=40)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return items_of(r.json())
            return []
        except Exception:  # noqa: BLE001
            time.sleep(3 * (k + 1))
    return []


def consts(it):
    f = lambda k: round(float(it.get(k) or 0), 3)
    return [f("m2TdlvAmp"), f("m2TdlvTlag"), f("s2TdlvAmp"), f("s2TdlvTlag"), f("msl")]


def at(lat, lon):
    for dy, dx in OFFS:
        its = get(TB, {"lat": round(lat + dy, 5), "lot": round(lon + dx, 5), "reqDate": TODAY.strftime("%Y%m%d"), "min": 60})
        if its and float(its[0].get("m2TdlvAmp") or 0) > 0:
            return consts(its[0])
    return None


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(d - b) * math.cos(math.radians((a + c) / 2)), math.radians(c - a))


def main():
    ports = json.loads((ROOT / "personal/mulddae/data/ports.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda p: at(p["lat"], p["lon"]), ports))
    out = {}
    for p, c in zip(ports, res):
        if c:
            out[str(p["id"])] = [p["name"], p["lat"], p["lon"], *c, 0]
    miss = [p for p, c in zip(ports, res) if not c]
    for p in miss:                       # 가장 가까운 항구 값 빌리기
        best = min(((km(p["lat"], p["lon"], v[1], v[2]), k) for k, v in out.items() if not v[8]), default=None)
        if best and best[0] < 30:
            out[str(p["id"])] = [p["name"], p["lat"], p["lon"], *out[best[1]][3:8], int(best[1])]
    # 기준항 = 해양조사원 조석예보 지점 (DT_0001~0099)
    ref = {}

    def one(n):
        code = f"DT_{n:04d}"
        its = get(HL, {"obsCode": code, "reqDate": TODAY.strftime("%Y%m%d")})
        if not its:
            return None
        la, lo = float(its[0]["lat"]), float(its[0]["lot"])
        c = at(la, lo)
        return (code, [its[0].get("obsvtrNm", code), la, lo, *c]) if c else None
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(one, range(1, 100)):
            if r:
                ref[r[0]] = r[1]
    data = {"updated": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "fields": ["이름", "위도", "경도", "m2진폭", "m2위상", "s2진폭", "s2위상", "평균해면", "빌린항구"],
            "ports": out, "ref": ref}
    OUTF.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    nb = sum(1 for v in out.values() if v[8])
    print(f"항구 {len(out)}/{len(ports)} (직접 {len(out) - nb}, 빌림 {nb}, 없음 {len(ports) - len(out)}) · 기준항 {len(ref)}")
    if len(out) < len(ports) * 0.8:
        sys.exit("상수를 받은 항구가 너무 적음")


if __name__ == "__main__":
    main()
