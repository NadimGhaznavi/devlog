"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  const error = document.getElementById("chart-error");
  if (typeof Plotly === "undefined") {
    error.hidden = false;
    return;
  }
  Plotly.newPlot("daily-chart", [{
    type: "bar", x: data.days.map(day => day.date), y: data.days.map(day => day.hours),
    marker: {color: "#236b52"},
    hovertemplate: "%{x}<br>%{y:.2f} " + data.hoursLabel + "<extra></extra>"
  }], {
    paper_bgcolor: "#fffefa", plot_bgcolor: "#fffefa",
    font: {family: "system-ui, sans-serif", color: "#213c32"},
    margin: {t: 20, r: 20, b: 55, l: 55},
    xaxis: {type: "category", title: {text: data.dateLabel}, fixedrange: true},
    yaxis: {title: {text: data.hoursLabel}, rangemode: "tozero", gridcolor: "#e6e9e1", fixedrange: true}
  }, {responsive: true, displayModeBar: false}).catch(() => { error.hidden = false; });
});
