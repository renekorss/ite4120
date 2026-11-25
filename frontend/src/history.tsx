import { useState, useEffect } from "react";
import { request, time, date, type Notice, type Check } from "./api";
import { Badge } from "./components";
export function History({
  token,
  fail,
}: {
  token: string;
  fail: (e: unknown) => void;
}) {
  const [tab, setTab] = useState("Notifications"),
    [history, setHistory] = useState<{
      checks: Check[];
      notices: Notice[];
    } | null>(null),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    Promise.all([
      request<{ items: Check[] }>("/me/status-checks", token),
      request<{ items: Notice[] }>("/me/notifications", token),
    ])
      .then(([c, n]) => {
        if (live) setHistory({ checks: c.items, notices: n.items });
      })
      .catch((e) => {
        if (live) fail(e);
      });
    return () => {
      live = false;
    };
  }, [token, retry]);
  return (
    <>
      <div className="segments">
        {["Notifications", "Status checks"].map((t) => (
          <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      {!history ? (
        <button onClick={() => setRetry(retry + 1)}>Reload history</button>
      ) : (
        <div className="history">
          {tab === "Status checks" ? (
            <>
              {history.checks.map((c) => (
                <article key={c.id}>
                  <div>
                    <strong>{time(c.requestedAt)}</strong>
                    <small>
                      {c.error
                        ? c.error.message + " (" + c.error.code + ")"
                        : c.statusChanged === null
                          ? "First recorded status"
                          : c.statusChanged
                            ? "Status changed"
                            : "No change"}
                      {c.isLatestSuccessful ? " · latest successful" : ""}
                    </small>
                    {c.outcome === "successful" && (
                      <small>{c.sourceLabel}</small>
                    )}
                  </div>
                  <Badge status={c.outcome} label={c.outcomeLabel} />
                </article>
              ))}
              <p>
                {history.checks.length
                  ? "Latest five checks."
                  : "No status checks yet."}
              </p>
            </>
          ) : (
            <>
              {history.notices.map((n) => (
                <article key={n.id}>
                  <div>
                    <strong>
                      <a href="#renewal">{n.documentLabel}</a>
                    </strong>
                    <small>
                      Expires {date(n.expiresOn)} · {n.daysBefore}-day reminder
                    </small>
                  </div>
                  <small>{time(n.sentAt)}</small>
                </article>
              ))}
              <p>
                {history.notices.length
                  ? "Latest " +
                    history.notices.length +
                    (history.notices.length === 1
                      ? " notification."
                      : " notifications.")
                  : "No notifications sent yet."}
              </p>
            </>
          )}
        </div>
      )}
    </>
  );
}
