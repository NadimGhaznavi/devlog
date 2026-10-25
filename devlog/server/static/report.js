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
  const projectColors = [
    "rgb(230, 57, 70)", "rgb(243, 84, 37)", "rgb(247, 127, 0)", "rgb(255, 166, 0)",
    "rgb(255, 214, 10)", "rgb(186, 216, 10)", "rgb(122, 200, 0)", "rgb(34, 197, 94)",
    "rgb(0, 184, 148)", "rgb(0, 168, 150)", "rgb(0, 188, 212)", "rgb(0, 157, 255)",
    "rgb(37, 99, 235)", "rgb(79, 70, 229)", "rgb(124, 58, 237)", "rgb(168, 85, 247)",
    "rgb(217, 70, 239)", "rgb(236, 72, 153)", "rgb(244, 63, 94)", "rgb(190, 24, 93)"
  ];
  const escapeLabel = label => label.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const traces = data.repositories.flatMap((repository, index) => {
    if (!data.days.some(day => (day.projects[repository] || 0) > 0)) return [];
    return [{
      type: "bar", name: escapeLabel(repository.replace(/^github\.com\//, "").replace(/^nadimghaznavi\//, "")),
      x: data.days.map(day => day.date), y: data.days.map(day => day.projects[repository] || 0),
      marker: {color: projectColors[index % projectColors.length]},
      hovertemplate: "%{x}<br>%{y:.2f} " + data.hoursLabel + "<extra>%{fullData.name}</extra>"
    }];
  });
  Plotly.newPlot("daily-chart", traces, {
    barmode: "stack", showlegend: true,
    legend: {orientation: "h", x: 0.5, xanchor: "center", y: -0.3, yanchor: "top", traceorder: "normal"},
    paper_bgcolor: color("--surface"), plot_bgcolor: color("--surface"),
    font: {family: "system-ui, sans-serif", color: color("--text")},
    hoverlabel: {bgcolor: color("--surface"), bordercolor: color("--accent"), font: {color: color("--text")}},
    margin: {t: 20, r: 20, b: 100, l: 55},
    xaxis: {type: "category", categoryorder: "array", categoryarray: data.days.map(day => day.date), title: {text: data.dateLabel}, fixedrange: true},
    yaxis: {title: {text: data.hoursLabel}, rangemode: "tozero", gridcolor: color("--grid"), zerolinecolor: color("--border"), fixedrange: true}
  }, {responsive: true, displayModeBar: false}).catch(() => { error.hidden = false; });
});
