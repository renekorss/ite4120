"""Contract shape and real HTTP integration checks for the local X-Road mock."""
from contextlib import redirect_stdout
from datetime import date
import http.client
import io
import json
from pathlib import Path
import socket
import sys
from threading import Thread
import time
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import DEFAULT_CLIENT, DEFAULT_PATH, MockServer, respond

CONTRACT = json.loads((Path(__file__).resolve().parents[1] /
                       "contracts/juhiluba-kehtivus.openapi.json").read_text())


def validate(value, schema):
    """Check the schema features used by this pinned upstream contract."""
    if "$ref" in schema:
        node = CONTRACT
        for key in schema["$ref"].removeprefix("#/").split("/"):
            node = node[key]
        return validate(value, node)
    if value is None and schema.get("nullable"):
        return
    if schema.get("type") == "object":
        if not isinstance(value, dict):
            raise AssertionError("Expected object")
        if set(value) - set(schema.get("properties", {})):
            raise AssertionError("Mock introduced a non-contract response field")
        for key, child in value.items():
            validate(child, schema["properties"][key])
    elif schema.get("type") == "array":
        if not isinstance(value, list):
            raise AssertionError("Expected array")
        for item in value:
            validate(item, schema["items"])
    elif schema.get("type") == "string":
        if not isinstance(value, str):
            raise AssertionError("Expected string")
    if "enum" in schema and value not in schema["enum"]:
        raise AssertionError("Value not in upstream enum")


class ContractTests(unittest.TestCase):
    def test_scenario_responses_follow_pinned_upstream_properties(self):
        for number in range(1, 7):
            with self.subTest(number=number):
                status, body = respond({"isikukood": f"{number:011d}"}, date(2026, 10, 16))
                schema = "JuhilubaKehtivusResponse" if status == 200 else "ErrorResult"
                validate(body, {"$ref": "#/components/schemas/" + schema})

    def test_valid_has_actual_estonian_fields_and_date_format(self):
        status, body = respond({"isikukood": "00000000002"}, date(2026, 10, 16))
        self.assertEqual(status, 200)
        self.assertEqual(body["juhtimisOiguseLoppKp"], "15.11.2026")
        self.assertEqual(body["staatus"], "kehtiv")
        self.assertEqual(body["kategooriad"][0]["kood"], "B")
        self.assertNotIn("medical_certificate", body)

    def test_invalid_omits_licence_details_and_uses_actual_reason_codes(self):
        for number, reason in ((3, "KEHTIVAT_JUHILUBA_EI_LEITUD"),
                               (4, "JUHTIMISOIGUS_EI_OLE_KEHTIV")):
            status, body = respond({"isikukood": f"{number:011d}"})
            self.assertEqual(status, 200)
            self.assertEqual(body["staatus"], "kehtetu")
            self.assertEqual(body["pohjuseKood"], reason)
            self.assertNotIn("loaNr", body)
            self.assertNotIn("kategooriad", body)
            self.assertNotIn("juhtimisOiguseLoppKp", body)

    def test_invalid_with_number_echoes_only_supplied_identity_and_number(self):
        status, body = respond({"isikukood": "00000000003", "loaNr": "MOCK0003"})
        self.assertEqual(status, 200)
        self.assertEqual(body["loaNr"], "MOCK0003")
        self.assertEqual(body["pohjuseKood"], "JUHILUBA_EI_OLE_KEHTIV")
        self.assertNotIn("eesnimi", body)

    def test_name_and_number_lookup(self):
        self.assertEqual(respond({"eesnimi": "Test", "perenimi": "Demo", "loaNr": "MOCK0001"})[0], 200)

    def test_missing_malformed_or_incorrect_field_types(self):
        for body in ({}, [], {"eesnimi": "Test", "perenimi": "Demo"},
                     {"loaNr": "MOCK0001"}, {"isikukood": None},
                     {"isikukood": "  "}, {"unexpected": "x"}):
            with self.subTest(body=body):
                status, result = respond(body)
                self.assertEqual((status, result["errorCode"]), (400, "1"))

    def test_unknown_person_or_mismatched_licence(self):
        for body in ({"isikukood": "00000000999"},
                     {"isikukood": "00000000001", "loaNr": "MOCK9999"},
                     {"isikukood": "00000000001", "eesnimi": "Wrong"}):
            self.assertEqual(respond(body)[0], 404)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.capture = redirect_stdout(self.output)
        self.capture.__enter__()
        self.server = MockServer(("127.0.0.1", 0), delay=0.1)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.capture.__exit__(None, None, None)

    def request(self, body=b'{"isikukood":"00000000001"}', headers=None, path=DEFAULT_PATH, method="POST", timeout=2):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=timeout)
        try:
            connection.request(method, path, body=body, headers=headers if headers is not None else {
                "Content-Type": "application/json", "X-Road-Client": DEFAULT_CLIENT})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def test_roundtrip_and_correlation(self):
        trace = str(uuid4())
        status, headers, body = self.request(headers={"Content-Type": "application/json",
            "X-Road-Client": DEFAULT_CLIENT, "X-Road-Id": trace})
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Road-Id"], trace)
        self.assertEqual(headers["X-Mock-Service"], "true")
        self.assertEqual(body["staatus"], "kehtiv")

    def test_logs_do_not_include_request_identity_body_or_path(self):
        self.request()
        logs = self.output.getvalue()
        self.assertNotIn("00000000001", logs)
        self.assertNotIn("isikukood", logs)
        self.assertNotIn(DEFAULT_PATH, logs)
        event = json.loads(logs.splitlines()[-1])
        self.assertEqual(event["http"]["response"]["status_code"], 200)

    def test_rejects_missing_client_header(self):
        self.assertEqual(self.request(headers={"Content-Type": "application/json"})[0], 403)

    def test_rejects_invalid_json_and_oversized_body(self):
        self.assertEqual(self.request(body=b"{")[0], 400)
        self.assertEqual(self.request(body=b"x" * 4097)[0], 400)

    def test_rejects_wrong_content_type_and_path(self):
        self.assertEqual(self.request(headers={"Content-Type": "text/plain", "X-Road-Client": DEFAULT_CLIENT})[0], 415)
        self.assertEqual(self.request(path="/unknown")[0], 404)

    def test_unavailability(self):
        self.assertEqual(self.request(body=b'{"isikukood":"00000000005"}')[0], 503)

    def test_slow_response_can_time_out_then_service_recovers(self):
        with self.assertRaises((TimeoutError, socket.timeout)):
            self.request(body=b'{"isikukood":"00000000006"}', timeout=0.02)
        time.sleep(0.15)
        self.assertEqual(self.request()[0], 200)

    def test_health(self):
        self.assertEqual(self.request(path="/health", method="GET")[0], 200)


if __name__ == "__main__":
    unittest.main()
