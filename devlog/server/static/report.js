"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  const error = document.getElementById("chart-error");
  if (typeof Plotly === "undefined") {
    error.hidden = false;
    return;
  }
  const theme = getComputedStyle(document.documentElement);
  const color = name => theme.getPropertyValue(name).trim();
  const barWidth = 0.8;
  const borderWidth = 4;
  const taskLineWidth = 2;
  const highlightMix = 0.35;
  const brighter = hex => "#" + hex.slice(1).match(/.{2}/g).map(channel => {
    const value = parseInt(channel, 16);
    return Math.round(value + (255 - value) * highlightMix).toString(16).padStart(2, "0");
  }).join("");
  const projectColors = [
    "#E63946", "#00BCD4", "#FFD60A", "#7C3AED",
    "#22C55E", "#F77F00", "#2563EB", "#EC4899",
    "#7AC800", "#009DFF", "#BE185D", "#FFA600",
    "#00A896", "#A855F7", "#F35425", "#4F46E5",
    "#BAD80A", "#F43F5E", "#00B894", "#D946EF"
  ];
  const escapeLabel = label => label.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const traces = data.repositories.flatMap((repository, index) => {
    if (!data.days.some(day => (day.projects[repository] || 0) > 0)) return [];
    return [{
      type: "bar", name: escapeLabel(repository.replace(/^github\.com\//, "").replace(/^nadimghaznavi\//, "")),
      x: data.days.map(day => day.date), y: data.days.map(day => day.projects[repository] || 0),
      customdata: data.days.map(() => repository),
      width: barWidth,
      marker: {
        color: projectColors[index % projectColors.length],
        line: {
          color: brighter(projectColors[index % projectColors.length]),
          width: data.days.map(day => day.projects[repository] > 0 ? borderWidth : 0)
        }
      },
      hovertemplate: "%{x}<br>%{y:.2f} " + data.hoursLabel + "<extra>%{fullData.name}</extra>"
    }];
  });
  const taskSeparators = visibleTraces => data.days.flatMap((day, dayIndex) => {
    let base = 0;
    return visibleTraces.flatMap(trace => {
      if (trace.visible === "legendonly" || trace.visible === false) return [];
      const repository = trace.customdata[dayIndex];
      let boundary = base;
      base += day.projects[repository] || 0;
      return (day.task_hours[repository] || []).slice(0, -1).map(hours => {
        boundary += hours;
        return {
          type: "line", xref: "x", yref: "y",
          x0: dayIndex - barWidth / 2, x1: dayIndex + barWidth / 2,
          y0: boundary, y1: boundary,
          line: {color: trace.marker.line.color, width: taskLineWidth}
        };
      });
    });
  });
  Plotly.newPlot("daily-chart", traces, {
    barmode: "stack", showlegend: true,
    shapes: taskSeparators(traces),
    legend: {orientation: "h", x: 0.5, xanchor: "center", y: -0.3, yanchor: "top", traceorder: "normal"},
    paper_bgcolor: color("--surface"), plot_bgcolor: color("--surface"),
    font: {family: "system-ui, sans-serif", color: color("--text")},
    hoverlabel: {bgcolor: color("--surface"), bordercolor: color("--accent"), font: {color: color("--text")}},
    margin: {t: 20, r: 20, b: 100, l: 55},
    xaxis: {type: "category", categoryorder: "array", categoryarray: data.days.map(day => day.date), title: {text: data.dateLabel}, fixedrange: true},
    yaxis: {title: {text: data.hoursLabel}, rangemode: "tozero", gridcolor: color("--grid"), zerolinecolor: color("--border"), fixedrange: true}
  }, {responsive: true, displayModeBar: false}).then(chart => {
    chart.on("plotly_restyle", () => Plotly.relayout(chart, {shapes: taskSeparators(chart.data)}));
    chart.on("plotly_click", event => {
      const point = event.points[0];
      const target = new URL(data.taskUrl, window.location.origin);
      target.searchParams.set("day", point.x);
      target.searchParams.set("repository", point.customdata);
      window.location.assign(target);
    });
  }).catch(() => { error.hidden = false; });
});
