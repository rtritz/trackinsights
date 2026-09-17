/* School Dashboard V4 -- tab switching, and nothing else.
 *
 * Every pane is already in the HTML, rendered from precomputed data, so this
 * file does no fetching, no rendering and no formatting. V3's script was 2,200
 * lines because the page arrived empty and JavaScript built it; here the page
 * arrives finished and the only thing left to do is decide which pane is
 * visible.
 *
 * Because the markup is complete before this runs, the page is readable with
 * JavaScript disabled or still loading -- the first pane is visible either way.
 */
(function () {
    'use strict';

    var root = document.getElementById('sd4');
    if (!root) { return; }

    var tabs = Array.prototype.slice.call(root.querySelectorAll('.tab'));
    var panes = Array.prototype.slice.call(root.querySelectorAll('.pane'));
    if (!tabs.length) { return; }

    function show(name) {
        panes.forEach(function (pane) {
            pane.classList.toggle('hidden', pane.getAttribute('data-pane') !== name);
        });
        tabs.forEach(function (tab) {
            tab.setAttribute('aria-selected',
                tab.getAttribute('data-tab') === name ? 'true' : 'false');
        });
        // The chosen tab rides in the URL fragment, so a reload or a shared link
        // lands on the same pane. History is replaced rather than pushed: tabs
        // are a view of one page, and stacking them would turn Back into a walk
        // through every tab the reader tried.
        try {
            history.replaceState(null, '', '#' + name);
        } catch (error) {
            /* A browser that refuses history still switches tabs. */
        }
    }

    root.querySelector('.tabs').addEventListener('click', function (event) {
        var tab = event.target.closest('.tab');
        if (tab) { show(tab.getAttribute('data-tab')); }
    });

    // Left/right move between tabs, which is what a tablist is expected to do.
    root.querySelector('.tabs').addEventListener('keydown', function (event) {
        var step = event.key === 'ArrowRight' ? 1 : (event.key === 'ArrowLeft' ? -1 : 0);
        if (!step) { return; }
        var current = tabs.findIndex(function (tab) {
            return tab.getAttribute('aria-selected') === 'true';
        });
        var next = tabs[(current + step + tabs.length) % tabs.length];
        if (next) {
            event.preventDefault();
            show(next.getAttribute('data-tab'));
            next.focus();
        }
    });

    var wanted = (window.location.hash || '').replace('#', '');
    if (wanted && tabs.some(function (t) { return t.getAttribute('data-tab') === wanted; })) {
        show(wanted);
    }
}());
