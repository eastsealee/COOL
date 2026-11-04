/* 웹 미리보기용: Streamlit 메뉴 안(iframe)에서 열릴 때만 화면 높이를 알려줌. 앱(안드로이드) 안에서는 아무것도 안 함 */
(function () {
  if (window.parent === window) return;
  const send = (type, data) => window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data || {}), "*");
  let last = 0;
  const h = () => { const v = Math.ceil(document.documentElement.getBoundingClientRect().height) + 4; if (Math.abs(v - last) >= 2) { last = v; send("streamlit:setFrameHeight", { height: v }); } };
  send("streamlit:componentReady", { apiVersion: 1 });
  window.addEventListener("load", h);
  if (window.ResizeObserver) new ResizeObserver(h).observe(document.body);
  h();
})();
