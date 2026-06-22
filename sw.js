/* 戰情室 Service Worker · 強制走網路、不讀快取（no-store network-first）
 * 目的：根治 GitHub Pages 的快取——每次載入一律向 GitHub 抓最新、完全不碰瀏覽器硬碟快取，
 *       只有真的離線才退回上次備援。裝一次後所有頁面永遠最新，不必再開無痕。
 * 修正：前一版用一般 fetch()，仍會讀瀏覽器 HTTP 快取→拿到舊 HTML。改成 {cache:'no-store'} 強制繞過。
 */
const CACHE = 'w2l-warroom-rt-v2';

self.addEventListener('install', e => self.skipWaiting());           // 新 SW 立即接管

self.addEventListener('activate', e => e.waitUntil((async () => {
  // 清掉所有舊快取（含前一版殘留的舊 index.html），避免再被吃到舊的
  const keys = await caches.keys();
  await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
  await self.clients.claim();
})()));

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (_) { return; }

  // 一律強制走網路、不讀任何快取（no-store）；失敗（離線）才退回備援
  e.respondWith(
    fetch(req, { cache: 'no-store' }).then(res => {
      // 只把「同源、成功、無 ?查詢字串」的回應留一份當離線備援（避免無限長大）
      if (res && res.ok && url.origin === self.location.origin && !url.search) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() => caches.match(req))
  );
});
