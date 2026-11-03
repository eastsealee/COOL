"""한국 바다의 섬·무인도 이름표 자료 만들기 — GitHub Actions '섬 이름 자료 만들기'에서 실행
- 자료: OpenStreetMap (place=island / islet 중 이름이 있는 것) — Overpass API
- 결과: mulddae/dial_component/islands.json  [[이름, 위도, 경도, 종류(1=섬, 2=작은 섬·무인도)], ...]
  물때 시계 지도에서 화면에 보이는 섬에 이름표를 붙이는 데 씀
"""
import json
import sys
import time
from pathlib import Path

import requests

OUT = Path(__file__).parent / "dial_component" / "islands.json"
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
# 한국 바다 (서해·남해·동해·제주·울릉·독도) — 북한 쪽은 빼려고 위도 38.7까지
BBOXES = [(33.0, 124.0, 35.5, 127.6), (35.5, 124.0, 38.7, 127.6), (33.0, 127.6, 35.5, 131.9), (35.5, 127.6, 38.7, 131.9)]
Q = """[out:json][timeout:180];
(node["place"~"^(island|islet)$"]["name"]({b});
 way["place"~"^(island|islet)$"]["name"]({b});
 relation["place"~"^(island|islet)$"]["name"]({b}););
out center tags;"""


def fetch(bbox):
    b = ",".join(map(str, bbox))
    for k in range(6):
        url = SERVERS[k % len(SERVERS)]
        try:
            r = requests.post(url, data={"data": Q.format(b=b)}, timeout=240,
                              headers={"User-Agent": "jjugap-mulddae/1 (github.com/eastsealee/COOL)"})
            if r.status_code == 200:
                return r.json().get("elements", [])
            print(f"  {url} → {r.status_code}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {url} → {e}", flush=True)
        time.sleep(20)
    raise SystemExit(f"Overpass 실패: {bbox}")


def main():
    seen, out = set(), []
    for bb in BBOXES:
        els = fetch(bb)
        print(f"{bb}: {len(els)}개", flush=True)
        for e in els:
            t = e.get("tags", {})
            name = (t.get("name:ko") or t.get("name") or "").strip()
            if not name or not any("가" <= ch <= "힣" for ch in name):
                continue                                   # 한글 이름이 있는 섬만
            if e["type"] == "node":
                la, lo = e["lat"], e["lon"]
            else:
                c = e.get("center") or {}
                la, lo = c.get("lat"), c.get("lon")
            if la is None:
                continue
            key = (name, round(la, 3), round(lo, 3))
            if key in seen:
                continue
            seen.add(key)
            out.append([name, round(la, 5), round(lo, 5), 1 if t.get("place") == "island" else 2])
        time.sleep(5)
    out.sort(key=lambda x: (x[3], x[0]))
    if len(out) < 300:
        sys.exit(f"섬이 너무 적습니다: {len(out)}")
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"완료: 섬 {sum(1 for x in out if x[3] == 1)} · 작은 섬 {sum(1 for x in out if x[3] == 2)} → {OUT} ({OUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
