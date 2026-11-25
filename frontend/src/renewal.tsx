import { useState, useEffect } from "react";
import { request, date, type Driving, type Guidance } from "./api";
import { Banner, Dialog, DocumentBadge } from "./components";
export function Renewal({
  token,
  driving,
  fail,
}: {
  token: string;
  driving: Driving;
  fail: (e: unknown) => void;
}) {
  const [g, setG] = useState<Guidance | null>(null),
    [modal, setModal] = useState(false),
    [fallback, setFallback] = useState(false),
    [copy, setCopy] = useState(""),
    [help, setHelp] = useState(false),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    request<Guidance>("/me/renewal-guidance", token)
      .then((x) => {
        if (live) setG(x);
      })
      .catch((e) => {
        if (live) fail(e);
      });
    return () => {
      live = false;
    };
  }, [token, retry]);
  const medical = g?.actions.some((a) => a.code === "renew_medical");
  const companion = medical
    ? driving.licences[0]
    : driving.medicalCertificates[0];
  return (
    <>
      <a href="#licence">‹ Licence</a>
      <h1>
        {g?.actions.length === 1 ? g.actions[0].title : "Renewal instructions"}
      </h1>
      {g ? (
        <>
          <p className="renewal-intro">
            {driving.nextExpiryDate
              ? "Before " + date(driving.nextExpiryDate) + ". "
              : ""}
            {medical && g.actions.length === 1 && companion?.status === "valid"
              ? "Your licence needs nothing now."
              : ""}
          </p>
          <div className="grid renewal-grid">
            <div>
              {g.actions.map((a) => (
                <section key={a.code}>
                  {g.actions.length > 1 && <h2>{a.title}</h2>}
                  {a.code === "renew_medical" ? (
                    <ol className="renewal-steps">
                      <li>Book a driver’s health check with your doctor.</li>
                      <li>
                        Bring your ID and any glasses or lenses you use for
                        driving.
                      </li>
                      <li>Your doctor submits the certificate digitally.</li>
                      <li>Come back and refresh your licence information.</li>
                    </ol>
                  ) : (
                    <p>{a.description}</p>
                  )}
                </section>
              ))}
              {!g.actions.some((a) => a.code === "renew_medical") && (
                <p>
                  Return to Licence and refresh after completing your renewal.
                </p>
              )}
              {medical && (
                <Banner>
                  <strong>Tip</strong>
                  <small>
                    Book your appointment before the certificate expires.
                  </small>
                </Banner>
              )}
            </div>
            <section className="card">
              <div className="between">
                <h2>
                  {companion
                    ? medical
                      ? "Driving licence"
                      : "Medical certificate"
                    : "Official e-service"}
                </h2>
                <DocumentBadge doc={companion} />
              </div>
              <p>
                {companion?.expiresOn
                  ? "Valid until " + date(companion.expiresOn) + "."
                  : "Estonian Transport Administration"}
              </p>
              <button className="link" onClick={() => setModal(true)}>
                Open the official e-service ↗
              </button>
            </section>
            {help && (
              <button className="link" onClick={() => setFallback(true)}>
                E-service didn’t open?
              </button>
            )}
            {fallback && (
              <Dialog
                title="Couldn’t open the e-service"
                icon="error"
                cancel="Close"
                close={() => setFallback(false)}
                action={
                  <button
                    className="primary"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(g.officialUrl);
                        setCopy("Address copied.");
                      } catch {
                        setCopy("Select and copy the address above.");
                      }
                    }}
                  >
                    Copy address
                  </button>
                }
              >
                <p>
                  Open <a href={g.officialUrl}>{g.officialUrl}</a> yourself.
                  (DLR-EXT-001)
                </p>
                <small role="status">{copy}</small>
              </Dialog>
            )}
            {modal && (
              <Dialog
                title="Leaving this app"
                close={() => setModal(false)}
                action={
                  <button
                    className="primary"
                    onClick={() => {
                      setModal(false);
                      setHelp(true);
                      const child = window.open("about:blank", "_blank");
                      if (child) {
                        child.opener = null;
                        child.location.replace(g.officialUrl);
                      } else setFallback(true);
                    }}
                  >
                    Continue
                  </button>
                }
              >
                <p>{g.externalNotice}</p>
              </Dialog>
            )}
          </div>
        </>
      ) : (
        <button onClick={() => setRetry(retry + 1)}>Reload instructions</button>
      )}
    </>
  );
}
