/**
 * ============================================================
 *  TrackInsights – Interactive Onboarding / Tutorial Engine
 * ============================================================
 *
 * Launched by clicking the hero "Track Insights" text on the home page.
 * Walks through all major features: navigation, search, athlete dashboards,
 * school dashboards, queries (percentiles, sectional trends, hypothetical),
 * and the about page.
 *
 * On subpages (athlete-dashboard, school-dashboard, queries/*), a page-
 * specific mini-tour highlights key UI elements on that page.
 *
 * Features:
 *  • Hero text = tour trigger with "click to get started" subtext
 *  • Step-by-step spotlight overlay with animated tooltips
 *  • Info cards for describing pages you can't see yet
 *  • Skip, Next, Back controls + keyboard nav
 *  • Completion state persisted in localStorage
 *  • Fully responsive & accessible
 */

(function () {
  'use strict';

  /* ─── Constants ─── */
  const STORAGE_KEY    = 'ti_onboarding_completed';
  const STORAGE_SKIP   = 'ti_onboarding_skipped';
  const GAP            = 14;
  const SPOT_PAD       = 8;
  const REPOSITION_MS  = 80;

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
    const placements = preferred ? [preferred, 'bottom', 'top', 'right', 'left'] : ['bottom', 'top', 'right', 'left'];

    for (const p of placements) {
      let top, left;
      switch (p) {
        case 'bottom':
          top  = targetRect.bottom + GAP;
          left = targetRect.left + targetRect.width / 2 - tooltipW / 2;
          if (top + tooltipH <= vh - 12 && left >= 8 && left + tooltipW <= vw - 8) return { placement: p, top, left };
          break;
        case 'top':
          top  = targetRect.top - tooltipH - GAP;
          left = targetRect.left + targetRect.width / 2 - tooltipW / 2;
          if (top >= 8 && left >= 8 && left + tooltipW <= vw - 8) return { placement: p, top, left };
          break;
        case 'right':
          top  = targetRect.top + targetRect.height / 2 - tooltipH / 2;
          left = targetRect.right + GAP;
          if (left + tooltipW <= vw - 8 && top >= 8 && top + tooltipH <= vh - 8) return { placement: p, top, left };
          break;
        case 'left':
          top  = targetRect.top + targetRect.height / 2 - tooltipH / 2;
          left = targetRect.left - tooltipW - GAP;
          if (left >= 8 && top >= 8 && top + tooltipH <= vh - 8) return { placement: p, top, left };
          break;
      }
    }
    const top  = Math.min(targetRect.bottom + GAP, vh - tooltipH - 12);
    const left = Math.max(8, Math.min(targetRect.left + targetRect.width / 2 - tooltipW / 2, vw - tooltipW - 8));
    return { placement: 'bottom', top, left };
  }

  /* ─── Page icons (SVG strings) ─── */
  const ICONS = {
    search: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    athlete: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    school: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    queries: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="15" x2="8" y2="9"/><line x1="12" y1="15" x2="12" y2="7"/><line x1="16" y1="15" x2="16" y2="11"/></svg>',
    percentile: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>',
    trends: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    hypothetical: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    about: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    check: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    result: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
  };

  /* ─── HOME PAGE steps ─── */
  const HOME_STEPS = [
    {
      type: 'info',
      icon: 'search',
      title: 'Welcome to Track Insights!',
      body: 'Let\'s take a quick tour of every feature. We\'ll walk through the navigation, athlete & school dashboards, data queries, and more.',
    },
    {
      selector: '#nav-search-pill',
      title: 'Search Athletes & Schools',
      body: 'Click to expand the search bar. Type any athlete\'s name or school to instantly find results and jump to their dashboard.',
      placement: 'bottom',
      mobileSelector: 'a[aria-label="Go to search"]',
      mobileBody: 'Tap here to go to the search page where you can look up any athlete or school.',
    },
    {
      selector: '#queries-toggle',
      title: 'Data Queries',
      body: 'Access powerful analytical tools — percentile rankings, sectional trends, and hypothetical performance analysis.',
      placement: 'bottom',
      mobileSelector: '#mobile-nav-toggle',
      mobileBody: 'Open the menu to navigate to Queries and explore analytical tools like percentiles, trends, and hypothetical rankings.',
    },
    {
      selector: '#about-toggle',
      title: 'About Track Insights',
      body: 'Meet the student-led team behind the app, read the inspiration story, and see project stats (23,000+ athletes, 62,500+ results).',
      placement: 'bottom',
    },
    // --- Info cards describing subpages ---
    {
      type: 'info',
      icon: 'athlete',
      title: 'Athlete Dashboard',
      body: 'After searching for an athlete, you\'ll see their full profile — name, school, graduation year, state rankings shown as interactive circles, achievement badges (medals for Sectional, Regional, State), and a complete playoff history table. Click any result to dive deeper.',
    },
    {
      type: 'info',
      icon: 'result',
      title: 'Athlete Result Detail',
      body: 'Clicking a specific result shows a detailed ranking breakdown: overall rank, rank among similar-enrollment schools, grade-level rank, plus collapsible leaderboards. A "Sectional Projections" panel shows how that performance would place across every sectional in the state.',
    },
    {
      type: 'info',
      icon: 'school',
      title: 'School Dashboard',
      body: 'View any school\'s profile with a Boys/Girls toggle, team stats by year, best marks with percentile bars for every event, and a full athlete roster you can filter by name. Click any athlete to jump to their dashboard.',
    },
    {
      type: 'info',
      icon: 'percentile',
      title: 'Percentiles Query',
      body: 'Select an event and filter by meet type, grade level, and season. Adjust granularity from 1% to 50% with a slider. See side-by-side Boys vs Girls percentile tables to understand performance distributions statewide.',
    },
    {
      type: 'info',
      icon: 'trends',
      title: 'Sectional Event Trends',
      body: 'Pick a gender and event to see an interactive chart and data table showing how median and cutoff marks have changed year-over-year. Discover whether events are getting faster/farther and how competitive they are.',
    },
    {
      type: 'info',
      icon: 'hypothetical',
      title: 'Hypothetical Athlete',
      body: 'Enter any performance (event + time or distance) and see how it would rank against real competition. Optionally filter by grade level and school enrollment. See overall, similar-enrollment, and grade-level rankings plus sectional projections.',
    },
    {
      type: 'info',
      icon: 'check',
      title: 'You\'re All Set!',
      body: 'That\'s the full tour! Click the hero text anytime to replay it. Now go search for an athlete and start exploring Indiana track & field data.',
      isFinal: true,
    },
  ];

  /* ─── ATHLETE DASHBOARD steps ─── */
  const ATHLETE_DASHBOARD_STEPS = [
    {
      type: 'info',
      icon: 'athlete',
      title: 'Athlete Dashboard',
      body: 'This page shows a complete profile for this athlete. Let\'s walk through the key sections.',
    },
    {
      selector: '#state-rankings-container',
      title: 'State Rankings',
      body: 'Interactive circles showing this athlete\'s best state rank in each event. Hover or tap for details.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#playoff-history-container',
      title: 'Playoff History',
      body: 'A complete table of every playoff result by year and event. Click any result to see detailed rankings and sectional projections.',
      placement: 'top',
      optional: true,
    },
    {
      selector: '#copy-dashboard-link',
      title: 'Share This Dashboard',
      body: 'Click to copy a direct link to this athlete\'s dashboard — great for sharing with coaches, teammates, or parents.',
      placement: 'left',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'That\'s the Athlete Dashboard!',
      body: 'Click any result in the playoff history to see how it ranks statewide. Or use the search to find another athlete.',
      isFinal: true,
    },
  ];

  /* ─── ATHLETE RESULT DETAIL steps ─── */
  const RESULT_DETAIL_STEPS = [
    {
      type: 'info',
      icon: 'result',
      title: 'Result Detail',
      body: 'This page shows exactly how one performance ranks against all competition. Let\'s explore the advanced analysis.',
    },
    {
      selector: '#where-rank-card',
      title: 'Sectional Projections',
      body: 'Expand this panel to see how this result would have placed in every sectional across the state. Shows projected rank, qualifying mark, and strength of field.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#rankings-container',
      title: 'Ranking Breakdowns',
      body: 'Three collapsible cards show Overall rank, Similar Enrollment rank, and Grade-Level rank, each with a full leaderboard you can expand.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'That\'s the Result Detail!',
      body: 'Use the back button to return to the athlete dashboard, or try the Hypothetical tool to test your own performance.',
      isFinal: true,
    },
  ];

  /* ─── SCHOOL DASHBOARD steps ─── */
  const SCHOOL_DASHBOARD_STEPS = [
    {
      type: 'info',
      icon: 'school',
      title: 'School Dashboard',
      body: 'Everything about this school\'s track & field program in one place. Let\'s take a look.',
    },
    {
      selector: '#global-gender-toggle',
      title: 'Boys / Girls Toggle',
      body: 'Switch between Boys and Girls data — this affects all sections on the page.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#team-stats-container',
      title: 'Team Stats',
      body: 'Year-by-year team points and placement data showing the program\'s competitive history.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#school-percentiles-container',
      title: 'Best Marks & Percentiles',
      body: 'The school\'s best mark in every event with a percentile bar showing how it compares statewide. Use the year filter to see trends.',
      placement: 'top',
      optional: true,
    },
    {
      selector: '#roster-container',
      title: 'Athlete Roster',
      body: 'All athletes grouped by graduation year. Use the search box above to filter, then click any name to view their full dashboard.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'That\'s the School Dashboard!',
      body: 'Toggle between Boys/Girls, explore the roster, and click any athlete to see their profile.',
      isFinal: true,
    },
  ];

  /* ─── QUERIES PAGE steps ─── */
  const QUERIES_INDEX_STEPS = [
    {
      type: 'info',
      icon: 'queries',
      title: 'Queries Hub',
      body: 'This is your launchpad for data exploration tools. Each card leads to a different analytical experience.',
    },
    {
      type: 'info',
      icon: 'percentile',
      title: 'Percentiles Query',
      body: 'Select an event and filter by meet type, grade, and season. Adjust granularity with a slider to see fine or coarse percentile breakdowns for Boys and Girls.',
    },
    {
      type: 'info',
      icon: 'trends',
      title: 'Sectional Event Trends',
      body: 'Interactive line charts showing how median and cutoff marks change year-over-year. See whether events are getting more competitive.',
    },
    {
      type: 'info',
      icon: 'hypothetical',
      title: 'Hypothetical Athlete',
      body: 'Enter any performance and instantly see how it would rank—overall, by enrollment, and by grade level—plus projections for all 32 sectionals.',
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Explore!',
      body: 'Click any card to get started. Each query page has its own filters and interactive results.',
      isFinal: true,
    },
  ];

  /* ─── PERCENTILES PAGE steps ─── */
  const PERCENTILES_STEPS = [
    {
      type: 'info',
      icon: 'percentile',
      title: 'Percentiles Query',
      body: 'Explore performance distributions across events, meet types, grade levels, and seasons.',
    },
    {
      selector: '#event-chip-group',
      title: 'Select an Event',
      body: 'Tap a chip to pick the track or field event you want to analyze. One event at a time.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#meet-chip-group',
      title: 'Filter by Meet Type',
      body: 'Choose Sectional, Regional, or State to see percentiles for that competition level. "All" includes everything.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#percentile-slider',
      title: 'Granularity Slider',
      body: 'Drag to control how fine the percentile breakdown is — from every 1% (detailed) to every 50% (just median).',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Try It!',
      body: 'Select an event to load percentile data. You can copy the query URL to share or bookmark your exact filters.',
      isFinal: true,
    },
  ];

  /* ─── SECTIONAL TRENDS PAGE steps ─── */
  const SECTIONAL_TRENDS_STEPS = [
    {
      type: 'info',
      icon: 'trends',
      title: 'Sectional Event Trends',
      body: 'Analyze how events are evolving over time with charts and data tables.',
    },
    {
      selector: '#gender-chip-group',
      title: 'Pick a Gender',
      body: 'Select Boys or Girls to see trend data for that division.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#event-chip-group',
      title: 'Pick an Event',
      body: 'Choose the event to analyze. The chart and table update immediately.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#trends-chart',
      title: 'Interactive Chart',
      body: 'A line chart showing Median and Cutoff marks over time. Use the legend checkboxes to toggle datasets on/off.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Explore the Data!',
      body: 'Scroll down for the full data table with % difference badges showing year-over-year changes.',
      isFinal: true,
    },
  ];

  /* ─── HYPOTHETICAL PAGE steps ─── */
  const HYPOTHETICAL_STEPS = [
    {
      type: 'info',
      icon: 'hypothetical',
      title: 'Hypothetical Athlete',
      body: 'Enter your own performance and see how it would rank against real playoff competition.',
    },
    {
      selector: '#gender-group',
      title: 'Select Gender',
      body: 'Choose Boys or Girls — this filters the available events.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#event-group',
      title: 'Select Event',
      body: 'Pick the event you want to test. Events update based on your gender selection.',
      placement: 'bottom',
      optional: true,
    },
    {
      selector: '#performance-input',
      title: 'Enter Your Performance',
      body: 'Type your time (e.g., 11.52) or distance (e.g., 45-06.25). The hint below updates based on the event you selected.',
      placement: 'top',
      optional: true,
    },
    {
      selector: '#submit-btn',
      title: 'See Your Ranking',
      body: 'Once all required fields are filled, click here to see overall, enrollment-based, and grade-level rankings plus sectional projections.',
      placement: 'top',
      optional: true,
    },
    {
      type: 'info',
      icon: 'check',
      title: 'Give It a Try!',
      body: 'Fill in the form and submit to see a detailed ranking breakdown — the same view as a real athlete result detail page.',
      isFinal: true,
    },
  ];

  /* ─── Detect which page we're on and return the appropriate steps ─── */
  function getPageSteps() {
    const path = window.location.pathname;

    if ($('#hero-tour-trigger'))                           return { page: 'home',              steps: HOME_STEPS };
    if (path.match(/\/athlete-dashboard\/\d+\/result\//))  return { page: 'result-detail',     steps: RESULT_DETAIL_STEPS };
    if (path.match(/\/athlete-dashboard\/\d+/))            return { page: 'athlete-dashboard',  steps: ATHLETE_DASHBOARD_STEPS };
    if (path.match(/\/school-dashboard\/\d+/))             return { page: 'school-dashboard',   steps: SCHOOL_DASHBOARD_STEPS };
    if (path === '/queries/percentiles')                   return { page: 'percentiles',        steps: PERCENTILES_STEPS };
    if (path === '/queries/sectional-trends')              return { page: 'sectional-trends',   steps: SECTIONAL_TRENDS_STEPS };
    if (path.startsWith('/queries/hypothetical'))           return { page: 'hypothetical',       steps: path.includes('/result') ? RESULT_DETAIL_STEPS : HYPOTHETICAL_STEPS };
    if (path === '/queries')                               return { page: 'queries',            steps: QUERIES_INDEX_STEPS };

    return null; // No tour for this page
  }

  /* ─── Cross-page tour infrastructure ─── */
  const CROSS_TOUR_KEY = 'ti_cross_tour';

  // Curated step sets for each phase (remove per-page finales;
  // the overall finale lives at the end of the last phase).
  // Also remove info cards for pages we'll actually visit (athlete/school/result dashboards, queries tools).
  const CROSS_HOME_EXCLUDED = [
    'Athlete Dashboard', 'Athlete Result Detail', 'School Dashboard',
    'Percentiles Query', 'Sectional Event Trends', 'Hypothetical Athlete',
    "You're All Set!",
  ];
  const CROSS_HOME_STEPS = HOME_STEPS.filter(s => !CROSS_HOME_EXCLUDED.includes(s.title));
  const CROSS_ATHLETE_STEPS = ATHLETE_DASHBOARD_STEPS.filter(s => !s.isFinal);
  const CROSS_RESULT_STEPS = RESULT_DETAIL_STEPS.filter(s => !s.isFinal);
  const CROSS_SCHOOL_STEPS = SCHOOL_DASHBOARD_STEPS.filter(s => !s.isFinal);
  const CROSS_QUERIES_STEPS = [QUERIES_INDEX_STEPS[0]];
  const CROSS_PERCENTILES_STEPS = PERCENTILES_STEPS.filter(s => !s.isFinal);
  const CROSS_TRENDS_STEPS = SECTIONAL_TRENDS_STEPS.filter(s => !s.isFinal);
  const CROSS_HYPOTHETICAL_STEPS = [
    ...HYPOTHETICAL_STEPS.filter(s => !s.isFinal),
    {
      type: 'info',
      icon: 'check',
      title: "You're All Set!",
      body: "That's the full tour of Track Insights! Click the hero text on the home page anytime to replay. Now go search for an athlete and start exploring!",
      isFinal: true,
    },
  ];

  // Example pages used in the cross-page tour
  const EXAMPLE_ATHLETE_ID = 292665;  // Sophia Kennedy
  const EXAMPLE_SCHOOL_ID  = 280;     // Park Tudor
  const EXAMPLE_RESULT_PATH = `/athlete-dashboard/292665/result/2997/1600 Meters`; // Sophia Kennedy – Sectional 1600m

  const TOUR_PHASES = [
    { page: 'home',              path: '/',                                              steps: CROSS_HOME_STEPS },
    { page: 'athlete-dashboard', path: `/athlete-dashboard/${EXAMPLE_ATHLETE_ID}`,       steps: CROSS_ATHLETE_STEPS },
    { page: 'result-detail',     path: EXAMPLE_RESULT_PATH,                              steps: CROSS_RESULT_STEPS },
    { page: 'school-dashboard',  path: `/school-dashboard/${EXAMPLE_SCHOOL_ID}`,         steps: CROSS_SCHOOL_STEPS },
    { page: 'queries',           path: '/queries',                                       steps: CROSS_QUERIES_STEPS },
    { page: 'percentiles',       path: '/queries/percentiles',                           steps: CROSS_PERCENTILES_STEPS },
    { page: 'sectional-trends',  path: '/queries/sectional-trends',                      steps: CROSS_TRENDS_STEPS },
    { page: 'hypothetical',      path: '/queries/hypothetical',                          steps: CROSS_HYPOTHETICAL_STEPS },
  ];

  const TOTAL_CROSS_STEPS = TOUR_PHASES.reduce((s, p) => s + p.steps.length, 0);

  function getGlobalOffset(phaseIndex) {
    let n = 0;
    for (let i = 0; i < phaseIndex; i++) n += TOUR_PHASES[i].steps.length;
    return n;
  }

  function saveCrossTourState(state) {
    try { localStorage.setItem(CROSS_TOUR_KEY, JSON.stringify(state)); } catch {}
  }
  function getCrossTourState() {
    try { const r = localStorage.getItem(CROSS_TOUR_KEY); return r ? JSON.parse(r) : null; } catch { return null; }
  }
  function clearCrossTourState() {
    try { localStorage.removeItem(CROSS_TOUR_KEY); } catch {}
  }

  /* ─── OnboardingEngine class ─── */
  class OnboardingEngine {
    constructor({ steps, page = 'home', isCrossTour = false, phaseIndex = 0, globalOffset = 0, totalGlobalSteps = 0 } = {}) {
      this.steps            = steps;
      this.page             = page;
      this.isCrossTour      = isCrossTour;
      this.phaseIndex       = phaseIndex;
      this.globalOffset     = globalOffset;
      this.totalGlobalSteps = totalGlobalSteps;
      this.currentStep      = 0;
      this.isActive         = false;
      this._resizeTimer     = null;

      // DOM refs (created lazily)
      this._shield     = null;
      this._spotlight  = null;
      this._tooltip    = null;
      this._overlay    = null;

      // Bound handlers for cleanup
      this._onResize      = this._handleResize.bind(this);
      this._onKeyDown     = this._handleKeyDown.bind(this);
      this._onShieldClick = this._handleShieldClick.bind(this);
    }

    /* ── Public API ── */

    start() {
      if (this.isActive) return;
      this.isActive    = true;
      this.currentStep = 0;
      this._createDOM();
      this._bindEvents();
      this._showStep(0);
    }

    restart() {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_SKIP);
      this.teardown();
      this.start();
    }

    teardown() {
      this.isActive = false;
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
      try { localStorage.setItem(STORAGE_KEY, '1'); } catch { /* silent */ }
    }
    _markSkipped() {
      try { localStorage.setItem(STORAGE_SKIP, '1'); } catch { /* silent */ }
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

    /* ── Event binding ── */

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
      if (this._shield) this._shield.removeEventListener('click', this._onShieldClick);
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
      // Block page interaction during tour
    }

    _trapFocus(e) {
      const container = this._tooltip || $('.onboarding-welcome__card');
      if (!container) return;
      const focusable = container.querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])');
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last  = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }

    /* ── Step navigation ── */

    _next() {
      if (this.currentStep < this.steps.length - 1) {
        this._showStep(this.currentStep + 1);
      } else {
        this._complete();
      }
    }

    _back() {
      if (this.currentStep > 0) {
        this._showStep(this.currentStep - 1);
      }
    }

    _skip() {
      if (this.isCrossTour) {
        clearCrossTourState();
      }
      this._markSkipped();
      this.teardown();
      if (this.isCrossTour && window.location.pathname !== '/') {
        window.location.href = '/';
      }
    }

    _complete() {
      if (this.isCrossTour) {
        const nextPhase = this.phaseIndex + 1;
        if (nextPhase < TOUR_PHASES.length) {
          saveCrossTourState({ active: true, phase: nextPhase });
          this.teardown();
          window.location.href = TOUR_PHASES[nextPhase].path;
          return;
        }
        // Last phase — full tour complete
        clearCrossTourState();
        this._markCompleted();
        this.teardown();
        if (window.location.pathname !== '/') {
          window.location.href = '/';
        }
        return;
      }
      this._markCompleted();
      this.teardown();
    }

    /* ── Count displayable steps (for progress) ── */

    _spotlightStepCount() {
      return this.steps.filter(s => !s.type).length;
    }

    _spotlightStepIndex(index) {
      let count = 0;
      for (let i = 0; i < index; i++) {
        if (!this.steps[i].type) count++;
      }
      return count;
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
        if (this._tooltip)   this._tooltip.classList.remove('visible');
      } else {
        // Check if optional step's target exists — skip if not
        if (step.optional) {
          const isMobile = window.matchMedia('(max-width: 767px)').matches;
          const selector = (isMobile && step.mobileSelector) ? step.mobileSelector : step.selector;
          const target = document.querySelector(selector);
          if (!target) {
            // Skip this optional step silently
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
      const displayIdx   = this.isCrossTour ? this.globalOffset + index : index;
      const displayTotal = this.isCrossTour ? this.totalGlobalSteps : this.steps.length;
      const isFinal = step.isFinal || false;
      const icon    = ICONS[step.icon] || ICONS.about;

      const wrapper = document.createElement('div');
      wrapper.className = 'onboarding-welcome';

      const card = document.createElement('div');
      card.className = 'onboarding-welcome__card';
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-modal', 'true');
      card.setAttribute('aria-label', esc(step.title));

      // Progress indicator
      const progressPct = Math.round((displayIdx / Math.max(displayTotal - 1, 1)) * 100);

      card.innerHTML = `
        <div class="onboarding-welcome__icon" aria-hidden="true">${icon}</div>
        <h2 class="onboarding-welcome__title">${esc(step.title)}</h2>
        <p class="onboarding-welcome__body">${esc(step.body)}</p>
        <div class="onboarding-info-progress">
          <div class="onboarding-info-progress__bar" style="width: ${progressPct}%"></div>
        </div>
        <div class="onboarding-info-progress__label">${displayIdx + 1} of ${displayTotal}</div>
        <div class="onboarding-welcome__actions">
          ${!isFinal ? `<button class="onboarding-nav__btn onboarding-nav__btn--ghost" data-action="skip" aria-label="Skip tour">Skip</button>` : ''}
          ${index > 0 ? `<button class="onboarding-nav__btn onboarding-nav__btn--ghost" data-action="back" aria-label="Go back">Back</button>` : ''}
          <button class="onboarding-nav__btn onboarding-nav__btn--primary" data-action="next" aria-label="${isFinal ? 'Finish tour' : (index === 0 ? 'Start tour' : 'Next')}">
            ${isFinal ? 'Finish' : (index === 0 ? 'Let\'s Go!' : 'Next')}
          </button>
        </div>
      `;

      card.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => {
          const action = btn.getAttribute('data-action');
          if (action === 'next')  this._next();
          if (action === 'back')  this._back();
          if (action === 'skip')  this._skip();
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
      const selector = (isMobile && step.mobileSelector) ? step.mobileSelector : step.selector;
      const body     = (isMobile && step.mobileBody) ? step.mobileBody : step.body;
      const target   = document.querySelector(selector);

      if (!target) {
        console.warn(`[Onboarding] Selector "${selector}" not found, skipping step ${index}`);
        this._next();
        return;
      }

      // Scroll target into view if needed
      const rect = target.getBoundingClientRect();
      if (rect.top < 0 || rect.bottom > window.innerHeight) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Wait for scroll to complete
        setTimeout(() => this._renderSpotlightStep(target, step, body, index), 400);
        return;
      }

      this._renderSpotlightStep(target, step, body, index);
    }

    _renderSpotlightStep(target, step, body, index) {
      const displayIdx   = this.isCrossTour ? this.globalOffset + index : index;
      const displayTotal = this.isCrossTour ? this.totalGlobalSteps : this.steps.length;

      this._positionSpotlight(target);

      this._tooltip.innerHTML = '';
      this._tooltip.classList.remove('visible');

      const arrow = document.createElement('div');
      arrow.className = 'onboarding-tooltip__arrow';
      this._tooltip.appendChild(arrow);

      // Step badge
      const badge = document.createElement('span');
      badge.className = 'onboarding-tooltip__step-badge';
      badge.textContent = `Step ${displayIdx + 1} of ${displayTotal}`;
      this._tooltip.appendChild(badge);

      // Progress bar
      const progressPct = Math.round((displayIdx / Math.max(displayTotal - 1, 1)) * 100);
      const progress = document.createElement('div');
      progress.className = 'onboarding-info-progress';
      progress.innerHTML = `<div class="onboarding-info-progress__bar" style="width: ${progressPct}%"></div>`;
      this._tooltip.appendChild(progress);

      const title = document.createElement('h3');
      title.className = 'onboarding-tooltip__title';
      title.textContent = step.title;
      this._tooltip.appendChild(title);

      const bodyEl = document.createElement('p');
      bodyEl.className = 'onboarding-tooltip__body';
      bodyEl.textContent = body;
      this._tooltip.appendChild(bodyEl);

      const nav = document.createElement('div');
      nav.className = 'onboarding-nav';

      if (index > 0) {
        const backBtn = document.createElement('button');
        backBtn.className = 'onboarding-nav__btn onboarding-nav__btn--ghost';
        backBtn.textContent = 'Back';
        backBtn.setAttribute('aria-label', 'Go to previous step');
        backBtn.addEventListener('click', () => this._back());
        nav.appendChild(backBtn);
      }

      const skipBtn = document.createElement('button');
      skipBtn.className = 'onboarding-nav__btn onboarding-nav__btn--ghost';
      skipBtn.textContent = 'Skip';
      skipBtn.setAttribute('aria-label', 'Skip tutorial');
      skipBtn.addEventListener('click', () => this._skip());
      nav.appendChild(skipBtn);

      const spacer = document.createElement('div');
      spacer.className = 'onboarding-nav__spacer';
      nav.appendChild(spacer);

      const isLast = index === this.steps.length - 1;
      const nextBtn = document.createElement('button');
      nextBtn.className = 'onboarding-nav__btn onboarding-nav__btn--primary';
      nextBtn.textContent = isLast ? 'Finish' : 'Next';
      nextBtn.setAttribute('aria-label', isLast ? 'Finish tour' : 'Next step');
      nextBtn.addEventListener('click', () => this._next());
      nav.appendChild(nextBtn);

      this._tooltip.appendChild(nav);
      this._tooltip.setAttribute('aria-label', `Step ${displayIdx + 1}: ${step.title}`);

      this._positionTooltip(target, step.placement);

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          this._tooltip.classList.add('visible');
        });
      });

      setTimeout(() => nextBtn.focus(), 380);
    }

    /* ── Positioning helpers ── */

    _positionSpotlight(target) {
      const rect = target.getBoundingClientRect();
      this._spotlight.style.setProperty('--spot-x', `${rect.left - SPOT_PAD}px`);
      this._spotlight.style.setProperty('--spot-y', `${rect.top  - SPOT_PAD}px`);
      this._spotlight.style.setProperty('--spot-w', `${rect.width  + SPOT_PAD * 2}px`);
      this._spotlight.style.setProperty('--spot-h', `${rect.height + SPOT_PAD * 2}px`);
      const cs = window.getComputedStyle(target);
      this._spotlight.style.setProperty('--spot-radius', cs.borderRadius || '12px');
    }

    _positionTooltip(target, preferredPlacement) {
      const rect = target.getBoundingClientRect();
      const expandedRect = {
        top:    rect.top    - SPOT_PAD,
        left:   rect.left   - SPOT_PAD,
        right:  rect.right  + SPOT_PAD,
        bottom: rect.bottom + SPOT_PAD,
        width:  rect.width  + SPOT_PAD * 2,
        height: rect.height + SPOT_PAD * 2,
      };

      this._tooltip.style.visibility = 'hidden';
      this._tooltip.style.display    = 'block';
      this._tooltip.classList.add('visible');
      const tw = this._tooltip.offsetWidth;
      const th = this._tooltip.offsetHeight;
      this._tooltip.classList.remove('visible');
      this._tooltip.style.visibility = '';

      const { placement, top, left } = computePlacement(expandedRect, tw, th, preferredPlacement);
      this._tooltip.style.top  = `${top}px`;
      this._tooltip.style.left = `${left}px`;

      const arrow = this._tooltip.querySelector('.onboarding-tooltip__arrow');
      if (arrow) {
        arrow.className = 'onboarding-tooltip__arrow';
        const arrowDir = { bottom: 'top', top: 'bottom', left: 'right', right: 'left' }[placement];
        arrow.classList.add(`onboarding-tooltip__arrow--${arrowDir}`);
      }
    }

    _positionCurrent() {
      const step = this.steps[this.currentStep];
      if (!step || step.type) return;
      const isMobile = window.matchMedia('(max-width: 767px)').matches;
      const selector = (isMobile && step.mobileSelector) ? step.mobileSelector : step.selector;
      const target   = document.querySelector(selector);
      if (!target) return;
      this._positionSpotlight(target);
      this._positionTooltip(target, step.placement);
    }
  }

  /* ─── Initialization ─── */

  function initOnboarding() {
    /* ── Check for an active cross-page tour ── */
    const crossState = getCrossTourState();
    if (crossState && crossState.active) {
      const phaseIdx = crossState.phase;
      const phase    = TOUR_PHASES[phaseIdx];
      if (phase) {
        const engine = new OnboardingEngine({
          steps:            phase.steps,
          page:             phase.page,
          isCrossTour:      true,
          phaseIndex:       phaseIdx,
          globalOffset:     getGlobalOffset(phaseIdx),
          totalGlobalSteps: TOTAL_CROSS_STEPS,
        });
        window.__tiOnboarding = engine;
        // Delay to let loading overlay clear and dynamic content render
        // Dashboard pages load data via API — give extra time
        const hasLoading = document.getElementById('loading-overlay') || document.getElementById('loading-state');
        const delay = hasLoading ? 3000 : 800;
        setTimeout(() => engine.start(), delay);
        return; // Cross-tour takes priority
      }
      // Invalid state — clear it
      clearCrossTourState();
    }

    /* ── Normal mode: set up hero trigger on home page ── */
    const pageConfig = getPageSteps();
    if (!pageConfig) return;

    if (pageConfig.page === 'home') {
      const trigger = $('#hero-tour-trigger');
      if (trigger) {
        const startCrossTour = () => {
          // Clear any prior state
          clearCrossTourState();
          localStorage.removeItem(STORAGE_KEY);
          localStorage.removeItem(STORAGE_SKIP);

          saveCrossTourState({ active: true, phase: 0 });

          const engine = new OnboardingEngine({
            steps:            TOUR_PHASES[0].steps,
            page:             'home',
            isCrossTour:      true,
            phaseIndex:       0,
            globalOffset:     0,
            totalGlobalSteps: TOTAL_CROSS_STEPS,
          });
          window.__tiOnboarding = engine;
          engine.start();
        };
        trigger.addEventListener('click', startCrossTour);
        trigger.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            startCrossTour();
          }
        });
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      // Wait for loading overlay to clear
      const delay = document.getElementById('loading-overlay') ? 1600 : 200;
      setTimeout(initOnboarding, delay);
    });
  } else {
    const delay = document.getElementById('loading-overlay') ? 1600 : 200;
    setTimeout(initOnboarding, delay);
  }
})();
