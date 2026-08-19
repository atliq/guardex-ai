# Local UI

`guardex-server --ui` serves a Playground, a Logs view, and a Config editor
alongside the `/v1` screening protocol, on one port.

## Install and run

```bash
pip install 'guardex-ai[local,ui]'
guardex-server --ui
```

Models load at startup, so the first run takes a minute. Then open
<http://127.0.0.1:8001>.

| Flag | Effect |
| --- | --- |
| `--ui` | Serve the UI at `/` |
| `--port` | Port to bind (default 8001) |
| `--log-text` | Record request text in the Logs view |
| `--ui-unsafe-bind` | Permit `--ui` on a non-loopback host |

## Playground

Screens text against the running pipeline and shows the verdict, the
detected PII entities with their confidence and detection method, the
processed text, and a per-gate timing breakdown.

The PII action and threshold controls seed from the server config and
override it for that one request. To change what every caller gets, use
the Config page.

## Logs

The last 1000 screening calls, held in memory and cleared on restart. Each
row carries the stage, action, category, PII count, and latency; expanding a
row shows the per-gate timings and the request id.

Request text is **not** recorded unless you start the server with
`--log-text`.

## Config

Every field applies to the running server the moment you change it. A
request that sets a field explicitly still wins over the server default.

**Save to guardex.policy.yaml** writes the fields you changed — defaults are
omitted — to the working directory:

```python
from guardex import Guard, GuardExPolicy

guard = Guard(policy=GuardExPolicy.from_yaml("guardex.policy.yaml"))
```

**Reset to defaults** restores every field and takes effect immediately.

## Authentication

There is none. `PUT /v1/config` changes screening policy for every caller of
the server, so `--ui` refuses a non-loopback `--host` unless you pass
`--ui-unsafe-bind`. To expose the UI beyond localhost, put your own
authenticating proxy in front of it.

## Building from source

The published wheel ships prebuilt assets, so installing does not require
Node. To work on the UI itself:

```bash
cd ui
npm ci
npm run dev        # http://localhost:5173, proxies /v1 to 127.0.0.1:8001
npm run build      # writes guardex/ui_assets/
```
