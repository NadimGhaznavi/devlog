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
  Plotly.newPlot("daily-chart", [{
    type: "bar", x: data.days.map(day => day.date), y: data.days.map(day => day.hours),
    marker: {color: color("--accent")},
    hovertemplate: "%{x}<br>%{y:.2f} " + data.hoursLabel + "<extra></extra>"
  }], {
    paper_bgcolor: color("--surface"), plot_bgcolor: color("--surface"),
    font: {family: "system-ui, sans-serif", color: color("--text")},
    hoverlabel: {bgcolor: color("--surface"), bordercolor: color("--accent"), font: {color: color("--text")}},
    margin: {t: 20, r: 20, b: 55, l: 55},
    xaxis: {type: "category", title: {text: data.dateLabel}, fixedrange: true},
    yaxis: {title: {text: data.hoursLabel}, rangemode: "tozero", gridcolor: color("--grid"), zerolinecolor: color("--border"), fixedrange: true}
  }, {responsive: true, displayModeBar: false}).catch(() => { error.hidden = false; });
});
