---
title: ZeroMQ Request/Reply Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.zmq-server"
spec_version: "0.4.0"
spec_status: "draft"
translation_key: bmforge-component-zmq
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This contract follows the [engineering policy]({{ site.baseurl }}{% link pages/engineering-contract.md %}), [health check contract]({{ site.baseurl }}{% link pages/health-checks.md %}), and [traceability rules]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

## Intent and scope

Implement application-owned `pyzmq` request/reply clients and servers for small JSON control and query messages over **TCP or named local IPC sockets**. This blueprint covers **REQ/REP only**. Transport selection changes the endpoint, not the message protocol or application handlers. Do not silently substitute PUB/SUB, PUSH/PULL, queues or distributed brokers; a different messaging pattern requires a separate approved specification.

## Approved runtime modules

This is the **complete approved module inventory for the reusable ZeroMQ REQ/REP infrastructure** in specification `0.4.0`. PyZMQ provides both transports; IPC adds no Python module or third-party dependency. Provision filesystem access and runtime directories through the application's existing deployment lifecycle.

| Origin | Module | Purpose |
| --- | --- | --- |
| Python stdlib | `collections.abc` | `Callable` handler interface |
| Python stdlib | `dataclasses` | `dataclass` and `field` for the message envelope |
| Python stdlib | `json` | Encode and decode the versioned message payload |
| Python stdlib | `threading` | `Thread` and `Event` for the socket-owning worker lifecycle |
| Python stdlib | `typing` | `Any` annotation in the envelope |
| Third-party | `zmq` | PyZMQ `Context`, REP socket, polling, timeout and cleanup |

**Approval boundary:** This list is binding for the reusable component infrastructure. Codex may rename local classes, configure ports and paths, and implement the application-owned handlers, but **must pause and ask the user** before adding, removing, or replacing an approved module or framework. Do not install another package as a workaround. User-approved changes belong in a revised BMForge specification before adoption.

These are Python import modules, not a complete transitive dependency tree. The consuming application's dependency file records installed package versions. Application business logic and separately selected BMForge components are outside this list; they must not quietly change this component's technology choices.

**Not part of this component:** `pymysql`, the BMGeoIP `GeoIpLookup` class, and application-specific `LookupHandler` behaviour in the snapshot are business integration, not additional approved transport modules. Do not substitute asyncio, a broker, a raw-socket protocol, or different ZeroMQ communication patterns. A new transport pattern needs its own approved specification.

## Reference snapshot

- `components/reference/bmgeoip/bmgeoip/zmq/ZMQServer.py`: socket-owning worker, endpoint passed to `bind`, ready/failure signalling, orderly cleanup
- `components/reference/bmgeoip/bmgeoip/zmq/ZMQMsg.py`: versioned JSON envelope
- `components/reference/bmgeoip/bmgeoip/server/LookupHandler.py`: example *application-owned* dispatch, input validation and error response
- `components/reference/bmgeoip/bmgeoip/constants/DZMQ.py`: snapshot of timeout and protocol constants

## Endpoint selection and local IPC

Choose one transport for the application endpoint. Preserve existing TCP defaults unless the application selects IPC. The server binds and each client connects using its resolved endpoint:

| Transport | Example | Configuration |
| --- | --- | --- |
| TCP | `tcp://127.0.0.1:18081` | Existing application interface/port resolver and `CMDB_NETWORK` conventions; clients use a reachable destination rather than a wildcard bind address. |
| Local IPC | `ipc:///run/example/control.sock` | An application-configured absolute filesystem path on the same host, shared by the server, clients and health probe. No IP address or TCP port is required. |

Keep IPC paths in application-owned configuration under the existing runtime-configuration precedence. `CMDB_NETWORK` remains IP-only: do not invent a port or extend its tuple schema for IPC. An IPC-only application has no IP listener to declare for this endpoint. Do not bind both transports or fall back to TCP implicitly.

For IPC on supported Unix-domain-socket platforms:

- Use an absolute named filesystem socket, not a relative path, wildcard or Linux abstract `ipc://@...` address. Abstract sockets do not provide filesystem access controls. Reject invalid paths and platform path-length violations; fail visibly if IPC is unavailable.
- Before starting the worker, deployment must provide the runtime directory and service user/group, restrict directory traversal to approved callers, and allow only the server identity to create/remove entries. Set a restrictive service umask before bind and verify the socket's effective access permissions. Do not temporarily expose a permissive socket or change the process-wide umask inside the worker. Clients only connect; they do not create directories, change permissions or remove socket files.
- Enforce one server instance per socket path through the service lifecycle. **A second libzmq IPC bind can replace an existing pathname binding**; do not rely on a TCP-style address-in-use error. Recover a stale socket only after establishing that its owning instance has stopped, and never unlink an arbitrary existing file or another instance's socket.
- The server owns bind/close and orderly socket cleanup; deployment recreates transient runtime directories after reboot. Verify clean stop/restart and controlled recovery after an unclean stop. Missing directories, permission errors or failed binds must prevent a ready/healthy report. Keep timeout, validation and application authorisation rules identical on both transports.

