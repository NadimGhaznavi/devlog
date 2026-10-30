/* BMFORGE_COMPONENT = {"id": "bmforge.timeline", "spec_version": "0.1.0"}
 * Browser assets: vis-timeline standalone UMD and CSS 8.5.6.
 */
(() => {
  "use strict";
  const source = document.getElementById("timing-data");
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const {labels, locale} = data;
  const SECOND = 1000, MINUTE = 60 * SECOND, DAY = 24 * 60 * MINUTE, REQUEST_TIMEOUT = 15000;
  const VIS_LOCALES = {en: "en"};
  const $ = id => document.getElementById("timing-" + id);
  const text = (key, fields = {}) => Object.entries(fields).reduce(
    (value, [name, replacement]) => value.replaceAll("{" + name + "}", replacement), labels[key]);
  const node = (tag, content) => {
    const element = document.createElement(tag);
    element.textContent = content;
    return element;
  };
  const duration = milliseconds => {
    const seconds = Math.floor(milliseconds / SECOND);
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
      .map(value => String(value).padStart(2, "0")).join(":");
  };
  const pad = value => String(value).padStart(2, "0");
  const localField = value => {
    const date = new Date(value);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
      + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  };
  function localInstant(value, original) {
    // Keep the original instant (including fractional seconds and DST fold) if untouched.
    if (value === localField(original)) return new Date(original);
    const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})([+-]\d{2}:\d{2})?$/.exec(value);
    if (!match) return new Date(NaN);
    const wall = Date.parse(value.slice(0, 19).replace(" ", "T") + "Z");
    if (!Number.isFinite(wall)) return new Date(NaN);
    const offsets = new Set([-DAY, 0, DAY].map(delta => new Date(wall + delta).getTimezoneOffset()));
    const candidates = [...offsets].map(offset => new Date(wall + offset * MINUTE))
      .filter(date => localField(date) === value.slice(0, 19).replace("T", " "));
    if (match[7]) {
      const explicit = new Date(value.replace(" ", "T"));
      return candidates.find(date => +date === +explicit) || new Date(NaN);
    }
    return candidates.length === 1 ? candidates[0] : new Date(NaN);
  }
  const endpoint = new URL(location.href);
  endpoint.pathname += "/timing";
  endpoint.searchParams.delete("saved");

  // Missing CSS is as unusable as a missing script. The recorded intervals stay available.
  if (!window.vis || document.getElementById("timing-styles").dataset.failed) {
    $("no-script").textContent = text("loadError");
    return;
  }

  let task = data.task, selected = task.intervals[0].interval_id;
  let busy = false, blocked = false, pendingUpdate = null;
  const items = new vis.DataSet();
  const rowFor = id => task.intervals.find(row => row.interval_id === id);
  const formTimes = () => {
    const row = rowFor(selected);
    return {start: localInstant($("start").value, row.started_at), end: localInstant($("end").value, row.ended_at)};
  };
  const dirty = () => {
    const row = rowFor(selected);
    const {start, end} = formTimes();
    return +start !== Date.parse(row.started_at) || +end !== Date.parse(row.ended_at);
  };
  const editable = enabled => ({updateTime: enabled, updateGroup: false, remove: false});
  function partName(index) {
    let name = "";
    for (let n = index + 1; n; n = Math.floor((n - 1) / 26)) {
      name = String.fromCharCode(65 + (n - 1) % 26) + name;
    }
    return text("part", {part: name});
  }
  function workItem(row, index) {
    return {id: row.interval_id, type: "range", start: new Date(row.started_at), end: new Date(row.ended_at),
      content: node("span", partName(index) + " · " + duration(Date.parse(row.ended_at) - Date.parse(row.started_at))),
      className: "timing-work", editable: editable(!busy && !blocked)};
  }
  function showError(message) {
    $("error").textContent = message;
    $("error").hidden = false;
  }
  function controls(status) {
    $("fields").disabled = busy || blocked;
    $("save").disabled = busy || blocked || !dirty();
    $("cancel").disabled = busy || (!dirty() && !pendingUpdate);
    $("track").setAttribute("aria-busy", String(busy));
    $("status").textContent = status || text(busy ? "saving" : blocked ? "reloadRequired" : dirty() ? "dirty" : "clean");
    const {start, end} = formTimes();
    $("total").textContent = Number.isFinite(+start) && Number.isFinite(+end) && end > start
      ? duration(end - start) : "—";
    items.update({id: selected, editable: editable(!busy && !blocked && !dirty())});
  }
  function fillForm(id) {
    selected = id;
    const row = rowFor(id);
    $("part").value = id;
    $("start").value = localField(row.started_at);
    $("end").value = localField(row.ended_at);
    syncPickers();
  }
  function syncPickers() {
    for (const field of ["start", "end"]) {
      $(field + "-picker").value = $(field).value.slice(0, 19).replace(" ", "T");
    }
  }
  function cancelUpdate() {
    if (pendingUpdate) {
      const callback = pendingUpdate;
      pendingUpdate = null;
      callback(null);
    }
  }
  function select(id) {
    cancelUpdate();
    const changed = selected !== id;
    fillForm(id);
    if (changed) renderStep();
    else timeline.setSelection(id);
    controls();
  }
  function bounds() {
    return {min: new Date(task.range_start), max: new Date(task.loaded_at)};
  }
  function taskWindow() {
    const row = rowFor(selected);
    const start = Date.parse(row.started_at), end = Date.parse(row.ended_at);
    const padding = Math.max(SECOND, (end - start) / 5);
    return {start: new Date(start - padding), end: new Date(end + padding)};
  }
  $("editor").hidden = false;
  const timeline = new vis.Timeline($("track"), items, {
    ...bounds(), ...taskWindow(), moveable: false, zoomable: false,
    showCurrentTime: false, selectable: true, multiselect: false,
    editable: {add: false, updateTime: true, updateGroup: false, remove: false, overrideItems: false},
    moment: value => vis.moment(value).locale(VIS_LOCALES[locale]), locale: VIS_LOCALES[locale],
    snap: null,
    onMove: (item, callback) => {
      if (busy || blocked || dirty() || !rowFor(item.id)) return callback(null);
      cancelUpdate();
      persist(item, callback);
    },
    onUpdate: (item, callback) => {
      if (busy || blocked || !rowFor(item.id)) return callback(null);
      select(item.id);
      pendingUpdate = callback;
      controls();
      $("start").focus();
    }
  });

  function renderStep() {
    const row = rowFor(selected);
    items.clear();
    items.add([
      workItem(row, task.intervals.indexOf(row)),
      {id: "commit", type: "point", start: new Date(task.completed_at), editable: false,
        className: "timing-commit", content: node("span", text("commitRecorded"))}
    ]);
    timeline.setOptions(bounds());
    const {start, end} = taskWindow();
    timeline.setWindow(start, end, {animation: false});
    timeline.setSelection(selected);
    const entry = node("li", "");
    entry.className = "interval";
    const times = node("p", "");
    times.append(node("time", localField(row.started_at)), " → ", node("time", localField(row.ended_at)));
    const elapsed = node("p", text("elapsed", {elapsed: duration(Date.parse(row.ended_at) - Date.parse(row.started_at))}));
    elapsed.className = "elapsed";
    entry.append(node("strong", partName(task.intervals.indexOf(row))), times, elapsed);
    document.querySelector("ol.timeline").replaceChildren(entry);
  }

  function renderSnapshot(detail) {
    if (!detail.editor) {
      // An authoritative snapshot can revoke completed-task editing.
      blocked = true;
      timeline.setOptions({editable: false});
      items.forEach(item => items.update({id: item.id, editable: false}));
      $("fields").disabled = true;
      $("reload").hidden = false;
      return false;
    }
    task = detail.editor;
    if (!rowFor(selected)) selected = task.intervals[0].interval_id;
    $("part").replaceChildren(...task.intervals.map((row, index) => {
      const option = node("option", partName(index));
      option.value = row.interval_id;
      return option;
    }));
    fillForm(selected);
    renderStep();
    const metadataTimes = document.querySelectorAll(".task-metadata time");
    metadataTimes[0].textContent = localField(task.started_at);
    metadataTimes[1].textContent = localField(task.completed_at);
    document.querySelector(".last-updated").textContent = text("lastUpdated", {timestamp: localField(task.loaded_at)});
    const total = task.intervals.reduce((sum, row) => sum + Date.parse(row.ended_at) - Date.parse(row.started_at), 0);
    document.querySelector(".report-heading .total strong").textContent = duration(total).split(":").slice(0, 2).join(":");
    return true;
  }

  async function refresh() {
    let detail;
    try {
      const response = await fetch(endpoint, {signal: AbortSignal.timeout(REQUEST_TIMEOUT)});
      if (!response.ok) throw new Error("Snapshot unavailable");
      detail = (await response.json()).task;
    } catch (error) {
      blocked = true;
      $("reload").hidden = false;
      return;
    }
    blocked = !renderSnapshot(detail);
    $("reload").hidden = blocked;
  }
  async function persist(item, callback) {
    busy = true;
    $("error").hidden = true;
    controls();
    let detail = null, message = null, recover = false;
    const payload = {revision: task.revision, loaded_at: task.loaded_at,
      intervals: task.intervals.map(row => ({...row,
        started_at: row.interval_id === item.id && +item.start !== Date.parse(row.started_at)
          ? item.start.toISOString() : row.started_at,
        ended_at: row.interval_id === item.id && +item.end !== Date.parse(row.ended_at)
          ? item.end.toISOString() : row.ended_at}))};
    try {
      const response = await fetch(endpoint, {
        method: "POST", headers: {"Content-Type": "application/json"},
        signal: AbortSignal.timeout(REQUEST_TIMEOUT),
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (response.ok && result.saved === true) {
        detail = result.task;
      } else if (response.status >= 400 && response.status < 500) {
        message = result.error;
        recover = response.status === 409;
      } else {
        throw new Error("Unconfirmed timing save");
      }
    } catch (error) {
      message = text("unconfirmed");
      recover = true;
    }
    // Settle the vis hook once, before replacing the DataSet with authoritative records.
    const accepted = detail?.editor?.intervals.find(row => row.interval_id === item.id);
    callback(accepted ? workItem(accepted, detail.editor.intervals.indexOf(accepted)) : null);
    if (detail) renderSnapshot(detail);
    if (recover) {
      blocked = true;
      await refresh();
    }
    busy = false;
    if (message) showError(message);
    controls(blocked ? text("reloadRequired") : detail ? text("saved") : recover ? text("refreshed") : undefined);
  }

  timeline.on("select", event => {
    if (busy || blocked) return;
    const id = event.items.find(id => rowFor(id));
    if (id) select(id);
  });
  $("part").addEventListener("change", () => select($("part").value));
  for (const field of ["start", "end"]) {
    $(field + "-picker").addEventListener("input", () => {
      const value = $(field + "-picker").value.replace("T", " ");
      $(field).value = value.length === 16 ? value + ":00" : value;
    });
  }
  $("form").addEventListener("input", () => { syncPickers(); controls(); });
  $("form").addEventListener("submit", event => {
    event.preventDefault();
    if (busy || blocked || !dirty()) return;
    const {start, end} = formTimes();
    if (!Number.isFinite(+start) || !Number.isFinite(+end)) {
      showError(text("invalidLocalTime"));
      return;
    }
    if (end <= start) {
      showError(text("badTiming"));
      return;
    }
    const callback = pendingUpdate || (() => {});
    pendingUpdate = null;
    persist({id: selected, start, end}, callback);
  });
  $("cancel").addEventListener("click", () => {
    cancelUpdate();
    fillForm(selected);
    $("error").hidden = true;
    controls();
  });
  window.addEventListener("beforeunload", event => {
    if (busy || (task && dirty())) { event.preventDefault(); event.returnValue = ""; }
  });
  $("no-script").hidden = true;
  $("records").open = false;
  renderSnapshot({editor: task});
  controls();
  timeline.redraw();
})();
