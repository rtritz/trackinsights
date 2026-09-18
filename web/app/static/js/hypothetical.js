/* Hypothetical
 *
 * Moved out of insights/hypothetical.html, where it sat as 204 lines inside a <script> tag.
 * Here it gets syntax checking, the browser can cache it, and "where is the
 * code for this page?" has the obvious answer: the file named after the page.
 *
 * It reads what it needs from the DOM rather than from Jinja, which is what
 * made moving it safe. Keep it that way -- pass values in with data- attributes
 * rather than templating them into the JavaScript.
 */

document.addEventListener('DOMContentLoaded', async () => {
  const loadingEl = document.getElementById('loading-options');
  const formEl = document.getElementById('hypothetical-form');
  const genderGroup = document.getElementById('gender-group');
  const eventGroup = document.getElementById('event-group');
  const yearGroup = document.getElementById('year-group');
  const meetTypeGroup = document.getElementById('meet-type-group');
  const performanceInput = document.getElementById('performance-input');
  const performanceHint = document.getElementById('performance-hint');
  const submitBtn = document.getElementById('submit-btn');
  const formError = document.getElementById('form-error');

  const FIELD_EVENTS = new Set(['High Jump', 'Long Jump', 'Pole Vault', 'Shot Put', 'Discus']);
  const EVENT_GROUPS = {
    'Sprints & Distance': ['100 Meters', '200 Meters', '400 Meters', '800 Meters', '1600 Meters', '3200 Meters'],
    'Hurdles': ['100 Hurdles', '110 Hurdles', '300 Hurdles'],
    'Field Events': ['High Jump', 'Long Jump', 'Pole Vault', 'Shot Put', 'Discus'],
  };

  const gradeGroup = document.getElementById('grade-group');
  const enrollmentInput = document.getElementById('enrollment-input');

  const GRADE_LEVELS = ['FR', 'SO', 'JR', 'SR'];

  let state = { gender: null, event: null, year: null, meetType: null, grade: null };

  const chipBase = 'btn btn-sm border border-base-300 rounded-full px-4 py-1.5 text-sm transition-all shadow-none hover:shadow-none';
  const chipActive = 'bg-primary text-white border-primary hover:bg-primary/90';
  const chipInactive = 'bg-white text-gray-700 hover:bg-base-200';

  function createChip(label, value, group, stateKey) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `${chipBase} ${chipInactive}`;
    btn.textContent = label;
    btn.dataset.value = value;
    btn.addEventListener('click', () => {
      group.querySelectorAll('button').forEach(b => {
        b.className = `${chipBase} ${chipInactive}`;
      });
      btn.className = `${chipBase} ${chipActive}`;
      state[stateKey] = value;
      onStateChange(stateKey);
    });
    return btn;
  }

  function onStateChange(changedKey) {
    // Update performance hint when event changes
    if (changedKey === 'event') {
      if (state.event) {
        const isField = FIELD_EVENTS.has(state.event);
        performanceInput.disabled = false;
        performanceInput.value = '';
        if (isField) {
          performanceInput.placeholder = "e.g. 5'10\" or 42'3\"";
          performanceHint.textContent = 'Enter a distance (feet\'inches")';
        } else {
          performanceInput.placeholder = 'e.g. 11.24 or 4:32.10';
          performanceHint.textContent = 'Enter a time (seconds or minutes:seconds)';
        }
      } else {
        performanceInput.disabled = true;
        performanceInput.value = '';
        performanceHint.textContent = 'Select an event first';
      }
    }

    // Filter events based on gender
    if (changedKey === 'gender') {
      renderEvents(state.gender);
    }

    validateForm();
  }

  function validateForm() {
    const hasPerformance = performanceInput.value.trim().length > 0;
    const allSelected = state.gender && state.event && state.year && state.meetType && hasPerformance;
    submitBtn.disabled = !allSelected;
    formError.classList.add('hidden');
  }

  function renderEvents(gender) {
    eventGroup.innerHTML = '';
    state.event = null;

    const skipBoys = new Set(['100 Hurdles']);
    const skipGirls = new Set(['110 Hurdles']);

    for (const [groupLabel, events] of Object.entries(EVENT_GROUPS)) {
      const header = document.createElement('div');
      header.className = 'col-span-2 sm:col-span-3 text-xs uppercase tracking-wide text-gray-400 mt-2 first:mt-0';
      header.textContent = groupLabel;
      eventGroup.appendChild(header);

      for (const evt of events) {
        if (gender === 'Boys' && skipBoys.has(evt)) continue;
        if (gender === 'Girls' && skipGirls.has(evt)) continue;
        eventGroup.appendChild(createChip(evt, evt, eventGroup, 'event'));
      }
    }

    // Auto-select first event
    const firstEventChip = eventGroup.querySelector('button');
    if (firstEventChip) firstEventChip.click();
    validateForm();
  }

  try {
    const resp = await fetch('/api/hypothetical-rank/options');
    if (!resp.ok) throw new Error('Failed to load options');
    const options = await resp.json();

    // Render gender chips
    for (const g of options.genders) {
      const chip = createChip(g, g, genderGroup, 'gender');
      genderGroup.appendChild(chip);
      if (g === 'Boys') {
        chip.click();
      }
    }

    // Render year chips
    for (const y of options.years) {
      yearGroup.appendChild(createChip(String(y), String(y), yearGroup, 'year'));
    }
    // Auto-select first year
    const firstYearChip = yearGroup.querySelector('button');
    if (firstYearChip) firstYearChip.click();

    // Render meet type chips
    for (const mt of options.meet_types) {
      meetTypeGroup.appendChild(createChip(mt, mt, meetTypeGroup, 'meetType'));
    }
    // Auto-select first meet type
    const firstMeetTypeChip = meetTypeGroup.querySelector('button');
    if (firstMeetTypeChip) firstMeetTypeChip.click();

    // Render grade level chips (optional, toggleable)
    for (const gl of GRADE_LEVELS) {
      const btn = createChip(gl, gl, gradeGroup, 'grade');
      // Allow deselect by clicking the active chip again
      btn.addEventListener('click', () => {
        if (btn.className.includes('bg-primary')) {
          // already active – check if it was just activated by createChip handler
          // We rely on the createChip handler running first setting state.grade = gl
        }
      });
      gradeGroup.appendChild(btn);
    }
    // Add a "Clear" button for grade
    const clearGradeBtn = document.createElement('button');
    clearGradeBtn.type = 'button';
    clearGradeBtn.className = `${chipBase} bg-base-200 text-gray-500 hover:bg-base-300 text-xs`;
    clearGradeBtn.textContent = '✕ Clear';
    clearGradeBtn.addEventListener('click', () => {
      gradeGroup.querySelectorAll('button').forEach(b => {
        if (b !== clearGradeBtn) b.className = `${chipBase} ${chipInactive}`;
      });
      state.grade = null;
    });
    gradeGroup.appendChild(clearGradeBtn);

    loadingEl.classList.add('hidden');
    formEl.classList.remove('hidden');
  } catch (err) {
    loadingEl.innerHTML = '<p class="text-red-600">Failed to load options. Please try again later.</p>';
    console.error(err);
    return;
  }

  performanceInput.addEventListener('input', () => validateForm());

  formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    formError.classList.add('hidden');

    if (!state.gender || !state.event || !state.year || !state.meetType || !performanceInput.value.trim()) {
      formError.textContent = 'Please fill in all fields.';
      formError.classList.remove('hidden');
      return;
    }

    const params = new URLSearchParams({
      event: state.event,
      time: performanceInput.value.trim(),
      gender: state.gender,
      year: state.year,
      meet_type: state.meetType,
    });

    if (state.grade) {
      params.set('grade_level', state.grade);
    }
    const enrollmentVal = enrollmentInput.value.trim();
    if (enrollmentVal) {
      params.set('enrollment', enrollmentVal);
    }

    window.location.href = `/insights/hypothetical/result?${params.toString()}`;
  });
});
