"""Local HTTP mock of the public ee-test juhilubaKehtivus v1 contract."""

from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import time
from uuid import UUID, uuid4

DEFAULT_PATH = "/r1/ee-test/GOV/70001490/liiklusregister/juhilubaKehtivus/v1"
DEFAULT_CLIENT = "ee-test/COM/00000000/licence-reminder-demo"
MEDICAL_PATH = "/demo/v1/medical-certificate"
MEDICAL_DAYS = {"valid": 365, "expiring": 365, "expired": 365, "invalid": -5,
                "slow": 365, "medical": 30, "both": 7, "renewed": 365}
MAX_BODY_BYTES = 4096
SCENARIOS = {
    "00000000001": ("valid", 730),
    "00000000002": ("licence_expiring", 30),
    "00000000003": ("licence_expired", -10),
    "00000000004": ("right_invalid", 730),
    "00000000005": ("unavailable", 0),
    "00000000006": ("slow", 730),
}


def error(code, message):
    """Return the upstream ErrorResult structure using a safe mock message."""
    return {"errorCode": code, "errorMessage": message}


def respond(payload, today=None):
    """Resolve synthetic inputs into an upstream-shaped HTTP status and body."""
    if not isinstance(payload, dict):
        return 400, error("1", "Sisend peab olema JSON-objekt.")
    allowed = {"isikukood", "eesnimi", "perenimi", "loaNr"}
    if set(payload) - allowed or any(not isinstance(v, str) for v in payload.values()):
        return 400, error("1", "Kontrolli päringu välju ja nende tüüpe.")
    values = {key: value.strip() for key, value in payload.items()}
    personal_code = values.get("isikukood")
    licence_number = values.get("loaNr")
    if not personal_code and not (values.get("eesnimi") and values.get("perenimi") and licence_number):
        return 400, error("1", "Lisa isikukood või eesnimi, perenimi ja juhiloa number.")
    # Test codes intentionally start with 0, so they cannot be real Estonian IDs.
    if personal_code:
        record_key = personal_code
    else:
        record_key = next((key for key in SCENARIOS
                           if licence_number == "MOCK" + key[-4:]
                           and values["eesnimi"] == "Test"
                           and values["perenimi"] == "Demo"), None)
    if record_key not in SCENARIOS:
        return 404, error("2", "Testandmeid ei leitud.")
    number = "MOCK" + record_key[-4:]
    if licence_number and licence_number != number:
        return 404, error("2", "Testandmeid ei leitud.")
    if any(values.get(key) and values[key] != expected
           for key, expected in (("eesnimi", "Test"), ("perenimi", "Demo"))):
        return 404, error("2", "Testandmeid ei leitud.")
    scenario, days = SCENARIOS[record_key]
    if scenario == "unavailable":
        return 503, error("MOCK_UNAVAILABLE", "Testteenus ei ole ajutiselt kättesaadav.")
    if scenario in ("licence_expired", "right_invalid"):
        reason = "JUHTIMISOIGUS_EI_OLE_KEHTIV" if scenario == "right_invalid" else (
            "JUHILUBA_EI_OLE_KEHTIV" if licence_number else "KEHTIVAT_JUHILUBA_EI_LEITUD")
        result = {key: values[key] for key in allowed if values.get(key)}
        result.update(staatus="kehtetu", pohjuseKood=reason,
                      sonum="Juhtimisõigus ei ole kehtiv." if scenario == "right_invalid"
                      else "Kehtivat juhiluba ei leitud.")
        return 200, result
    today = today or datetime.now(timezone.utc).date()
    expiry = today + timedelta(days=days)
    issued = date(expiry.year - 10, expiry.month, min(expiry.day, 28))
    return 200, {
        "eesnimi": "Test", "perenimi": "Demo", "isikukood": record_key,
        "loaNr": number, "loaTyyp": "JUHILUBA", "staatus": "kehtiv",
        "valjastamisKp": issued.strftime("%d.%m.%Y"),
        "juhtimisOiguseLoppKp": expiry.strftime("%d.%m.%Y"),
        "kategooriad": [{"kood": "B", "esmakordseValjastamiseKp": "01.06.2015",
                         "kehtivusKp": expiry.strftime("%d.%m.%Y")}],
    }


