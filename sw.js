const CACHE = 'gauss-scanner-v3';
const ASSETS = [
  '/gauss-dna/scanner.html',
  '/gauss-dna/calculadora.html',
  '/gauss-dna/manifest.json',
  '/gauss-dna/scanner-manifest.json',
  '/gauss-dna/icon-192.png',
  '/gauss-dna/icon-512.png',
  '/gauss-dna/apple-touch-icon.png',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.url.includes('binance.com') || e.request.url.includes('telegram.org')) return;
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
