document.addEventListener('DOMContentLoaded', () => {
  const dataElement = document.getElementById('event-chart-data');
  if (!dataElement) {
    return;
  }

  const chartData = JSON.parse(dataElement.textContent || '{}');
  const isFieldEvent = chartData.eventType === 'Field';
  const distributionAxisTitle = (data) => isFieldEvent
    ? 'Distance (inches)'
    : data.distributionUsesMinutes
      ? 'Time (minutes)'
      : 'Time (seconds)';
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
  const distributionFrame = document.getElementById('distribution-chart-frame');
  const distributionEmpty = document.getElementById('distribution-empty');
  const percentileTimes = document.getElementById('event-percentile-times');
  const distributionControls = document.getElementById('distribution-controls');
  const distributionStatus = document.getElementById('distribution-status');
  const trendCanvas = document.getElementById('event-trend-chart');

  const leaderboardControls = document.getElementById('leaderboard-controls');
  if (leaderboardControls) {
    const meetType = document.getElementById('leaderboard-meet-type');
    const season = document.getElementById('leaderboard-season');
    const results = document.getElementById('leaderboard-results');
    const count = document.getElementById('leaderboard-count');
    const status = document.getElementById('leaderboard-status');
    let pendingRequest = null;
    const loadLeaderboard = async () => {
      pendingRequest?.abort();
      const controller = new AbortController();
      pendingRequest = controller;
      leaderboardControls.setAttribute('aria-busy', 'true');
      status.hidden = true;
      const url = new URL(leaderboardControls.dataset.url, window.location.origin);
      url.searchParams.set('gender', leaderboardControls.dataset.gender);
      url.searchParams.set('meet_type', meetType.value);
      url.searchParams.set('year', season.value);
      try {
        const response = await fetch(url, {signal: controller.signal});
        if (!response.ok) throw new Error(`Leaderboard request failed (${response.status}).`);
        const data = await response.json();
        if (!controller.signal.aborted) {
          results.innerHTML = data.html;
          count.textContent = data.countLabel;
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.warn('Leaderboard could not load:', error);
          status.textContent = 'Unable to update the leaderboard. Please try again.';
          status.hidden = false;
        }
      } finally {
        if (pendingRequest === controller) {
          pendingRequest = null;
          leaderboardControls.removeAttribute('aria-busy');
        }
      }
    };
    meetType.addEventListener('change', loadLeaderboard);
    season.addEventListener('change', loadLeaderboard);
  }

  if (typeof Chart === 'undefined') {
    [distributionCanvas, trendCanvas].forEach((canvas) => {
      if (canvas) {
        canvas.parentElement.textContent = 'Charts could not load. Please refresh to try again.';
      }
    });
    return;
  }

  if (distributionCanvas) {
    const distributionYAxis = (counts) => {
      const peak = Math.max(0, ...counts.map(Number));
      if (peak === 0) return {max: 1, step: 1};
      const magnitude = 10 ** Math.floor(Math.log10(peak / 6));
      const scaledStep = peak / 6 / magnitude;
      const niceStep = scaledStep <= 1.5 ? 1 : scaledStep <= 3.5 ? 2 : scaledStep <= 7.5 ? 5 : 10;
      const step = Math.max(1, niceStep * magnitude);
      return {max: (Math.floor(peak / step) + 1) * step, step};
    };
    let currentData = chartData;
    let distribution = currentData.distribution;
    let distributionLabels = currentData.lowerIsBetter
      ? [...distribution.labels].reverse()
      : distribution.labels;
    let distributionCounts = currentData.lowerIsBetter
      ? [...distribution.counts].reverse()
      : distribution.counts;
    let yAxis = distributionYAxis(distributionCounts);
    const percentileIndex = (value) => {
      if (distribution.bin_start === null || !distribution.bin_width) return null;
      const offset = distribution.has_underflow ? 1 : 0;
      const index = (Number(value) - distribution.bin_start) / distribution.bin_width - 0.5 + offset;
      return currentData.lowerIsBetter ? distribution.labels.length - 1 - index : index;
    };
    const percentileMarkers = {
      id: 'percentileMarkers',
      afterDatasetsDraw(chart) {
        const {ctx, chartArea, scales} = chart;
        if (!chartArea) return;
        const markers = [];
        ctx.save();
        (currentData.percentiles || []).forEach((percentile) => {
          const index = percentileIndex(percentile.value);
          if (index === null) return;
          const x = scales.x.getPixelForValue(index);
          if (x < chartArea.left || x > chartArea.right) return;
          const isMedian = percentile.label === '50th';
          const color = isMedian ? '#8c0327' : 'rgba(140, 3, 39, 0.75)';
          ctx.strokeStyle = color;
          ctx.lineWidth = isMedian ? 2 : 1.5;
          ctx.setLineDash(isMedian ? [] : [5, 4]);
          ctx.beginPath();
          ctx.moveTo(x, chartArea.top);
          ctx.lineTo(x, chartArea.bottom);
          ctx.stroke();
          ctx.setLineDash([]);
          markers.push({x, label: `${percentile.label.slice(0, -2)}%`, color});
        });

        ctx.font = '600 9px Arial, sans-serif';
        const labelHeight = 12;
        markers.forEach((marker) => {
          const labelWidth = ctx.measureText(marker.label).width + 8;
          const left = Math.max(
            chartArea.left,
            Math.min(chartArea.right - labelWidth, marker.x - labelWidth / 2),
          );
          let lane = 0;
          while (markers.some((other) => {
            if (other === marker || other.lane !== lane || other.left === undefined) return false;
            return left < other.left + other.width + 3 && left + labelWidth + 3 > other.left;
          })) lane += 1;
          marker.left = left;
          marker.width = labelWidth;
          marker.lane = lane;

          const top = chartArea.top + 2 + lane * 12;
          ctx.fillStyle = 'rgba(255,255,255,.94)';
          ctx.fillRect(left, top, labelWidth, labelHeight);
          ctx.strokeStyle = marker.color;
          ctx.lineWidth = 1;
          ctx.strokeRect(left, top, labelWidth, labelHeight);
          ctx.fillStyle = '#8c0327';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(marker.label, left + labelWidth / 2, top + labelHeight / 2);
        });
        ctx.restore();
      },
    };
    let distributionChart = null;
    const makeDistributionChart = () => new Chart(distributionCanvas, {
      type: 'line',
      data: {
        labels: distributionLabels,
        datasets: [{
          label: 'Athletes',
          data: distributionCounts,
          borderColor: '#8c0327',
          borderWidth: 2.5,
          backgroundColor: 'rgba(140, 3, 39, 0.14)',
          fill: true,
          tension: 0.45,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: '#8c0327',
        }],
      },
      plugins: [percentileMarkers],
      options: {
        maintainAspectRatio: false,
        layout: { padding: { top: 0 } },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => `${items[0].label}${isFieldEvent ? ' in' : currentData.distributionUsesMinutes ? ' min' : ' sec'}`,
              label: (item) => `${item.formattedValue} athlete${Number(item.raw) === 1 ? '' : 's'}`,
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: distributionAxisTitle(currentData) },
            grid: { display: false },
            ticks: { maxRotation: 0, minRotation: 0, autoSkip: true, maxTicksLimit: 10 },
          },
          y: {
            beginAtZero: true,
            max: yAxis.max,
            ticks: { precision: 0, stepSize: yAxis.step },
          },
        },
      },
    });
    if (distributionLabels.length) distributionChart = makeDistributionChart();

    const updateDistribution = (data) => {
      currentData = data;
      distribution = data.distribution;
      distributionLabels = data.lowerIsBetter
        ? [...distribution.labels].reverse()
        : distribution.labels;
      distributionCounts = data.lowerIsBetter
        ? [...distribution.counts].reverse()
        : distribution.counts;
      yAxis = distributionYAxis(distributionCounts);

      const percentileCards = data.percentiles.map((percentile) => {
        const card = document.createElement('div');
        const label = document.createElement('p');
        label.className = 'percentile-label font-impact text-base-content/60';
        label.textContent = `${percentile.label} percentile`;
        const value = document.createElement('p');
        value.className = 'percentile-value font-impact italic text-primary';
        value.textContent = percentile.display;
        if (!isFieldEvent) {
          const unit = document.createElement('span');
          unit.className = 'ml-1 text-sm not-italic text-base-content/55';
          unit.textContent = Number(percentile.value) >= 60 ? 'min' : 'sec';
          value.appendChild(unit);
        }
        card.append(label, value);
        return card;
      });
      percentileTimes.replaceChildren(...percentileCards);
      percentileTimes.hidden = percentileCards.length === 0;

      const hasData = distributionLabels.length > 0;
      distributionFrame.hidden = !hasData;
      distributionEmpty.hidden = hasData;
      if (!hasData) {
        distributionChart?.destroy();
        distributionChart = null;
        return;
      }
      if (!distributionChart) {
        distributionChart = makeDistributionChart();
        return;
      }
      distributionChart.data.labels = distributionLabels;
      distributionChart.data.datasets[0].data = distributionCounts;
      distributionChart.options.scales.x.title.text = distributionAxisTitle(data);
      distributionChart.options.scales.y.max = yAxis.max;
      distributionChart.options.scales.y.ticks.stepSize = yAxis.step;
      distributionChart.update();
    };

    if (distributionControls) {
      const meetType = document.getElementById('distribution-meet-type');
      const season = document.getElementById('distribution-season');
      let pendingRequest = null;
      const loadDistribution = async () => {
        pendingRequest?.abort();
        const controller = new AbortController();
        pendingRequest = controller;
        distributionControls.setAttribute('aria-busy', 'true');
        distributionStatus.hidden = true;
        const url = new URL(distributionControls.dataset.url, window.location.origin);
        url.searchParams.set('gender', distributionControls.dataset.gender);
        url.searchParams.set('meet_type', meetType.value);
        url.searchParams.set('year', season.value);
        try {
          const response = await fetch(url, {signal: controller.signal});
          if (!response.ok) throw new Error(`Distribution request failed (${response.status}).`);
          const data = await response.json();
          if (!controller.signal.aborted) updateDistribution(data);
        } catch (error) {
          if (error.name !== 'AbortError') {
            console.warn('Distribution could not load:', error);
            distributionStatus.textContent = 'Unable to update the distribution. Please try again.';
            distributionStatus.hidden = false;
          }
        } finally {
          if (pendingRequest === controller) {
            pendingRequest = null;
            distributionControls.removeAttribute('aria-busy');
          }
        }
      };
      meetType.addEventListener('change', loadDistribution);
      season.addEventListener('change', loadDistribution);
    }
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
