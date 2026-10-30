---
title: Timeline Editing Component
lang: en
locale: en-US
language_name: English
component_id: "bmforge.timeline"
spec_version: "0.1.0"
spec_status: "draft"
translation_key: bmforge-component-timeline
---

**Component ID:** `{{ page.component_id }}` · **Specification:** `{{ page.spec_version }}` ({{ page.spec_status }})

## Intent and prerequisites

Use **vis-timeline** as the BMForge standard for editing timeline objects: dated items, time ranges and optional groups. Let the library implement the time axis, selection, pan/zoom, dragging and range resizing. The application owns the records, supported operations, validation and persistence.

**Requires the [HTTP Display Server]({{ site.baseurl }}{% link pages/component-http.md %}) component and its project-local `bmforge-http` skill.** Serve the editor and its JSON endpoints through the application's existing HTTP listener. Do not add a timeline service, listener, database, Python web framework or separate health endpoint. A database component is selected only if the application needs one. Follow the [engineering contract]({{ site.baseurl }}{% link pages/engineering-contract.md %}) and [class responsibilities]({{ site.baseurl }}{% link pages/classification.md %}).

The manager checks this dependency before `init`, `attach` or `add` writes files. Select `bmforge-http,bmforge-timeline` together, or add timeline to a project whose BMForge lock already records HTTP. A missing dependency produces an actionable error; it is never silently installed or overwritten. Selecting HTTP alone does not select timeline. Existing applications retain their instructions and architecture under the normal attachment rules.

Select this component only when the application requires timeline editing. HTTP alone does not load timeline assets.

## Approved runtime modules

| Origin | Approved dependency | Version | Purpose |
| --- | --- | --- | --- |
| Browser JavaScript | **vis-timeline**, standalone UMD bundle | **8.5.6** | `vis.Timeline`, `vis.DataSet`, bundled time and interaction support |
| Browser CSS | vis-timeline stylesheet | **8.5.6** | Timeline layout, items, range handles and controls |
| Browser built-ins | DOM, Fetch, JSON, Date and Intl | Browser-provided | Safe labels, HTTP requests, serialization and display |

The standalone bundle includes its supporting dependencies; do not load separate peer packages or Moment scripts on top of it. This adds **no Python package** and does not change HTTP's approved Python module inventory. Do not add a Python timeline wrapper, React/Vue, a build system, or a competing timeline widget. Any library replacement or version upgrade requires user approval and a revised specification.

## Approved asset delivery

Load these matching, version-specific assets:

```html
<script src="https://unpkg.com/vis-timeline@8.5.6/standalone/umd/vis-timeline-graph2d.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/vis-timeline@8.5.6/styles/vis-timeline-graph2d.min.css">
```

An application may copy these exact files into its own static vendor directory when local delivery is required; retain upstream license notices and record the version. Do not fetch them during requests, load from another application's runtime or use `latest`. The verified SHA-256 values are:

| Asset | SHA-256 |
| --- | --- |
| Standalone JavaScript `.min.js` | `608430ebe8f4e6df544b0a91995a620a02b82c393827036638f332f35064e7b3` |
| Stylesheet `.min.css` | `67273f3f1bfc5fee585494e8b8818d7cad98c229737488bc56f140547badc1f5` |

The `graph2d` filename is upstream's distribution name; using it does not select a second charting capability. Show an actionable editor-load error if required assets fail rather than leaving a blank panel.

## Records and presentation

Map application entities to a `vis.DataSet` and pass it to `new vis.Timeline(container, items, options)` (with a groups DataSet only when needed). Preserve stable application IDs across fetches and edits; on creation, use the server-assigned ID from the accepted response. Keep the domain model independent of vis-timeline's presentation fields.

- Represent an instant with a `point` or `box`, and a duration with a `range` containing `start` and `end`. Validate finite dates and require `end > start` for duration records. Define supported types, required fields and size limits at the application boundary.
- Use DOM elements whose `textContent` contains untrusted labels. Apply the same rule to item templates, group labels and tooltips; never concatenate user input into HTML or CSS. Keep vis-timeline's XSS protection enabled. Pass server data using structured JSON or Jinja2's `tojson` with HTML autoescaping.
- Follow HTTP's dark, high-contrast GUI contract for the axis, grid, items, selected items, range handles, forms and focus. Keep status readable without relying on color alone. Provide labeled precise date/time controls and explicit save/cancel actions usable with a keyboard, including create/delete controls when those operations are supported. Pointer gestures must not be the only editing path.
- Use the application's existing localization catalogues for controls and errors. Map application locale tags to vis-timeline locale codes explicitly, and configure axis date labels as well as widget action strings. Locale does not select timezone. Do not add a new translation or date library implicitly.

## Editing and persistence

Set `selectable: true` and configure `editable.add`, `editable.updateTime`, `editable.updateGroup` and `editable.remove` individually for the requested operations. Keep `editable.overrideItems: false`. For partial per-item permissions, specify all three item flags (`updateTime`, `updateGroup`, `remove`); use `editable: false` for fully locked items. A read-only item is a display restriction, not authorization.

