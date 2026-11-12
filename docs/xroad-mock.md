# X-Road licence HTTP mock

This optional local service accepts HTTP requests and responds using the published
**ee-test `juhilubaKehtivus` v1 JSON contract**. It has no database dependency and
makes no calls to any real registry. The application can later use a configurable
integration base URL to select this mock during development.

## Postman collection

In Postman, select **Import** and choose
[`xroad-mock.postman_collection.json`](../mocks/xroad/postman/xroad-mock.postman_collection.json).
Start the mock with the command below, then open a request and select **Send**, or
run the whole collection. The ten requests include expected status and response-field
assertions. No separate environment is needed: collection variables hold `baseUrl`,
`servicePath` and `xRoadClient`. Update them if you changed the mock configuration.
Allow more than two seconds for the default slow-response scenario. This collection
covers the upstream mock, not the future frontend-facing API.

## Run and send a request

```sh
docker compose -p ite4120-xroad-mock -f compose.mock.yaml up -d --wait
curl --fail-with-body --max-time 5 \
  -H 'Content-Type: application/json' \
  -H 'X-Road-Client: ee-test/COM/00000000/licence-reminder-demo' \
  --data @mocks/xroad/request-valid.json \
  http://127.0.0.1:18081/r1/ee-test/GOV/70001490/liiklusregister/juhilubaKehtivus/v1
```

The body is `{"isikukood":"00000000001"}`. Test identifiers deliberately begin with
0 and cannot be real Estonian national IDs. Do not submit real identities. These
fixtures have no relationship to the account UUIDs in the optional SQL demo dataset.

Example response (date values are relative to the UTC request date):

```json
{
  "eesnimi": "Test",
  "perenimi": "Demo",
  "isikukood": "00000000001",
  "loaNr": "MOCK0001",
  "loaTyyp": "JUHILUBA",
  "staatus": "kehtiv",
  "valjastamisKp": "15.10.2018",
  "juhtimisOiguseLoppKp": "15.10.2028",
  "kategooriad": [
    {
      "kood": "B",
      "esmakordseValjastamiseKp": "01.06.2015",
      "kehtivusKp": "15.10.2028"
    }
  ]
}
```

The values above illustrate the field layout, not a fixed fixture timestamp.
`juhtimisOiguseLoppKp` is the source's driving-right end date; do not assume it means
every possible licence/certificate deadline. Date parsing must use `dd.MM.yyyy`.

| Request `isikukood` | Response scenario |
| --- | --- |
| `00000000001` | HTTP 200, valid licence, expiry 730 days ahead |
| `00000000002` | HTTP 200, valid licence, expiry 30 days ahead; the future application decides whether to show “At risk” |
| `00000000003` | HTTP 200, `kehtetu`, expired-licence reason; no licence details or categories |
| `00000000004` | HTTP 200, `kehtetu`, `JUHTIMISOIGUS_EI_OLE_KEHTIV`; no licence details or medical dates |
| `00000000005` | HTTP 503, synthetic service-unavailable error |
| `00000000006` | Delayed valid response, useful with `curl --max-time 1` to exercise a timeout |
| Any other identifier | HTTP 404, `errorCode: "2"` |
| Missing/invalid required inputs | HTTP 400, `errorCode: "1"` |

Name-based input also works with `{"eesnimi":"Test","perenimi":"Demo","loaNr":"MOCK0001"}`.
The request rule is a personal code **or** first name + surname + licence number.
A supplied licence number or name must match the selected synthetic person. Mock
validation rejects unknown fields and non-string inputs; this is a conservative mock
policy, not a claim about undocumented upstream handling of extra properties.

For an invalid response, identity fields come from the request, and `loaNr` appears
only when supplied. `pohjuseKood` uses the actual contract's three codes. Messages are
Estonian synthetic text; exact upstream wording is not asserted. Synthetic HTTP-layer
errors use `MOCK_*` codes. The 503/timeout scenarios are explicitly injected failures,
not claims about official service availability or official reason-code enumerations.

## Contract provenance and limits

Sources retrieved on 2026-10-16:

