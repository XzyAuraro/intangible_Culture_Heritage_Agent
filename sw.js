const CACHE_NAME = 'palace-v1';
const ASSETS = [
  'index.html',
];

// 安装时：缓存基础资源
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
});

// 拦截请求：优先从缓存读取，实现离线秒开
self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then((res) => {
      return res || fetch(e.request);
    })
  );
});
