// 一個最小化的 Service Worker，主要目的是宣告 App 的存在
self.addEventListener('install', (event) => {
  console.log('Service Worker installing.');
});

self.addEventListener('fetch', (event) => {
  // 這個簡單的 fetch 監聽器是讓 iOS 觸發「安裝到主畫面」提示的關鍵之一
  event.respondWith(fetch(event.request));
});