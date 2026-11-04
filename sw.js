/* 홈 화면 앱(PWA)용: 화면 파일은 인터넷이 될 때 늘 새로 받고, 안 될 때만 저장해 둔 것을 씀. 물때·날씨 자료는 저장하지 않음 */
const C = "jjugap-v1";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;     // 자료(raw.githubusercontent)는 손대지 않음
  e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); return r; })
    .catch(() => caches.match(e.request)));
});
