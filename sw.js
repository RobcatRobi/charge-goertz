// ChargeGörtz Service Worker v1.0
const CACHE = 'cg-v1';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/index.html','/icon-192.png'])));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

// Push empfangen
self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {title:'ChargeGörtz',body:'Neue Benachrichtigung'};
  e.waitUntil(self.registration.showNotification(data.title||'ChargeGörtz', {
    body: data.body||'',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: 'cg-alert',
    requireInteraction: data.urgent||false,
    data: { url: data.url||'/' }
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url||'/'));
});
