/* Sectional Trends
 *
 * Moved out of insights/sectional-trends.html, where it sat as 558 lines inside a <script> tag.
 * Here it gets syntax checking, the browser can cache it, and "where is the
 * code for this page?" has the obvious answer: the file named after the page.
 *
 * It reads what it needs from the DOM rather than from Jinja, which is what
 * made moving it safe. Keep it that way -- pass values in with data- attributes
 * rather than templating them into the JavaScript.
 */

document.addEventListener('DOMContentLoaded', () => {
  const genderChipGroup = document.getElementById('gender-chip-group');
  const eventChipGroup = document.getElementById('event-chip-group');
  const resultsHeader = document.getElementById('results-header');
  const resultsTitle = document.getElementById('results-title');
  const resultsLoading = document.getElementById('results-loading');
  const resultsError = document.getElementById('results-error');
  const resultsErrorMessage = document.getElementById('results-error-message');
  const resultsEmpty = document.getElementById('results-empty');
  const resultsContent = document.getElementById('results-content');
  const resultsBody = document.getElementById('results-body');
  const difficultyTooltip = document.getElementById('difficulty-tooltip');
  const difficultyTooltipList = document.getElementById('difficulty-tooltip-list');
  const downloadPdfBtn = document.getElementById('download-pdf-btn');

  // Download PDF button handler
  if (downloadPdfBtn) {
    downloadPdfBtn.addEventListener('click', () => {
      alert("Sorry, this feature hasn't been implemented. It's coming soon!");
    });
  }

  const chipBaseClasses = 'chip-btn btn btn-sm border border-base-300 text-sm px-4 py-2 transition-colors shadow-none hover:shadow-none focus:shadow-none';
  const eventChipClasses = 'chip-btn btn btn-xs border border-base-300 text-sm w-full px-3 py-2 transition-colors justify-center text-center shadow-none hover:shadow-none focus:shadow-none';

  const EVENT_GROUPS = [
    {
      label: 'Sprints & Distance',
      events: ['100 Meters', '200 Meters', '400 Meters', '800 Meters', '1600 Meters', '3200 Meters'],
    },
    {
      label: 'Hurdles',
      events: ['100 Hurdles', '110 Hurdles', '300 Hurdles'],
    },
    {
      label: 'Relays',
      events: ['4 x 100 Relay', '4 x 400 Relay', '4 x 800 Relay'],
    },
    {
      label: 'Field Events',
      events: ['High Jump', 'Long Jump', 'Pole Vault', 'Shot Put', 'Discus'],
    },
  ];

  // Events that are gender-specific
  const GENDER_LOCKED_EVENTS = {
    '100 Hurdles': 'Girls',
    '110 Hurdles': 'Boys',
  };

  const orderEvents = (events = []) => {
    const priorityEntries = EVENT_GROUPS.flatMap((group, groupIndex) =>
      group.events.map((name, eventIndex) => [name, groupIndex * 100 + eventIndex])
    );
    const priority = new Map(priorityEntries);
    return [...events].sort((a = '', b = '') => {
      const aRank = priority.has(a) ? priority.get(a) : Number.MAX_SAFE_INTEGER;
      const bRank = priority.has(b) ? priority.get(b) : Number.MAX_SAFE_INTEGER;
      if (aRank !== bRank) {
        return aRank - bRank;
      }
      return a.localeCompare(b);
    });
  };

  const insertGroupDividers = (container) => {
    const divider = document.createElement('div');
    divider.className = 'col-span-full border-t border border-1 border-base-200/80';
    container.appendChild(divider);
  };

  const setChipSelected = (chip, isSelected) => {
    chip.dataset.selected = isSelected ? 'true' : 'false';
    chip.classList.toggle('btn-primary', isSelected);
    chip.classList.toggle('btn-outline', !isSelected);
    chip.classList.toggle('btn-ghost', !isSelected);
    chip.classList.toggle('text-white', isSelected);
    chip.classList.toggle('text-base-content', !isSelected);
  };

  let state = {
    options: null,
    selectedGender: 'Boys',
    selectedEvent: '100 Meters',
    trendsData: null,
    chart: null,
    fetchTimeout: null,
  };

  const queueFetch = () => {
    if (state.fetchTimeout) {
      clearTimeout(state.fetchTimeout);
    }
    state.fetchTimeout = setTimeout(() => {
      if (state.selectedGender && state.selectedEvent) {
        fetchTrendsData();
      }
    }, 150);
  };

  // Fetch filter options
  const fetchOptions = async () => {
    try {
      const response = await fetch('/api/sectional-trends/options');
      if (!response.ok) throw new Error('Failed to load options');
      state.options = await response.json();
      renderFilters();
    } catch (error) {
      console.error('Error fetching options:', error);
    }
  };

  const renderFilters = () => {
    if (!state.options) return;

    // Render gender chips
    genderChipGroup.innerHTML = '';
    for (const gender of state.options.genders || []) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = chipBaseClasses;
      chip.textContent = gender;
      chip.dataset.value = gender;
      chip.addEventListener('click', () => selectGender(gender));
      genderChipGroup.appendChild(chip);
    }

    // Apply default gender selection
    updateChipSelection(genderChipGroup, state.selectedGender);

    // Render event chips
    renderEventChips(state.options.events || []);

    // Trigger initial fetch with defaults
    queueFetch();
  };

  const syncEventSelection = () => {
    Array.from(eventChipGroup.querySelectorAll('.chip-btn')).forEach(chip => {
      const isSelected = chip.dataset.value === state.selectedEvent;
      setChipSelected(chip, isSelected);
    });
  };

  const renderEventChips = (events) => {
    eventChipGroup.innerHTML = '';
    const orderedEvents = orderEvents(events);
    const groupsLookup = new Map();
    EVENT_GROUPS.forEach(group => {
      group.events.forEach(eventName => {
        groupsLookup.set(eventName, group.label);
      });
    });

    let previousGroupLabel = null;
    orderedEvents.forEach(eventName => {
      const currentLabel = groupsLookup.get(eventName) || null;
      if (previousGroupLabel !== null && currentLabel && currentLabel !== previousGroupLabel) {
        insertGroupDividers(eventChipGroup);
      }

      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = eventChipClasses;
      chip.dataset.value = eventName;
      chip.textContent = eventName;
      chip.addEventListener('click', () => {
        state.selectedEvent = eventName;
        syncEventSelection();

        // If this event is gender-locked, force that gender
        const lockedGender = GENDER_LOCKED_EVENTS[eventName];
        if (lockedGender && state.selectedGender !== lockedGender) {
          state.selectedGender = lockedGender;
          updateChipSelection(genderChipGroup, lockedGender);
        }

        // Update gender chip disabled states
        updateGenderChipStates();
        queueFetch();
      });
      eventChipGroup.appendChild(chip);
      setChipSelected(chip, state.selectedEvent === eventName);

      previousGroupLabel = currentLabel || previousGroupLabel;
    });
  };

  const selectGender = (gender) => {
    // Check if current event is locked to a different gender
    const lockedGender = GENDER_LOCKED_EVENTS[state.selectedEvent];
    if (lockedGender && lockedGender !== gender) {
      return; // Don't allow switching if event is gender-locked
    }

    state.selectedGender = gender;
    updateChipSelection(genderChipGroup, gender);
    queueFetch();
  };

  const updateGenderChipStates = () => {
    const lockedGender = GENDER_LOCKED_EVENTS[state.selectedEvent];

    for (const chip of genderChipGroup.querySelectorAll('.chip-btn')) {
      const chipGender = chip.dataset.value;
      const isDisabled = !!(lockedGender && lockedGender !== chipGender);

      chip.disabled = isDisabled;
      if (isDisabled) {
        chip.classList.add('opacity-40', 'cursor-not-allowed');
      } else {
        chip.classList.remove('opacity-40', 'cursor-not-allowed');
      }
    }
  };

  const updateChipSelection = (container, selectedValue) => {
    for (const chip of container.querySelectorAll('.chip-btn')) {
      const isSelected = chip.dataset.value === selectedValue;
      chip.classList.toggle('btn-primary', isSelected);
      chip.classList.toggle('btn-ghost', !isSelected);
    }
  };

  const fetchTrendsData = async () => {
    showLoading(true);
    hideError();

    const params = new URLSearchParams({
      gender: state.selectedGender,
      event: state.selectedEvent,
    });

    try {
      const response = await fetch(`/api/sectional-trends?${params}`);
      if (!response.ok) throw new Error('Failed to load trends data');

      const data = await response.json();
      if (data.error) throw new Error(data.error);

      state.trendsData = data;
      renderResults();
    } catch (error) {
      console.error('Error fetching trends:', error);
      showError(error.message || 'Failed to load trends data.');
    } finally {
      showLoading(false);
    }
  };

  const showLoading = (show) => {
    resultsLoading.classList.toggle('hidden', !show);
    if (show) {
      resultsEmpty.classList.add('hidden');
      resultsContent.classList.add('hidden');
    }
  };

  const showError = (message) => {
    resultsErrorMessage.textContent = message;
    resultsError.classList.remove('hidden');
  };

  const hideError = () => {
    resultsError.classList.add('hidden');
  };

  const renderResults = () => {
    const data = state.trendsData;
    if (!data || !data.rows || data.rows.length === 0) {
      resultsEmpty.classList.remove('hidden');
      resultsContent.classList.add('hidden');
      resultsHeader.classList.add('hidden');
      return;
    }

    resultsEmpty.classList.add('hidden');
    resultsContent.classList.remove('hidden');
    resultsHeader.classList.remove('hidden');
    resultsTitle.textContent = `${data.gender} ${data.event}`;

    // For field events, higher is better; for track events, lower is better
    const isFieldEvent = data.event_type === 'Field';

    // Helper to format a raw value difference
    const formatDiff = (diff) => {
      const absDiff = Math.abs(diff);
      if (isFieldEvent) {
        // Format as feet-inches
        const feet = Math.floor(absDiff / 12);
        const inches = (absDiff % 12).toFixed(1);
        if (feet > 0) {
          return `${feet}'${inches}"`;
        }
        return `${inches}"`;
      } else {
        // Format as time
        const minutes = Math.floor(absDiff / 60);
        const seconds = (absDiff % 60).toFixed(2);
        if (minutes > 0) {
          return `${minutes}:${seconds.padStart(5, '0')}`;
        }
        return `${seconds}s`;
      }
    };

    // Helper to create trend badge
    const createTrendBadge = (currentVal, previousVal) => {
      if (previousVal == null || currentVal == null) return null;

      const diff = currentVal - previousVal;
      // Use 0.01 threshold for track events (times), 0.1 inches for field events
      const threshold = isFieldEvent ? 0.1 : 0.01;
      if (Math.abs(diff) < threshold) return null; // No meaningful change

      // Up arrow = increase in value (higher time or higher distance)
      // Down arrow = decrease in value (lower time or lower distance)
      const isIncrease = diff > 0;

      // Green = improvement: lower time (track) or higher distance (field)
      // Red = regression: higher time (track) or lower distance (field)
      const isImprovement = isFieldEvent ? diff > 0 : diff < 0;
      const formattedDiff = formatDiff(diff);

      const badge = document.createElement('span');
      badge.className = `ml-1 inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full border ${isImprovement ? 'text-green-600 border-green-600' : 'text-red-500 border-red-500'}`;

      const arrow = isIncrease 
        ? '<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clip-rule="evenodd"/></svg>'
        : '<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>';

      badge.innerHTML = `${arrow}<span>${formattedDiff}</span>`;

      return badge;
    };

    // Render table
    resultsBody.innerHTML = '';
    let previousRow = null;

    for (const row of data.rows) {
      const tr = document.createElement('tr');
      tr.className = 'transition-colors duration-150 hover:bg-primary/5';

      const seasonTd = document.createElement('td');
      seasonTd.textContent = row.season;
      tr.appendChild(seasonTd);

      const medianTd = document.createElement('td');
      medianTd.textContent = row.median_mark || '—';
      if (previousRow) {
        const medianBadge = createTrendBadge(row.median_raw, previousRow.median_raw);
        if (medianBadge) medianTd.appendChild(medianBadge);
      }
      tr.appendChild(medianTd);

      const cutoffTd = document.createElement('td');
      cutoffTd.textContent = row.cutoff_performance || '—';
      if (previousRow) {
        const cutoffBadge = createTrendBadge(row.cutoff_raw, previousRow.cutoff_raw);
        if (cutoffBadge) cutoffTd.appendChild(cutoffBadge);
      }
      tr.appendChild(cutoffTd);

      const pctAboveMedianTd = document.createElement('td');
      if (row.median_raw && row.cutoff_raw && row.median_raw !== 0) {
        const pctAbove = Math.abs(((row.cutoff_raw - row.median_raw) / row.median_raw) * 100);
        pctAboveMedianTd.textContent = `${pctAbove.toFixed(1)}%`;
      } else {
        pctAboveMedianTd.textContent = '—';
      }
      tr.appendChild(pctAboveMedianTd);

      resultsBody.appendChild(tr);
      previousRow = row;
    }

    // Render chart
    renderChart(data);
  };

  const renderChart = (data) => {
    const ctx = document.getElementById('trends-chart').getContext('2d');
    const legendContainer = document.getElementById('chart-legend-container');

    // Destroy existing chart
    if (state.chart) {
      state.chart.destroy();
    }

    const labels = data.rows.map(r => r.season);
    const medianData = data.rows.map(r => r.median_raw);
    const cutoffData = data.rows.map(r => r.cutoff_raw);

    // Create custom HTML legend
    const createLegend = (chart) => {
      legendContainer.innerHTML = '';
      chart.data.datasets.forEach((dataset, index) => {
        const meta = chart.getDatasetMeta(index);
        // Check both meta.hidden and dataset.hidden for initial state
        const isHidden = meta.hidden === true || dataset.hidden === true;

        const item = document.createElement('label');
        item.className = 'flex items-center gap-2 cursor-pointer select-none px-3 py-1.5 rounded-lg hover:bg-base-100 transition-colors';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = !isHidden;
        checkbox.className = 'checkbox checkbox-sm';
        checkbox.style.borderColor = dataset.borderColor;
        checkbox.style.setProperty('--chkbg', dataset.borderColor);
        checkbox.addEventListener('change', () => {
          meta.hidden = !checkbox.checked;
          chart.update();
        });

        const colorBox = document.createElement('span');
        colorBox.className = 'w-4 h-1 rounded-full';
        colorBox.style.backgroundColor = dataset.borderColor;

        const labelText = document.createElement('span');
        labelText.className = 'text-sm font-medium text-base-content';
        labelText.textContent = dataset.label;

        item.appendChild(checkbox);
        item.appendChild(colorBox);
        item.appendChild(labelText);
        legendContainer.appendChild(item);
      });
    };

    state.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Median Mark',
            data: medianData,
            borderColor: 'rgb(59, 130, 246)',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: false,
            tension: 0.3,
            pointRadius: 6,
            pointHoverRadius: 8,
            hidden: true,
          },
          {
            label: 'State Cutoff',
            data: cutoffData,
            borderColor: 'rgb(239, 68, 68)',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            fill: false,
            tension: 0.3,
            pointRadius: 6,
            pointHoverRadius: 8,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 600
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                const row = data.rows[context.dataIndex];
                if (context.dataset.label === 'Median Mark') {
                  return `Median: ${row.median_mark}`;
                } else {
                  return `Cutoff: ${row.cutoff_performance}`;
                }
              }
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'Season'
            }
          },
          y: {
            title: {
              display: true,
              text: data.event_type === 'Field' ? 'Distance' : 'Time (seconds)'
            },
            ticks: {
              callback: function(value) {
                if (data.event_type === 'Field') {
                  // Format as feet-inches (approximate)
                  const feet = Math.floor(value / 12);
                  const inches = Math.round(value % 12);
                  return `${feet}'${inches}"`;
                } else {
                  // Format as time
                  const minutes = Math.floor(value / 60);
                  const seconds = (value % 60).toFixed(2);
                  return minutes > 0 ? `${minutes}:${seconds.padStart(5, '0')}` : `${seconds}s`;
                }
              }
            }
          }
        }
      }
    });

    // Create the custom HTML legend after chart is created
    createLegend(state.chart);
  };

  const showDifficultyTooltip = (e, season) => {
    const rankings = state.trendsData?.difficulty_rankings?.[season];
    if (!rankings || rankings.length === 0) return;

    difficultyTooltipList.innerHTML = '';
    rankings.forEach((item, index) => {
      const li = document.createElement('li');
      li.className = 'flex justify-between gap-4';
      if (item.event === state.selectedEvent) {
        li.className += ' font-bold text-primary';
      }
      li.innerHTML = `
        <span>${index + 1}. ${item.event}</span>
        <span class="text-gray-500">${item.difficulty.toFixed(1)}%</span>
      `;
      difficultyTooltipList.appendChild(li);
    });

    // Position tooltip
    const rect = e.target.getBoundingClientRect();
    difficultyTooltip.style.left = `${rect.left + window.scrollX}px`;
    difficultyTooltip.style.top = `${rect.bottom + window.scrollY + 8}px`;
    difficultyTooltip.classList.remove('hidden');
  };

  const hideDifficultyTooltip = () => {
    difficultyTooltip.classList.add('hidden');
  };

  // Close tooltip when clicking elsewhere
  document.addEventListener('click', (e) => {
    if (!difficultyTooltip.contains(e.target) && !e.target.closest('[data-season]')) {
      hideDifficultyTooltip();
    }
  });

  // Initialize
  fetchOptions();
});
