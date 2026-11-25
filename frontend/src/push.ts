import { ApiError, request } from "./api";
export const supportsPush = () =>
  window.isSecureContext &&
  "serviceWorker" in navigator &&
  "PushManager" in window &&
  "Notification" in window;
export async function connectPush(token: string, key: string) {
  if (!supportsPush())
    throw new ApiError(
      0,
      "PUSH_UNSUPPORTED",
      "Open this site in a browser that supports notifications over HTTPS or localhost.",
    );
  const permission = await Notification.requestPermission();
  if (permission !== "granted")
    throw new ApiError(
      0,
      "PUSH_PERMISSION",
      "Notifications are blocked. Allow notifications for this site in browser settings, then try again.",
    );
  await navigator.serviceWorker.register("/sw.js");
  const registration = await navigator.serviceWorker.ready;
  const bytes = Uint8Array.from(
    atob(key.replace(/-/g, "+").replace(/_/g, "/")),
    (c) => c.charCodeAt(0),
  );
  let subscription = await registration.pushManager.getSubscription();
  if (
    subscription &&
    String(
      new Uint8Array(
        subscription.options.applicationServerKey || new ArrayBuffer(0),
      ),
    ) !== String(bytes)
  ) {
    await subscription.unsubscribe();
    subscription = null;
  }
  subscription ??= await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: bytes,
  });
  const { endpoint, keys } = subscription.toJSON();
  await request("/me/push-subscriptions", token, "POST", { endpoint, keys });
}
