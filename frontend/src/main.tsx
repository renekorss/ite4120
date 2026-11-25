import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ApiError,
  date,
  errorText,
  request,
  daysLeft,
  time,
  type Check,
  type Config,
  type Driving,
  type Preferences,
  type Session,
} from "./api";
import { Reminders } from "./reminders";
import { SignIn } from "./login";
import { Banner, Badge, Brand, Sheet, DocumentBadge } from "./components";
import { History } from "./history";
import { Renewal } from "./renewal";
import "./style.css";

const pages = ["Overview", "Licence", "Reminders", "History"] as const;
type Page = (typeof pages)[number] | "Renewal";
const destination = (): Page =>
  [...pages, "Renewal" as const].find(
    (p) => "#" + p.toLowerCase() === location.hash,
  ) || "Overview";
const go = (p: Page) => {
  location.hash = p.toLowerCase();
};
type Data = { driving: Driving; prefs: Preferences; config: Config };
function Header({
  page,
  name,
  method,
  logout,
  busy,
}: {
  page: Page;
  name: string;
  method: string;
  logout: () => void;
  busy: boolean;
}) {
  const [menu, setMenu] = useState(false);
  return (
    <header>
      <a href="#overview" className="brand-home">
        <Brand />
      </a>
      <nav aria-label="Main navigation">
        {pages.map((p) => (
          <a
            key={p}
            href={"#" + p.toLowerCase()}
            aria-current={
              (page === "Renewal" ? "Licence" : page) === p ? "page" : undefined
            }
          >
            <span className="nav-icon" aria-hidden="true">
              <i
                style={{
                  maskImage: "url(/design/" + p.toLowerCase() + "-nav.svg)",
                }}
              />
            </span>
            {p}
          </a>
        ))}
      </nav>
      <div className="account">
        <span>{name}</span>
        <button className="link" disabled={busy} onClick={logout}>
          Log out
        </button>
      </div>
      <button
        aria-label="Account menu"
        aria-expanded={menu}
        className="menu"
        onClick={() => setMenu(!menu)}
      >
        <img src="/design/menu.svg" alt="" />
      </button>
      {menu && (
        <Sheet
          label="Account menu"
          kind="account-sheet"
          close={() => setMenu(false)}
        >
          <div className="between">
            <div>
              <strong>{name}</strong>
              <small>Logged in with {method} (demo)</small>
            </div>
            <button className="link" onClick={() => setMenu(false)}>
              Close
            </button>
          </div>
          <div className="menu-links">
            {pages.map((p) => (
              <a
                key={p}
                className="menu-row"
                href={"#" + p.toLowerCase()}
                onClick={() => setMenu(false)}
              >
                {p}
              </a>
            ))}
          </div>
          <button className="secondary" onClick={logout} disabled={busy}>
            Log out
          </button>
        </Sheet>
      )}
    </header>
  );
}
function Overview({ d, p }: { d: Driving; p: Preferences }) {
  const next = d.nextExpiryDate,
    medical = d.medicalCertificates.some(
      (m) => m.expiresOn && m.expiresOn === next,
    );
  const title =
    d.status === "at_risk"
      ? medical
        ? "Renew your medical certificate"
        : "Renew your driving licence"
      : d.status === "valid"
        ? "Your driving status is valid"
        : d.status === "invalid"
          ? "Check your driving entitlement"
          : "Check your driving status";
  const rows = [
    [
      "licence",
      "Driving licence",
      d.licences[0]?.expiresOn
        ? (!d.licences[0].isCurrent
            ? "Previously recorded until "
            : d.licences[0].expiryKind === "driving_right"
              ? "Entitlement until "
              : "Valid until ") + date(d.licences[0].expiresOn)
        : "View licence details",
      "Licence",
    ],
    [
      "medical",
      "Medical certificate",
      d.medicalCertificates[0]?.expiresOn
        ? (d.medicalCertificates[0].isCurrent ? "Expires " : "Saved expiry: ") +
          date(d.medicalCertificates[0].expiresOn)
        : "No certificate data",
      "Licence",
    ],
    ["reminders", "Reminders", p.enabled ? "On" : "Off", "Reminders"],
  ];
  return (
    <div className="overview">
      <section className="hero">
        <div className="between">
          <small>Driving status</small>
          <Badge status={d.status} label={d.statusLabel} />
        </div>
        <h2>{title}</h2>
        <p>
          {(d.status !== "at_risk" ||
            d.reasonCodes.includes("BOTH_EXPIRY_APPROACHING")) &&
            (d.explanations[0] ||
              (!next && "Refresh to check your latest driving information."))}
          {next &&
            (d.nextExpiryIsStale ? " Saved deadline: " : " Expires ") +
              date(next) +
              (daysLeft(next) >= 0
                ? " — in " + daysLeft(next) + " days."
                : ".")}
        </p>
        <button className="primary" onClick={() => go("Renewal")}>
          See how to renew
        </button>
      </section>
      <div>
        {rows.map(([icon, title, sub, target]) => (
          <a className="doclink" key={icon} href={"#" + target.toLowerCase()}>
            <img src={"/design/" + icon + ".png"} alt="" />
            <div>
              <strong>{title}</strong>
              <small>{sub}</small>
            </div>
            <img className="chevron" src="/design/chevron-desktop.svg" alt="" />
          </a>
        ))}
      </div>
    </div>
  );
}
function LicencePage({ d }: { d: Driving }) {
  const renewalButton = (
    <button className="primary" onClick={() => go("Renewal")}>
      See how to renew
    </button>
  );
  return (
    <>
      <div className="grid">
        <section className="card">
          <div className="between">
            <h2>Driving licence</h2>
            <DocumentBadge doc={d.licences[0]} />
          </div>
          {!d.licences.length && <p>No licence details available.</p>}
          {d.licences.map((l) => (
            <dl key={l.id}>
              <dt>Issued</dt>
              <dd>{date(l.issuedOn)}</dd>
              <dt>
                {l.expiryKind === "driving_right"
                  ? "Entitlement ends"
                  : "Expires"}
              </dt>
              <dd>{date(l.expiresOn)}</dd>
              <dt>Categories</dt>
              <dd>
                {l.categories
                  .map(
                    (c) =>
                      c.code +
                      (c.expiresOn && c.expiresOn !== l.expiresOn
                        ? " · " + date(c.expiresOn)
                        : ""),
                  )
                  .join(", ") || "Unavailable"}
              </dd>
              {!l.isCurrent && (
                <>
                  <dt>Saved on</dt>
                  <dd>{time(l.cachedAt)}</dd>
                </>
              )}
            </dl>
          ))}
          {d.renewalActions?.includes("renew_licence") && renewalButton}
        </section>
        <section className="card">
          <div className="between">
            <h2>Medical certificate</h2>
            <DocumentBadge doc={d.medicalCertificates[0]} />
          </div>
          <dl>
            <dt>Required</dt>
            <dd>
              {d.medicalRequirement === "required"
                ? "Yes"
                : d.medicalRequirement === "not_required"
                  ? "No"
                  : "Unknown"}
            </dd>
            {d.medicalCertificates.map((m) => (
              <React.Fragment key={m.id}>
                <dt>Expires</dt>
                <dd>{date(m.expiresOn)}</dd>
                {m.expiresOn && (
                  <>
                    <dt>Days left</dt>
                    <dd>{Math.max(0, daysLeft(m.expiresOn))}</dd>
                  </>
                )}
                {!m.isCurrent && (
                  <>
                    <dt>Saved on</dt>
                    <dd>{time(m.cachedAt)}</dd>
                  </>
                )}
              </React.Fragment>
            ))}
          </dl>
          {!d.medicalCertificates.length && (
            <p>No certificate data available.</p>
          )}
          {d.renewalActions?.includes("renew_medical") && renewalButton}
        </section>
      </div>
      {d.warnings
        .filter((w) => w.code !== "STALE_DATA")
        .map((w) => (
          <small className="footnote" key={w.code}>
            {w.message}
          </small>
        ))}
    </>
  );
}
function Dashboard({
  session,
  name,
  method,
  end,
}: {
  session: Session;
  name: string;
  method: string;
  end: (msg: string) => void;
}) {
  const [page, setPage] = useState(destination),
    [data, setData] = useState<Data | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [refreshNotice, setRefreshNotice] = useState(""),
    [refreshing, setRefreshing] = useState(false),
    [warning, setWarning] = useState(false),
    [retry, setRetry] = useState(0);
  const token = session.accessToken;
  function fail(e: unknown) {
    if (e instanceof ApiError && e.status === 401) end(errorText(e));
    else setError(errorText(e));
  }
  useEffect(() => {
    const change = () => {
      setPage(destination());
      setRefreshNotice("");
      setError("");
      window.scrollTo(0, 0);
      requestAnimationFrame(() =>
        document
          .querySelector<HTMLElement>("main")
          ?.focus({ preventScroll: true }),
      );
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    let live = true;
    Promise.all([
      request<Driving>("/me/driving-data", token),
      request<Preferences>("/me/reminder-preferences", token),
      request<Config>("/config"),
    ])
      .then(([driving, prefs, config]) => {
        if (live) {
          setData({ driving, prefs, config });
          setError("");
        }
      })
      .catch((e) => {
        if (live) fail(e);
      });
    return () => {
      live = false;
    };
  }, [token, retry]);
  useEffect(() => {
    const remaining = new Date(session.expiresAt).getTime() - Date.now();
    const w = setTimeout(
        () => setWarning(true),
        Math.max(0, remaining - 1000 * session.sessionWarningSeconds),
      ),
      expiry = setTimeout(
        () => end("Your session has expired. Log in again. (AUTH_REQUIRED)"),
        Math.max(0, remaining),
      );
    return () => {
      clearTimeout(w);
      clearTimeout(expiry);
    };
  }, [session]);
  async function logout() {
    setBusy(true);
    try {
      await request("/auth/logout", token, "POST");
      end("You have been logged out.");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setRefreshing(true);
    setRefreshNotice("Checking your licence and medical certificate…");
    setBusy(true);
    setError("");
    try {
      const res = await request<{ data: Driving; check: Check }>(
        "/me/driving-data/refresh",
        token,
        "POST",
      );
      setData((d) => d && { ...d, driving: res.data });
      if (res.check.error) {
        setRefreshNotice("");
        setError(res.check.error.message + " (" + res.check.error.code + ")");
      } else {
        const status = res.data.statusLabel;
        setRefreshNotice(
          res.check.statusChanged === false
            ? "Data refreshed. Driving status is still " + status + "."
            : "Data refreshed. Driving status: " + status + ".",
        );
      }
    } catch (e) {
      setRefreshNotice("");
      fail(e);
    } finally {
      setRefreshing(false);
      setBusy(false);
    }
  }
  const driving = page === "Overview" || page === "Licence";
  return (
    <>
      <a
        className="skip"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Skip to content
      </a>
      <Header
        page={page}
        name={name}
        method={method}
        logout={logout}
        busy={busy}
      />
      <main id="main" data-page={page} tabIndex={-1}>
        {warning && (
          <Banner kind="warning">
            Your session is about to expire. Save any changes.
          </Banner>
        )}

        {page !== "Renewal" && (
          <div className="page-heading">
            <div>
              <h1>
                {page === "Overview" ? "Hi, " + name.split(" ")[0] : page}
              </h1>
              {driving && data && (
                <p className="updated">
                  {data.driving.lastUpdatedAt
                    ? "Updated " + time(data.driving.lastUpdatedAt)
                    : "No successful update yet"}
                  {page === "Licence" && " · via X-Road"}
                </p>
              )}
              {page === "Reminders" && (
                <p>Get notified before your next deadline.</p>
              )}
            </div>
            {driving && data && (
              <button
                className={
                  "refresh desktop-refresh " +
                  (page === "Overview" ? "link" : "secondary")
                }
                disabled={busy}
                onClick={refresh}
              >
                {refreshing ? "Refreshing…" : "Refresh data"}
              </button>
            )}
          </div>
        )}
        {driving && (
          <p
            role="status"
            aria-atomic="true"
            className="refresh-notice desktop-notice"
          >
            {refreshNotice}
          </p>
        )}
        {error && (
          <>
            <Banner kind="error">
              {driving && data ? (
                <>
                  <strong>Couldn’t refresh</strong>
                  <small>{error}</small>
                </>
              ) : (
                error
              )}
            </Banner>
            {driving && data && (
              <button
                className="primary retry-refresh"
                disabled={busy}
                onClick={refresh}
              >
                Try again
              </button>
            )}
          </>
        )}
        {!data ? (
          <section aria-live="polite">
            {error ? (
              <button onClick={() => setRetry(retry + 1)}>Retry loading</button>
            ) : (
              "Loading…"
            )}
          </section>
        ) : (
          <>
            {driving && !error && data.driving.isStale && (
              <Banner kind="warning">
                {data.driving.lastUpdatedAt
                  ? "Showing saved information. Check the last successful update above."
                  : "No saved driving information. Refresh to try again."}
              </Banner>
            )}
            {page === "Overview" && (
              <Overview d={data.driving} p={data.prefs} />
            )}
            {page === "Licence" && <LicencePage d={data.driving} />}
            {page === "Reminders" && (
              <Reminders
                accountId={session.userId}
                token={token}
                config={data.config}
                prefs={data.prefs}
                next={data.driving.nextExpiryDate}
                documentLabel={
                  data.driving.medicalCertificates.some(
                    (m) =>
                      m.expiresOn &&
                      m.expiresOn === data.driving.nextExpiryDate,
                  )
                    ? "medical certificate"
                    : "driving licence"
                }
                onSave={(prefs) => setData({ ...data, prefs })}
                fail={fail}
              />
            )}
            {driving && (
              <p
                role="status"
                aria-atomic="true"
                className="refresh-notice mobile-notice"
              >
                {refreshNotice}
              </p>
            )}
            {driving && (
              <button
                className={
                  "mobile-refresh " +
                  (page === "Overview" ? "link" : "secondary")
                }
                disabled={busy}
                onClick={refresh}
              >
                {refreshing ? "Refreshing…" : "Refresh data"}
              </button>
            )}
            {page === "History" && <History token={token} fail={fail} />}
            {page === "Renewal" && (
              <Renewal driving={data.driving} token={token} fail={fail} />
            )}
          </>
        )}
      </main>
    </>
  );
}
function App() {
  const [user, setUser] = useState<{
      s: Session;
      n: string;
      method: string;
    } | null>(null),
    [notice, setNotice] = useState("");
  return user ? (
    <Dashboard
      key={user.s.accessToken}
      session={user.s}
      name={user.n}
      method={user.method}
      end={(msg) => {
        setUser(null);
        setNotice(msg);
        history.replaceState(null, "", location.pathname);
      }}
    />
  ) : (
    <SignIn
      notice={notice}
      onLogin={(s, n, method) => setUser({ s, n, method })}
    />
  );
}
createRoot(document.getElementById("root")!).render(<App />);
