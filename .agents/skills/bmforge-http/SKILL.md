---
name: bmforge-http
description: Implement a small Python standard-library HTTP display server with optional Jinja2 templates and on-demand health, using BMForge's pinned HTTP transport contract. Use when the application needs an HTTP UI or API.
---

# HTTP Display Server

Read `references/specification.md`, `references/engineering-contract.md` and `references/health-checks.md` before implementation. The fixed Python module inventory appears in `references/specification.md`.

- Inspect the **frozen** BMGeoIP HTTP examples under `references/source/bmgeoip/bmgeoip/server/`. These illustrate transport only, not an application to copy wholesale.
- Build an **application-owned** `http.server.ThreadingHTTPServer` and request handler; choose actual routes, bind port/interface, templates, and configuration from this application's requirements. Use Jinja2 only when rendering HTML. No Flask, FastAPI, Django or replacement framework without approval.
- Supply an on-demand `GET /health` through this HTTP application, including relevant internal checks on existing component interfaces. No new monitoring daemon.
- When providing a user-facing UI, apply the already-installed `bmforge-localization` skill for translated text, request-local language selection and HTML `lang`, without changing the HTTP transport's approved Python module list.
- Keep workflow logic in `activity/`, external and domain bridges in `interface/`, and data values in `entity/`. Request handlers must not issue SQL directly.
- Place the literal `BMFORGE_COMPONENT` marker with ID `bmforge.http-server` and spec version `0.3.0` in the owning implementation module.
- Run the contract's acceptance tests in the consumer. Do not treat copying the example as completion.
