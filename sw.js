/* 戰情室 Service Worker · 網路優先（network-first）
 * 目的：根治 GitHub Pages 的 10 分鐘快取——每次載入一律先抓網路最新版，
 *       只有真的離線才退回上次快取。裝一次後所有頁面永遠最新，不必再開無痕。
 * 安全：不預載、不鎖版本；連得上網就一定拿到最新，風險極低。
 */
const CACHE = 'w2l-warroom-rt';

self.addEventListener('install', e => self.skipWaiting());           // 新 SW 立即接管
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                                  // 只管 GET
  let url;
  try { url = new URL(req.url); } catch (_) { return; }

  // 帶 ?t= 的即時資料（data.json/week.json…）：純走網路、不進快取（避免無限長大）
  if (url.search) {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }

  // 其餘（html/css/js/png/字型…）：網路優先，成功就順手更新離線備援
  e.respondWith(
    fetch(req).then(res => {
      if (res && res.ok && url.origin === self.location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() => caches.match(req))
  );
});
