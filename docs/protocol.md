# DevLog request/reply contract

Version 1 uses one UTF-8 JSON frame per request and reply on the configured ZMQ
endpoint (`tcp://0.0.0.0:19701` by default). There is one user and one global
active task. The service never reads a Git checkout or executes Git.

```json
{"protocol_version":1,"sender":"dl","target":"devlog","method":"start","payload":{"repository":"github.com/owner/project"}}
```

Every envelope has exactly `protocol_version` (integer 1), `sender` (nonempty
string), `target` (string or null), `method` (nonempty string), and `payload`
(object). Requests target `devlog`; replies target the request sender and echo
the method. A reply's payload is either `{"status":"ok","result":{...}}` or
`{"status":"error","error":{"code":"...","message_key":"...","message":"..."}}`.
Malformed requests receive an `invalid_request` error; invalid requests do not stop the listener. This includes syntactically valid JSON with escaped **lone Unicode surrogates** in envelope strings, nested payload strings or object keys. They are rejected before handler dispatch. Valid surrogate pairs remain accepted, and a valid request after an invalid one continues to work on the same ZeroMQ worker.
Unexpected internal failures receive an error and terminate the worker visibly,
so the service exits and systemd can restart it.

| Method | Payload | Result |
| --- | --- | --- |
| `status` | Empty object | `task_id`, `repository` (both null when idle; otherwise the global active task's ID and full repository identity) |
| `start` | `repository` | `task_id`, `status: running` |
| `pause` | `repository` | `task_id`, `status: paused` |
| `commit` | `repository`, `phase: prepare`, optional `commit_sha` for recovery | Unfinished task's `task_id` and `status`, or the task already linked to the supplied SHA |
| `commit` | `repository`, `phase: complete`, `task_id`, `commit_sha`, `message` | `task_id`, `status: completed`, `commit_sha` |
| `health` | Empty object | Empty result, after checking the worker's application DAL |

`status` reads the global tracker state without modifying tasks or intervals.
It requires no local Git checkout and rejects nonempty payloads.

The CLI normalizes the GitHub `origin` remote into `github.com/owner/repository`
(case insensitive, no `.git`). The server treats that identifier as data. It has
no local checkout path, Git credentials, or dependency on the checkout's location.

`start` atomically pauses the current task and creates or resumes the requested
repository's unfinished task. Repeating it on the active task does not add an
interval. Repeating `pause` on a paused task changes nothing. Pausing an inactive
repository never pauses a different repository. A repository has at most one
unfinished task. `commit` completion is idempotent for the same task and SHA.
An already completed task cannot be linked to a different SHA.

The server timestamps transitions in UTC and persists every active interval.
Open intervals continue across service restarts. Paused time is excluded.
Reports include completed and unfinished work, split at configured local-day
boundaries, including daylight-saving transitions. Report date endpoints are
inclusive; the default is the last seven calendar days. Maximum range: 366 days.

Both client send and receive have finite timeouts (five seconds each by default),
and each call uses a fresh REQ socket. There are no automatic request retries.
A timeout after sending means the result may be unknown. `start` and `pause` can
be repeated to establish the desired state. After an uncertain commit completion,
`dl commit --record SHA` records the existing commit without committing or pushing
again. No local commit is discarded. Git and MariaDB are separate systems; their
updates cannot form a single transaction.

HTTP provides read-only `GET`/`HEAD` routes `/`, `/api/report`, `/health`, and the
two application static assets. Reports accept `repository`, `start`, `end`, and
`lang` query parameters. `/health` returns 200 only when HTTP, ZMQ, and the
application's own DB connections work; known dependency failure returns 503.
Credentials and internal exception details are never returned by the service.

The listeners are intended for the user's trusted network. This version has no
authentication protocol or public-internet deployment contract.
