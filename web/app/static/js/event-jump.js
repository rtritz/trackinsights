/* The "jump to event" chip strip.
 *
 * The sticky row of little buttons -- 100m, 200m, 4x400, SP -- that sits above
 * a long qualifier list and scrolls you to an event. The regional and state
 * qualifier pages both have one, and both had their own copy of this code.
 * They are the same strip, so it lives here once.
 *
 * This file does NOT own a page. It expects two elements to already exist:
 *
 *     <div id="event-jump-wrap">   the bar, hidden until there is something in it
 *       <div id="event-jump-bar">  the chips go in here
 *
 * and it is used from a page script like this:
 *
 *     const { initEventJump, resetEventJump } = window.EventJump;
 *     initEventJump(events);   // after you render the event sections
 *     resetEventJump();        // when you clear them
 *
 * Each event section you render must carry the id and data-chip-key that
 * initEventJump expects, or the chips will have nothing to scroll to:
 *
 *     id="event-${eventSlug(name)}-${index}"
 *     data-chip-key="${eventSlug(name)}-${index}"
 *
 * Load it with a <script> tag BEFORE the page's own script. Both use defer,
 * which runs them in document order.
 */

window.EventJump = (function () {
  'use strict';

  // Looked up lazily rather than at load time: this file is deferred, but so is
  // the page script, and reading the DOM only when asked keeps the two
  // independent of each other's ordering.
  const wrap = () => document.getElementById('event-jump-wrap');
  const bar = () => document.getElementById('event-jump-bar');

  let sectionObserver = null;

  function eventSlug(eventName) {
    return String(eventName || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  }

  /* "100 Meters" is too wide for a chip; "100m" is not. */
  function shortEventLabel(eventName) {
    const map = {
      '100 Meters': '100m',
      '200 Meters': '200m',
      '400 Meters': '400m',
      '800 Meters': '800m',
      '1600 Meters': '1600m',
      '3200 Meters': '3200m',
      '100 Hurdles': '100H',
      '110 Hurdles': '110H',
      '300 Hurdles': '300H',
      '4 x 100 Relay': '4x100',
      '4 x 400 Relay': '4x400',
      '4 x 800 Relay': '4x800',
      'High Jump': 'HJ',
      'Long Jump': 'LJ',
      'Pole Vault': 'PV',
      'Shot Put': 'SP',
      'Discus': 'Discus',
    };
    return map[eventName] || eventName;
  }

  /* How far above the target to stop, so the bar does not cover the heading. */
  function getEventScrollOffset() {
    const el = wrap();
    const barHeight = el && !el.classList.contains('hidden')
      ? el.getBoundingClientRect().height
      : 0;
    return 110 + barHeight;
  }

  function setActiveEventChip(chipKey) {
    const el = bar();
    if (!el) return;
    el.querySelectorAll('button[data-chip-key]').forEach((chip) => {
      const active = chip.dataset.chipKey === chipKey;
      chip.classList.toggle('bg-primary', active);
      chip.classList.toggle('text-primary-content', active);
      chip.classList.toggle('border-primary', active);
      chip.classList.toggle('shadow-md', active);
      chip.classList.toggle('bg-white', !active);
      chip.classList.toggle('text-base-content', !active);
      chip.classList.toggle('border-base-300', !active);
      chip.classList.toggle('hover:border-primary/50', !active);
    });
  }

  /* Empty the bar and hide it. Call this whenever you clear the results. */
  function resetEventJump() {
    if (sectionObserver) {
      sectionObserver.disconnect();
      sectionObserver = null;
    }
    const barEl = bar();
    if (barEl) barEl.innerHTML = '';
    const wrapEl = wrap();
    if (wrapEl) wrapEl.classList.add('hidden');
  }

  /* Build one chip per event, then keep the highlighted chip in step with what
   * is on screen -- an IntersectionObserver, not a scroll handler, so the
   * browser does the work.
   */
  function initEventJump(events) {
    resetEventJump();
    const wrapEl = wrap();
    const barEl = bar();
    if (!wrapEl || !barEl || !Array.isArray(events) || !events.length) {
      return;
    }

    const targets = [];
    events.forEach((eventBlock, index) => {
      const event = eventBlock.event;
      const chipKey = `${eventSlug(event)}-${index}`;
      const targetId = `event-${chipKey}`;
      targets.push({ targetId, chipKey });

      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'rounded-lg border px-3 py-2 text-xs sm:text-sm font-semibold bg-white text-base-content border-base-300 hover:border-primary hover:bg-primary/10 focus:bg-primary/20 focus:border-primary transition-colors cursor-pointer outline-none';
      chip.dataset.targetId = targetId;
      chip.dataset.chipKey = chipKey;
      chip.textContent = shortEventLabel(event);
      chip.addEventListener('click', () => {
        const target = document.getElementById(targetId);
        if (!target) return;
        const targetY = target.getBoundingClientRect().top + window.scrollY - getEventScrollOffset();
        window.scrollTo({ top: targetY, behavior: 'smooth' });
        setActiveEventChip(chipKey);
      });
      barEl.appendChild(chip);
    });

    wrapEl.classList.remove('hidden');
    setActiveEventChip(targets[0]?.chipKey || '');

    sectionObserver = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (visible.length) {
        setActiveEventChip(visible[0].target.dataset.chipKey || '');
      }
    }, {
      root: null,
      rootMargin: '-170px 0px -45% 0px',
      threshold: [0.2, 0.4, 0.6],
    });

    targets.forEach(({ targetId }) => {
      const el = document.getElementById(targetId);
      if (el) sectionObserver.observe(el);
    });
  }

  return { eventSlug, shortEventLabel, initEventJump, resetEventJump };
})();
