---
name: bmforge-timeline
description: Implement editable timeline objects in a BMForge HTTP UI using vis-timeline at the approved version. Use for selecting, creating, moving, resizing, updating or deleting dated items and ranges, including application-defined locked markers and time boundaries. Requires bmforge-http.
---

# Timeline editing

Read `references/specification.md` and `references/engineering-contract.md` before implementation. Require the project-local `bmforge-http` skill and follow its transport, JSON-write, health and dark GUI contracts. Install HTTP explicitly alongside this skill if it is absent; never create a second server.

- Use **vis-timeline 8.5.6**, its standalone UMD JavaScript bundle and matching CSS at the exact URLs in the specification. The bundle supplies `vis.Timeline`, `vis.DataSet` and its supporting dependencies. Do not add another timeline library, Python wrapper, frontend framework or build tool.
- Map application-owned records to stable item IDs, `start`, optional `end`, safe display content and optional groups. Keep business entities, SQL and persistence outside browser rendering. Load only the capabilities the application requests.
- Enable editing actions individually. Use `onAdd`, `onUpdate`, `onMove` and `onRemove` for allowed operations. Settle each callback exactly once: accept with `callback(item)` only after a successful server acknowledgement; cancel with `callback(null)` on rejection, cancellation or a failed request. Do not save on every `onMoving` event.
- For a range, let vis-timeline handle dragging and resizing. Provide labeled date/time fields and explicit save/cancel actions for precise and keyboard editing through the same validation and persistence path.
- Validate IDs, editable fields, item types, times and domain constraints at the server boundary. Preserve locked objects and any application-defined barriers on the server as well as in the UI; a read-only marker does not itself prevent other items crossing it.
- Serialize instants with UTC or an explicit offset, select browser-local or UTC display deliberately, and follow the specification's daylight-saving and date-only rules. Do not infer timezone from locale or use ambiguous wall-clock strings as instants.
- Render labels with DOM `textContent`, keep the library's XSS protection enabled, and apply HTTP's dark, high-contrast styling. Use the application's localization keys for controls and errors; map its existing locale tags to the library's locale codes explicitly.
- Keep failed changes visibly unsaved, preserve the last accepted state and refetch authoritative data when a failed request leaves the outcome uncertain. Do not report success from a drag event or a DataSet update alone.
- Record `bmforge.timeline` specification `0.1.0` in the owning implementation as described in the specification. Run its acceptance checks in the consuming application; installing this skill does not implement an editor.