Upstream details: [ZeroMQ IPC transport](https://libzmq.readthedocs.io/en/latest/zmq_ipc.html) and [Linux Unix-domain socket permissions](https://man7.org/linux/man-pages/man7/unix.7.html).

## Required contract

- Implement the selected configurable TCP or IPC endpoint as described above, using the same REQ/REP envelope on both. For TCP, declare the listener via BMForge Network Configuration and CMDB conventions; never expose a listener beyond the trusted network without explicit review of security requirements.
- The worker creates, owns, uses, and closes its own ZeroMQ context and REP socket **on the same thread**. Use a bounded poll interval, send timeout, and `LINGER=0`; do not share sockets across threads.
- Report bind/initialisation failure synchronously to the parent before it claims the listener is ready. Surface later fatal worker failures through an explicit check or equivalent supervisor integration.
- Receive exactly one JSON frame per request and send exactly one reply per received request, including invalid messages, preserving REQ/REP alternation. Define safe behaviour for malformed frames and handler exceptions; do not allow one bad request to kill the worker silently.
- A versioned UTF-8 JSON envelope includes `protocol_version` (integer), `sender` (nonempty string), `target` (string or null), `method` (nonempty string), and `payload` (object). Reject incompatible versions or invalid shapes. Bound message size for the application's threat model.
- **Reject invalid Unicode scalar values before application dispatch.** JSON `\\u` escapes can decode into lone UTF-16 surrogates even when the wire frame is valid UTF-8. Validate all decoded strings and object keys, including nested payloads and envelope correlation fields. Respond with `invalid_request` and keep the listener usable. Valid escaped surrogate *pairs* representing Unicode characters are legal. Invalid external Unicode must never be classified as a fatal application defect.
- Replies preserve correlation context from the request when available. Define success `status: ok` and error `status: error`, with structured `error.code` and `error.message`. Application handlers define supported `method` values, argument validation, authorisation if required and business operations.
- Shut down promptly on service stop, release the endpoint, and report fatal errors. Client implementations need bounded send/receive timeouts and a defined retry/reconnect policy on either transport, because a failed REQ exchange can require rebuilding a REQ socket.
- Reserve `method: "health"` with empty object payload on the existing REQ/REP endpoint. A working listener/handler replies with the usual `status: "ok"` envelope; an unavailable listener must fail the bounded client call. Do not add an HTTP server, background supervisor, or automatic recovery solely for monitoring. The application's HTTP `/health` may call this method to report ZeroMQ status to CMDB.
- Do not add a generic dispatcher, discovery service, persistence layer, or asynchronous broker without a requirement.

## Acceptance checks

1. Exercise each transport the application supports: TCP on a loopback ephemeral port and/or IPC at a temporary absolute socket path. A real client exchanges the same valid request/reply envelope, including protocol and routing fields. When both are supported, run the protocol, failure and health checks below on both.
2. Bad JSON, multi-frame message, unsupported protocol version, wrong target and unsupported method return defined errors; worker remains usable afterwards.
3. Syntactically valid JSON containing escaped lone `\\ud800` / `\\udfff` values in envelope strings, nested payload values or object keys yields `invalid_request`. A subsequent valid request succeeds on the **same server**, and valid Unicode including escaped surrogate pairs remains accepted.
4. A handler exception is handled according to documented failure policy, never a silent hang.
5. TCP bind conflict is reported during startup; IPC duplicate startup is prevented by the service lifecycle without replacing the active binding. Missing/unwritable IPC directories, invalid/overlong paths and unsupported IPC fail startup visibly without a TCP fallback. Forced worker failure is observable by its supervisor.
6. Shutdown releases sockets and threads; client timeout/recovery is tested. For IPC, verify socket cleanup, clean restart and controlled stale-socket recovery without deleting unrelated files.
7. A `health` request gets a normal success reply while the ZeroMQ handler is usable; a stopped listener times out/fails within the configured bound and cannot be reported healthy by the application.
8. Application code does not import bmgeoip or BMForge at runtime; its message methods and payload schemas are documented locally.
9. Verify the ZeroMQ transport uses the approved runtime modules only; any proposed replacement or addition was approved by the user before implementation.
10. For IPC, a permitted local user exchanges requests; a different unprivileged user outside the approved access group cannot connect or replace the socket. Verify effective directory/socket permissions from creation, no TCP listener for this endpoint, and client/health configuration that needs no IP address or port. Document the user/group checks actually run.
