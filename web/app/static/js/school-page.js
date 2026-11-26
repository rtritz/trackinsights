/* The page content is rendered by Jinja; only the event chart changes in place.
 * Season tabs and the Boys/Girls switch are plain links. */
(function () {
    'use strict';

    const root = document.getElementById('school-page');
    if (!root) return;

    // Filters are real links (new-tab, no-JS and crawlers all work). Switching a
    // filter is a change of view, not an arrival, so skip the intro overlay.
    root.querySelectorAll('a[data-nav]').forEach(link => {
        link.addEventListener('click', event => {
            if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            try { sessionStorage.setItem('ti-skip-intro', '1'); } catch (_) { /* Storage is optional. */ }
        });
    });

    // Results tables: the pinned name column shows its edge only while the
    // table is scrolled sideways (phones), when marks slide under the names.
    root.querySelectorAll('[data-scroll-edge]').forEach(box => {
        const update = () => box.toggleAttribute('data-scrolled', box.scrollLeft > 0);
        box.addEventListener('scroll', update, { passive: true });
        update();
    });

    // Season write-up: "Read more" reveals the honors list inline.
    root.querySelectorAll('[data-more-toggle]').forEach(button => {
        const more = document.getElementById(button.getAttribute('aria-controls'));
        if (!more) return;
        button.addEventListener('click', () => {
            const open = more.hidden;
            more.hidden = !open;
            button.setAttribute('aria-expanded', String(open));
            button.textContent = open ? 'Show less' : 'Read more';
        });
    });

    // Stage and outlook cards open their server-rendered list.
    root.querySelectorAll('[data-open-list]').forEach(card => {
        card.addEventListener('click', () => {
            const dialog = document.getElementById(card.dataset.openList);
            if (dialog && typeof dialog.showModal === 'function') dialog.showModal();
        });
    });

    // Sortable list tables: click a header to sort by it, again to reverse.
    // Cells carry data-sort (numbers or text); empty values always sort last.
    root.querySelectorAll('table[data-sortable]').forEach(table => {
        const headers = Array.from(table.querySelectorAll('thead th[data-sort-type]'));
        headers.forEach((th, column) => {
            const button = th.querySelector('button');
            if (!button) return;
            button.addEventListener('click', () => {
                const ascending = th.getAttribute('aria-sort') !== 'ascending';
                const numeric = th.dataset.sortType === 'number';
                const body = table.tBodies[0];
                const value = row => {
                    const cell = row.cells[column];
                    const raw = cell ? (cell.dataset.sort ?? cell.textContent).trim() : '';
                    return raw === '' ? null : (numeric ? Number(raw) : raw.toLowerCase());
                };
                const rows = Array.from(body.rows);
                rows.sort((a, b) => {
                    const x = value(a), y = value(b);
                    if (x === null || y === null) return x === y ? 0 : (x === null ? 1 : -1);
                    const order = numeric ? x - y : x.localeCompare(y);
                    return ascending ? order : -order;
                });
                body.append(...rows);
                // The sorted column shows ▲/▼ in a slot that is always reserved,
                // so sorting never changes a column's width.
                headers.forEach(other => {
                    other.removeAttribute('aria-sort');
                    const icon = other.querySelector('.sort-icon');
                    if (icon) icon.textContent = '';
                });
                th.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
                const icon = th.querySelector('.sort-icon');
                if (icon) icon.textContent = ascending ? '▲' : '▼';
            });
        });
    });


    // Team Rank by Season: a line where up is better. The vertical axis is
    // standing ("Top X%"), so rising means improving; each point is labelled
    // with its rank and its percentile. Drawn at the container's pixel width
    // so the labels are a true 12px.
    const standingBox = root.querySelector('[data-standing-chart]');
    const standingJson = root.querySelector('[data-standing-points]');
    let standing = [];
    try { standing = standingJson ? JSON.parse(standingJson.textContent) : []; } catch (_) { standing = []; }

    function ordinal(n) {
        const v = n % 100;
        return n + (['th', 'st', 'nd', 'rd'][(v - 20) % 10] || ['th', 'st', 'nd', 'rd'][v] || 'th');
    }

    // "all" ranks against every program; "group" against same-size schools.
    let standingScope = 'all';

    function drawStanding() {
        if (!standingBox || !standing.length) return;
        const grouped = standingScope === 'group';
        // Each season on the chosen scale; seasons without a size-group rank drop out.
        const series = standing
            .map(pt => grouped
                ? (pt.g_rank && pt.g_of ? { ...pt, shownRank: pt.g_rank, shownOf: pt.g_of, p: 1 - (pt.g_rank - 1) / pt.g_of } : null)
                : { ...pt, shownRank: pt.rank, shownOf: pt.of })
            .filter(Boolean);
        if (!series.length) { standingBox.replaceChildren(); return; }
        const NS = 'http://www.w3.org/2000/svg';
        const el = (tag, attrs, text) => {
            const node = document.createElementNS(NS, tag);
            Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
            if (text != null) node.textContent = text;
            return node;
        };
        const width = Math.max(320, standingBox.clientWidth);
        // left fits the axis words; right holds the TOP / BOTTOM HALF labels,
        // outside the plot so no point label can collide with them.
        const height = 270, left = 64, right = 92, top = 44, bottom = 40;
        const plotW = width - left - right, plotH = height - top - bottom;
        const inset = Math.min(56, plotW / 8);   // keeps end labels off the axis text
        const n = series.length;
        const x = i => left + (n === 1 ? plotW / 2 : inset + i * (plotW - 2 * inset) / (n - 1));
        const y = p => top + (1 - p) * plotH;
        const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, width, height, class: 'block text-base-content', 'font-size': 12, role: 'img', 'aria-label': 'Team rank by season' });
        // Two halves, shaded, so "which half of the state?" reads at a glance:
        // a faint maroon top half and a faint grey bottom half, labelled at the right.
        svg.append(el('rect', { x: left, y: y(1), width: plotW, height: y(0.5) - y(1), fill: 'var(--color-primary)', 'fill-opacity': 0.05 }));
        svg.append(el('rect', { x: left, y: y(0.5), width: plotW, height: y(0) - y(0.5), fill: 'currentColor', 'fill-opacity': 0.035 }));
        [['Top half', 0.75, 'var(--color-primary)', 0.6], ['Bottom half', 0.25, 'currentColor', 0.45]].forEach(([label, p, color, opacity]) => {
            svg.append(el('text', { x: width - right + 10, y: y(p) + 4, fill: color, 'fill-opacity': opacity, 'font-size': 10, 'font-weight': 700, 'letter-spacing': '0.06em' }, label.toUpperCase()));
        });
        // Plain words: best, the median (where the halves meet), last.
        [[1, 'Best'], [0.5, 'Median'], [0, 'Last']].forEach(([p, label]) => {
            svg.append(el('line', { x1: left, x2: width - right, y1: y(p), y2: y(p), stroke: 'currentColor', 'stroke-opacity': p === 0 ? 0.25 : (p === 0.5 ? 0.22 : 0.08) }));
            if (label) svg.append(el('text', { x: left - 12, y: y(p) + 4, 'text-anchor': 'end', fill: 'currentColor', 'fill-opacity': 0.5 }, label));
        });
        // Top half: "Top X%". Bottom half: "Bottom X%" (the share ranked at or below it).
        const standingLabel = pt => {
            const top = Math.max(1, Math.round(100 * (pt.shownRank - 1) / pt.shownOf));
            return top <= 50 ? `Top ${top}%` : `Bottom ${Math.max(1, Math.round(100 * (pt.shownOf - pt.shownRank + 1) / pt.shownOf))}%`;
        };
        const pts = series.map((pt, i) => ({ ...pt, cx: x(i), cy: y(pt.p) }));
        svg.append(el('path', { d: pts.map((pt, i) => `${i ? 'L' : 'M'}${pt.cx},${pt.cy}`).join(' '), fill: 'none', stroke: 'var(--color-primary)', 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
        pts.forEach(pt => {
            const g = el('g', {});
            g.append(el('title', {}, grouped
                ? `${pt.year}: ${ordinal(pt.shownRank)} of ${pt.shownOf} ${pt.group} schools (${standingLabel(pt).toLowerCase()}) · ${ordinal(pt.rank)} of ${pt.of} overall`
                : `${pt.year}: ${ordinal(pt.rank)} of ${pt.of} programs (${standingLabel(pt).toLowerCase()})`));
            g.append(el('circle', { cx: pt.cx, cy: pt.cy, r: 4.5, fill: '#fff', stroke: 'var(--color-primary)', 'stroke-width': 2.5 }));
            // The rank only; the shaded halves give the standing, the tooltip the
            // exact share. Below the point when it is near the top.
            const above = pt.cy - top > 20;
            g.append(el('text', { x: pt.cx, y: above ? pt.cy - 12 : pt.cy + 22, 'text-anchor': 'middle', fill: 'currentColor', 'font-weight': 700 }, ordinal(pt.shownRank)));
            svg.append(g);
            const link = el('a', { href: pt.url, 'data-nav': '' });
            link.append(el('text', { x: pt.cx, y: height - 14, 'text-anchor': 'middle', fill: 'var(--color-primary)', 'font-weight': 700 }, pt.year));
            svg.append(link);
        });
        standingBox.replaceChildren(svg);
        // Season links skip the intro overlay, like the header's links.
        standingBox.querySelectorAll('a[data-nav]').forEach(a => a.addEventListener('click', () => {
            try { sessionStorage.setItem('ti-skip-intro', '1'); } catch (_) { /* optional */ }
        }));
    }
    drawStanding();
    // The All / Small (or Large) schools switch redraws on the chosen scale.
    root.querySelectorAll('[data-standing-scope]').forEach(button => {
        button.addEventListener('click', () => {
            standingScope = button.dataset.standingScope;
            root.querySelectorAll('[data-standing-scope]').forEach(other => {
                const on = other === button;
                other.setAttribute('aria-pressed', String(on));
                ['bg-white', 'font-semibold', 'text-primary', 'shadow-sm'].forEach(c => other.classList.toggle(c, on));
                ['font-medium', 'text-base-content/60'].forEach(c => other.classList.toggle(c, !on));
            });
            drawStanding();
        });
    });

    // "Show earlier seasons" under the relay cards: reveals the folded rows.
    root.querySelectorAll('[data-show-earlier]').forEach(button => {
        const rows = Array.from(button.closest('section').querySelectorAll('[data-earlier-row]'));
        if (!rows.length) return;
        const label = button.textContent;
        let open = false;
        button.addEventListener('click', () => {
            open = !open;
            rows.forEach(row => row.classList.toggle('hidden', !open));
            button.setAttribute('aria-expanded', String(open));
            button.textContent = open ? 'Show fewer seasons' : label;
        });
    });

    if (window.SchoolRankPopup) {
        window.SchoolRankPopup.init(root, {
            schoolId: root.dataset.schoolId,
            gender: root.dataset.gender,
            season: root.dataset.season,
            latestSeason: root.dataset.latestSeason,
        });
    }

    const json = document.getElementById('school-page-events');
    let events = [];
    try { events = json ? JSON.parse(json.textContent) : []; } catch (_) { /* Leave server-rendered results intact. */ }
    if (!Array.isArray(events)) events = [];
    const buttons = Array.from(root.querySelectorAll('[data-event-index]'));
    const panels = Array.from(root.querySelectorAll('[data-event-panel]'));
    const renderedWidth = new Map();
    let activeIndex = null;

    // Widths are in the payload's native units: seconds for races, inches for field events.
    const binSizes = {
        '100 Meters': 0.2, '200 Meters': 0.4, '400 Meters': 1,
        '800 Meters': 2, '1600 Meters': 5, '3200 Meters': 10,
        '100 Hurdles': 0.3, '110 Hurdles': 0.3, '300 Hurdles': 1,
        '4 x 100 Relay': 0.5, '4 x 400 Relay': 3, '4 x 800 Relay': 10,
        'High Jump': 1, 'Pole Vault': 3, 'Long Jump': 6, 'Shot Put': 12, 'Discus': 60,
    };

    function markerName(entry) {
        if (entry.is_relay) return 'Relay';
        let name = String(entry.name || '').trim();
        if (!name) return 'Athlete';
        // Stored names are often ALL CAPS; show them in title case.
        if (name === name.toUpperCase()) name = name.toLowerCase().replace(/(^|[\s'-])\S/g, c => c.toUpperCase());
        // The payload normally uses "First Last"; support "Last, First" too.
        if (name.includes(',')) return name.split(',')[0].trim();
        // Skip generational suffixes so "Greg Tompkins III" labels as "Tompkins".
        const words = name.split(/\s+/);
        while (words.length > 1 && /^(jr\.?|sr\.?|ii|iii|iv)$/i.test(words[words.length - 1])) words.pop();
        return words.pop();
    }

    function renderChart(index, panel) {
        const event = events[index];
        const container = panel.querySelector('[data-distribution]');
        if (!event || !container || !window.SchoolDistribution) return;
        const width = container.clientWidth;
        // Redraw only when the available width has really changed.
        if (renderedWidth.has(index) && Math.abs(renderedWidth.get(index) - width) < 24) return;
        // The server sends only the statewide values the chart needs (see chart_events).
        const values = Array.isArray(event.values) ? event.values : [];
        const entries = Array.isArray(event.entries) ? event.entries : [];
        // One threshold cannot faithfully represent multiple meet-specific cuts.
        const cutoff = value => Array.isArray(value) && value.length === 1 ? value[0] : null;
        window.SchoolDistribution.render(container, {
            event: event.name,
            width,
            values,
            markers: entries.map(entry => ({ value: entry.value, mark: entry.mark, name: markerName(entry), fullName: entry.name, year: entry.year })),
            lowerIsBetter: event.lower_is_better,
            unit: event.unit,
            binSize: binSizes[event.name],
            countLabel: /relay/i.test(event.name || '') ? 'relay teams' : 'athletes',
            regionalCutoff: cutoff(event.regional_cutoff),
            stateCutoff: cutoff(event.state_cutoff),
        });
        if ((Array.isArray(event.regional_cutoff) && event.regional_cutoff.length > 1) ||
            (Array.isArray(event.state_cutoff) && event.state_cutoff.length > 1)) {
            const note = document.createElement('p');
            note.className = 'mt-2 text-xs text-base-content/60';
            note.textContent = 'Cuts differed between meets this season, so they are not drawn on this chart.';
            container.appendChild(note);
        }
        renderedWidth.set(index, width);
    }

    function selectEvent(index) {
        activeIndex = index;
        buttons.forEach(button => {
            const active = Number(button.dataset.eventIndex) === index;
            button.setAttribute('aria-pressed', String(active));
            button.classList.toggle('btn-primary', active);
            button.classList.toggle('btn-ghost', !active);
            button.classList.toggle('border-base-300', !active);
            button.classList.toggle('bg-white', !active);
            // Events without our entries stay readable when chosen, muted otherwise.
            if (button.hasAttribute('data-empty')) button.classList.toggle('text-base-content/55', !active);
        });
        panels.forEach(panel => {
            const active = Number(panel.dataset.eventPanel) === index;
            panel.hidden = !active;
            if (active) renderChart(index, panel);
        });
    }
    buttons.forEach(button => button.addEventListener('click', () => selectEvent(Number(button.dataset.eventIndex))));
    const initial = buttons.find(button => button.getAttribute('aria-pressed') === 'true');
    if (initial) selectEvent(Number(initial.dataset.eventIndex));

    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            drawStanding();
            const panel = panels.find(p => Number(p.dataset.eventPanel) === activeIndex);
            if (panel) renderChart(activeIndex, panel);
        }, 150);
    });
}());
