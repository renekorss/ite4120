import { useState } from "react";
import { errorText, request, scenarios, type Session } from "./api";
import { Banner, Brand, Sheet } from "./components";

const methods = ["Smart-ID", "Mobile-ID", "ID-card"];
const demoNames = [
  "Karl Kask",
  "Liisa Tamm",
  "Jaan Saar",
  "Eva Mägi",
  "Rasmus Kivi",
  "Anna Paju",
  "Mari Maasikas",
];

export function SignIn({
  onLogin,
  notice,
}: {
  onLogin: (s: Session, name: string, method: string) => void;
  notice: string;
}) {
  const [method, setMethod] = useState(""),
    [code, setCode] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [menu, setMenu] = useState(false),
    [loggedOut, setLoggedOut] = useState(
      notice === "You have been logged out.",
    );
  function choose(m: string) {
    setMethod(m);
    setCode("");
    setError("");
    setMenu(false);
    setLoggedOut(false);
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await request<Session>("/auth/demo-login", "", "POST", {
        personalCode: code,
      });
      onLogin(session, demoNames[Number(code) - 1] || "Demo driver", method);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const invalidCode =
    error.includes("(AUTH_INVALID)") || error.includes("(VALIDATION_ERROR)");
  return (
    <div className="login-page">
      <header>
        <Brand />
        <button
          className="menu"
          aria-label="Login menu"
          onClick={() => setMenu(true)}
        >
          <img alt="" src="/design/menu.svg" />
        </button>
      </header>
      {menu && (
        <Sheet
          label="Login menu"
          kind="account-sheet"
          close={() => setMenu(false)}
        >
          <div className="between">
            <strong>Log in with</strong>
            <button className="link" onClick={() => setMenu(false)}>
              Close
            </button>
          </div>
          {methods.map((m) => (
            <button className="menu-row" key={m} onClick={() => choose(m)}>
              {m}
            </button>
          ))}
        </Sheet>
      )}
      <main className="login">
        {loggedOut ? (
          <>
            <h1>You’re logged out</h1>
            <p>On a shared device, close this tab too.</p>
            <button className="primary" onClick={() => choose("")}>
              Log in again
            </button>
          </>
        ) : (
          <>
            {notice && notice !== "You have been logged out." && (
              <Banner>{notice}</Banner>
            )}
            {method ? (
              <>
                <button className="link back" onClick={() => choose("")}>
                  ‹ &nbsp;Other methods
                </button>
                <h1>{method}</h1>
                <p>
                  Enter a demo personal ID code or choose a demo account below.
                </p>
                {error && (
                  <Banner kind="error">
                    <strong>Couldn’t log in</strong>
                    <small>{error}</small>
                  </Banner>
                )}
                <form onSubmit={submit}>
                  <label htmlFor="code">Personal ID code</label>
                  <input
                    id="code"
                    required
                    pattern="[0-9]{11}"
                    inputMode="numeric"
                    maxLength={11}
                    autoComplete="off"
                    value={code}
                    aria-invalid={invalidCode}
                    onChange={(e) => {
                      setCode(e.target.value);
                      setError("");
                    }}
                    placeholder="11 digits"
                    aria-describedby="hint"
                  />
                  <small id="hint">
                    {invalidCode
                      ? "Choose an 11-digit code from Demo accounts."
                      : "Demo sign-in only. No identity provider is contacted."}
                  </small>

                  <button className="primary" disabled={busy}>
                    {busy ? "Logging in…" : "Continue"}
                  </button>
                </form>
                <details>
                  <summary>Demo accounts</summary>
                  {scenarios.map((s, i) => {
                    const id = String(i + 1).padStart(11, "0");
                    return (
                      <button
                        className="choice"
                        key={s}
                        onClick={() => {
                          setCode(id);
                          setError("");
                          document.getElementById("code")?.focus();
                        }}
                      >
                        <span>{s}</span>
                        <code>{id}</code>
                      </button>
                    );
                  })}
                </details>
              </>
            ) : (
              <>
                <h1>Log in</h1>
                <p>Check your licence and get expiry reminders.</p>
                <div className="method-list">
                  <small>Log in with</small>
                  {methods.map((m) => (
                    <button key={m} onClick={() => choose(m)}>
                      <img alt="" src={"/design/" + m.toLowerCase() + ".png"} />
                      {m}
                      <img alt="" src="/design/method-chevron.svg" />
                    </button>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </main>
      {!loggedOut && (
        <footer>Demo data from the Transport Administration via X-Road.</footer>
      )}
    </div>
  );
}
