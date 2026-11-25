import { useState, useEffect } from "react";
import {
  ApiError,
  date,
  reminderDate,
  request,
  type Config,
  type Preferences,
} from "./api";
import { connectPush, supportsPush } from "./push";
import { Banner, Dialog } from "./components";

export function Reminders({
  accountId,
  token,
  prefs,
  onSave,
  next,
  documentLabel,
  config,
  fail,
}: {
  accountId: string;
  token: string;
  prefs: Preferences;
  onSave: (p: Preferences) => void;
  next: string | null;
  documentLabel: string;
  config: Config;
  fail: (err: unknown) => void;
}) {
  const [days, setDays] = useState(prefs.intervals),
    [modal, setModal] = useState(""),
    [busy, setBusy] = useState(false),
    [blocked, setBlocked] = useState(false),
    [saved, setSaved] = useState(""),
    [connected, setConnected] = useState(false);
  useEffect(() => {
    let live = true;
    if (supportsPush())
      navigator.serviceWorker
        .getRegistration("/")
        .then((r) => r?.pushManager.getSubscription())
        .then((sub) => {
          if (live)
            setConnected(
              Boolean(sub) &&
                Notification.permission === "granted" &&
                sessionStorage.getItem("registeredFor") === accountId,
            );
        })
        .catch(() => {});
    return () => {
      live = false;
    };
  }, [token]);
  async function save(enabled: boolean, register = false) {
    setBusy(true);
    setSaved("");
    try {
      if (register) {
        if (!config.push.publicKey)
          throw new ApiError(
            0,
            "PUSH_NOT_CONFIGURED",
            "Browser delivery is unavailable. Contact the operator.",
          );
        await connectPush(token, config.push.publicKey);
        sessionStorage.setItem("registeredFor", accountId);
        setConnected(true);
      }
      const selected =
        enabled && !days.length ? prefs.availableIntervals : days;
      const p = await request<Preferences>(
        "/me/reminder-preferences",
        token,
        "PUT",
        { enabled, intervals: selected },
      );
      onSave(p);
      setDays(p.intervals);
      setSaved(enabled ? "Reminder settings saved." : "Reminders turned off.");
      setBlocked(false);
      setModal("");
    } catch (e) {
      setModal("");
      if (e instanceof ApiError && e.code === "PUSH_PERMISSION") {
        setBlocked(true);
        return;
      }
      fail(
        e instanceof ApiError
          ? e
          : new ApiError(
              0,
              "PUSH_REGISTRATION_FAILED",
              "Browser registration failed. Check notification permissions and try again.",
            ),
      );
    } finally {
      setBusy(false);
    }
  }
  const upcoming = prefs.intervals
    .filter(
      (n) =>
        next &&
        Date.parse(next) - n * 86400000 >=
          Math.floor(Date.now() / 86400000) * 86400000,
    )
    .sort((a, b) => b - a)[0];
  const disable = (style: string) => (
    <button
      className={"danger-link " + style}
      onClick={() => setModal("disable")}
    >
      Turn off reminders
    </button>
  );
  return (
    <>
      {blocked && (
        <div role="alert">
          <Banner kind="warning">
            <strong>Notifications are blocked</strong>
            <small>
              Allow them in your browser’s site settings, then try again.
              (PUSH_PERMISSION)
            </small>
          </Banner>
        </div>
      )}
      {saved && (
        <Banner kind="success">
          <strong>{prefs.enabled ? "Saved" : "Reminders turned off"}</strong>
          <small>
            {prefs.enabled && next && upcoming
              ? "Next reminder on " + reminderDate(next, upcoming) + "."
              : saved}
          </small>
        </Banner>
      )}
      <div className="grid reminder-grid">
        <section className="card">
          <div className="between">
            <h2>Reminders</h2>
            <button
              type="button"
              className="switch-state"
              role="switch"
              aria-label="Reminders"
              aria-checked={prefs.enabled}
              disabled={busy}
              onClick={() => setModal(prefs.enabled ? "disable" : "allow")}
            >
              <img
                alt=""
                src={
                  "/design/toggle-" + (prefs.enabled ? "on" : "off") + ".svg"
                }
              />
              {prefs.enabled ? "On" : "Off"}
            </button>
          </div>
          <small>
            Next deadline:{" "}
            {next ? documentLabel + ", " + date(next) : "unavailable"}.
          </small>
          {!prefs.enabled ? (
            <>
              <button className="primary" onClick={() => setModal("allow")}>
                {blocked ? "Try again" : "Turn on reminders"}
              </button>
              <small>Your browser will ask to allow notifications.</small>
            </>
          ) : (
            <>
              {!connected && (
                <button
                  className="link connect"
                  onClick={() => setModal("allow")}
                >
                  Connect this browser
                </button>
              )}
              {disable("desktop-disable")}
            </>
          )}
        </section>
        <section
          className={"card interval-card" + (!prefs.enabled ? " inactive" : "")}
        >
          <fieldset disabled={!prefs.enabled || busy}>
            <legend>Remind me</legend>
            {prefs.availableIntervals.map((n) => (
              <label className="interval" key={n}>
                <input
                  type="checkbox"
                  checked={prefs.enabled && days.includes(n)}
                  onChange={(e) => {
                    setSaved("");
                    setDays(
                      e.target.checked
                        ? [...days, n]
                        : days.filter((v) => v !== n),
                    );
                  }}
                />
                {n} days before <small>{reminderDate(next, n)}</small>
              </label>
            ))}
            {prefs.enabled && (
              <button
                className="primary"
                disabled={!days.length || busy}
                onClick={() => save(true)}
              >
                Save
              </button>
            )}
          </fieldset>
        </section>
      </div>
      {prefs.enabled && disable("mobile-disable")}
      {modal && (
        <Dialog
          title={
            modal === "allow"
              ? "Allow notifications from " + location.hostname + "?"
              : "Turn off reminders?"
          }
          icon={modal === "allow" ? "info" : "warning"}
          kind={modal === "allow" ? "permission" : ""}
          cancel={modal === "allow" ? "Block" : "Cancel"}
          close={() => {
            if (!busy) setModal("");
          }}
          cancelAction={() => {
            if (!busy) {
              if (modal === "allow") setBlocked(true);
              setModal("");
            }
          }}
          action={
            <button
              className={
                "primary " + (modal === "disable" ? "destructive" : "")
              }
              disabled={busy}
              onClick={() => save(modal === "allow", modal === "allow")}
            >
              {busy ? "Saving…" : modal === "allow" ? "Allow" : "Turn off"}
            </button>
          }
        >
          {modal === "disable" && (
            <p>
              You won’t get expiry reminders. You can turn them on again
              anytime.
            </p>
          )}
        </Dialog>
      )}
    </>
  );
}
