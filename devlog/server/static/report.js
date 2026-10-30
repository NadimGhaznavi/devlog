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
  const duration = hours => {
    const minutes = Math.round(hours * 60);
    return String(Math.floor(minutes / 60)).padStart(2, "0") + ":" + String(minutes % 60).padStart(2, "0");
  };
  const dailyUrl = day => {
    const target = new URL(data.dailyUrl, window.location.origin);
    target.searchParams.set("day", day);
    return target.href;
  };
  const barWidth = 0.8;
  const borderWidth = 4;
  const taskLineWidth = 2;
  const shadeFactor = 0.5;
  const darker = hex => "#" + hex.slice(1).match(/.{2}/g).map(channel => {
    const value = parseInt(channel, 16);
    return Math.round(value * shadeFactor).toString(16).padStart(2, "0");
  }).join("");
  const escapeLabel = label => label.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const traces = data.repositories.flatMap(repository => {
    if (!data.days.some(day => (day.projects[repository] || 0) > 0)) return [];
    return [{
      type: "bar", name: escapeLabel(repository.replace(/^github\.com\//, "").replace(/^nadimghaznavi\//, "")),
      x: data.days.map(day => day.date), y: data.days.map(day => day.projects[repository] || 0),
      customdata: data.days.map(() => repository),
      width: barWidth,
      marker: {
        color: data.projectColors[repository],
        line: {
          color: darker(data.projectColors[repository]),
          width: data.days.map(day => day.projects[repository] > 0 ? borderWidth : 0)
        }
      },
      hovertemplate: data.days.map(day => "%{fullData.name}: " + duration(day.projects[repository] || 0) + "<extra></extra>")
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
          layer: "above",
          x0: dayIndex - barWidth / 2, x1: dayIndex + barWidth / 2,
          y0: boundary, y1: boundary,
          line: {color: trace.marker.line.color, width: taskLineWidth}
        };
      });
    });
  });
  const chartMargin = {t: 40, r: 20, b: 100, l: 55};
  const dayLabels = visibleTraces => {
    const totalStyle = getComputedStyle(document.querySelector(".total strong"));
    const dayWidth = (document.getElementById("daily-chart").clientWidth - chartMargin.l - chartMargin.r) / data.days.length;
    // Reserve enough width for a daily total such as 24:00 on narrow charts.
    const fontSize = Math.min(parseFloat(totalStyle.fontSize) * 2 / 3, Math.max(10, dayWidth / 3.5));
    return data.days.map((day, dayIndex) => {
      const hours = visibleTraces.reduce((sum, trace) =>
        sum + (trace.visible === "legendonly" || trace.visible === false ? 0 : trace.y[dayIndex]), 0);
      return {
        x: day.date, y: hours, xref: "x", yref: "y",
        text: `<a href="${escapeLabel(dailyUrl(day.date))}" target="_self">${duration(hours)}</a>`,
        showarrow: false, captureevents: true, yanchor: "bottom", yshift: 8,
        font: {
          family: totalStyle.fontFamily, weight: Number(totalStyle.fontWeight),
          size: fontSize, color: totalStyle.color
        }
      };
    });
  };
  Plotly.newPlot("daily-chart", traces, {
    barmode: "stack", showlegend: true,
    shapes: taskSeparators(traces),
    annotations: dayLabels(traces),
    legend: {orientation: "h", x: 0.5, xanchor: "center", y: -0.4, yanchor: "top", traceorder: "normal"},
    paper_bgcolor: color("--background"), plot_bgcolor: color("--background"),
    font: {family: "system-ui, sans-serif", color: color("--text")},
    hoverlabel: {bgcolor: color("--surface"), bordercolor: color("--accent"), font: {color: color("--text")}},
    margin: chartMargin,
    xaxis: {type: "category", categoryorder: "array", categoryarray: data.days.map(day => day.date), title: {text: data.dateLabel}, fixedrange: true},
    yaxis: {title: {text: data.hoursLabel}, rangemode: "tozero", gridcolor: color("--grid"), zerolinecolor: color("--border"), fixedrange: true}
  }, {responsive: true, displayModeBar: false}).then(chart => {
    const labelLinks = () => chart.querySelectorAll(".annotation").forEach((annotation, index) => {
      // Plotly wraps the annotation background in its own link above the text.
      const anchor = annotation.querySelector(".bg").parentElement;
      anchor.setAttribute("href", dailyUrl(data.days[index].date));
      anchor.setAttribute("target", "_self");
      anchor.setAttribute("role", "link");
      anchor.setAttribute("tabindex", "0");
      anchor.setAttribute("aria-label", data.dailyLabel.replace("{date}", data.days[index].date));
      annotation.querySelectorAll(".annotation-text a").forEach(textLink => {
        textLink.setAttribute("aria-hidden", "true");
        textLink.setAttribute("tabindex", "-1");
      });
    });
    chart.on("plotly_afterplot", labelLinks);
    labelLinks();
    chart.on("plotly_restyle", () => Plotly.relayout(chart, {
      shapes: taskSeparators(chart.data), annotations: dayLabels(chart.data)
    }));
    const panel = chart.closest("details");
    const resizeLabels = () => {
      if (panel.open) Plotly.relayout(chart, {annotations: dayLabels(chart.data)});
    };
    window.addEventListener("resize", resizeLabels);
    panel.addEventListener("toggle", () => {
      if (panel.open) {
        Plotly.Plots.resize(chart);
        resizeLabels();
      }
    });
    chart.on("plotly_click", event => {
      const point = event.points[0];
      const target = new URL(data.taskUrl, window.location.origin);
      target.searchParams.set("day", point.x);
      target.searchParams.set("repository", point.customdata);
      window.location.assign(target);
    });
  }).catch(() => { error.hidden = false; });
});
