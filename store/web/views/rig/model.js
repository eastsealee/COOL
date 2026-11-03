/* 갑오징어·쭈꾸미 채비 계산 모델 (정적 모델 — 정확한 값이 아니라 '경향'을 보는 용도)

   근거: 궁디피싱 채비 과학 영상 3편
   - 조류는 수심 평균값(노트), 바닥 근처 유속은 1/7 법칙으로 줄어듦
   - 원줄이 눕는 정도는 '배와 물의 상대속도'로 정해짐 (배가 흐르면 그만큼 빼서 계산)
   - 단차 = 높이, 가짓줄 = 반경. 에기 높이 = 단차 − 가짓줄 × cos(가짓줄 각도)
   - 보정: 수심 10m · PE 0.8호 · 봉돌 20호 · 1노트(배가 조류를 향해 버팀) → 원줄 약 38° 가 되게 원줄 항력계수를 맞춤
           (같은 계산으로 0.5노트 · 16~18호 → 13~15° 도 맞음)
           1노트에서 단차 15 · 가짓줄 30 · 에기 2.5호는 바닥에 누움 (영상 결론과 같음)
   - 수심: 바닥 근처 물살(1/7 법칙) + 원줄이 누운 만큼 단차 매듭이 낮아지는 것(knotTilt)을 함께 반영
*/
(function (root) {
  "use strict";
  const RHO = 1025, G = 9.80665, KN = 0.514444, GF = G / 1000;   // 1 gf = 0.0098 N

  // PE 원줄 호수 → 지름(mm), 에스테르 가짓줄 호수 → 지름(mm)  (일본 표준 호수표)
  const PE_D = { 0.3: 0.090, 0.4: 0.104, 0.5: 0.117, 0.6: 0.128, 0.8: 0.148, 1: 0.165, 1.2: 0.185, 1.5: 0.205, 2: 0.235, 3: 0.285 };
  const ES_D = { 2: 0.235, 2.5: 0.260, 3: 0.285, 4: 0.330, 5: 0.370, 6: 0.405 };
  const SINKERS = [8, 10, 12, 15, 18, 20, 25, 30, 35, 40];   // 호 (1호 = 3.75 g) — 서해 최대 수심 60m 기준 40호까지
  const EGIS = [1.8, 2.0, 2.2, 2.5, 3.0];

  const CD_LINE = 2.6;    // 원줄 유효 항력계수 (꼬인 합사·진동 포함, 영상 수치에 맞춘 값)
  const CD_BRANCH = 1.2;  // 가짓줄
  const CD_SINKER = 1.0;
  const EGI_WET_25 = 2.0 * GF;   // 에기 2.5호 수중 무게 약 2 gf (누운 에기 상승력 ≈ 수중무게의 1/4 = 0.45~0.5 gf 에서 역산)
  const EGI_CDA_25 = 4.0e-4;     // 에기 2.5호 유효 항력면적(m²)

  const egiWet = s => EGI_WET_25 * Math.pow(s / 2.5, 3);
  const egiCdA = s => EGI_CDA_25 * Math.pow(s / 2.5, 2);
  const sinkerWet = ho => ho * 3.75 / 1000 * G * (1 - 1.025 / 11.3);   // 납 비중 11.3

  // 수심 평균 U → 바닥에서 z(m) 높이의 유속 (1/7 법칙: 평균의 8/7 배 × (z/H)^(1/7))
  function profile(U, H, z) {
    z = Math.min(Math.max(z, 0.03), H);
    return U * (8 / 7) * Math.pow(z / H, 1 / 7);
  }

  // 높이 z에서 '채비 기준' 물의 상대유속 벡터 [조류 방향, 옆 방향] (m/s)
  //  p.cur 조류(노트), p.sog 배 대지속도(노트), p.rel 배가 움직이는 방향과 조류 방향 사이 각도(도)
  //  채비(봉돌)는 배에 끌려 배와 같은 속도로 바닥을 따라 움직인다고 봄
  function relFlow(p, z) {
    const u = profile(p.cur * KN, p.H, z);
    const vb = (p.sog || 0) * KN, a = (p.rel || 0) * Math.PI / 180;
    return [u - vb * Math.cos(a), -vb * Math.sin(a)];
  }
  const mag = v => Math.hypot(v[0], v[1]);

  // ---- 원줄: 봉돌에서 수면까지 층별로 항력을 쌓아 각도·풀린 줄 길이 계산
  function mainLine(p) {
    const H = p.H, n = 240, dz = H / n;
    const d = (PE_D[p.pe] || 0.148) / 1000;
    const Ws = sinkerWet(p.sinker);
    // 봉돌(총알형) 항력: 부피 → 지름, 길이 = 지름 × 2.2 로 보고 옆면적 사용
    const V = p.sinker * 3.75 / 1000 / 11300;
    const sd = Math.cbrt(V / (Math.PI / 4 * 2.2));
    const w0 = relFlow(p, sd / 2), m0 = mag(w0);
    const Ds = 0.5 * RHO * CD_SINKER * (sd * 2.2 * sd) * m0 * m0;
    let Th = m0 > 0 ? [w0[0] / m0 * Ds, w0[1] / m0 * Ds] : [0, 0];
    const Tv = Ws;
    const angleBottom = Math.atan2(mag(Th), Tv);
    let x = [0, 0], L = 0, wMaxRel = 0;
    const shape = [[0, 0, 0]];                          // [수평거리, 높이, 각도]
    for (let i = 0; i < n; i++) {
      const z = (i + 0.5) * dz;
      const phi = Math.atan2(mag(Th), Tv);
      const w = relFlow(p, z), m = mag(w);
      wMaxRel = Math.max(wMaxRel, m);
      const f = 0.5 * RHO * CD_LINE * d * m * m * Math.cos(phi) * dz;   // 기울어진 줄은 수직 성분만 받음
      if (m > 0) { Th[0] += w[0] / m * f; Th[1] += w[1] / m * f; }
      const t = Math.tan(phi), th = mag(Th) || 1;
      x[0] += Th[0] / th * t * dz; x[1] += Th[1] / th * t * dz;
      L += dz / Math.cos(phi);
      if ((i + 1) % 12 === 0) shape.push([mag(x), z + dz / 2, phi]);
    }
    const angleTop = Math.atan2(mag(Th), Tv);
    return {
      angleTop: angleTop * 180 / Math.PI, angleBottom: angleBottom * 180 / Math.PI,
      offset: mag(x), lineOut: L, Th: mag(Th), Ws, shape,
      bottomFlow: mag(relFlow(p, 0.15)) / KN, surfaceFlow: mag(relFlow(p, H)) / KN, wMax: wMaxRel / KN,
    };
  }

  // ---- 가짓줄 + 에기: 단차 h(cm) 매듭에 매단 진자. 바닥 근처 상대유속에 밀려 각도 α 로 기움
  // ---- 수심 반영: 바닥을 찍고 기다리면 원줄이 기운 채로 봉돌에서 올라가므로 단차 매듭이 그만큼 낮아짐
  //  봉돌 바로 위 원줄 각도 ≈ 수면 쪽 원줄 각도의 절반으로 봄 (원줄은 아래로 갈수록 덜 누움)
  //  수심이 깊을수록 원줄이 많이 누워 같은 단차라도 매듭(=에기 매단 곳)이 낮아짐
  const _tilt = new Map();
  function knotTilt(p) {
    const k = [p.H, p.cur, p.sog, p.rel, p.pe, p.sinker].join("|");
    if (!_tilt.has(k)) {
      if (_tilt.size > 300) _tilt.clear();
      _tilt.set(k, 0.5 * mainLine(p).angleTop);
    }
    return _tilt.get(k);
  }
  function knotHeight(p, hCm) { return hCm * Math.cos(knotTilt(p) * Math.PI / 180); }

  function branch(p, hCm, LCm) {
    const h = knotHeight(p, hCm) / 100, L = LCm / 100;
    const We = egiWet(p.egi), CdA = egiCdA(p.egi);
    const db = (ES_D[p.es] || 0.33) / 1000;
    let a = 0;
    for (let k = 0; k < 60; k++) {
      const e = h - L * Math.cos(a);
      const zE = Math.max(e, 0.02), zB = Math.max(h - L * Math.cos(a) / 2, 0.02);
      const wE = mag(relFlow(p, zE)), wB = mag(relFlow(p, zB));
      const De = 0.5 * RHO * CdA * wE * wE;
      // 가짓줄 자체 항력은 절반을 에기 쪽 끝에 몰았다고 봄 (모멘트 근사)
      const Db = 0.5 * 0.5 * RHO * CD_BRANCH * db * L * Math.pow(wB * Math.cos(a), 2);
      const an = Math.atan2(De + Db, We);
      if (Math.abs(an - a) < 1e-6) { a = an; break; }
      a = 0.5 * a + 0.5 * an;
    }
    const eCm = (h - L * Math.cos(a)) * 100;
    let state;
    if (eCm <= 0) state = "lying";
    else if (eCm < 3) state = "touch";
    else if (eCm <= 25) state = "float";
    else state = "high";
    return { alpha: a * 180 / Math.PI, egiCm: Math.max(eCm, 0), rawCm: eCm, state,
             lyingCm: eCm < 0 ? Math.min(-eCm / Math.max(Math.cos(a), 0.05), LCm) : 0,
             egiFlow: mag(relFlow(p, Math.max(eCm / 100, 0.02))) / KN };
  }

  // 대상어별 목표 에기 높이 (영상: 갑오징어는 위를 보고, 쭈꾸미는 바닥을 봄)
  const TARGET = { gab: { lo: 5, hi: 15, mid: 10, label: "바닥 위 5~15cm" },
                   jju: { lo: 0, hi: 3, mid: 0.5, label: "바닥에 닿게 (0~3cm)" } };
  const MEDIAN = { L: 35, h: 12.5 };                     // 시청자 55명 중앙값 (가짓줄 30~40, 단차 10~15)

  // 지금 단차 그대로 둘 때 맞는 가짓줄 길이
  function branchForDrop(p, hCm, sp) {
    const t = TARGET[sp];
    let best = null;
    for (let L = 5; L <= 80; L += 1) {
      const r = branch(p, hCm, L);
      const inRange = r.rawCm >= t.lo && r.rawCm <= t.hi;
      const s = Math.abs(r.rawCm - t.mid) - (inRange ? 5 : 0) + 0.01 * Math.abs(L - MEDIAN.L);
      if (!best || s < best.s) best = { L, s, r, inRange };
    }
    return best;
  }

  // 처음부터 맞출 때 추천 조합 (목표 높이에 맞으면서 중앙값 채비에 가까운 것)
  function recommend(p, sp) {
    const t = TARGET[sp], out = [];
    for (let h = 5; h <= 50; h += 5) {
      for (let L = 10; L <= 70; L += 5) {
        const r = branch(p, h, L);
        const inRange = r.rawCm >= t.lo && r.rawCm <= t.hi;
        // 목표 높이 안에 드는 조합 중에서는 많이 쓰는 채비(중앙값)에 가까운 것을 먼저
        const s = inRange
          ? 0.1 * Math.abs(r.rawCm - t.mid) + 0.05 * Math.abs(L - MEDIAN.L) + 0.1 * Math.abs(h - MEDIAN.h) + (L >= 55 ? 1 : 0)
          : 10 + Math.abs(r.rawCm - t.mid);
        out.push({ h, L, r, s, inRange });
      }
    }
    out.sort((a, b) => a.s - b.s);
    const picks = [];
    for (const c of out) {
      if (picks.every(q => q.h !== c.h)) picks.push(c);
      if (picks.length === 3) break;
    }
    return picks;
  }

  // 원줄이 maxDeg 이하로 서게 하는 가장 가벼운 봉돌
  function sinkerFor(p, maxDeg) {
    for (const ho of SINKERS) {
      if (mainLine({ ...p, sinker: ho }).angleTop <= maxDeg) return ho;
    }
    return null;
  }

  // 착저까지 풀린 원줄 길이(m) → 실제 수심 추정 (같은 조건에서 줄 길이가 맞는 수심을 찾음)
  function depthFromLine(p, lineM) {
    let lo = 1, hi = lineM;
    if (mainLine({ ...p, H: hi }).lineOut < lineM) return lineM;
    for (let k = 0; k < 40; k++) {
      const mid = (lo + hi) / 2;
      if (mainLine({ ...p, H: mid }).lineOut > lineM) hi = mid; else lo = mid;
    }
    return (lo + hi) / 2;
  }

  const api = { KN, PE_D, ES_D, SINKERS, EGIS, TARGET, MEDIAN, profile, relFlow, mainLine, branch,
                branchForDrop, recommend, sinkerFor, depthFromLine, knotTilt, knotHeight };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RigModel = api;
})(this);
