/* School Dashboard V4 -- tab switching, the qualifier view toggle, and the
 * ranked-list popup.
 *
 * Everything on the page itself is rendered server-side from one precomputed
 * payload, so this file does no formatting and no rendering of dashboard
 * content. The one thing it fetches is a ranked list, and only when a reader
 * opens one: those lists are shared by every school and larger than the page, so
 * they are stored once per gender/season rather than embedded in the payload.
 */
(function () {
    'use strict';

    var root = document.getElementById('sd4');
    if (!root) { return; }

    var script = document.currentScript ||
        document.querySelector('script[src*="school-dashboard-v4.js"]');
    var SCHOOL = Number((script && script.dataset.schoolId) || 0);
    var GENDER = (script && script.dataset.gender) || 'Boys';
    var SEASON = (script && script.dataset.season) || '';

    function esc(value) {
        var div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    // ------------------------------------------------------------------ tabs
    var tabs = Array.prototype.slice.call(root.querySelectorAll('.navtab'));
    var panes = Array.prototype.slice.call(root.querySelectorAll('.pane'));

    function showTab(name) {
        panes.forEach(function (pane) {
            pane.classList.toggle('hidden', pane.getAttribute('data-pane') !== name);
        });
        tabs.forEach(function (tab) {
            tab.setAttribute('aria-selected',
                tab.getAttribute('data-tab') === name ? 'true' : 'false');
        });
        // The chosen tab rides in the fragment so a reload or a shared link lands
        // on the same pane. Replaced, not pushed: tabs are one page's views, and
        // stacking them would turn Back into a walk through every tab tried.
        try { history.replaceState(null, '', '#' + name); } catch (error) { /* fine */ }
    }

    var tabStrip = root.querySelector('.navtabs');
    if (tabStrip) {
        tabStrip.addEventListener('click', function (event) {
            var tab = event.target.closest('.navtab');
            if (tab) { showTab(tab.getAttribute('data-tab')); }
        });
        tabStrip.addEventListener('keydown', function (event) {
            var step = event.key === 'ArrowRight' ? 1 : (event.key === 'ArrowLeft' ? -1 : 0);
            if (!step) { return; }
            var at = tabs.findIndex(function (t) {
                return t.getAttribute('aria-selected') === 'true';
            });
            var next = tabs[(at + step + tabs.length) % tabs.length];
            if (next) {
                event.preventDefault();
                showTab(next.getAttribute('data-tab'));
                next.focus();
            }
        });
    }

    // ------------------------------------------- qualifiers / closest misses
    var vtabs = root.querySelector('.vtabs');
    if (vtabs) {
        vtabs.addEventListener('click', function (event) {
            var button = event.target.closest('.vtab');
            if (!button) { return; }
            var wanted = button.getAttribute('data-view');
            root.querySelectorAll('.view').forEach(function (section) {
                section.classList.toggle('hidden', section.getAttribute('data-view') !== wanted);
            });
            root.querySelectorAll('.vtab').forEach(function (other) {
                other.setAttribute('aria-pressed',
                    other.getAttribute('data-view') === wanted ? 'true' : 'false');
            });
        });
    }

    // ------------------------------------------------------- ranked lists
    var modal = document.getElementById('sd4-modal');
    var title = document.getElementById('sd4-modal-title');
    var subtitle = document.getElementById('sd4-modal-sub');
    var body = document.getElementById('sd4-modal-body');
    var jump = document.getElementById('sd4-jump');
    var topButton = document.getElementById('sd4-top');
    var bottomButton = document.getElementById('sd4-bottom');
    var enrollSelect = document.getElementById('sd4-enroll');
    var enrollInput = document.getElementById('sd4-enroll-max');
    // The list on screen, so changing the filter re-renders without refetching.
    var current = null;
    // Which of our entries the next jump lands on, and the one the reader came
    // from -- clicking a rank in the results table means "show me this athlete",
    // not "show me whichever of ours ranks highest".
    var jumpAt = 0;
    var originAthlete = null;
    var lastFocused = null;
    // Keyed by event so reopening a list costs nothing.
    var cache = {};

    function schoolLink(id, label) {
        return id
            ? '<a class="link" href="/school-dashboard/' + id + '">' + esc(label) + '</a>'
            : esc(label);
    }

    // The enrollment ceiling currently in force, or null for no filter.
    function enrollmentLimit() {
        if (!enrollSelect) { return null; }
        if (enrollSelect.value === 'custom') {
            var typed = parseInt(enrollInput && enrollInput.value, 10);
            return typed > 0 ? typed : null;
        }
        var preset = parseInt(enrollSelect.value, 10);
        return preset > 0 ? preset : null;
    }

    function renderList(payload) {
        var isProgram = payload.kind === 'program';
        var limit = enrollmentLimit();
        // A school with no enrollment on file is left out of a filtered view
        // rather than treated as zero -- "under 500" should not quietly mean
        // "under 500, plus everyone we have no figure for".
        var rows = limit === null
            ? payload.rows
            : payload.rows.filter(function (row) {
                return typeof row.enrollment === 'number' && row.enrollment <= limit;
            });

        // Filtering renumbers the list, but the statewide rank stays beside it:
        // a reader wants "4th in this band" without losing "160th in the state".
        var columns = payload.columns.slice();
        if (limit !== null) { columns.splice(1, 0, 'In filter'); }

        var head = '<thead><tr>' + columns.map(function (c) {
            return '<th>' + esc(c) + '</th>';
        }).join('') + '</tr></thead>';

        var lines = rows.map(function (row, index) {
            var mine = row.school_id === SCHOOL;
            var name = isProgram
                ? schoolLink(row.school_id, row.name)
                : (row.athlete_id
                    ? '<a class="link" href="/athlete-dashboard/' + row.athlete_id + '">' +
                      esc(row.name) + '</a>'
                    : esc(row.name));
            var enrolled = typeof row.enrollment === 'number' ? row.enrollment : '\u2014';
            var cells = isProgram
                ? '<td>' + name + '</td><td>' + esc(row.value == null ? '\u2014' : row.value) +
                  '</td><td>' + esc(enrolled) + '</td>'
                : '<td>' + name + '</td><td>' + schoolLink(row.school_id, row.school) +
                  '</td><td>' + esc(row.mark == null ? '\u2014' : row.mark) + '</td><td>' +
                  esc(enrolled) + '</td>';
            var rankCell = '<td class="' + (limit === null ? '' : 'of') + '">' +
                esc(row.rank) + '</td>';
            var inFilter = limit === null ? '' : '<td>' + (index + 1) + '</td>';
            return '<tr class="' + (mine ? 'us' : '') + '"' + (mine ? ' data-us' : '') +
                (row.athlete_id ? ' data-athlete="' + row.athlete_id + '"' : '') + '>' +
                rankCell + inFilter + cells + '</tr>';
        }).join('');

        body.innerHTML = rows.length
            ? '<table>' + head + '<tbody>' + lines + '</tbody></table>'
            : '<div class="rankbox-note">No schools match that enrollment limit.</div>';
        // A filter can remove the reader's own school, so the jump is offered
        // only when there is somewhere to jump to.
        var ours = body.querySelectorAll('[data-us]');
        if (jump) {
            jump.hidden = !ours.length;
            // Most schools have more than one entry in an event -- 292 of 375 in
            // the 100m -- so the jump cycles rather than always landing on the
            // same row, and says how many there are to cycle through.
            if (ours.length > 1) {
                jump.setAttribute('data-many', '');
                jump.title = 'Jump through our ' + ours.length + ' entries';
                jump.setAttribute('aria-label', jump.title);
            } else {
                jump.removeAttribute('data-many');
                jump.title = 'Jump to our entry';
                jump.setAttribute('aria-label', jump.title);
            }
            var badge = jump.querySelector('.count');
            if (ours.length > 1) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'count';
                    jump.appendChild(badge);
                }
                badge.textContent = ours.length;
            } else if (badge) {
                badge.remove();
            }
        }
        // Start on the entry whose rank was clicked, when there was one.
        jumpAt = 0;
        if (originAthlete) {
            for (var i = 0; i < ours.length; i++) {
                if (ours[i].getAttribute('data-athlete') === String(originAthlete)) {
                    jumpAt = i;
                    break;
                }
            }
        }
    }

    function openModal() {
        lastFocused = document.activeElement;
        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        var card = modal.querySelector('.rankbox-card');
        if (card) { card.focus(); }
    }

    function closeModal() {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
        if (lastFocused && lastFocused.focus) { lastFocused.focus(); }
    }

    function show(event, athleteId) {
        if (!modal) { return; }
        originAthlete = athleteId || null;
        openModal();
        title.textContent = event || 'Statewide Program Rankings';
        subtitle.textContent = 'Loading…';
        body.innerHTML = '';
        if (jump) { jump.hidden = true; }

        if (cache[event] !== undefined) {
            var hit = cache[event];
            current = hit;
            subtitle.textContent = hit.subtitle;
            title.textContent = hit.title;
            renderList(hit);
            return;
        }

        var url = '/api/v4/rankings/' + encodeURIComponent(GENDER) + '/' +
            encodeURIComponent(SEASON) + (event ? '?event=' + encodeURIComponent(event) : '');
        fetch(url)
            .then(function (response) {
                if (!response.ok) { throw new Error('Those rankings are not available.'); }
                return response.json();
            })
            .then(function (payload) {
                cache[event] = payload;
                current = payload;
                title.textContent = payload.title;
                subtitle.textContent = payload.subtitle;
                renderList(payload);
            })
            .catch(function (error) {
                subtitle.textContent = '';
                body.innerHTML = '<div class="note">' + esc(error.message) + '</div>';
            });
    }

    root.addEventListener('click', function (event) {
        var link = event.target.closest('.ranklink');
        if (link) {
            event.preventDefault();
            show(link.getAttribute('data-event') || '',
                 link.getAttribute('data-athlete') || null);
        }
    });

    if (modal) {
        modal.addEventListener('click', function (event) {
            // The backdrop closes it; a click inside the card must not.
            if (event.target === modal || event.target.closest('[data-close]')) {
                closeModal();
            }
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && !modal.hidden) { closeModal(); }
        });
    }

    function scrollToRow(row) {
        if (!row) { return; }
        // Clear the class from whichever row had it last. The animation ends
        // transparent so a stale one is invisible, but leaving it on means every
        // row ever jumped to still claims to be the current one.
        body.querySelectorAll('.flash').forEach(function (old) {
            old.classList.remove('flash');
        });
        row.scrollIntoView({ block: 'center', behavior: 'smooth' });
        void row.offsetWidth;               // restart the animation
        row.classList.add('flash');
    }

    if (jump) {
        jump.addEventListener('click', function () {
            var ours = body.querySelectorAll('[data-us]');
            if (!ours.length) { return; }
            if (jumpAt >= ours.length) { jumpAt = 0; }
            scrollToRow(ours[jumpAt]);
            jumpAt = (jumpAt + 1) % ours.length;
        });
    }
    if (topButton) {
        topButton.addEventListener('click', function () { body.scrollTop = 0; });
    }
    if (bottomButton) {
        bottomButton.addEventListener('click', function () {
            body.scrollTop = body.scrollHeight;
        });
    }

    // Changing the filter re-renders what is already loaded; nothing is refetched.
    if (enrollSelect) {
        enrollSelect.addEventListener('change', function () {
            var custom = enrollSelect.value === 'custom';
            if (enrollInput) {
                enrollInput.classList.toggle('hidden', !custom);
                if (custom) { enrollInput.focus(); }
            }
            if (current) { renderList(current); }
        });
    }
    if (enrollInput) {
        enrollInput.addEventListener('input', function () {
            if (current) { renderList(current); }
        });
    }

    // --------------------------------------------------------------- filters
    // Switching gender or season is a full page load, because each view is its
    // own URL. Flag it so the base template skips the Track Insights intro on
    // the way in -- the reader is changing a filter, not arriving at the site.
    root.addEventListener('click', function (event) {
        if (!event.target.closest('a[data-filter]')) { return; }
        try { sessionStorage.setItem('ti-skip-intro', '1'); } catch (error) { /* fine */ }
    });

    var wanted = (window.location.hash || '').replace('#', '');
    if (wanted && tabs.some(function (t) { return t.getAttribute('data-tab') === wanted; })) {
        showTab(wanted);
    }
}());
