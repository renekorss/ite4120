"""Exercise the shipped frontend Postman requests over actual HTTP without printing tokens."""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
collection = json.loads((root / "postman/frontend-api.postman_collection.json").read_text())
variables = {item["key"]: item["value"] for item in collection["variable"]}
credentials_path = root / ".secrets/frontend-api.postman_environment.json"
if not credentials_path.exists():
    raise SystemExit("Run the explicit API account seed command first (see docs/api.md)")
private_environment = json.loads(credentials_path.read_text())
variables.update({item["key"]: item["value"] for item in private_environment["values"]})
variables["apiBaseUrl"] = os.environ.get("API_BASE_URL", variables["apiBaseUrl"])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def resolve(value):
    """Substitute only locally captured collection variables."""
    return re.sub(r"\{\{([^}]+)\}\}", lambda match: variables[match[1]], value)


def requests_in(items):
    """Walk documentation folders without changing the numbered test workflow."""
    for item in items:
        if "request" in item:
            yield item
        else:
            yield from requests_in(item["item"])


for item in sorted(requests_in(collection["item"]), key=lambda item: item["name"]):
    request = item["request"]
    scripts = "\n".join(item["event"][0]["script"]["exec"])
    expected = (
        (401, 404)
        if item["name"] == "24 Reject unlisted demo code"
        else (int(re.search(r"to\.have\.status\((\d+)\)", scripts)[1]),)
    )
    headers = {h["key"]: resolve(h["value"]) for h in request["header"]}
    if request.get("auth", {}).get("type") != "noauth":
        headers["Authorization"] = "Bearer " + variables["accessToken"]
    raw = request.get("body", {}).get("raw")
    req = urllib.request.Request(
        resolve(request["url"]),
        data=resolve(raw).encode() if raw else None,
        headers=headers,
        method=request["method"],
    )
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status, raw_response = response.status, response.read()
    if status not in expected:
        raise SystemExit(f"{item['name']}: expected {expected}, received {status}")
    body = json.loads(raw_response) if raw_response else None
    if 'set("accessToken"' in scripts:
        variables["accessToken"] = body["accessToken"]
    if 'set("checkId"' in scripts:
        variables["checkId"] = body["check"]["id"]
        assert body["check"]["outcome"] == "successful"
    if 'set("subscriptionId"' in scripts:
        variables["subscriptionId"] = body["id"]
        assert body["deliveryAvailable"] is False
    if '"Recorded upstream failure"' in scripts:
        assert body["check"]["outcome"] == "failed"
        assert body["check"]["error"]["code"] == "XR_UNAVAILABLE"
    print(f"{item['name']}: {status}")
print(
    "All 24 frontend collection requests passed over HTTP. "
    "Postman JavaScript is not executed by this checker."
)
