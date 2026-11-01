---
name: bmforge-zmq
description: Implement application-owned ZeroMQ REQ/REP clients and servers using PyZMQ over TCP or named local IPC sockets, a declared message catalogue and on-demand health. Use when a project requires ZeroMQ interprocess messaging.
---

# ZeroMQ REQ/REP

Read `references/specification.md`, `references/engineering-contract.md` and `references/health-checks.md`. The runtime import whitelist and transport semantics are binding.

- Inspect pinned `references/source/bmgeoip/bmgeoip/zmq/` transport examples without copying GeoIP message handling.
- Request the application's transport choice: `tcp://host:port` with network settings, or `ipc:///absolute/path.sock` for processes on the same host. Keep existing TCP defaults unless IPC is selected. Configure both server and clients for the selected endpoint; do not require a TCP port for IPC or open an extra listener.
- Request timeouts and **supported message methods**. If the message list is unknown, ask for it rather than inventing operations.
- For IPC, require deployment-owned runtime directory, ownership, restrictive permissions/umask and single-instance lifecycle before binding. Keep socket creation with the server; clients only connect. Follow the specification's collision, stale-path and cleanup rules. Keep IPC paths outside the IP-only `CMDB_NETWORK` schema.
- Keep PyZMQ socket ownership, serialization, error handling and bounded request/reply mechanics in the transport. Keep dispatch operations in application interfaces/activities. Use only the approved REQ/REP pattern.
- Expose the specified native `health` message without a new listener or special worker. Coordinate with the HTTP health check when both exist.
- Add the literal `BMFORGE_COMPONENT` marker with ID `bmforge.zmq-server`, spec version `0.4.0`, to the owning module.
- Test a real local request/reply on each supported transport, malformed envelope, unknown command, timeout/failure, health and clean shutdown/restart. For IPC, also verify access from approved/denied local users, startup/path failures and no TCP listener. Specifically test escaped lone Unicode surrogates in sender/method, nested payload strings and object keys: respond `invalid_request`, keep the REP worker alive, and answer a subsequent valid request. Valid Unicode surrogate pairs must remain accepted. No alternate broker/framework without approval.