class MockServer(ThreadingHTTPServer):
    """Configurable, dependency-free development HTTP server."""
    daemon_threads = True

    def __init__(self, address, path=DEFAULT_PATH, client=DEFAULT_CLIENT, delay=2.0):
        self.medical_reference_date = date.fromisoformat(os.environ.get("MOCK_MEDICAL_REFERENCE_DATE") or datetime.now(timezone.utc).date().isoformat())
        self.mock_path = path
        self.mock_client = client
        self.mock_delay = delay
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    """Serve mock responses without recording request bodies or identity fields."""
    server_version = "LocalMock"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        # BaseHTTPRequestHandler logs paths and may include untrusted input.
        pass

    def send_json(self, status, body):
        trace = getattr(self, "trace", str(uuid4()))
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Road-Id", trace)
        self.send_header("X-Road-Client", self.server.mock_client)
        if self.path == self.server.mock_path:
            self.send_header("X-Road-Service", self.server.mock_path.removeprefix("/r1/").rsplit("/", 1)[0])
        self.send_header("X-Road-Request-Id", str(uuid4()))
        self.send_header("X-Mock-Service", "true")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        print(json.dumps({"@timestamp": datetime.now(timezone.utc).isoformat(),
                          "event": {"action": "mock.request", "outcome": "success" if status < 400 else "failure"},
                          "trace": {"id": trace}, "http": {"response": {"status_code": status}}}), flush=True)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "mock": True})
        else:
            self.send_json(404, error("MOCK_ROUTE", "Testteenuse aadressi ei leitud."))

    def do_POST(self):
        try:
            self.trace = str(UUID(self.headers.get("X-Road-Id", "")))
        except ValueError:
            self.trace = str(uuid4())
        if self.path not in (self.server.mock_path, MEDICAL_PATH):
            self.send_json(404, error("MOCK_ROUTE", "Testteenuse aadressi ei leitud."))
            return
        if self.headers.get("X-Road-Client") != self.server.mock_client:
            self.send_json(403, error("MOCK_CLIENT", "Testkliendi päis puudub või on vigane."))
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, error("MOCK_CONTENT_TYPE", "Kasuta application/json sisutüüpi."))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES or self.headers.get("Transfer-Encoding"):
                self.send_json(400, error("1", "Päringu sisu puudub või on liiga suur."))
                return
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError, TimeoutError):
            self.send_json(400, error("1", "Päringu JSON-sisu on vigane."))
            return
        if self.path == MEDICAL_PATH:
            if not isinstance(payload, dict) or set(payload) != {"scenario"} or not isinstance(payload["scenario"], str):
                self.send_json(400, error("1", "Invalid demo scenario."))
                return
            days = MEDICAL_DAYS.get(payload["scenario"])
            if days is None:
                self.send_json(404, error("2", "Unknown demo scenario."))
                return
            expiry = self.server.medical_reference_date + timedelta(days=days)
            self.send_json(200, {"required": True, "expiresOn": expiry.isoformat()})
            return
        status, body = respond(payload)
        if status == 200 and isinstance(payload, dict) and payload.get("isikukood") == "00000000006":
            time.sleep(self.server.mock_delay)
        self.send_json(status, body)


def main():
    """Start the explicitly configured local mock service."""
    delay = float(os.environ.get("MOCK_DELAY_SECONDS", "2"))
    if not 0 <= delay <= 30:
        raise ValueError("MOCK_DELAY_SECONDS must be between 0 and 30")
    server = MockServer((os.environ.get("MOCK_BIND", "127.0.0.1"),
                         int(os.environ.get("MOCK_PORT", "8081"))),
                        os.environ.get("MOCK_XROAD_PATH", DEFAULT_PATH),
                        os.environ.get("MOCK_XROAD_CLIENT", DEFAULT_CLIENT), delay)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
