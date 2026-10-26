/* DevLog's completed-task editor. All edits remain a draft until Save. */
(() => {
  "use strict";
  const source = document.getElementById("timing-data");
  if (!source) return;
  const {task, labels, locale} = JSON.parse(source.textContent);
  const SECOND = 1000, MINUTE = 60 * SECOND, MIN_WINDOW = MINUTE, MIN_INTERVAL = 1;
  const $ = id => document.getElementById(`timing-${id}`);
  const text = (key, fields = {}) => Object.entries(fields).reduce(
    (value, [name, replacement]) => value.replaceAll(`{${name}}`, replacement), labels[key]);
  const formatter = new Intl.DateTimeFormat(locale, {
    timeZone: task.timezone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", timeZoneName: "shortOffset"
  });
  function timestamp(value) {
    const p = Object.fromEntries(formatter.formatToParts(value).map(part => [part.type, part.value]));
    return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second} ${p.timeZoneName}`;
  }
  function duration(milliseconds) {
    const seconds = Math.floor(milliseconds / SECOND);
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
      .map(value => String(value).padStart(2, "0")).join(":");
  }
  function partName(index) {
    let result = "";
    for (let n = index + 1; n; n = Math.floor((n - 1) / 26)) {
      result = String.fromCharCode(65 + (n - 1) % 26) + result;
    }
    return text("part", {part: result});
  }
  const original = task.intervals.map(row => ({...row, start: Date.parse(row.started_at), end: Date.parse(row.ended_at)}));
  const intervals = original.map(row => ({...row}));
  const loaded = Date.parse(task.loaded_at);
  const completed = Date.parse(task.completed_at);
  const workLimit = Math.min(loaded, completed);
  const context = task.context.map(row => ({...row, start: Date.parse(row.started_at),
    end: Math.min(loaded, row.ended_at ? Date.parse(row.ended_at) : loaded)}));
  const first = Date.parse(task.range_start);
  let viewStart = first, viewEnd = loaded;
  let selected = null, dragging = null, saving = false, blocked = false, leaving = false;
  const dirty = () => intervals.some((row, i) => row.start !== original[i].start || row.end !== original[i].end);
  const position = value => (value - viewStart) / (viewEnd - viewStart) * 100;
  function limits(index, edge) {
    const row = intervals[index];
    let lower = edge === "start" ? (intervals[index - 1]?.end ?? first) : row.start + MIN_INTERVAL;
    let upper = edge === "end" ? (intervals[index + 1]?.start ?? workLimit) : row.end - MIN_INTERVAL;
    for (const fixed of context) {
      if (edge === "start" && fixed.end <= row.start) lower = Math.max(lower, fixed.end);
      if (edge === "end" && fixed.start >= row.end) upper = Math.min(upper, fixed.start);
    }
    return [lower, upper];
  }
  function boundaryName(index, edge) {
    const boundary = edge === "start" ? (index ? "resumed" : "start")
      : (index === intervals.length - 1 ? "end" : "paused");
    return text("boundary", {part: partName(index), boundary: text(boundary)});
  }
  function setWindow(start, end) {
    const span = Math.min(loaded - first, Math.max(MIN_WINDOW, end - start));
    viewStart = Math.max(first, Math.min(start, loaded - span));
    viewEnd = viewStart + span;
    render();
  }
  function zoom(factor) {
    const anchor = selected ? intervals[selected.index][selected.edge]
      : (intervals[0].start + intervals.at(-1).end) / 2;
    const span = (viewEnd - viewStart) * factor;
    setWindow(anchor - span / 2, anchor + span / 2);
  }
  function spanNode(start, end, kind, label, detail) {
    if (end <= viewStart || start >= viewEnd || end <= start) return;
    const node = document.createElement("div");
    node.className = `timing-span ${kind}`;
    node.style.left = `${position(Math.max(viewStart, start))}%`;
    node.style.width = `${position(Math.min(viewEnd, end)) - position(Math.max(viewStart, start))}%`;
    const name = document.createElement("strong"), subtitle = document.createElement("span");
    name.textContent = label;
    subtitle.textContent = detail;
    node.append(name, subtitle);
    node.title = `${label}\n${timestamp(start)} → ${timestamp(end)}\n${detail}`;
    $("spans").append(node);
  }
  const handles = [];
  intervals.forEach((row, index) => {
    for (const edge of ["start", "end"]) {
      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = "timing-handle";
      handle.dataset.index = index;
      handle.dataset.edge = edge;
      handle.setAttribute("role", "slider");
      handle.setAttribute("aria-orientation", "horizontal");
      handle.setAttribute("aria-label", boundaryName(index, edge));
      handle.setAttribute("aria-describedby", "timing-help");
      const select = () => { selected = {index, edge}; render(); };
      handle.addEventListener("focus", select);
      handle.addEventListener("pointerdown", event => {
        if (event.button !== 0 || saving || blocked) return;
        select();
        handle.focus({preventScroll: true});
        dragging = {index, edge, x: event.clientX, value: intervals[index][edge], pointer: event.pointerId};
        handle.setPointerCapture(event.pointerId);
        event.preventDefault();
      });
      handle.addEventListener("pointermove", event => {
        if (!dragging || dragging.pointer !== event.pointerId) return;
        if (Math.abs(event.clientX - dragging.x) < 2) {
          change(index, edge, dragging.value);
          return;
        }
        const delta = (event.clientX - dragging.x) / $("track").getBoundingClientRect().width * (viewEnd - viewStart);
        const step = event.shiftKey ? SECOND : MINUTE;
        change(index, edge, Math.round((dragging.value + delta) / step) * step);
      });
      handle.addEventListener("pointerup", () => { dragging = null; });
      handle.addEventListener("pointercancel", () => {
        if (dragging) intervals[dragging.index][dragging.edge] = dragging.value;
        dragging = null;
        render();
      });
      handle.addEventListener("lostpointercapture", () => { dragging = null; });
      handle.addEventListener("keydown", event => {
        const direction = {ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1}[event.key];
        if (!direction || saving || blocked) return;
        event.preventDefault();
        change(index, edge, intervals[index][edge] + direction * (event.shiftKey ? SECOND : MINUTE));
        const value = intervals[index][edge];
        if (value < viewStart || value > viewEnd) {
          const span = viewEnd - viewStart;
          setWindow(value - span / 2, value + span / 2);
        }
      });
      $("handles").append(handle);
      handles.push({handle, index, edge});
    }
  });
  function change(index, edge, value) {
    const [lower, upper] = limits(index, edge);
    intervals[index][edge] = Math.max(lower, Math.min(upper, value));
    $("error").hidden = true;
    render();
  }
  function render() {
    $("spans").replaceChildren();
    const spans = [...context.map(row => ({...row, fixed: true})), ...intervals.map((row, index) => ({...row, index}))]
      .sort((a, b) => a.start - b.start);
    let cursor = first;
    for (const row of spans) {
      if (row.start > cursor) {
        const pause = cursor >= intervals[0].start && row.start <= intervals.at(-1).end;
        spanNode(cursor, row.start, pause ? "pause" : "idle", text(pause ? "pause" : "idle"), duration(row.start - cursor));
      }
      spanNode(row.start, row.end, row.fixed ? "fixed" : "active",
        row.fixed ? text("task", {task_id: row.task_id}) : partName(row.index),
        row.fixed ? row.repository.split("/").at(-1) : text("elapsed", {elapsed: duration(row.end - row.start)}));
      cursor = Math.max(cursor, row.end);
    }
    if (cursor < loaded) spanNode(cursor, loaded, "idle", text("idle"), duration(loaded - cursor));
    $("axis").replaceChildren();
    const ticks = $("track").clientWidth < 600 ? 2 : 5;
    for (let index = 0; index < ticks; index++) {
      const tick = document.createElement("span");
      tick.className = "timing-tick";
      tick.style.left = `${index / (ticks - 1) * 100}%`;
      const value = timestamp(viewStart + (viewEnd - viewStart) * index / (ticks - 1));
      const date = document.createElement("span"), time = document.createElement("span");
      date.textContent = value.slice(0, 10);
      time.textContent = value.slice(11);
      tick.append(date, time);
      $("axis").append(tick);
    }
    for (const {handle, index, edge} of handles) {
      const value = intervals[index][edge], [lower, upper] = limits(index, edge);
      handle.hidden = value < viewStart || value > viewEnd;
      handle.disabled = saving || blocked;
      handle.style.left = `${position(value)}%`;
      handle.setAttribute("aria-valuemin", lower);
      handle.setAttribute("aria-valuemax", upper);
      handle.setAttribute("aria-valuenow", value);
      handle.setAttribute("aria-valuetext", timestamp(value));
      handle.title = `${boundaryName(index, edge)}: ${timestamp(value)}`;
      handle.classList.toggle("selected", selected?.index === index && selected?.edge === edge);
    }
    $("now").hidden = viewEnd < loaded;
    $("now").title = timestamp(loaded);
    $("completed").hidden = completed < viewStart || completed > viewEnd;
    $("completed").style.left = `${position(completed)}%`;
    $("completed").title = `${text("commitRecorded")}: ${timestamp(completed)}`;
    $("selection").textContent = selected
      ? `${boundaryName(selected.index, selected.edge)} · ${timestamp(intervals[selected.index][selected.edge])}` : "";
    const total = intervals.reduce((sum, row) => sum + row.end - row.start, 0);
    $("total").textContent = text("elapsed", {elapsed: duration(total)});
    document.querySelector(".report-heading .total strong").textContent = (total / 3600000).toFixed(2);
    $("save").disabled = !dirty() || saving || blocked;
    $("cancel").disabled = !dirty() || saving;
    $("status").textContent = text(saving ? "saving" : dirty() ? "dirty" : "clean");
    for (const id of ["focus", "zoom-in", "zoom-out", "show-all"]) $(id).disabled = saving;
    $("zoom-in").disabled ||= viewEnd - viewStart <= MIN_WINDOW;
    $("zoom-out").disabled ||= viewStart === first && viewEnd === loaded;
  }
  $("zoom-in").addEventListener("click", () => zoom(0.5));
  $("zoom-out").addEventListener("click", () => zoom(2));
  $("show-all").addEventListener("click", () => setWindow(first, loaded));
  $("focus").addEventListener("click", () => {
    const span = Math.max(MIN_WINDOW, intervals.at(-1).end - intervals[0].start);
    setWindow(intervals[0].start - span / 5, intervals.at(-1).end + span / 5);
  });
  $("cancel").addEventListener("click", () => {
    intervals.forEach((row, index) => { row.start = original[index].start; row.end = original[index].end; });
    $("error").hidden = true;
    selected = null;
    setWindow(first, loaded);
  });
  $("save").addEventListener("click", async () => {
    saving = true;
    $("error").hidden = true;
    render();
    const endpoint = new URL(location.href);
    endpoint.pathname = `/tasks/${task.task_id}/timing`;
    endpoint.searchParams.delete("saved");
    try {
      const response = await fetch(endpoint, {
        method: "POST", headers: {"Content-Type": "application/json"},
        signal: AbortSignal.timeout(15000),
        body: JSON.stringify({revision: task.revision, loaded_at: task.loaded_at,
          intervals: intervals.map((row, index) => ({interval_id: row.interval_id,
            started_at: row.start === original[index].start ? row.started_at : new Date(row.start).toISOString(),
            ended_at: row.end === original[index].end ? row.ended_at : new Date(row.end).toISOString()}))})
      });
      const result = await response.json();
      if (!response.ok) {
        $("error").textContent = result.error;
        $("error").hidden = false;
        $("reload").hidden = false;
        blocked = result.code === "error.timing_conflict";
      } else if (result.saved === true) {
        const target = new URL(location.href);
        target.searchParams.set("saved", "timing");
        leaving = true;
        location.assign(target);
        return;
      } else {
        throw new Error("Unconfirmed timing save");
      }
    } catch (error) {
      $("error").textContent = text("unconfirmed");
      $("error").hidden = false;
      $("reload").hidden = false;
      blocked = true;
    }
    saving = false;
    render();
  });
  window.addEventListener("beforeunload", event => {
    if (dirty() && !leaving) { event.preventDefault(); event.returnValue = ""; }
  });
  new ResizeObserver(() => render()).observe($("track"));
  $("loaded").textContent = text("loaded", {timestamp: timestamp(loaded)});
  $("records").open = false;
  $("no-script").hidden = true;
  $("editor").hidden = false;
  render();
})();
