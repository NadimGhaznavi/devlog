---
name: bmforge-zmq
description: Implement an application-owned ZeroMQ REQ/REP server using PyZMQ, a declared message catalogue, request/reply semantics and on-demand health. Use when a project requires ZeroMQ interprocess messaging.
---

# ZeroMQ REQ/REP

Read `references/specification.md`, `references/engineering-contract.md` and `references/health-checks.md`. The runtime import whitelist and transport semantics are binding.

- Inspect pinned `references/source/bmgeoip/bmgeoip/zmq/` transport examples without copying GeoIP message handling.
- Request application-provided `port`, interface/bind address, timeouts, and **supported message methods**. If the message list is unknown, ask for it rather than inventing operations.
- Keep PyZMQ socket ownership, serialization, error handling and bounded request/reply mechanics in the transport. Keep dispatch operations in application interfaces/activities. Use only the approved REQ/REP pattern.
- Expose the specified native `health` message without a new listener or special worker. Coordinate with the HTTP health check when both exist.
- Add the literal `BMFORGE_COMPONENT` marker with ID `bmforge.zmq-server`, spec version `0.3.1`, to the owning module.
- Test a real local request/reply, malformed envelope, unknown command, timeout/failure and clean shutdown. Specifically test escaped lone Unicode surrogates in sender/method, nested payload strings and object keys: respond `invalid_request`, keep the REP worker alive, and answer a subsequent valid request. Valid Unicode surrogate pairs must remain accepted. No alternate broker/framework without approval.
