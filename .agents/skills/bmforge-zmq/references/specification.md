---
title: ZeroMQ Request/Reply Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.zmq-server"
spec_version: "0.3.0"
spec_status: "draft"
translation_key: bmforge-component-zmq
---

# ZeroMQ Request/Reply Server

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

This contract follows the [engineering policy]({{ site.baseurl }}{% link pages/engineering-contract.md %}), [health check contract]({{ site.baseurl }}{% link pages/health-checks.md %}), and [traceability rules]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}).

## Intent and scope

Implement a locally owned `pyzmq` request/reply listener for small JSON control and query messages. This blueprint covers **REQ/REP only**. Do not silently substitute PUB/SUB, PUSH/PULL, queues or distributed brokers. Specify a different transport separately when application requirements demand it.

## Approved runtime modules

This is the **complete approved module inventory for the reusable ZeroMQ REQ/REP Server infrastructure** in specification `0.3.0`.

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

- `components/reference/bmgeoip/bmgeoip/zmq/ZMQServer.py`: socket-owning worker, ready/failure signalling, orderly cleanup
- `components/reference/bmgeoip/bmgeoip/zmq/ZMQMsg.py`: versioned JSON envelope
- `components/reference/bmgeoip/bmgeoip/server/LookupHandler.py`: example *application-owned* dispatch, input validation and error response
- `components/reference/bmgeoip/bmgeoip/constants/DZMQ.py`: snapshot of timeout and protocol constants

## Required contract

- Implement server with configurable `tcp://host:port` endpoint using application network settings. Declare the listener via BMForge Network Configuration and CMDB conventions; never expose a listener beyond the trusted network without explicit review of security requirements.
- The worker creates, owns, uses, and closes its own ZeroMQ context and REP socket **on the same thread**. Use a bounded poll interval, send timeout, and `LINGER=0`; do not share sockets across threads.
- Report bind/initialisation failure synchronously to the parent before it claims the listener is ready. Surface later fatal worker failures through an explicit check or equivalent supervisor integration.
- Receive exactly one JSON frame per request and send exactly one reply per received request, including invalid messages, preserving REQ/REP alternation. Define safe behaviour for malformed frames and handler exceptions; do not allow one bad request to kill the worker silently.
- A versioned UTF-8 JSON envelope includes `protocol_version` (integer), `sender` (nonempty string), `target` (string or null), `method` (nonempty string), and `payload` (object). Reject incompatible versions or invalid shapes. Bound message size for the application's threat model.
- Replies preserve correlation context from the request when available. Define success `status: ok` and error `status: error`, with structured `error.code` and `error.message`. Application handlers define supported `method` values, argument validation, authorisation if required and business operations.
- Shut down promptly on service stop, release the port, and report fatal errors. Client implementations need a receive timeout and defined retry/reconnect policy, because a failed REQ exchange can require rebuilding a REQ socket.
- Reserve `method: "health"` with empty object payload on the existing REQ/REP endpoint. A working listener/handler replies with the usual `status: "ok"` envelope; an unavailable listener must fail the bounded client call. Do not add an HTTP server, background supervisor, or automatic recovery solely for monitoring. The application's HTTP `/health` may call this method to report ZeroMQ status to CMDB.
- Do not add a generic dispatcher, discovery service, persistence layer, or asynchronous broker without a requirement.

## Acceptance checks

1. Start on loopback ephemeral port; a client exchanges a valid request/reply envelope, including protocol and routing fields.
2. Bad JSON, multi-frame message, unsupported protocol version, wrong target and unsupported method return defined errors; worker remains usable afterwards.
3. A handler exception is handled according to documented failure policy, never a silent hang.
4. Bind conflict is reported during startup; forced worker failure is observable by its supervisor.
5. Shutdown releases sockets and threads; client timeout/recovery is tested.
6. A `health` request gets a normal success reply while the ZeroMQ handler is usable; a stopped listener times out/fails within the configured bound and cannot be reported healthy by the application.
7. Application code does not import bmgeoip or BMForge at runtime; its message methods and payload schemas are documented locally.
8. Verify the ZeroMQ transport uses the approved runtime modules only; any proposed replacement or addition was approved by the user before implementation.