| Hook | Application responsibility |
| --- | --- |
| `onAdd(item, callback)` | Collect required fields, validate and save a new record; accept the server's ID and canonical values. |
| `onUpdate(item, callback)` | Open the application's edit form; save accepted field changes or cancel. |
| `onMove(item, callback)` | Validate and persist the completed drag, range resize or permitted group move. |
| `onRemove(item, callback)` | Apply the application's delete confirmation and persist deletion before acceptance. |
| `onMoving(item, callback)` | Optionally constrain a drag preview; settle the callback for that preview without a persistence request. |

For each enabled mutation, call its callback **exactly once**: `callback(item)` after a successful server acknowledgement with canonical values, or `callback(null)` for cancellation, validation rejection or request failure. Accept a delete only after its server acknowledgement. Use the same application save path for drag and form edits. Do not persist on every pointer move, generic DataSet change or viewport `rangechange` event.

Use the HTTP contract's bounded JSON requests, method/schema validation and appropriate access/origin policy. The server must whitelist editable fields, validate IDs and group membership, and enforce permissions and domain rules using authoritative state. Reject forged changes to locked records and protected boundaries even when a browser bypasses its UI. Where the application has concurrent writers, define a stale-edit policy that prevents silent overwrites.

The application defines any overlap, snapping, minimum-duration or boundary rules; the component does not invent them. In particular, an immutable commit marker or other boundary does **not** automatically prevent a neighboring range crossing it. Enforce such a rule explicitly on the server and mirror it in previews only when the application's requirements call for it. Do not copy DevLog-specific workflow into unrelated applications.

Keep pending and failed states visible. A rejected operation preserves the last accepted state. A timeout or lost response can occur after a successful server write: cancel the pending UI edit, report the uncertain outcome, then refetch authoritative state before allowing another edit to that object. Do not blindly retry writes. Reloading the page must reconstruct accepted records from application storage, not browser memory.

## Time semantics

For instant-based records, use ISO 8601 timestamps with `Z` or an explicit numeric offset on the wire and UTC in persistence. Convert valid timestamps to JavaScript `Date` values and serialize edited instants with `toISOString()`. Never treat an offset-free wall-clock string as an instant or slice a UTC string into a local `datetime-local` input.

Choose and label browser-local or UTC display deliberately. For UTC axes, use the bundled constructor with `moment: date => vis.moment(date).utc()`. Local display follows the browser's timezone, which may differ from the server's. Local-form conversion must round-trip across midnight and daylight-saving transitions; reject nonexistent local times and disambiguate repeated local times rather than silently choosing an instant. Define whether domain durations mean elapsed time or calendar time. An arbitrary named-zone axis requiring additional timezone data is a separately approved dependency decision.

Keep date-only calendar records as date-only values with an explicit calendar policy; do not apply UTC conversion to them implicitly. This component does not impose instant semantics on all-day events.

## Traceability and upstream references

Use `BMFORGE_COMPONENT = {"id": "bmforge.timeline", "spec_version": "0.1.0"}` in the owning Python page/API module when it clearly owns this component. For a JavaScript-only owner, record the same ID and specification version in a source comment; do not create a Python service just to hold a marker. Record the browser asset version separately. Follow [specification traceability]({{ site.baseurl }}{% link pages/specification-lifecycle.md %}); automated JavaScript scanning is not implemented.

The pinned contract above is sufficient for offline skill use. Consult these upstream primary sources for API detail; they do not authorize changing the pinned library version:

- [vis-timeline documentation](https://visjs.github.io/vis-timeline/docs/timeline/), especially Editing Items, Data Format, Localization and Time zone.
- [Version 8.5.6 source and release](https://github.com/visjs/vis-timeline/tree/v8.5.6).
- [Versioned editing callback example](https://github.com/visjs/vis-timeline/blob/v8.5.6/examples/timeline/editing/editingItemsCallbacks.html).

## Acceptance checks

1. `init` and `attach` reject timeline without HTTP before creating files. Both succeed with the pair selected. `add` accepts an already pinned HTTP skill, preserves its bytes and lock entry, and rejects a missing dependency without changing an existing project.
2. Load only the approved JS/CSS version through the existing HTTP server; verify a visible asset-load error and no extra listener, Python wrapper or frontend framework.
3. In the browser, select, pan/zoom and perform each enabled create/update/move/resize/delete operation. Check the canonical ID and values, then reload and confirm persistence. Verify the precise keyboard form uses the same rules.
4. Cancel a form/delete and simulate validation rejection, server failure, timeout and lost acknowledgement. Check one callback completion, visible unsaved/uncertain status, restored or refetched state and no unintended repeat write.
5. Send direct invalid API requests for unknown IDs, disallowed fields/groups, malformed times, reversed ranges and locked items. Apply overlap, barrier and stale-edit checks only where the application specifies those rules. Verify a subsequent valid request succeeds.
6. Round-trip UTC and explicit offsets, browser/server timezone differences, midnight, and daylight-saving skipped/repeated local times. Verify date-only records retain their calendar date where supported.
7. Render malicious item/group/tooltip labels as inert text; inspect dark desktop/mobile styling, readable range handles, visible focus, localized controls and keyboard editing.

---

[HTTP Display Server]({{ site.baseurl }}{% link pages/component-http.md %}) · [Component Blueprints]({{ site.baseurl }}{% link pages/component-blueprints.md %}) · [Back to BMForge]({{ site.baseurl }}{% link index.md %})
