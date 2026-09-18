/* Regional Qualifiers.
 *
 * Moved out of insights/regional-qualifiers.html, where it sat as 706 lines inside a <script> tag.
 *
 * This page is configured by its route -- the API it calls and the wording it
 * shows differ between the regional and state versions. Those settings used to
 * be templated straight into `const` declarations, which is what kept the code
 * stuck in the template. They now arrive as JSON in a
 * <script type="application/json" id="page-config"> block, read below.
 *
 * If you add a setting: add it to the JSON block in the template and read it
 * here. Do not template values into JavaScript.
 */

document.addEventListener('DOMContentLoaded', () => {
  const pageConfig = JSON.parse(
      document.getElementById('page-config').textContent);
  const apiStatusUrl = pageConfig.apiStatusUrl;
  const apiDetailUrl = pageConfig.apiDetailUrl;
  const completedField = pageConfig.completedField;
  const totalField = pageConfig.totalField;
  const missingField = pageConfig.missingField;
  const coverageUnit = pageConfig.coverageUnit;
  const loadErrorMessage = pageConfig.loadErrorMessage;
  const statusErrorMessage = pageConfig.statusErrorMessage;
  const detailUnavailableText = pageConfig.detailUnavailableText;
  const groupLabel = pageConfig.groupLabel;
  // The jump-to-event chip strip is shared with the other qualifiers
  // page; it lives in js/event-jump.js, loaded before this file.
  const { eventSlug, shortEventLabel, initEventJump, resetEventJump }
    = window.EventJump;

  const params = new URLSearchParams(window.location.search);
  const parsedYear = Number.parseInt(params.get('year') || '2026', 10);
  const selectedYear = Number.isInteger(parsedYear) && parsedYear >= 2000 ? parsedYear : 2026;

  const state = {
    year: selectedYear,
    gender: 'Boys',
    statusPayload: null,
    selectedRegional: null,
    detailRequestId: 0,
  };

  const yearSelect = document.getElementById('year-select');
  const genderGroup = document.getElementById('gender-group');
  const statusGrid = document.getElementById('status-grid');
  const detailSection = document.getElementById('detail-section');
  const detailTitle = document.getElementById('detail-title');
  const detailMessage = document.getElementById('detail-message');
  const detailLoading = document.getElementById('detail-loading');
  const detailContent = document.getElementById('detail-content');

  const genders = ['Boys', 'Girls'];

  yearSelect.value = String(state.year);

  yearSelect.addEventListener('change', () => {
  const nextYear = Number.parseInt(yearSelect.value, 10);
    if (!Number.isInteger(nextYear) || nextYear < 2000) {
      yearSelect.value = String(state.year);
      return;
    }

    state.year = nextYear;
    state.selectedRegional = null;
    clearDetailTable();

  const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set('year', String(state.year));
    window.history.replaceState({}, '', nextUrl.toString());

    fetchStatus();
  });

  function setLoading(isLoading) {
    detailLoading.classList.toggle('hidden', !isLoading);
  }

  function setMessage(text, tone = 'default') {
    detailMessage.classList.remove('hidden', 'alert-error', 'alert-info', 'alert-warning', 'alert-success');
    if (tone === 'error') {
      detailMessage.classList.add('alert-error');
    } else if (tone === 'warning') {
      detailMessage.classList.add('alert-warning');
    } else if (tone === 'success') {
      detailMessage.classList.add('alert-success');
    } else {
      detailMessage.classList.add('alert-info');
    }
    detailMessage.innerHTML = `<span>${text}</span>`;
  }

  function clearDetailTable() {
    detailSection.classList.add('hidden');
    detailContent.classList.add('hidden');
    detailContent.innerHTML = '';
    detailMessage.classList.add('hidden');
    detailTitle.textContent = '';
    resetEventJump();
  }

  function getRegionalHost(regionalNum) {
  const regionals = state.statusPayload?.regionals || [];
  const match = regionals.find((regional) => regional.regional_num === regionalNum);
    return match?.regional_host || 'Host TBD';
  }

  function renderGenderButtons() {
    genderGroup.innerHTML = '';
    genders.forEach((gender) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `btn btn-sm rounded-full ${gender === state.gender ? 'btn-primary' : 'btn-outline'}`;
      btn.textContent = gender;
      btn.addEventListener('click', () => {
        if (state.gender === gender) return;
        state.gender = gender;
        state.selectedRegional = null;
        renderGenderButtons();
        clearDetailTable();
        fetchStatus();
      });
      genderGroup.appendChild(btn);
    });
  }

  async function fetchStatus() {
    try {
      const response = await fetch(`${apiStatusUrl}?gender=${encodeURIComponent(state.gender)}&year=${state.year}`);
      if (!response.ok) {
        throw new Error(statusErrorMessage);
      }
      const payload = await response.json();
      state.statusPayload = payload;
      renderRegionalCards();
    } catch (error) {
      statusGrid.innerHTML = '';
      setMessage(error.message || statusErrorMessage, 'error');
    }
  }

  function renderRegionalCards() {
    statusGrid.innerHTML = '';
  const regionals = state.statusPayload?.regionals || [];

    regionals.forEach((regional) => {
      const ready = regional.status === 'ready';
      const card = document.createElement('article');
      card.className = 'rounded-lg border p-3 text-center transition-all';
      if (ready) {
        card.classList.add('border-primary', 'bg-white', 'cursor-pointer', 'hover:border-2', 'hover:shadow-lg', 'hover:border-primary');
      } else {
        card.classList.add('border-warning/40', 'bg-warning/5', 'cursor-pointer', 'hover:border-warning', 'hover:shadow-md', 'opacity-80');
      }

      if (ready) {
        card.innerHTML = `
          <h3 class="font-semibold text-sm">${groupLabel} #${regional.regional_num}</h3>
          <p class="text-xs text-base-content/60 mt-1">${regional.regional_host || 'Host TBD'}</p>
        `;
        card.addEventListener('click', () => fetchRegionalDetail(regional.regional_num));
      } else {
        const missing = (regional.missing_sectionals || []);
        const missingText = missing.length
          ? `Awaiting Sectional${missing.length > 1 ? 's' : ''}: ${missing.join(', ')}`
          : 'Awaiting sectional data';
        card.innerHTML = `
          <h3 class="font-semibold text-sm">${groupLabel} #${regional.regional_num}</h3>
          <p class="text-xs font-semibold text-warning mt-1">Pending</p>
          <p class="text-xs text-base-content/50 mt-0.5">${missingText}</p>
        `;
        card.addEventListener('click', () => {
          detailSection.classList.remove('hidden');
          detailTitle.textContent = `${state.year} ${state.gender} ${groupLabel} #${regional.regional_num}`;
          detailContent.classList.add('hidden');
          detailContent.innerHTML = '';
          setMessage(`Pending — ${missingText}.`, 'warning');
        });
      }

      statusGrid.appendChild(card);
    });
  }

  function renderDetail(payload) {
  const context = payload.context || {};
  const events = payload.events || [];
  const regionalNum = Number(context.regional_num);
  const safeRegionalNum = Number.isFinite(regionalNum) ? regionalNum : context.regional_num;
  const regionalHost = Number.isFinite(regionalNum) ? getRegionalHost(regionalNum) : 'Host TBD';
    detailSection.classList.remove('hidden');
    detailTitle.textContent = `${state.year} ${context.gender} ${groupLabel} #${safeRegionalNum} - ${regionalHost}`;

    if (context.status !== 'ready') {
      clearDetailTable();
      const missing = (context[missingField] || []).join(', ');
      const missingText = missing ? ` Missing ${coverageUnit}: ${missing}.` : '';
      detailSection.classList.remove('hidden');
      setMessage(`This ${groupLabel.toLowerCase()} is not ready yet. Coverage is ${context[completedField]}/${context[totalField]} ${coverageUnit} loaded.${missingText}`, 'warning');
      return;
    }

    if (!events.length) {
      clearDetailTable();
      detailSection.classList.remove('hidden');
      setMessage('No qualifier data found for this regional.', 'warning');
      return;
    }

    initEventJump(events);

    detailMessage.classList.add('hidden');
    detailContent.classList.remove('hidden');
    detailContent.innerHTML = '';

    events.forEach((eventBlock, index) => {
      const section = document.createElement('section');
      section.className = 'space-y-2';
      const chipKey = `${eventSlug(eventBlock.event)}-${index}`;
      section.id = `event-${chipKey}`;
      section.dataset.chipKey = chipKey;

      const headerWrap = document.createElement('div');
      headerWrap.className = 'flex flex-wrap items-center gap-2 relative';

      const header = document.createElement('h3');
      header.className = 'text-base font-semibold text-base-content';
      header.textContent = eventBlock.event;
      headerWrap.appendChild(header);

      if (eventBlock.standard_mark) {
        const standard = document.createElement('span');
        standard.className = 'badge badge-sm text-xs font-semibold border-emerald-600/40 bg-emerald-50 text-emerald-700';
        standard.textContent = `Standard: ${eventBlock.standard_mark}`;
        headerWrap.appendChild(standard);
      }

      // Up arrow button at top right of section header
      const upArrowBtn = document.createElement('button');
      upArrowBtn.type = 'button';
      upArrowBtn.setAttribute('aria-label', 'Back to top');
      upArrowBtn.setAttribute('title', 'Back to top');
      upArrowBtn.className = 'up-arrow-btn absolute right-0 top-0 bg-white border border-base-300 rounded-full p-0.5 shadow-sm hover:border-primary hover:bg-primary/10 focus:bg-primary/20 focus:border-primary transition-colors outline-none cursor-pointer';
      upArrowBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fill-rule="evenodd" d="M10.707 3.293a1 1 0 00-1.414 0l-6 6a1 1 0 101.414 1.414L9 6.414V17a1 1 0 102 0V6.414l4.293 4.293a1 1 0 001.414-1.414l-6-6z" clip-rule="evenodd" />
        </svg>
      `;
      upArrowBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      headerWrap.appendChild(upArrowBtn);

      section.appendChild(headerWrap);

      const qualifiers = Array.isArray(eventBlock.qualifiers) ? eventBlock.qualifiers : [];
      if (!qualifiers.length) {
        const empty = document.createElement('p');
        empty.className = 'text-sm text-base-content/60';
        empty.textContent = 'No qualifiers available.';
        section.appendChild(empty);
        detailContent.appendChild(section);
        return;
      }

      const wrap = document.createElement('div');
      wrap.className = 'overflow-x-auto border border-base-200 rounded-lg relative';
      const isRelayEvent = String(eventBlock.event || '').startsWith('4 x ');
      const nameHeader = isRelayEvent ? 'School' : 'Name';
      const gradeHeader = isRelayEvent ? '' : 'Grade';
      wrap.innerHTML = `
        <table class="table table-xs sm:table-sm w-full bg-white group/event-table">
          <thead>
            <tr>
              <th class="w-10"></th>
              <th class="text-left pl-1">${nameHeader}</th>
              <th>${gradeHeader}</th>
              <th>School</th>
              <th>Result</th>
              <th>Place</th>
              <th>Sectional Host</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      `;

      const tbody = wrap.querySelector('tbody');
      // Compute tie-aware rankings: equal result2 values share the same rank.
      const qRanks = new Array(qualifiers.length);
      {
        let lastVal = null;
        let lastRank = 0;
        for (let i = 0; i < qualifiers.length; i++) {
          const v = qualifiers[i]?.result2;
          if (i > 0 && v !== null && v !== undefined && v === lastVal) {
            qRanks[i] = lastRank;
          } else {
            qRanks[i] = i + 1;
            lastRank = i + 1;
            lastVal = v;
          }
        }
      }
      qualifiers.forEach((row, index) => {
        const tr = document.createElement('tr');
        const displayName = row.name || row.school || '-';
        const metStandard = Boolean(row.met_standard) || row.qualifier_type === 'standard';
        const linkClass = 'text-inherit hover:underline';
        let linkedName = displayName;
        if (!row.is_placeholder && displayName !== '-') {
          if (isRelayEvent && row.school_id) {
            linkedName = `<a href="/school-dashboard/${row.school_id}" class="${linkClass}">${displayName}</a>`;
          } else if (!isRelayEvent && row.athlete_id) {
            linkedName = `<a href="/athlete-dashboard/${row.athlete_id}" class="${linkClass}">${displayName}</a>`;
          }
        }
        let nameText = linkedName;
        // Add callback badge if needed
        if (row.qualifier_type === 'fill' || row.is_callback) {
          nameText = `${linkedName} <span class="text-blue-600 font-semibold">(callback)</span>`;
        }
        // Style entire row for placeholder
        if (row.is_placeholder) {
          tr.classList.add('text-orange-600', 'bg-orange-50');
        }
        const resultText = metStandard
          ? `${row.result || ''} <span class="text-emerald-700 font-bold ml-1">STAN</span>`
          : `${row.result || ''}`;
        const schoolDisplay = row.school || '';
        const schoolCell = (!row.is_placeholder && row.school_id && schoolDisplay && schoolDisplay !== '-')
          ? `<a href="/school-dashboard/${row.school_id}" class="${linkClass}">${schoolDisplay}</a>`
          : schoolDisplay;
        tr.innerHTML = `
          <td class="w-10 pr-1 font-semibold">${qRanks[index]}</td>
          <td class="pl-1">${nameText}</td>
          <td>${row.grade || ''}</td>
          <td>${schoolCell}</td>
          <td>${resultText}</td>
          <td>${row.place || ''}</td>
          <td>${row.sectional_host || ''}</td>
        `;
        tbody.appendChild(tr);
      });

      section.appendChild(wrap);
      detailContent.appendChild(section);
    });
  }

  async function fetchRegionalDetail(regionalNum) {
    state.selectedRegional = regionalNum;
    state.detailRequestId += 1;
  const requestId = state.detailRequestId;
    detailSection.classList.remove('hidden');
  const regionalHost = getRegionalHost(regionalNum);
    detailTitle.textContent = `${state.year} ${state.gender} ${groupLabel} #${regionalNum} - ${regionalHost}`;
    setLoading(true);
    detailContent.classList.add('hidden');
    detailContent.innerHTML = '';
    detailMessage.classList.add('hidden');

    try {
      const response = await fetch(`${apiDetailUrl}?gender=${encodeURIComponent(state.gender)}&regional_num=${regionalNum}&year=${state.year}`);
      if (requestId !== state.detailRequestId) {
        return;
      }
      if (!response.ok) {
        throw new Error(loadErrorMessage);
      }
      const payload = await response.json();
      if (requestId !== state.detailRequestId) {
        return;
      }
      renderDetail(payload);
    } catch (error) {
      if (requestId !== state.detailRequestId) {
        return;
      }
      clearDetailTable();
      setMessage(error.message || loadErrorMessage, 'error');
    } finally {
      if (requestId === state.detailRequestId) {
        setLoading(false);
      }
    }
  }

  renderGenderButtons();
  fetchStatus();

  // ---- Top List (combined across all regionals) ----
  const topListBtn = document.getElementById('top-list-btn');
  const topListState = { requestId: 0 };

  function buildEventTable(eventBlock, rows, expanded) {
  const wrap = document.createElement('div');
    wrap.className = 'overflow-x-auto relative';
  const isRelayEvent = String(eventBlock.event || '').startsWith('4 x ');
  const nameHeader = isRelayEvent ? 'School' : 'Name';
  const gradeHeader = isRelayEvent ? '' : 'Grade';
    wrap.innerHTML = `
      <table class="table table-xs sm:table-sm w-full bg-white group/event-table">
        <thead>
          <tr>
            <th class="w-10"></th>
            <th class="text-left pl-1">${nameHeader}</th>
            <th>${gradeHeader}</th>
            <th>School</th>
            <th>Result</th>
            <th>Place</th>
            <th>Sectional Host</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    `;
  const tbody = wrap.querySelector('tbody');
    // Compute tie-aware rankings across the FULL list (so rank is consistent regardless of expansion)
  const ranks = new Array(rows.length);
    let lastVal = null;
    let lastRank = 0;
    for (let i = 0; i < rows.length; i++) {
      const v = rows[i]?.result2;
      if (i > 0 && v !== null && v !== undefined && v === lastVal) {
        ranks[i] = lastRank;
      } else {
        ranks[i] = i + 1;
        lastRank = i + 1;
        lastVal = v;
      }
    }
  const visibleRows = expanded ? rows : rows.slice(0, 10);
    visibleRows.forEach((row, idx) => {
      const tr = document.createElement('tr');
      const rank = ranks[idx];
      const displayName = row.name || row.school || '-';
      const metStandard = Boolean(row.met_standard) || row.qualifier_type === 'standard';
      let nameText = displayName;
      if (row.qualifier_type === 'fill' || row.is_callback) {
        nameText = `${displayName} <span class="text-blue-600 font-semibold">(callback)</span>`;
      }
      if (row.is_placeholder) {
        tr.classList.add('text-orange-600', 'bg-orange-50');
      }
      const resultText = metStandard
        ? `${row.result || ''} <span class="text-emerald-700 font-bold ml-1">STAN</span>`
        : `${row.result || ''}`;
      tr.innerHTML = `
        <td class="w-10 pr-1 font-semibold">${rank}</td>
        <td class="pl-1">${nameText}</td>
        <td>${row.grade || ''}</td>
        <td>${row.school || ''}</td>
        <td>${resultText}</td>
        <td>${row.place || ''}</td>
        <td>${row.sectional_host || ''}</td>
      `;
      tbody.appendChild(tr);
    });
    return wrap;
  }

  function renderTopList(payload) {
  const events = payload.events || [];
    detailSection.classList.remove('hidden');
    detailTitle.textContent = `${state.year} ${state.gender} Combined Regional Rankings`;
    detailMessage.classList.add('hidden');

    if (!events.length) {
      clearDetailTable();
      detailSection.classList.remove('hidden');
      detailTitle.textContent = `${state.year} ${state.gender} Combined Regional Rankings`;
      setMessage('No data available yet for any regional.', 'warning');
      return;
    }

    initEventJump(events);
    detailContent.classList.remove('hidden');
    detailContent.innerHTML = '';

    events.forEach((eventBlock, index) => {
      const section = document.createElement('section');
      section.className = 'space-y-2';
      const chipKey = `${eventSlug(eventBlock.event)}-${index}`;
      section.id = `event-${chipKey}`;
      section.dataset.chipKey = chipKey;

      const headerWrap = document.createElement('div');
      headerWrap.className = 'flex flex-wrap items-center gap-2 relative';

      const header = document.createElement('h3');
      header.className = 'text-base font-semibold text-base-content';
      header.textContent = eventBlock.event;
      headerWrap.appendChild(header);

      if (eventBlock.standard_mark) {
        const standard = document.createElement('span');
        standard.className = 'badge badge-sm text-xs font-semibold border-emerald-600/40 bg-emerald-50 text-emerald-700';
        standard.textContent = `Standard: ${eventBlock.standard_mark}`;
        headerWrap.appendChild(standard);
      }

      const upArrowBtn = document.createElement('button');
      upArrowBtn.type = 'button';
      upArrowBtn.setAttribute('aria-label', 'Back to top');
      upArrowBtn.setAttribute('title', 'Back to top');
      upArrowBtn.className = 'up-arrow-btn absolute right-0 top-0 bg-white border border-base-300 rounded-full p-0.5 shadow-sm hover:border-primary hover:bg-primary/10 focus:bg-primary/20 focus:border-primary transition-colors outline-none cursor-pointer';
      upArrowBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fill-rule="evenodd" d="M10.707 3.293a1 1 0 00-1.414 0l-6 6a1 1 0 101.414 1.414L9 6.414V17a1 1 0 102 0V6.414l4.293 4.293a1 1 0 001.414-1.414l-6-6z" clip-rule="evenodd" />
        </svg>
      `;
      upArrowBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      headerWrap.appendChild(upArrowBtn);

      section.appendChild(headerWrap);

      const rows = Array.isArray(eventBlock.qualifiers) ? eventBlock.qualifiers : [];
      if (!rows.length) {
        const empty = document.createElement('p');
        empty.className = 'text-sm text-base-content/60';
        empty.textContent = 'No entries available.';
        section.appendChild(empty);
        detailContent.appendChild(section);
        return;
      }

      let expanded = false;
      const wrap = document.createElement('div');
      wrap.className = 'overflow-x-auto border border-base-200 rounded-lg';
      const tableHolder = document.createElement('div');
      tableHolder.appendChild(buildEventTable(eventBlock, rows, expanded));
      wrap.appendChild(tableHolder);

      if (rows.length > 10) {
        const footer = document.createElement('div');
        footer.className = 'flex justify-center border-t border-base-200 bg-base-100/40 px-2 py-2';
        const showAllBtn = document.createElement('button');
        showAllBtn.type = 'button';
        showAllBtn.className = 'btn btn-xs btn-ghost text-primary';
        showAllBtn.textContent = `Show All (${rows.length})`;
        showAllBtn.addEventListener('click', () => {
          expanded = !expanded;
          tableHolder.innerHTML = '';
          tableHolder.appendChild(buildEventTable(eventBlock, rows, expanded));
          showAllBtn.textContent = expanded ? 'Collapse' : `Show All (${rows.length})`;
        });
        footer.appendChild(showAllBtn);
        wrap.appendChild(footer);
      }

      section.appendChild(wrap);

      detailContent.appendChild(section);
    });
  }

  async function fetchTopList() {
    topListState.requestId += 1;
  const requestId = topListState.requestId;
    state.selectedRegional = null;
    detailSection.classList.remove('hidden');
    detailTitle.textContent = `${state.year} ${state.gender} Combined Regional Rankings`;
    detailContent.classList.add('hidden');
    detailContent.innerHTML = '';
    detailMessage.classList.add('hidden');
    setLoading(true);
    try {
      const response = await fetch(`/api/regional-qualifiers/top-list?gender=${encodeURIComponent(state.gender)}&year=${state.year}`);
      if (requestId !== topListState.requestId) return;
      if (!response.ok) {
        throw new Error('Unable to load top list.');
      }
      const payload = await response.json();
      if (requestId !== topListState.requestId) return;
      renderTopList(payload);
    } catch (error) {
      if (requestId !== topListState.requestId) return;
      clearDetailTable();
      detailSection.classList.remove('hidden');
      detailTitle.textContent = `${state.year} ${state.gender} Combined Regional Rankings`;
      setMessage(error.message || 'Unable to load rankings.', 'error');
    } finally {
      if (requestId === topListState.requestId) {
        setLoading(false);
      }
    }
  }

  if (topListBtn) {
    topListBtn.addEventListener('click', () => {
      fetchTopList();
      detailSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
});
