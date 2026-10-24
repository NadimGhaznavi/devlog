---
title: HTTP Display Server Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.http-server"
spec_version: "0.3.0"
spec_status: "draft"
translation_key: bmforge-component-http
---

# HTTP Display Server

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This contract follows the [engineering policy]({{ site.baseurl }}{% link pages/engineering-contract.md %}), [health check contract]({{ site.baseurl }}{% link pages/health-checks.md %}), and [traceability rules]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

## Intent and scope

Provide a small, locally owned HTTP service using Python's `ThreadingHTTPServer`, `BaseHTTPRequestHandler`, and (when HTML is needed) Jinja2 templates with autoescaping. Do not introduce Flask, FastAPI, a frontend build, authentication framework, or extra infrastructure unless required by the consumer.

## Approved runtime modules

This is the **complete approved module inventory for the reusable HTTP Display Server infrastructure** in specification `0.3.0`.

| Origin | Module | Purpose |
| --- | --- | --- |
| Python stdlib | `argparse` | CLI host and port options |
| Python stdlib | `http.server` | `ThreadingHTTPServer`, `BaseHTTPRequestHandler` and HTTP lifecycle |
| Python stdlib | `ipaddress` | Validate the configured IPv4 bind address |
| Python stdlib | `json` | JSON requests and the `/health` response |
| Python stdlib | `logging` | Report actionable request or lifecycle failures |
| Python stdlib | `pathlib` | Resolve templates and static assets |
| Python stdlib | `signal` | SIGTERM shutdown handling |
| Python stdlib | `urllib.parse` | URL and query-string parsing |
| Third-party | `jinja2` | `Environment`, `FileSystemLoader`, `StrictUndefined`, `select_autoescape` for server-rendered HTML |

**Approval boundary:** This list is binding for the reusable component infrastructure. Codex may rename local classes, configure ports and paths, and implement the application-owned handlers, but **must pause and ask the user** before adding, removing, or replacing an approved module or framework. Do not install another package as a workaround. User-approved changes belong in a revised BMForge specification before adoption.

These are Python import modules, not a complete transitive dependency tree. The consuming application's dependency file records installed package versions. Application business logic and separately selected BMForge components are outside this list; they must not quietly change this component's technology choices.

**Not part of this component:** PyMySQL imports in the BMGeoIP HTTP handler belong to the GeoIP application's database operations, not HTTP transport. Plotly.js, Leaflet and Cytoscape.js are *optional browser presentation capabilities* specified separately in [Display Visualizations]({{ site.baseurl }}{% link pages/component-visualization.md %}), never implicit HTTP dependencies. Select only those the application actually needs. Do not replace this implementation with Django, Flask, FastAPI, Werkzeug, Gunicorn, NGINX, or another server framework without user approval.

## Reference snapshot

- `components/reference/bmgeoip/bmgeoip/server/BMGeoIPServer.py`: listener, CLI binding, integration, lifecycle
- `components/reference/bmgeoip/bmgeoip/server/BMGeoIPHandler.py`: GET/HEAD/POST routing, templates, JSON response, health endpoints

These contain GeoIP-specific routes, data-loader integration, globals, and filenames. **Do not reproduce those behaviours** in unrelated applications.

## Required contract

- The application supplies the server class/entry point, request handler, routes, and service dependencies.
- Read listener defaults from the application's declared network constants and production overrides; optionally allow explicit CLI overrides. Validate host and port before bind. Publish the listener in `CMDB_NETWORK` and use the Network Configuration process.
- Use a bounded request socket timeout. Bind failure and fatal worker failure must surface as errors; do not claim readiness before successfully binding.
- Implement `GET`, `HEAD`, and only the required mutation methods. A HEAD request sends headers but no body. Unknown routes return 404.
- Return accurate status codes, `Content-Type`, UTF-8 where applicable, `Content-Length`, `Cache-Control: no-store` where appropriate, and `X-Content-Type-Options: nosniff`.
- For JSON writes, validate method, path, Content-Type, request length, schema, and user-supplied fields; reject malformed or oversized requests with 4xx rather than uncontrolled exceptions. Consider origin/access policy for state-changing endpoints; same-origin checks are not authentication.
- Use Jinja2 HTML autoescaping and fail on missing template values; keep templates, static assets and route data application-owned. Never embed secrets in rendered output or public diagnostics.
- Serve `GET /health` on the existing HTTP listener as the application's CMDB-facing check: `200` when its required components are usable, `503` when a known required component is unavailable. Return the small component-status JSON defined by Application Health Checks. A fixed `200` for a running process is insufficient. Do not add a separate `/ready` implementation without a concrete requirement.
- Cleanly close the HTTP listener and any owned background workers during termination, including SIGTERM. No orphaned threads.
- Keep application-specific business logic out of the generic HTTP mechanics. Use typed interfaces or injected collaborators where useful without inventing extra layers.

## Acceptance checks

1. Bind to a test loopback address and ephemeral port; GET known path returns correct body, type and length; HEAD omits body.
2. Unknown route is 404; unsupported mutation and malformed/oversized JSON do not crash the server.
3. HTML user-provided values are escaped; static assets cannot traverse outside allowed paths.
4. `GET /health` returns `200` and component statuses when required components are usable; a simulated ZeroMQ or application DB failure returns `503` with the failed component identified. No direct database probe by CMDB and no new HTTP listener.
5. Address-in-use, invalid port and graceful shutdown are tested; service exits without lingering workers.
6. Confirm the installed application exposes its declared address/port, respects production overrides, and has no runtime import of BMForge/bmgeoip.
7. Verify the HTTP implementation uses the approved runtime modules only; any proposed replacement or addition was approved by the user before implementation.
