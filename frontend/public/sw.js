self.addEventListener("push", (event) => {
  if (!event.data) return;
  const { title, body, tag } = event.data.json();
  event.waitUntil(
    self.registration.showNotification(title, { body, tag, renotify: false }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow("/#renewal"));
});
