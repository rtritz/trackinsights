/**
 * ============================================================
 *  TrackInsights – Interactive Onboarding / Tutorial Engine
 * ============================================================
 *
 * A modern, action-driven walkthrough inspired by best practices from
 * Notion, Figma, Slack, and Trello onboarding patterns.
 *
 * Key design principles (from interactive walkthrough research):
 *  • Action-driven: spotlight steps let users click the real element
 *  • Benefit-focused copy: short, warm, tells users WHY not just WHAT
 *  • Progressive disclosure: one concept per step, no overload
 *  • Celebratory finish: confetti burst rewards tour completion
 *  • Always skippable: respect user autonomy
 *  • Lightbulb FAB: instant replay from any page
 *
 * On subpages, page-specific mini-tours highlight key UI elements.
 */

(function () {
  'use strict';

  /* ─── Constants ─── */
  const STORAGE_KEY     = 'ti_onboarding_completed';
  const STORAGE_SKIP    = 'ti_onboarding_skipped';
  const CROSS_PAGE_KEY  = 'ti_main_tour_resume';
  const GAP             = 14;
  const SPOT_PAD        = 8;
  const REPOSITION_MS   = 80;

  /* ─── Utility helpers ─── */
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  };
  const removeEl = (el) => el && el.parentNode && el.parentNode.removeChild(el);

  /**
   * Compute the best placement for the tooltip relative to the target rect.
   */
  function computePlacement(targetRect, tooltipW, tooltipH, preferred) {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const placements = preferred
      ? [preferred, 'bottom', 'top', 'right', 'left']
      : ['bottom', 'top', 'right', 'left'];

    for (const p of placements) {
      let top, left;
      switch (p) {
        case 'bottom':
          top  = targetRect.bottom + GAP;
          left = Math.max(8, Math.min(targetRect.left + targetRect.width / 2 - tooltipW / 2, vw - tooltipW - 8));
          if (top + tooltipH <= vh - 12)
            return { placement: p, top, left };
          break;
        case 'top':
          top  = targetRect.top - tooltipH - GAP;
          left = Math.max(8, Math.min(targetRect.left + targetRect.width / 2 - tooltipW / 2, vw - tooltipW - 8));
          if (top >= 8)
            return { placement: p, top, left };
          break;
        case 'right':
          top  = targetRect.top + targetRect.height / 2 - tooltipH / 2;
          left = targetRect.right + GAP;
          if (left + tooltipW <= vw - 8 && top >= 8 && top + tooltipH <= vh - 8)
            return { placement: p, top, left };
          break;
        case 'left':
          top  = targetRect.top + targetRect.height / 2 - tooltipH / 2;
          left = targetRect.left - tooltipW - GAP;
          if (left >= 8 && top >= 8 && top + tooltipH <= vh - 8)
            return { placement: p, top, left };
          break;
      }
    }
    const top  = Math.min(targetRect.bottom + GAP, vh - tooltipH - 12);
    const left = Math.max(8, Math.min(
      targetRect.left + targetRect.width / 2 - tooltipW / 2, vw - tooltipW - 8
    ));
    return { placement: 'bottom', top, left };
  }

  /* ─── Mini confetti burst for celebration ─── */
  function launchConfetti() {
    const count = 60;
    const container = document.createElement('div');
    container.style.cssText =
      'position:fixed;inset:0;z-index:10010;pointer-events:none;overflow:hidden';
    document.body.appendChild(container);

    const colors = ['#8c0327', '#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#f97316'];
    for (let i = 0; i < count; i++) {
      const piece = document.createElement('div');
      const color = colors[Math.floor(Math.random() * colors.length)];
      const x = 50 + (Math.random() - 0.5) * 60;
      const rotation = Math.random() * 360;
      const delay = Math.random() * 0.3;
      const size = 6 + Math.random() * 6;
      const shape = Math.random() > 0.5 ? '50%' : '2px';

      piece.style.cssText = `
        position:absolute;
        left:${x}%;top:40%;
        width:${size}px;height:${size * (Math.random() > 0.5 ? 1 : 1.6)}px;
        background:${color};
        border-radius:${shape};
        opacity:1;
        transform:rotate(${rotation}deg);
        animation:confetti-fall ${1.2 + Math.random() * 1}s cubic-bezier(.25,.46,.45,.94) ${delay}s forwards;
      `;
      container.appendChild(piece);
    }
    setTimeout(() => removeEl(container), 3000);
  }

  /* ─── Page icons (SVG strings) ─── */
  const ICONS = {
    wave: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
    search: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
    athlete: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
    school: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
    queries: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="15" x2="8" y2="9"/><line x1="12" y1="15" x2="12" y2="7"/><line x1="16" y1="15" x2="16" y2="11"/></svg>`,
    percentile: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>`,
    trends: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
    hypothetical: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    about: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
    check: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
    party: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5.8 11.3 2 22l10.7-3.79"/><path d="M4 3h.01"/><path d="M22 8h.01"/><path d="M15 2h.01"/><path d="M22 20h.01"/><path d="m22 2-2.24.75a2.9 2.9 0 0 0-1.96 3.12v0c.1.86-.57 1.63-1.45 1.63h-.38c-.86 0-1.6.6-1.76 1.44L14 10"/><path d="m22 13-.82-.33c-.86-.34-1.82.2-1.98 1.11v0c-.11.7-.72 1.22-1.43 1.22H17"/><path d="m11 2 .33.82c.34.86-.2 1.82-1.11 1.98v0C9.52 4.9 9 5.52 9 6.23V7"/></svg>`,
    result: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
  };

  /* ═══════════════════════════════════════════════════════════
     HOME PAGE STEPS — 10 action-driven steps
     Each step focuses on ONE capability with benefit-first copy.
     Spotlight steps use `driven: true` so clicking the real
     element also advances the tour (learn by doing).
     ═══════════════════════════════════════════════════════════ */
  const HOME_STEPS = [
    {
      type: 'info',
      icon: 'wave',
      title: 'Welcome to Track Insights!',
      body: 'Indiana high school track & field \u2014 23,000 athletes, 62,500 results, zero guesswork. Let\u2019s walk through each page.',
    },
    {
      selector: '#nav-search-pill',
      title: 'Search',
      body: 'Find any athlete or school instantly. Click the search bar to exit the tour and start searching \u2014 or press Next to continue.',
      cta: 'Next',
      driven: true,
      exitsOnClick: true,
      placement: 'bottom',
      mobileSelector: 'a[aria-label="Go to search"]',
      mobileBody: 'Tap here to search for any athlete or school.',
    },
    {
      selector: '#queries-toggle',
      title: 'Queries',
      body: 'Your data playground \u2014 percentile rankings, sectional trends over time, and a hypothetical tool to test any performance against the state. Click to visit!',
      cta: 'Visit Queries \u2192',
      driven: true,
      navigates: true,
      placement: 'bottom',
      mobileSelector: '#mobile-nav-toggle',
      mobileBody: 'Open the menu to find Queries.',
    },
    {
      selector: '#about-toggle',
      title: 'About',
      body: 'Meet the developers and learn how Track Insights was built.',
      cta: 'Visit About \u2192',
      driven: true,
      navigates: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#tutorial-lightbulb',
      title: 'Page-Specific Tours',
      body: 'This lightbulb appears on every page. Tap it anytime for a guided walkthrough of whatever page you\u2019re on \u2014 athlete dashboards, school pages, queries, and more.',
      cta: 'Got it',
      placement: 'top',
    },
    {
      type: 'info',
      icon: 'party',
      title: "You're all set!",
      body: 'Start by searching for an athlete or school. Remember \u2014 the lightbulb gives you a tour on every page.',
      isFinal: true,
    },
  ];

  /* ─── ATHLETE DASHBOARD steps ─── */
  const ATHLETE_DASHBOARD_STEPS = [
    {
      type: 'info',
      icon: 'athlete',
      title: 'Athlete Dashboard',
      body: "Here's everything about this athlete. Let's look at the key sections.",
    },
    {
      selector: '#state-rankings-container',
      title: 'State Rankings',
      body: 'These circles show their best state rank per event. Hover or tap for details.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#playoff-history-container',
      title: 'Playoff History',
      body: 'Every result by year and event. Click any row to see how it ranks statewide.',
      placement: 'top',
      optional: true,
    },
    {
      selector: '#copy-dashboard-link',
      title: 'Share',
      body: 'Copy a direct link — great for coaches, teammates, or parents.',
      placement: 'left',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Nice!',
      body: 'Click any result to see full rankings, or search for another athlete.',
      isFinal: true,
    },
  ];

  /* ─── ATHLETE RESULT DETAIL steps ─── */
  const RESULT_DETAIL_STEPS = [
    {
      type: 'info',
      icon: 'result',
      title: 'Result Detail',
      body: 'See exactly how this performance stacks up against all competition.',
    },
    {
      selector: '#where-rank-card',
      title: 'Sectional Projections',
      body: 'How would this result place in every sectional? Expand to find out.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#rankings-container',
      title: 'Ranking Breakdowns',
      body: 'Overall, similar-enrollment, and grade-level rankings with full leaderboards.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Got it!',
      body: 'Use the back button to return, or try the Hypothetical tool with your own time.',
      isFinal: true,
    },
  ];

  /* ─── SCHOOL DASHBOARD steps ─── */
  const SCHOOL_DASHBOARD_STEPS = [
    {
      type: 'info',
      icon: 'school',
      title: 'School Dashboard',
      body: "The full story of this school's track program. Let's explore.",
    },
    {
      selector: '#global-gender-toggle',
      title: 'Boys / Girls',
      body: 'Switch divisions — everything on the page updates.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#team-stats-container',
      title: 'Team Stats',
      body: 'Year-by-year points and placement history.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#school-percentiles-container',
      title: 'Best Marks',
      body: "Percentile bars show how the school's top marks compare statewide.",
      placement: 'top',
      optional: true,
    },
    {
      selector: '#roster-container',
      title: 'Roster',
      body: 'Search by name, then click any athlete to jump to their dashboard.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Nice!',
      body: 'Explore the roster and click any athlete to dig deeper.',
      isFinal: true,
    },
  ];

  /* ─── QUERIES PAGE steps ─── */
  const QUERIES_INDEX_STEPS = [
    {
      type: 'info',
      icon: 'queries',
      title: 'Queries Hub',
      body: 'Your launchpad for data tools. Each card opens a different analysis.',
    },
    {
      type: 'info',
      icon: 'percentile',
      title: 'Percentiles',
      body: 'Compare performances across events, meet types, grades, and seasons.',
    },
    {
      type: 'info',
      icon: 'trends',
      title: 'Sectional Trends',
      body: 'See whether events are getting more competitive year-over-year.',
    },
    {
      type: 'info',
      icon: 'hypothetical',
      title: 'Hypothetical Athlete',
      body: 'Plug in any time or distance and get a full ranking breakdown.',
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Jump in!',
      body: 'Click any card to get started.',
      isFinal: true,
    },
  ];

  /* ─── PERCENTILES PAGE steps ─── */
  const PERCENTILES_STEPS = [
    {
      type: 'info',
      icon: 'percentile',
      title: 'Percentiles',
      body: 'See how performances distribute across the state.',
    },
    {
      selector: '#event-chip-group',
      title: 'Pick an Event',
      body: 'Tap a chip to load percentile data for that event.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#meet-chip-group',
      title: 'Filter by Meet',
      body: 'Sectional, Regional, or State — or "All" for everything.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#percentile-slider',
      title: 'Granularity',
      body: 'Drag for finer or coarser breakdowns — from every 1% to every 50%.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Give it a try!',
      body: 'Select an event to see the data. Copy the URL to share your exact filters.',
      isFinal: true,
    },
  ];

  /* ─── SECTIONAL TRENDS PAGE steps ─── */
  const SECTIONAL_TRENDS_STEPS = [
    {
      type: 'info',
      icon: 'trends',
      title: 'Sectional Trends',
      body: 'How have events changed over time?',
    },
    {
      selector: '#gender-chip-group',
      title: 'Gender',
      body: 'Select Boys or Girls.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#event-chip-group',
      title: 'Event',
      body: 'Pick the event — chart and table update instantly.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#trends-chart',
      title: 'Chart',
      body: 'Median and cutoff lines over time. Toggle datasets with the legend.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Explore!',
      body: 'Scroll down for the full data table with year-over-year % changes.',
      isFinal: true,
    },
  ];

  /* ─── HYPOTHETICAL PAGE steps ─── */
  const HYPOTHETICAL_STEPS = [
    {
      type: 'info',
      icon: 'hypothetical',
      title: 'Hypothetical Athlete',
      body: 'Enter your own performance and see how it stacks up.',
    },
    {
      selector: '#gender-group',
      title: 'Gender',
      body: 'Pick Boys or Girls to filter events.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#event-group',
      title: 'Event',
      body: 'Choose the event to test your time or distance.',
      driven: true,
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#performance-input',
      title: 'Your Performance',
      body: 'Type a time (e.g. 11.52) or distance (e.g. 45-06.25).',
      driven: true,
      placement: 'top',
      optional: true,
    },
    {
      selector: '#submit-btn',
      title: 'See Rankings',
      body: 'Hit submit for overall, enrollment, and grade-level rankings plus sectional projections.',
      driven: true,
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Go for it!',
      body: 'Fill in the form to see a full ranking breakdown.',
      isFinal: true,
    },
  ];

  /* ─── Page detection ─── */
  function getPageSteps() {
    const path = window.location.pathname;

    if ($('#hero-tour-trigger'))
      return { page: 'home', steps: HOME_STEPS };
    if (path.match(/\/athlete-dashboard\/\d+\/result\//))
      return { page: 'result-detail', steps: RESULT_DETAIL_STEPS };
    if (path.match(/\/athlete-dashboard\/\d+/))
      return { page: 'athlete-dashboard', steps: ATHLETE_DASHBOARD_STEPS };
    if (path.match(/\/school-dashboard\/\d+/))
      return { page: 'school-dashboard', steps: SCHOOL_DASHBOARD_STEPS };
    if (path === '/queries/percentiles')
      return { page: 'percentiles', steps: PERCENTILES_STEPS };
    if (path === '/queries/sectional-trends')
      return { page: 'sectional-trends', steps: SECTIONAL_TRENDS_STEPS };
    if (path.startsWith('/queries/hypothetical'))
      return {
        page: 'hypothetical',
        steps: path.includes('/result') ? RESULT_DETAIL_STEPS : HYPOTHETICAL_STEPS,
      };
    if (path === '/queries')
      return { page: 'queries', steps: QUERIES_INDEX_STEPS };

    return null;
  }

  /* ═══════════════════════════════════════════════════════════
     OnboardingEngine — drives the walkthrough
     ═══════════════════════════════════════════════════════════ */
  class OnboardingEngine {
    constructor({ steps, page = 'home' } = {}) {
      this.steps       = steps;
      this.page        = page;
      this.currentStep = 0;
      this.isActive    = false;
      this._resizeTimer    = null;
      this._drivenCleanup  = null;

      // DOM refs
      this._shield    = null;
      this._spotlight = null;
      this._tooltip   = null;
      this._overlay   = null;

      // Bound handlers
      this._onResize      = this._handleResize.bind(this);
      this._onKeyDown     = this._handleKeyDown.bind(this);
      this._onShieldClick = this._handleShieldClick.bind(this);
    }

    /* ── Public API ── */

    start(fromStep = 0) {
      if (this.isActive) return;
      this.isActive    = true;
      this.currentStep = fromStep;
      this._createDOM();
      this._bindEvents();
      this._showStep(fromStep);
    }

    restart() {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_SKIP);
      this.teardown();
      this.start();
    }

    teardown() {
      this.isActive = false;
      this._cleanupDriven();
      this._unbindEvents();
      removeEl(this._overlay);
      removeEl(this._shield);
      removeEl(this._spotlight);
      removeEl(this._tooltip);
      const wc = $('.onboarding-welcome');
      removeEl(wc);
      this._overlay = this._shield = this._spotlight = this._tooltip = null;
    }

    /* ── Persistence ── */

    _isCompleted() {
      try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch { return false; }
    }
    _isSkipped() {
      try { return localStorage.getItem(STORAGE_SKIP) === '1'; } catch { return false; }
    }
    _markCompleted() {
      try { localStorage.setItem(STORAGE_KEY, '1'); } catch {}
    }
    _markSkipped() {
      try { localStorage.setItem(STORAGE_SKIP, '1'); } catch {}
    }

    /* ── DOM creation ── */

    _createDOM() {
      this._overlay = document.createElement('div');
      this._overlay.className = 'onboarding-overlay';
      this._overlay.setAttribute('aria-hidden', 'true');
      document.body.appendChild(this._overlay);

      this._shield = document.createElement('div');
      this._shield.className = 'onboarding-shield';
      document.body.appendChild(this._shield);

      this._spotlight = document.createElement('div');
      this._spotlight.className = 'onboarding-spotlight';
      this._spotlight.setAttribute('aria-hidden', 'true');
      document.body.appendChild(this._spotlight);

      this._tooltip = document.createElement('div');
      this._tooltip.className = 'onboarding-tooltip';
      this._tooltip.setAttribute('role', 'dialog');
      this._tooltip.setAttribute('aria-modal', 'true');
      this._tooltip.setAttribute('aria-label', 'Onboarding step');
      document.body.appendChild(this._tooltip);

      requestAnimationFrame(() => {
        this._overlay.classList.add('active');
      });
    }

    /* ── Events ── */

    _bindEvents() {
      window.addEventListener('resize', this._onResize);
      window.addEventListener('orientationchange', this._onResize);
      document.addEventListener('keydown', this._onKeyDown);
      if (this._shield) this._shield.addEventListener('click', this._onShieldClick);
    }

    _unbindEvents() {
      window.removeEventListener('resize', this._onResize);
      window.removeEventListener('orientationchange', this._onResize);
      document.removeEventListener('keydown', this._onKeyDown);
      if (this._shield)
        this._shield.removeEventListener('click', this._onShieldClick);
    }

    _handleResize() {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => {
        if (this.isActive) this._positionCurrent();
      }, REPOSITION_MS);
    }

    _handleKeyDown(e) {
      if (!this.isActive) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        this._skip();
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault();
        this._next();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        this._back();
      } else if (e.key === 'Tab') {
        this._trapFocus(e);
      }
    }

    _handleShieldClick() {
      // Block page interaction while tour is active
    }

    _trapFocus(e) {
      const container = this._tooltip || $('.onboarding-welcome__card');
      if (!container) return;
      const focusable = container.querySelectorAll(
        'button, [href], input, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last  = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }

    /* ── Driven action support ── */

    _cleanupDriven() {
      if (this._drivenCleanup) {
        this._drivenCleanup();
        this._drivenCleanup = null;
      }
    }

    /**
     * Make the spotlight target clickable. Clicking it advances the tour
     * (the "learn by doing" pattern from Trello/Figma onboarding).
     */
    _attachDrivenAction(target, step) {
      this._cleanupDriven();

      const self = this;
      const handler = (e) => {
        e.stopPropagation();
        if (catcher.parentNode) catcher.parentNode.removeChild(catcher);

        if (step && step.exitsOnClick) {
          // Exit the tour entirely and let the user interact
          self.teardown();
          target.click();
        } else if (step && step.navigates) {
          // Save tour position so we can resume after navigation
          try {
            sessionStorage.setItem(CROSS_PAGE_KEY, JSON.stringify({
              nextStep: self.currentStep + 1
            }));
          } catch {}
          // Tear down the tour, then let the link navigate
          self.teardown();
          target.click();
        } else {
          // Regular driven action: click then advance
          target.click();
          setTimeout(() => self._next(), 350);
        }
      };

      // Transparent click-catcher positioned over the spotlight
      const catcher = document.createElement('div');
      catcher.className = 'onboarding-driven-catcher';
      const rect = target.getBoundingClientRect();
      catcher.style.cssText = `
        position:fixed;z-index:10002;cursor:pointer;
        top:${rect.top - SPOT_PAD}px;left:${rect.left - SPOT_PAD}px;
        width:${rect.width + SPOT_PAD * 2}px;height:${rect.height + SPOT_PAD * 2}px;
        border-radius:${window.getComputedStyle(target).borderRadius || '12px'};
      `;
      catcher.addEventListener('click', handler);
      document.body.appendChild(catcher);

      this._drivenCleanup = () => {
        catcher.removeEventListener('click', handler);
        removeEl(catcher);
      };
    }

    /* ── Navigation ── */

    _next() {
      this._cleanupDriven();
      if (this.currentStep < this.steps.length - 1) {
        this._showStep(this.currentStep + 1);
      } else {
        this._complete();
      }
    }

    _back() {
      this._cleanupDriven();
      if (this.currentStep > 0) {
        this._showStep(this.currentStep - 1);
      }
    }

    _skip() {
      this._markSkipped();
      this.teardown();
    }

    _complete() {
      const step = this.steps[this.steps.length - 1];
      this._markCompleted();
      if (step && step.isFinal) {
        launchConfetti();
        // Keep overlay visible so confetti shows against dark backdrop
        setTimeout(() => this.teardown(), 2500);
      } else {
        this.teardown();
      }
    }

    /* ── Step rendering ── */

    _showStep(index) {
      this.currentStep = index;
      const step = this.steps[index];

      const oldWelcome = $('.onboarding-welcome');
      removeEl(oldWelcome);

      if (step.type === 'info' || step.type === 'welcome') {
        this._showInfoStep(step, index);
        if (this._spotlight) this._spotlight.style.display = 'none';
        if (this._tooltip) this._tooltip.classList.remove('visible');
      } else {
        // Spotlight step — skip if element missing and step is optional
        if (step.optional) {
          const isMobile = window.matchMedia('(max-width: 767px)').matches;
          const selector = (isMobile && step.mobileSelector)
            ? step.mobileSelector
            : step.selector;
          const target = document.querySelector(selector);
          if (!target) {
            if (index < this.steps.length - 1) {
              this._showStep(index + 1);
            } else {
              this._complete();
            }
            return;
          }
        }
        this._showSpotlightStep(step, index);
        if (this._spotlight) this._spotlight.style.display = '';
      }
    }

    _showInfoStep(step, index) {
      const total   = this.steps.length;
      const isFinal = step.isFinal || false;
      const icon    = ICONS[step.icon] || ICONS.about;

      const wrapper = document.createElement('div');
      wrapper.className = 'onboarding-welcome';

      const card = document.createElement('div');
      card.className = 'onboarding-welcome__card';
      if (isFinal) card.classList.add('onboarding-welcome__card--final');
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-modal', 'true');
      card.setAttribute('aria-label', esc(step.title));

      // Build step dots
      let dotsHtml = '';
      for (let i = 0; i < total; i++) {
        const cls = i < index
          ? 'done'
          : i === index
            ? 'active'
            : '';
        dotsHtml += `<span class="onboarding-dots__dot ${
          cls ? 'onboarding-dots__dot--' + cls : ''
        }"></span>`;
      }

      card.innerHTML = `
        <div class="onboarding-welcome__accent"></div>
        <div class="onboarding-welcome__icon${
          isFinal ? ' onboarding-welcome__icon--final' : ''
        }" aria-hidden="true">${icon}</div>
        <h2 class="onboarding-welcome__title">${esc(step.title)}</h2>
        <p class="onboarding-welcome__body">${esc(step.body)}</p>
        <div class="onboarding-dots">${dotsHtml}</div>
        <div class="onboarding-welcome__counter">${index + 1} / ${total}</div>
        <div class="onboarding-welcome__actions">
          ${
            !isFinal
              ? `<button class="onboarding-nav__btn onboarding-nav__btn--ghost" data-action="skip">Skip tour</button>`
              : ''
          }
          ${
            index > 0
              ? `<button class="onboarding-nav__btn onboarding-nav__btn--ghost" data-action="back">Back</button>`
              : ''
          }
          <button class="onboarding-nav__btn onboarding-nav__btn--primary" data-action="next">
            ${isFinal ? "Let's go!" : 'Next \u2192'}
          </button>
        </div>
      `;

      card.querySelectorAll('[data-action]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const action = btn.getAttribute('data-action');
          if (action === 'next') this._next();
          if (action === 'back') this._back();
          if (action === 'skip') this._skip();
        });
      });

      wrapper.appendChild(card);
      document.body.appendChild(wrapper);

      requestAnimationFrame(() => {
        requestAnimationFrame(() => card.classList.add('visible'));
      });

      setTimeout(() => {
        const primaryBtn = card.querySelector('.onboarding-nav__btn--primary');
        if (primaryBtn) primaryBtn.focus();
      }, 400);
    }

    _showSpotlightStep(step, index) {
      const isMobile = window.matchMedia('(max-width: 767px)').matches;
      const selector = (isMobile && step.mobileSelector)
        ? step.mobileSelector
        : step.selector;
      const body = (isMobile && step.mobileBody) ? step.mobileBody : step.body;
      const target = document.querySelector(selector);

      if (!target) {
        console.warn(
          `[Onboarding] Selector "${selector}" not found, skipping step ${index}`
        );
        this._next();
        return;
      }

      const rect = target.getBoundingClientRect();
      if (rect.top < 0 || rect.bottom > window.innerHeight) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(
          () => this._renderSpotlightStep(target, step, body, index),
          400
        );
        return;
      }

      this._renderSpotlightStep(target, step, body, index);
    }

    _renderSpotlightStep(target, step, body, index) {
      const total = this.steps.length;

      this._positionSpotlight(target);

      this._tooltip.innerHTML = '';
      this._tooltip.classList.remove('visible');

      const arrow = document.createElement('div');
      arrow.className = 'onboarding-tooltip__arrow';
      this._tooltip.appendChild(arrow);

      // Step badge
      const badge = document.createElement('span');
      badge.className = 'onboarding-tooltip__step-badge';
      badge.textContent = `${index + 1} of ${total}`;
      this._tooltip.appendChild(badge);

      const titleEl = document.createElement('h3');
      titleEl.className = 'onboarding-tooltip__title';
      titleEl.textContent = step.title;
      this._tooltip.appendChild(titleEl);

      const bodyEl = document.createElement('p');
      bodyEl.className = 'onboarding-tooltip__body';
      bodyEl.textContent = body;
      this._tooltip.appendChild(bodyEl);

      // Driven action hint
      if (step.driven) {
        const hint = document.createElement('div');
        hint.className = 'onboarding-tooltip__driven-hint';
        hint.innerHTML = `<span class="onboarding-tooltip__driven-arrow">\u2191</span> or press Next`;
        this._tooltip.appendChild(hint);
      }

      const nav = document.createElement('div');
      nav.className = 'onboarding-nav';

      if (index > 0) {
        const backBtn = document.createElement('button');
        backBtn.className = 'onboarding-nav__btn onboarding-nav__btn--ghost';
        backBtn.textContent = 'Back';
        backBtn.addEventListener('click', () => this._back());
        nav.appendChild(backBtn);
      }

      const skipBtn = document.createElement('button');
      skipBtn.className = 'onboarding-nav__btn onboarding-nav__btn--ghost';
      skipBtn.textContent = 'Skip';
      skipBtn.addEventListener('click', () => this._skip());
      nav.appendChild(skipBtn);

      const spacer = document.createElement('div');
      spacer.className = 'onboarding-nav__spacer';
      nav.appendChild(spacer);

      const isLast = index === this.steps.length - 1;
      const nextBtn = document.createElement('button');
      nextBtn.className = 'onboarding-nav__btn onboarding-nav__btn--primary';
      nextBtn.textContent = step.cta || (isLast ? 'Finish' : 'Next');
      nextBtn.addEventListener('click', () => {
        if (step.navigates && target) {
          // CTA button on navigating steps should actually navigate
          this._cleanupDriven();
          try {
            sessionStorage.setItem(CROSS_PAGE_KEY, JSON.stringify({
              nextStep: this.currentStep + 1
            }));
          } catch {}
          this.teardown();
          target.click();
        } else {
          this._next();
        }
      });
      nav.appendChild(nextBtn);

      this._tooltip.appendChild(nav);
      this._tooltip.setAttribute(
        'aria-label',
        `Step ${index + 1}: ${step.title}`
      );

      this._positionTooltip(target, step.placement);

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          this._tooltip.classList.add('visible');
        });
      });

      // Attach driven action if applicable
      if (step.driven) {
        this._attachDrivenAction(target, step);
      }

      setTimeout(() => nextBtn.focus(), 380);
    }

    /* ── Positioning ── */

    _positionSpotlight(target) {
      const rect = target.getBoundingClientRect();
      this._spotlight.style.setProperty('--spot-x', `${rect.left - SPOT_PAD}px`);
      this._spotlight.style.setProperty('--spot-y', `${rect.top - SPOT_PAD}px`);
      this._spotlight.style.setProperty(
        '--spot-w',
        `${rect.width + SPOT_PAD * 2}px`
      );
      this._spotlight.style.setProperty(
        '--spot-h',
        `${rect.height + SPOT_PAD * 2}px`
      );
      const cs = window.getComputedStyle(target);
      this._spotlight.style.setProperty(
        '--spot-radius',
        cs.borderRadius || '12px'
      );
    }

    _positionTooltip(target, preferredPlacement) {
      const rect = target.getBoundingClientRect();
      const expandedRect = {
        top:    rect.top - SPOT_PAD,
        left:   rect.left - SPOT_PAD,
        right:  rect.right + SPOT_PAD,
        bottom: rect.bottom + SPOT_PAD,
        width:  rect.width + SPOT_PAD * 2,
        height: rect.height + SPOT_PAD * 2,
      };

      this._tooltip.style.visibility = 'hidden';
      this._tooltip.style.display    = 'block';
      this._tooltip.classList.add('visible');
      const tw = this._tooltip.offsetWidth;
      const th = this._tooltip.offsetHeight;
      this._tooltip.classList.remove('visible');
      this._tooltip.style.visibility = '';

      const { placement, top, left } = computePlacement(
        expandedRect,
        tw,
        th,
        preferredPlacement
      );
      this._tooltip.style.top  = `${top}px`;
      this._tooltip.style.left = `${left}px`;

      const arrowEl = this._tooltip.querySelector('.onboarding-tooltip__arrow');
      if (arrowEl) {
        arrowEl.className = 'onboarding-tooltip__arrow';
        const arrowDir = {
          bottom: 'top',
          top: 'bottom',
          left: 'right',
          right: 'left',
        }[placement];
        arrowEl.classList.add(`onboarding-tooltip__arrow--${arrowDir}`);
      }
    }

    _positionCurrent() {
      const step = this.steps[this.currentStep];
      if (!step || step.type) return;
      const isMobile = window.matchMedia('(max-width: 767px)').matches;
      const selector = (isMobile && step.mobileSelector)
        ? step.mobileSelector
        : step.selector;
      const target = document.querySelector(selector);
      if (!target) return;
      this._positionSpotlight(target);
      this._positionTooltip(target, step.placement);
    }
  }

  /* ═══════════════════════════════════════════════════════════
     Initialization
     ═══════════════════════════════════════════════════════════ */

  function startTour(steps, page, fromStep) {
    if (window.__tiOnboarding && window.__tiOnboarding.isActive) {
      window.__tiOnboarding.teardown();
    }
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_SKIP);
    const engine = new OnboardingEngine({ steps, page });
    window.__tiOnboarding = engine;
    engine.start(fromStep || 0);
  }

  /**
   * Cross-page resume: if we navigated away during the main tour,
   * show a banner on the destination page and resume when the user
   * returns to home.
   */
  function checkCrossPageResume() {
    try {
      const raw = sessionStorage.getItem(CROSS_PAGE_KEY);
      if (!raw) return false;
      const { nextStep } = JSON.parse(raw);
      const path = window.location.pathname;

      if (path === '/' || path === '') {
        // Back on home — resume the main tour
        sessionStorage.removeItem(CROSS_PAGE_KEY);
        startTour(HOME_STEPS, 'home', nextStep);
        return true;
      } else {
        // On a sub-page — show "Continue Main Tour" banner
        showCrossPageBanner();
        return true;
      }
    } catch {
      return false;
    }
  }

  function showCrossPageBanner() {
    // Remove any existing banner
    const old = $('.onboarding-cross-banner');
    if (old) removeEl(old);

    const banner = document.createElement('div');
    banner.className = 'onboarding-cross-banner';
    banner.innerHTML = `
      <div class="onboarding-cross-banner__inner">
        <span class="onboarding-cross-banner__text">
          \uD83D\uDCA1 Tap the <strong>lightbulb</strong> to tour this page
        </span>
        <a href="/" class="onboarding-nav__btn onboarding-nav__btn--primary onboarding-cross-banner__btn">
          Continue Main Tour \u2192
        </a>
        <button class="onboarding-cross-banner__close" aria-label="Dismiss">\u2715</button>
      </div>
    `;
    document.body.appendChild(banner);

    banner.querySelector('.onboarding-cross-banner__close').addEventListener('click', () => {
      sessionStorage.removeItem(CROSS_PAGE_KEY);
      removeEl(banner);
    });

    requestAnimationFrame(() => {
      requestAnimationFrame(() => banner.classList.add('visible'));
    });
  }

  function initOnboarding() {
    const pageConfig = getPageSteps();
    if (!pageConfig) return;

    if (pageConfig.page === 'home') {
      // Always wire the hero trigger for manual re-launch
      const trigger = $('#hero-tour-trigger');
      if (trigger) {
        const launch = () => startTour(HOME_STEPS, 'home');
        trigger.addEventListener('click', launch);
        trigger.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            launch();
          }
        });
      }

      // Auto-start on first visit (never completed or skipped)
      try {
        const done = localStorage.getItem(STORAGE_KEY) === '1';
        const skip = localStorage.getItem(STORAGE_SKIP) === '1';
        if (!done && !skip) {
          startTour(HOME_STEPS, 'home');
        }
      } catch {}
    }
  }

  function initLightbulb() {
    const lightbulb = $('#tutorial-lightbulb');
    if (!lightbulb) return;

    lightbulb.addEventListener('click', () => {
      const pageConfig = getPageSteps();
      if (!pageConfig) return;

      // Clear cross-page state if user manually starts a sub-tour
      sessionStorage.removeItem(CROSS_PAGE_KEY);

      if (pageConfig.page === 'home') {
        startTour(HOME_STEPS, 'home');
      } else {
        startTour(pageConfig.steps, pageConfig.page);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      const delay = document.getElementById('loading-overlay') ? 1600 : 200;
      setTimeout(() => {
        const resumed = checkCrossPageResume();
        if (!resumed) initOnboarding();
        initLightbulb();
      }, delay);
    });
  } else {
    const delay = document.getElementById('loading-overlay') ? 1600 : 200;
    setTimeout(() => {
      const resumed = checkCrossPageResume();
      if (!resumed) initOnboarding();
      initLightbulb();
    }, delay);
  }
})();