- [RIA ee-test service catalogue](https://x-tee.ee/catalogue/ee-test).
- [Published licence-service OpenAPI YAML](https://x-tee.ee/catalogue-data/ee-test/ee-test/GOV/70001490/liiklusregister/juhilubaKehtivus_3.yaml).
- [X-Road REST message protocol](https://docs.x-road.global/Protocols/pr-rest_x-road_message_protocol_for_rest.html).

`mocks/xroad/contracts/source.json` records the original file's SHA-256 and retrieval
information. The checked-in OpenAPI JSON preserves structural schema data, references,
enums, nullability and paths, while omitting descriptive prose/examples. This pins a
public **test** contract snapshot; it does not prove the production service is available
or that this project is eligible to consume it. Obtain the approved integration contract
and access before connecting to real systems.

The source contract contains no medical-certificate expiry or health details. It
returns licence/category details only for `staatus: "kehtiv"`. Medical-expiry reminders
and invalid-document details therefore still require another approved service/contract.
No fictional medical fields or local `valid/at_risk/invalid` fields are added to this
upstream JSON. Code 95 fields are supported by the pinned schema but omitted from these
fixtures because the synthetic ordinary category-B licence has no code 95 entry.

This mock simulates the consumer-facing `/r1/...` request shape, `X-Road-Client`, and
safe UUID correlation headers. It marks every response with `X-Mock-Service: true`.
It is **not a Security Server**: no membership authorization, certificates, signatures,
request hashes, message transport or full gateway error behavior is implemented. The
fixed client header is a test routing check, not authentication. Public error responses
also use the provider-shaped mock error body; do not use them to validate actual
Security Server fault schemas. Real interface testing still needs the approved X-tee
capability. Local HTTP carries synthetic data only and binds to localhost.

## Configuration and operations

All settings are owned by the development maintainer and require container recreation.

| Setting | Default / purpose |
| --- | --- |
| `MOCK_HOST_PORT` | `18081`; published only on `127.0.0.1` |
| `MOCK_DELAY_SECONDS` | `2`; injected delay for scenario 6, allowed range 0–30 seconds |
| `MOCK_XROAD_CLIENT` | Synthetic `ee-test/COM/00000000/licence-reminder-demo` |
| `MOCK_XROAD_PATH` | Test service consumer path shown above; configurable for contract revisions |
| `MOCK_BIND`, `MOCK_PORT` | Container interface `0.0.0.0:8081`; standalone Python defaults to `127.0.0.1:8081` |

```sh
# Contract shape and actual HTTP request/response tests in Docker.
docker compose -p ite4120-xroad-mock -f compose.mock.yaml run --rm --no-deps xroad-mock python -m unittest discover -s tests -v
# Same tests without Docker (requires permission to bind local sockets).
python3 -m unittest discover -s mocks/xroad/tests -v
# Review safe JSON request outcome logs.
docker compose -p ite4120-xroad-mock -f compose.mock.yaml logs xroad-mock
# Stop just the mock; PostgreSQL and its data remain separate.
docker compose -p ite4120-xroad-mock -f compose.mock.yaml down
```

The mock uses only Python's standard library; no package-manager dependencies or
lockfile are introduced. The official Python 3.13 slim/bookworm image is digest-pinned
in `compose.mock.yaml` (Python PSF licence; OS components inventoried by SPDX). It runs
as a non-root user with read-only files and no Linux capabilities. Existing image-scan
and SBOM scripts include the image. Vulnerability clearance remains a release gate,
not implied by passing tests. No production use is approved; `http.server` is sufficient
for this isolated development fixture, not a production server.

No persistent data, request bodies, names, identity numbers, licence numbers, raw paths
or client addresses are logged. Output is one JSON event per request, with UTC timestamp,
safe trace UUID and HTTP outcome. `docker compose ... down` removes the ephemeral mock
container and its local logs; no fixture-request history needs database retention. Log
levels and complete production audit/export policies remain application responsibilities.

## Traceability and verification

Change request: mimic X-Road licence requests and upstream responses for upcoming API
integration (US-05; supports data parsing for US-03/04/06/13). TEHIK requirements:
synthetic test data, input validation, safe errors/logs, correlation, explicit integration
configuration and controlled positive/negative integration tests. Implementation:
`mocks/xroad/server.py`, contract snapshot, optional `compose.mock.yaml`.

15 automated checks cover source response fields/types/enums, date format, valid/invalid
semantics, name lookup, missing/unknown/mismatched inputs, actual HTTP calls, headers,
no-sensitive-data logging, malformed/oversized payloads, content type, wrong routes,
unavailability, timeout recovery and health. These passed in Docker. The initial host
HTTP tests could not bind sockets under the sandbox; the Docker run passed all tests.
These tests validate the implemented fixture subset; they do not claim full upstream
business-rule or X-Road security-protocol conformance. No database migration or app
backend/frontend implementation is included.
