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
  }, {responsive: true, displayModeBar: false}).then(chart => {
    chart.on("plotly_click", event => {
      const point = event.points[0];
      const target = new URL(data.taskUrl, window.location.origin);
      target.searchParams.set("day", point.x);
      target.searchParams.set("repository", point.customdata);
      window.location.assign(target);
    });
  }).catch(() => { error.hidden = false; });
});
