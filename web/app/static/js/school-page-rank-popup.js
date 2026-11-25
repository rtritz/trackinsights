/* SchoolRankPopup.init(root, { schoolId, gender, season })
 * Delegates clicks on .ranklink elements inside root. data-event selects the
 * event (empty for program rankings); data-athlete identifies an individual,
 * otherwise the school's relay/program row is selected. data-rank and
 * data-name supply context when the entry is missing or filtered out;
 * data-season overrides the page season (All-Time cards name their year).
 * Returns { destroy() }; repeated init on the same root replaces the old one.
 *
 * School size: the season's ranked programs split at their median enrollment
 * (so each half holds about the same number of schools, and the split is the
 * same in every list for that season). Every list offers All / Small / Large.
 *
 * Grade: athlete lists (not relays or programs) also filter by class year that
 * season -- the All-Time list by the year of the mark. Both filters combine, and
 * ranks are renumbered inside whatever is shown.
 *
 * Every filter is always available. When the clicked athlete (or school) is
 * not in the filtered group, a dashed "would rank here" row shows where that
 * mark would fall among them. Both filters reset to All on each open.
 */
(function () {
    'use strict';

    const instances = new WeakMap();
    let serial = 0;

    const ICONS = {
        top: 'M6 4h12M12 20V8M7 13l5-5 5 5',
        bottom: 'M6 20h12M12 4v12M7 11l5 5 5-5',
        target: 'M12 3v3M12 18v3M3 12h3M18 12h3M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
    };

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = String(text);
        return node;
    }

    function iconButton(icon, label) {
        const node = element('button', 'btn btn-sm btn-square btn-ghost border-base-300');
        node.type = 'button';
        node.title = label;
        node.setAttribute('aria-label', label);
        node.innerHTML = `<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[icon]}"/></svg>`;
        return node;
    }

    const GRADES = ['FR', 'SO', 'JR', 'SR'];

    function switchGroup(label) {
        const group = element('div', 'inline-flex items-center rounded-lg border border-base-300 bg-base-200/60 p-0.5');
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', label);
        return group;
    }

    function chip(label, active, onPick) {
        const node = element('button', `whitespace-nowrap rounded-md px-3 py-1 text-sm transition ${active ? 'bg-white font-semibold text-primary shadow-sm' : 'font-medium text-base-content/60 hover:text-base-content'}`, label);
        node.type = 'button';
        node.setAttribute('aria-pressed', String(active));
        node.addEventListener('click', onPick);
        return node;
    }

    function median(values) {
        const sorted = values.slice().sort((a, b) => a - b);
        if (!sorted.length) return null;
        const mid = Math.floor(sorted.length / 2);
        return Math.round(sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2);
    }

    function init(root, options) {
        if (instances.has(root)) instances.get(root).destroy();
        options = options || {};
        const cache = new Map();
        const splits = new Map();
        const dialog = element('dialog', 'modal');
        const card = element('div', 'modal-box max-w-3xl flex flex-col gap-3');
        const header = element('div', 'flex items-start justify-between gap-4');
        const heading = element('div');
        const title = element('h2', 'text-xl font-bold text-primary');
        title.id = `school-rank-popup-title-${++serial}`;
        const subtitle = element('p', 'text-sm text-base-content/70');
        const close = element('button', 'btn btn-sm btn-ghost', '✕');
        close.type = 'button';
        close.setAttribute('aria-label', 'Close rankings');
        heading.append(title, subtitle);
        header.append(heading, close);
        dialog.setAttribute('aria-labelledby', title.id);

        const controls = element('div', 'flex flex-wrap items-center justify-between gap-2');
        const sizeBox = element('div', 'flex flex-wrap items-center gap-2');
        const chips = switchGroup('School size');
        const gradeChips = switchGroup('Grade');
        sizeBox.append(chips, gradeChips);
        const navigation = element('div', 'flex items-center gap-1');
        const top = iconButton('top', 'Go to top');
        const jump = iconButton('target', 'Go to the selected entry');
        const bottom = iconButton('bottom', 'Go to bottom');
        navigation.append(top, jump, bottom);
        controls.append(sizeBox, navigation);
        // One line explaining the size groups, instead of numbers in the switch.
        const sizeNote = element('p', 'hidden -mt-1 text-xs text-base-content/55');
        const status = element('p', 'text-sm text-base-content/70');
        status.setAttribute('role', 'status');
        const body = element('div', 'overflow-auto max-h-[60vh] border border-base-200 rounded-lg');
        card.append(header, controls, sizeNote, status, body);
        dialog.appendChild(card);
        root.appendChild(dialog);

        let current = null, origin = null, lastFocused = null, generation = 0, split = null, target = null;
        let size = '';                       // '', 'small' or 'large'
        let grade = '';                      // '' or FR/SO/JR/SR
        let sort = { key: 'rank', ascending: true };

        // ---------------------------------------------------------- size chips
        function renderChips() {
            chips.replaceChildren();
            // All / Small / Large, with a one-line note for the selected group only.
            const choices = [['', 'All schools']].concat(split ? [['small', 'Small'], ['large', 'Large']] : []);
            const cutoff = split ? split.toLocaleString() : '';
            const notes = { small: `Small schools: enrollment under ${cutoff} (the median)`,
                            large: `Large schools: enrollment ${cutoff} or more (the median)` };
            if (!choices.some(([value]) => value === size)) size = '';
            sizeNote.classList.toggle('hidden', !size);
            sizeNote.textContent = size ? notes[size] : '';
            choices.forEach(([value, label]) => {
                chips.appendChild(chip(label, value === size, () => { size = value; renderChips(); renderList(); }));
            });

            // Grade: athlete lists only (relays and programs carry no grade).
            gradeChips.replaceChildren();
            const graded = hasGrades();
            gradeChips.classList.toggle('hidden', !graded);
            if (graded) {
                [['', 'All grades']].concat(GRADES.map(value => [value, value])).forEach(([value, label]) => {
                    gradeChips.appendChild(chip(label, value === grade, () => { grade = value; renderChips(); renderList(); }));
                });
            }
        }

        function hasGrades() {
            return Boolean(current && current.kind !== 'program' && current.rows.some(row => GRADES.includes(row.grade)));
        }

        function inGrade(row) {
            return !grade || !hasGrades() || row.grade === grade;
        }

        function inSize(row) {
            if (!size || split == null) return true;
            if (typeof row.enrollment !== 'number' || !Number.isFinite(row.enrollment)) return false;
            return size === 'large' ? row.enrollment >= split : row.enrollment < split;
        }

        function isOrigin(row) {
            if (!origin) return false;
            if (origin.athlete) return String(row.athlete_id ?? '') === origin.athlete;
            return row.athlete_id == null && String(row.school_id ?? '') === String(options.schoolId ?? '');
        }

        function link(id, path, text) {
            // IDs are database integers; never construct a URL from arbitrary text.
            if (id == null || !/^\d+$/.test(String(id))) return document.createTextNode(text == null ? '—' : String(text));
            const anchor = element('a', 'text-primary no-underline transition hover:text-primary/70', text == null ? '—' : text);
            anchor.href = `/${path}/${encodeURIComponent(String(id))}`;
            return anchor;
        }

        // ---------------------------------------------------------- the list
        function renderList() {
            if (!current) return;
            const sizeFiltered = Boolean(size && split != null);
            const gradeFiltered = Boolean(grade && hasGrades());
            const filtered = sizeFiltered || gradeFiltered;
            const inGroup = current.rows.filter(row => inSize(row) && inGrade(row));
            const program = current.kind === 'program';
            // Competition ranking inside the size group: ties share a rank.
            const groupRank = new Map();
            inGroup.forEach(row => groupRank.set(row, 1 + inGroup.filter(other => Number(other.rank) < Number(row.rank)).length));

            // Sortable columns. "Mark" sorts by rank (the list is ranked by mark).
            const hasYear = !program && current.rows.some(row => row.year != null);
            const hasGrade = hasGrades();
            const columns = program
                ? [['rank', 'Rank'], ['name', 'School'], ['enrollment', 'Enrollment']]
                : [['rank', 'Rank'], ['name', 'Athlete']]
                    .concat(hasGrade ? [['grade', 'Grade']] : [], [['school', 'School'], ['mark', 'Mark']],
                            hasYear ? [['year', 'Year']] : [], [['enrollment', 'Enrollment']]);
            const value = (row, key) => {
                if (key === 'rank' || key === 'mark') return Number(row.rank);
                if (key === 'grade') return GRADES.includes(row.grade) ? GRADES.indexOf(row.grade) : null;
                if (key === 'enrollment') return typeof row.enrollment === 'number' ? row.enrollment : null;
                if (key === 'year') return row.year == null ? null : Number(row.year);
                const text = key === 'school' ? row.school : row.name;
                return text == null ? null : String(text).toLowerCase();
            };
            // The clicked entry, when the filters leave it out: shown as a dashed
            // "would rank here" row at the place its mark falls in this group.
            const original = current.rows.find(isOrigin);
            const ghost = original && filtered && !inGroup.includes(original) ? original : null;
            if (ghost) groupRank.set(ghost, 1 + inGroup.filter(other => Number(other.rank) < Number(ghost.rank)).length);
            const rows = inGroup.concat(ghost ? [ghost] : []).sort((a, b) => {
                const x = value(a, sort.key), y = value(b, sort.key);
                if (x === null || y === null) return x === y ? 0 : (x === null ? 1 : -1);
                const order = typeof x === 'number' ? x - y : x.localeCompare(y);
                return (sort.ascending ? order : -order) || Number(a.rank) - Number(b.rank);
            });

            const selectedIndex = rows.findIndex(isOrigin);
            const targetRank = Number(original ? original.rank : origin.rank);
            let nearbyIndex = -1;
            if (selectedIndex < 0 && rows.length && Number.isFinite(targetRank)) {
                nearbyIndex = rows.reduce((best, row, index) =>
                    Math.abs(Number(row.rank) - targetRank) < Math.abs(Number(rows[best].rank) - targetRank) ? index : best, 0);
            }
            if (ghost) status.textContent = `${origin.name || 'This entry'} isn't in this group. The dashed row shows where ${program ? 'the program' : 'that mark'} would rank.`;
            else if (selectedIndex >= 0 || !origin.name) status.textContent = '';
            else status.textContent = `${origin.name} was not found in these rankings.`;

            body.replaceChildren();
            target = null;
            if (!rows.length) {
                body.appendChild(element('p', 'p-4 text-sm text-base-content/70', program ? 'No schools in this size group.' : 'No entries in this group.'));
                return;
            }
            const table = element('table', 'table table-sm table-pin-rows w-full');
            const headRow = element('tr', 'bg-base-200');
            columns.forEach(([key, label]) => {
                const th = element('th', key === 'enrollment' ? 'hidden sm:table-cell' : '');
                th.scope = 'col';
                const active = sort.key === key;
                if (active) th.setAttribute('aria-sort', sort.ascending ? 'ascending' : 'descending');
                // The icon slot is always reserved, so sorting never shifts a column.
                const button = element('button', 'inline-flex items-center gap-1 font-semibold text-base-content transition hover:text-primary', label);
                button.type = 'button';
                button.appendChild(element('span', 'inline-block w-3 text-center text-[10px] text-primary', active ? (sort.ascending ? '▲' : '▼') : ''));
                button.addEventListener('click', () => {
                    sort = { key, ascending: sort.key === key ? !sort.ascending : key !== 'enrollment' };
                    renderList();
                });
                th.appendChild(button);
                headRow.appendChild(th);
            });
            const thead = element('thead');
            thead.appendChild(headRow);
            table.appendChild(thead);
            const tbody = element('tbody');
            rows.forEach((row, index) => {
                const mine = String(row.school_id ?? '') === String(options.schoolId ?? '');
                const selected = index === selectedIndex;
                const hypothetical = row === ghost;
                const tr = element('tr', hypothetical
                    ? 'bg-warning/10 italic text-base-content/70 outline-2 outline-dashed outline-warning -outline-offset-2'
                    : (selected ? 'bg-warning/25 font-semibold' : (mine ? 'bg-primary/10' : '')));
                if (selected) tr.setAttribute('aria-current', 'true');
                const cell = (content, className) => {
                    const td = element('td', className || '');
                    if (content instanceof Node) td.appendChild(content);
                    else td.textContent = content == null ? '—' : String(content);
                    tr.appendChild(td);
                };
                if (filtered) {
                    const wrap = element('span', 'whitespace-nowrap');
                    wrap.append(element('span', '', groupRank.get(row)),
                                element('span', 'ml-1 text-xs font-normal text-base-content/50', `(${row.rank} overall)`));
                    cell(wrap);
                } else {
                    cell(row.rank);
                }
                const named = content => {
                    if (!hypothetical) return content;
                    const wrap = element('span');
                    wrap.append(content, element('span', 'ml-1.5 whitespace-nowrap text-xs not-italic text-base-content/50', 'would rank here'));
                    return wrap;
                };
                if (program) {
                    cell(named(link(row.school_id, 'school-dashboard', row.name)));
                } else {
                    cell(named(link(row.athlete_id, 'athlete-dashboard', row.name)));
                    if (hasGrade) cell(row.grade);
                    cell(link(row.school_id, 'school-dashboard', row.school));
                    cell(row.mark);
                    if (hasYear) cell(row.year);
                }
                cell(typeof row.enrollment === 'number' ? row.enrollment.toLocaleString() : row.enrollment, 'hidden sm:table-cell');
                if (selected || hypothetical || (selectedIndex < 0 && index === nearbyIndex)) target = tr;
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);
            body.appendChild(table);
            jump.disabled = !target;
            goToTarget('auto');
        }

        function goToTarget(behavior) {
            if (target) target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: behavior || 'smooth' });
        }

        function getPayload(season, eventName) {
            const key = `${season}|${eventName}`;
            if (!cache.has(key)) {
                const url = `/api/rankings/${encodeURIComponent(options.gender)}/${encodeURIComponent(season)}` +
                    (eventName ? `?event=${encodeURIComponent(eventName)}` : '');
                const entry = {};
                entry.request = fetch(url).then(response => {
                    if (!response.ok) throw new Error('Those rankings are not available.');
                    return response.json();
                }).then(payload => {
                    if (!payload || !Array.isArray(payload.rows)) throw new Error('Invalid rankings response.');
                    entry.resolved = payload;
                    return payload;
                }).catch(error => {
                    cache.delete(key);
                    throw error;
                });
                cache.set(key, entry);
            }
            return cache.get(key).request;
        }

        // One size split per season, from the program list (one row per school).
        async function loadSplit(season) {
            if (!splits.has(season)) {
                try {
                    const program = await getPayload(season, '');
                    splits.set(season, median(program.rows.map(row => row.enrollment)
                        .filter(value => typeof value === 'number' && Number.isFinite(value) && value > 0)));
                } catch (_) { return null; }
            }
            return splits.get(season);
        }

        async function show(trigger) {
            const eventName = trigger.dataset.event || '';
            const season = trigger.dataset.season || options.season;
            origin = { athlete: trigger.dataset.athlete || '', rank: trigger.dataset.rank || '', name: trigger.dataset.name || '' };
            lastFocused = trigger;
            const request = ++generation;
            current = null;
            sort = { key: 'rank', ascending: true };
            grade = '';   // every list opens unfiltered
            size = '';
            title.textContent = eventName || 'Statewide Program Rankings';
            subtitle.textContent = 'Loading…';
            status.textContent = '';
            body.replaceChildren();
            jump.disabled = true;
            if (!dialog.open) dialog.showModal();
            close.focus();
            try {
                const splitSeason = season === 'all-time' ? (options.latestSeason || season) : season;
                const [payload, seasonSplit] = await Promise.all([getPayload(season, eventName), loadSplit(splitSeason)]);
                if (request !== generation || !dialog.open) return;
                current = Object.assign({ season }, payload);
                split = seasonSplit;
                title.textContent = payload.title || title.textContent;
                subtitle.textContent = payload.subtitle || '';
                renderChips();
                renderList();
            } catch (error) {
                if (request !== generation || !dialog.open) return;
                subtitle.textContent = '';
                status.textContent = error.message || 'Unable to load rankings.';
            }
        }

        function onClick(event) {
            const trigger = event.target.closest('.ranklink');
            if (!trigger || !root.contains(trigger) || dialog.contains(trigger)) return;
            // A link inside a card (the athlete's name) keeps its own job.
            const anchor = event.target.closest('a');
            if (anchor && trigger.contains(anchor)) return;
            event.preventDefault();
            show(trigger);
        }
        // Cards that act as buttons (role="button") need Enter/Space too.
        function onKey(event) {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            const trigger = event.target.closest('.ranklink[role="button"]');
            if (!trigger || trigger !== event.target || !root.contains(trigger)) return;
            event.preventDefault();
            show(trigger);
        }
        function onClose() {
            generation++;
            if (lastFocused && lastFocused.isConnected) lastFocused.focus();
        }
        function onBackdrop(event) {
            if (event.target === dialog) dialog.close();
        }
        root.addEventListener('click', onClick);
        root.addEventListener('keydown', onKey);
        dialog.addEventListener('close', onClose);
        dialog.addEventListener('click', onBackdrop);
        close.addEventListener('click', () => dialog.close());
        top.addEventListener('click', () => body.scrollTo({ top: 0, behavior: 'smooth' }));
        bottom.addEventListener('click', () => body.scrollTo({ top: body.scrollHeight, behavior: 'smooth' }));
        jump.addEventListener('click', () => goToTarget('smooth'));

        const instance = { destroy() {
            generation++;
            root.removeEventListener('click', onClick);
            root.removeEventListener('keydown', onKey);
            if (dialog.open) dialog.close();
            dialog.removeEventListener('close', onClose);
            if (lastFocused && lastFocused.isConnected) lastFocused.focus();
            dialog.remove();
            instances.delete(root);
        } };
        instances.set(root, instance);
        return instance;
    }

    window.SchoolRankPopup = { init };
}());
