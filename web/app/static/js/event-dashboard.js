document.addEventListener('DOMContentLoaded', () => {
  const dataElement = document.getElementById('event-chart-data');
  if (!dataElement) {
    return;
  }

  const chartData = JSON.parse(dataElement.textContent || '{}');
  const isFieldEvent = chartData.eventType === 'Field';
  const trendAxisTitle = isFieldEvent
    ? 'Median distance (inches)'
    : 'Median time (seconds)';
  const markLabel = (value) => {
    if (isFieldEvent) {
      const inches = Number(value);
      const feet = Math.floor(inches / 12);
      const remainder = inches - feet * 12;
      return `${feet}'${remainder.toFixed(2).replace(/\.?0+$/, '')}"`;
    }

    const seconds = Number(value);
    if (seconds >= 60) {
      const minutes = Math.floor(seconds / 60);
      return `${minutes}:${(seconds - minutes * 60).toFixed(2).padStart(5, '0')}`;
    }
    return `${seconds.toFixed(2)}s`;
  };
  const distributionCanvas = document.getElementById('event-distribution-chart');
  const trendCanvas = document.getElementById('event-trend-chart');

  if (typeof Chart === 'undefined') {
    [distributionCanvas, trendCanvas].forEach((canvas) => {
      if (canvas) {
        canvas.parentElement.textContent = 'Charts could not load. Please refresh to try again.';
      }
    });
    return;
  }

  if (distributionCanvas && chartData.distribution.labels.length) {
    const distributionCounts = chartData.distribution.counts;
    const totalResults = distributionCounts.reduce((total, count) => total + count, 0);
    const percentileColors = ['#2563eb', '#d97706', '#059669'];
    const percentileMarkers = [];
    let cumulativeCount = 0;
    const sortedPercentiles = [...(chartData.percentiles || [])].sort(
      (a, b) => Number(a.label.replace(/\D/g, '')) - Number(b.label.replace(/\D/g, '')),
    );

    const getCurvePoint = (chart, x) => {
      const points = chart.getDatasetMeta(0).data;
      if (!points.length) {
        return null;
      }

      if (x <= points[0].x) {
        return { x, y: points[0].y };
      }

      for (let index = 1; index < points.length; index += 1) {
        const previous = points[index - 1];
        const current = points[index];
        if (x <= current.x) {
          const progress = (x - previous.x) / (current.x - previous.x);
          return { x, y: previous.y + (current.y - previous.y) * progress };
        }
      }

      return { x, y: points[points.length - 1].y };
    };

    sortedPercentiles.forEach((percentile, percentileIndex) => {
      const targetRank = totalResults * Number(percentile.label.replace(/\D/g, '')) / 100;
      cumulativeCount = 0;
      for (let index = 0; index < distributionCounts.length; index += 1) {
        const count = distributionCounts[index];
        if (count > 0 && cumulativeCount + count >= targetRank) {
          const fraction = (targetRank - cumulativeCount) / count;
          percentileMarkers.push({
            label: percentile.label,
            color: percentileColors[percentileIndex % percentileColors.length],
            position: index + fraction - 0.5,
          });
          break;
        }
        cumulativeCount += count;
      }
    });

    const percentileLines = {
      id: 'percentileLines',
      afterDatasetsDraw(chart) {
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.font = '12px sans-serif';

        percentileMarkers.forEach(({ label, color, position }) => {
          const x = chartArea.left
            + ((position + 0.5) / chart.data.labels.length) * chartArea.width;
          const curvePoint = getCurvePoint(chart, x);
          if (!curvePoint) {
            return;
          }

          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(x, curvePoint.y);
          ctx.lineTo(x, chartArea.bottom);
          ctx.stroke();
          ctx.fillStyle = color;
          ctx.fillText(label, x, chartArea.bottom + 5);
        });

        ctx.restore();
      },
    };

    const distributionCrosshair = {
      id: 'distributionCrosshair',
      beforeEvent(chart, args) {
        const { event } = args;
        if (event.type === 'mouseout' || event.type === 'touchend') {
          if (pointerX !== null) {
            pointerX = null;
            args.changed = true;
          }
          return;
        }

        if (event.type !== 'mousemove' && event.type !== 'touchmove') {
          return;
        }

        const { chartArea } = chart;
        const nextPointerX = event.x >= chartArea.left && event.x <= chartArea.right
          && event.y >= chartArea.top && event.y <= chartArea.bottom
          ? event.x
          : null;
        if (nextPointerX !== pointerX) {
          pointerX = nextPointerX;
          args.changed = true;
        }
      },
      afterDraw(chart) {
        if (pointerX === null) {
          return;
        }

        const { ctx, chartArea } = chart;
        const curvePoint = getCurvePoint(chart, pointerX);
        if (!curvePoint) {
          return;
        }

        ctx.save();
        ctx.strokeStyle = 'rgba(220, 38, 38, 0.75)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(pointerX, chartArea.top);
        ctx.lineTo(pointerX, chartArea.bottom);
        ctx.stroke();
        ctx.fillStyle = '#dc2626';
        ctx.beginPath();
        ctx.arc(curvePoint.x, curvePoint.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      },
    };
    let pointerX = null;

    new Chart(distributionCanvas, {
      type: 'line',
      data: {
        labels: chartData.distribution.labels,
        datasets: [{
          label: 'Athlete-season bests',
          data: chartData.distribution.counts,
          backgroundColor: 'rgba(220, 38, 38, 0.18)',
          borderColor: '#dc2626',
          borderWidth: 2,
          tension: 0.4,
          fill: 'origin',
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: '#dc2626',
          pointHoverBorderColor: '#ffffff',
          pointHoverBorderWidth: 1.5,
        }],
      },
      plugins: [percentileLines, distributionCrosshair],
      options: {
        maintainAspectRatio: false,
        layout: { padding: { bottom: 20 } },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              title: (items) => items[0].label,
              label: (item) => `${item.formattedValue} athlete-season bests`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { display: false },
            border: { display: false },
          },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(148, 163, 184, 0.16)' },
            ticks: { display: false, precision: 0 },
            border: { display: false },
          },
        },
      },
    });
  }

  if (trendCanvas && chartData.trend.years.length) {
    const trendChart = new Chart(trendCanvas, {
      type: 'line',
      data: {
        labels: chartData.trend.years,
        datasets: chartData.trend.datasets.map((dataset) => ({
          ...dataset,
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2,
        })),
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (item) => `${item.dataset.label}: ${markLabel(item.raw)}`,
            },
          },
        },
        scales: {
          x: { title: { display: true, text: 'Season' } },
          y: {
            reverse: false,
            title: { display: true, text: trendAxisTitle },
            ticks: { callback: (value) => markLabel(value) },
          },
        },
      },
    });

    document.querySelectorAll('.event-trend-toggle').forEach((toggle) => {
      toggle.addEventListener('change', () => {
        const datasetIndex = trendChart.data.datasets.findIndex(
          (dataset) => dataset.label === toggle.dataset.trend,
        );
        if (datasetIndex === -1) {
          return;
        }

        trendChart.setDatasetVisibility(datasetIndex, toggle.checked);
        trendChart.update();
      });
    });
  }
});
