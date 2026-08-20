# Server Mode and Local UI

Read this when the user needs a shared GuardEx screening process, a separate
deployment boundary, HTTP clients, or the local Playground/Logs/Config UI.

## Local vs Server Mode

`Guard()` with no `api_key`, `base_url`, `GUARDEX_API_KEY`, or
`GUARDEX_BASE_URL` uses the in-process `LocalRunner`. This is simplest for one
Python process.

Use server mode when several workers would otherwise each load the ML models, a
central safety service is desired, or the app only installs the lightweight core
SDK:

```python
from guardex import Guard

guard = Guard(base_url="http://guardex.internal:8001")
```

`api_key` is sent as an `Authorization: Bearer ...` header for a proxy or
gateway to validate. The reference GuardEx server itself does not implement
authentication.

## Reference Server

```bash
pip install 'guardex-ai[local,server]'
guardex-server --host 0.0.0.0 --port 8001
```

The server exposes:

- `POST /v1/screen`
- `POST /v1/screen/batch`
- `POST /v1/classify`
- `POST /v1/pii/scan`
- `POST /v1/pii/mask`
- `POST /v1/grounding`
- `GET /v1/health`

Models warm during startup. Put the server on a private network or behind auth
if reachable outside the host.

## Local UI

```bash
pip install 'guardex-ai[local,ui]'
guardex-server --ui
```

The UI is served at `http://127.0.0.1:8001` and includes:

- Playground: run sample or custom text through the full gate cascade
- Logs: in-memory recent screening events, cleared on restart
- Config: edit server defaults and save them to `guardex.policy.yaml`

The UI has no authentication. The CLI refuses `--ui` on non-loopback hosts
unless `--ui-unsafe-bind` is passed. Do not expose it publicly unless the user
has explicitly added network protections.

`--log-text` stores request text in the Logs view. Leave it off unless the user
accepts that raw text may include sensitive data.

## Engine Config

Keep these files separate:

- `guardex_policy.yaml`, `guardex.policy.yaml`, or any explicit path passed to
  `GuardExPolicy.from_yaml(...)`: application policy knobs such as blocked
  categories, PII action/threshold, topic scope, safety routes, and grounding
  defaults. The UI saves `guardex.policy.yaml`.
- `guardex.yaml`: local ML engine settings auto-loaded from the current working
  directory, such as model repos, cache directory, Ollama, and feature toggles.

Do not treat `guardex.yaml` as the user-facing policy file.
