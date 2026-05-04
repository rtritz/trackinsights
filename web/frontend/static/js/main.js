document.addEventListener('DOMContentLoaded', function () {
  const setupSearch = (form, searchInput, resultsDiv) => {
    if (!form || !searchInput || !resultsDiv) {
      return;
    }

    let abortController = null;
    let searchTimeout = null;
    let currentResults = []; // Track current search results

    const navigateToResult = (item) => {
      if (item.type === 'school') {
        window.location.href = `/school-dashboard/${item.id}`;
      } else if (item.type === 'athlete') {
        window.location.href = `/athlete-dashboard/${item.id}`;
      }
    };

    const performSearch = async (query) => {
      if (abortController) {
        abortController.abort();
      }

      if (searchTimeout) {
        clearTimeout(searchTimeout);
        searchTimeout = null;
      }

      if (!query) {
        resultsDiv.innerHTML = '';
        resultsDiv.classList.remove('open');
        currentResults = [];
        return;
      }

      resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
      resultsDiv.classList.add('open');

      abortController = new AbortController();

      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
          signal: abortController.signal,
        });
        if (!res.ok) throw new Error('Search request failed');
        const data = await res.json();
        currentResults = data; // Store results for Enter key handling
        if (data.length === 0) {
          resultsDiv.innerHTML = '<div class="no-results">No results found for "' + escapeHtml(query) + '"</div>';
          resultsDiv.classList.add('open');
        } else {
          resultsDiv.innerHTML = '';
          const ul = document.createElement('ul');
          ul.className = 'list-none p-0 m-0';

          data.forEach(item => {
            const li = document.createElement('li');
            li.className = 'mb-2';
            const btn = document.createElement('button');
            btn.className = 'btn btn-ghost p-2 px-4 bg-gray-100 rounded-full w-full text-left justify-between flex';

            if (item.type === 'school') {
              btn.innerHTML = `
                            <span class="result-text">${escapeHtml(item.name)}</span>
                            <span class="result-badge font-bold border-2 border-green-500 text-green-600 rounded-full px-3 py-0.5 text-sm whitespace-nowrap" style="margin-right:4px;">School</span>
                        `.trim();
              btn.addEventListener('click', () => {
                window.location.href = `/school-dashboard/${item.id}`;
                console.log('Navigating to school ID:', item.id);
              });
            } else if (item.type === 'athlete') {
              let gender = (item.gender || '').toLowerCase();
              let genderBadgeClass = '';
              let genderLabel = '';

              if (gender === 'b' || gender === 'boys') {
                genderBadgeClass = 'border-blue-500 text-blue-600';
                genderLabel = 'Boys';
              } else if (gender === 'g' || gender === 'girls') {
                genderBadgeClass = 'border-pink-500 text-pink-600';
                genderLabel = 'Girls';
              } else {
                genderBadgeClass = 'border-gray-400 text-gray-600';
                genderLabel = escapeHtml(item.gender || 'A');
              }

              const classYear = item.graduation_year ? escapeHtml(item.graduation_year) : '00';
        btn.innerHTML = `
              <span class="result-text">${escapeHtml(item.name)}, Class of ${classYear} - ${escapeHtml(item.school || '')}</span>
              <span class="result-badge font-bold border-2 rounded-full px-1 ${genderBadgeClass}" style="margin-right:4px;">${genderLabel}</span>
            `.trim();
              btn.addEventListener('click', () => {
                window.location.href = `/athlete-dashboard/${item.id}`;
                console.log('Navigating to athlete ID:', item.id);
              });
            }

            li.appendChild(btn);
            ul.appendChild(li);
          });

          resultsDiv.appendChild(ul);
          resultsDiv.classList.add('open');
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          return;
        }
        resultsDiv.innerHTML = '<div class="no-results" style="color: #dc3545;">Error performing search. Please try again.</div>';
        resultsDiv.classList.add('open');
      }
    };

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      // If there are any results, navigate to the first one on Enter
      if (currentResults.length > 0) {
        navigateToResult(currentResults[0]);
        return;
      }
    });

    searchInput.addEventListener('input', function () {
      const query = this.value.trim();
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }

      if (!query) {
        resultsDiv.innerHTML = '';
        resultsDiv.classList.remove('open');
        currentResults = [];
        return;
      }

      searchTimeout = setTimeout(() => {
        performSearch(query);
      }, 500);
    });
  };

  setupSearch(
    document.getElementById('navSearchForm'),
    document.getElementById('navSearchInput'),
    document.getElementById('nav-search-results'),
  );

  setupSearch(
    document.getElementById('searchForm'),
    document.getElementById('searchInput') || document.getElementById('search-box'),
    document.getElementById('results'),
  );

  const getNormalizedPath = () => {
    const rawPath = (window.location.pathname || '/').trim();
    if (!rawPath || rawPath === '/') {
      return '/';
    }
    return rawPath.endsWith('/') ? rawPath.slice(0, -1) : rawPath;
  };

  const pagePath = getNormalizedPath();

  const tourSteps = [
    {
      path: '/',
      title: 'Home',
      body: 'Start here for search and insights. Use the top navigation to jump quickly.',
    },
    {
      path: '/',
      title: 'Search',
      body: 'Use the top popout search bar (desktop) to find an athlete or school in one step.',
      highlightSelector: '#nav-search-pill',
      openDesktopSearch: true,
    },
    {
      path: '/insights',
      title: 'Insights',
      body: 'Open percentile, sectional trends, or hypothetical tools from this hub.',
    },
  ];

  const subpageTips = {
    '/insights': 'Use this hub to pick the exact query tool you need: percentiles, sectional trends, or hypothetical results.',
    '/athlete-dashboard': 'This page summarizes season history and achievements. Use linked results to inspect ranking details.',
    '/athlete-dashboard/result': 'This page breaks down one performance. Expand sections to compare statewide placement quickly.',
    '/school-dashboard': 'This page shows school-wide trends and top performers. Use linked athlete names for deeper drill-downs.',
    '/insights/percentiles': 'Set only the filters you need, then read the percentile table as a fast benchmark for your event.',
    '/insights/sectional-trends': 'Pick a gender and event to view historical trend lines and qualification depth.',
    '/insights/hypothetical': 'Enter one performance to see projected placement without opening full reports.',
    '/insights/hypothetical/result': 'Use this projection summary to compare projected placements across sectionals and years.',
    '/insights/reports/percentiles-summary': 'This report is best for quick reference. Download the PDF for offline review.',
    '/about': 'This page explains the project background. Return to Home to start searching immediately.',
  };

  const isInsightsPage = pagePath === '/insights'
    || pagePath === '/insights/percentiles'
    || pagePath === '/insights/sectional-trends'
    || pagePath === '/insights/hypothetical'
    || pagePath === '/insights/hypothetical/result'
    || pagePath === '/insights/reports/percentiles-summary';

  const tourStorage = {
    active: 'ti.walkthrough.active.v3',
    neverShow: 'ti.walkthrough.neverShow.v3',
    step: 'ti.walkthrough.step.v3',
  };

  const params = new URLSearchParams(window.location.search);
  const requestedStep = Number.parseInt(params.get('step') || '', 10);
  const hasExplicitRequestedStep = Number.isInteger(requestedStep) && requestedStep >= 0 && requestedStep < tourSteps.length;
  const savedStep = Number.parseInt(localStorage.getItem(tourStorage.step) || '', 10);
  const isSavedStepValid = Number.isInteger(savedStep) && savedStep >= 0 && savedStep < tourSteps.length;

  const getPathStepIndex = (path) => tourSteps.findIndex((step) => step.path === path);
  let currentMainStepIndex = hasExplicitRequestedStep
    ? requestedStep
    : isSavedStepValid
      ? savedStep
    : getPathStepIndex(pagePath);

  const hasAnyMainPath = tourSteps.some((step) => step.path === pagePath);
  const isMainPage = hasAnyMainPath;

  const wasTourActive = localStorage.getItem(tourStorage.active) === '1';
  const shouldForceStart = params.get('walkthrough') === '1';
  const neverShowTour = localStorage.getItem(tourStorage.neverShow) === '1';

  if (shouldForceStart) {
    localStorage.setItem(tourStorage.active, '1');
  } else if (!neverShowTour && pagePath === '/') {
    localStorage.setItem(tourStorage.active, '1');
  }

  const isTourActive = shouldForceStart || (!neverShowTour && localStorage.getItem(tourStorage.active) === '1');

  if (isTourActive && currentMainStepIndex > -1) {
    localStorage.setItem(tourStorage.step, String(currentMainStepIndex));
  }

  if (isMainPage && currentMainStepIndex > -1) {
    const expectedPath = tourSteps[currentMainStepIndex]?.path;
    if (expectedPath && expectedPath !== pagePath && !hasExplicitRequestedStep && !isSavedStepValid) {
      currentMainStepIndex = getPathStepIndex(pagePath);
    }
  }

  const createPanelShell = (positionClasses) => {
    const wrapper = document.createElement('div');
    wrapper.className = `fixed z-[90] ${positionClasses}`;
    return wrapper;
  };

  const createTutorialCard = ({ title, body, controls, onClose = null }) => {
    const card = document.createElement('div');
    card.className = 'card w-[min(92vw,22rem)] bg-white border border-base-300 shadow-xl';

    const cardBody = document.createElement('div');
    cardBody.className = 'card-body p-4 gap-3 relative';

    if (typeof onClose === 'function') {
      const closeButton = document.createElement('button');
      closeButton.type = 'button';
      closeButton.className = 'btn btn-ghost btn-xs absolute top-2 right-2';
      closeButton.setAttribute('aria-label', 'Close tutorial');
      closeButton.textContent = '×';
      closeButton.addEventListener('click', onClose);
      cardBody.appendChild(closeButton);
    }

    const heading = document.createElement('h3');
    heading.className = 'card-title text-base text-primary';
    heading.textContent = title;

    const text = document.createElement('p');
    text.className = 'text-sm text-base-content/80 leading-snug';
    text.textContent = body;

    const actions = document.createElement('div');
    actions.className = 'card-actions justify-end flex-wrap gap-2';
    controls.forEach((control) => actions.appendChild(control));

    cardBody.appendChild(heading);
    cardBody.appendChild(text);
    cardBody.appendChild(actions);
    card.appendChild(cardBody);

    return card;
  };

  const makeButton = ({ label, classes, onClick, type = 'button' }) => {
    const button = document.createElement('button');
    button.type = type;
    button.className = classes;
    button.textContent = label;
    button.addEventListener('click', onClick);
    return button;
  };

  const completeTour = () => {
    localStorage.removeItem(tourStorage.active);
  };

  let activeHighlightTarget = null;

  const clearStepEmphasis = () => {
    if (!activeHighlightTarget) {
      return;
    }
    activeHighlightTarget.classList.remove('ring-4', 'ring-primary', 'ring-offset-2');
    activeHighlightTarget = null;
  };

  const dismissTourForNavigation = () => {
    if (localStorage.getItem(tourStorage.active) !== '1') {
      return;
    }
    localStorage.removeItem(tourStorage.active);
    localStorage.removeItem(tourStorage.step);
    clearStepEmphasis();
  };

  const applyStepEmphasis = (step) => {
    clearStepEmphasis();

    if (!step || !step.highlightSelector) {
      return;
    }

    const target = document.querySelector(step.highlightSelector);
    if (!target) {
      return;
    }

    const isDesktop = window.matchMedia('(min-width: 768px)').matches;
    if (step.openDesktopSearch && isDesktop && step.highlightSelector === '#nav-search-pill') {
      const openAndFocusSearch = () => {
        const isOpen = target.dataset.open === 'true';
        if (!isOpen) {
          target.click();
        }

        const navSearchInput = document.getElementById('navSearchInput');
        if (navSearchInput) {
          setTimeout(() => {
            navSearchInput.focus();
            navSearchInput.select();
          }, isOpen ? 0 : 120);
        }
      };

      setTimeout(openAndFocusSearch, 0);
    }

    target.classList.add('ring-4', 'ring-primary', 'ring-offset-2');
    target.style.borderRadius = target.style.borderRadius || '9999px';
    activeHighlightTarget = target;
  };

  const bindTourDismissOnNav = () => {
    const insightsLink = document.getElementById('queries-toggle');
    if (insightsLink) {
      insightsLink.addEventListener('click', dismissTourForNavigation);
    }

    const mobileSearchLink = document.querySelector('a[aria-label="Go to search"]');
    if (mobileSearchLink) {
      mobileSearchLink.addEventListener('click', dismissTourForNavigation);
    }

    const navSearchPill = document.getElementById('nav-search-pill');
    if (navSearchPill) {
      navSearchPill.addEventListener('click', dismissTourForNavigation);
    }
  };

  bindTourDismissOnNav();

  const lightbulbWidget = {
    wrap: null,
    button: null,
    panel: null,
    card: null,
    isOpen: false,
    panelAnimation: null,
    glowAnimation: null,
  };

  const lightbulbNudge = {
    veil: null,
    card: null,
    autoTimer: null,
  };

  const lampIdleShadow = '0 10px 24px rgba(0,0,0,0.22), 0 0 16px rgba(253, 224, 71, 0.62)';
  const lampActiveShadow = '0 14px 28px rgba(0,0,0,0.22), 0 0 34px rgba(253, 234, 112, 0.98)';
  const lampOutlineColor = '1px solid rgba(254, 249, 195, 0.94)';
  const lampButtonBackground = '#FDE047';
  const lampButtonBorder = '#FACC15';
  const lampIconColor = '#78350F';

  const getLightbulbFooterSlot = () => document.getElementById('ti-footer-lightbulb-slot') || document.body;

  function ensureLightbulbWidget() {
    if (lightbulbWidget.wrap) {
      return lightbulbWidget;
    }

    const tipButtonWrap = document.createElement('div');
    tipButtonWrap.id = 'ti-lightbulb-wrap';
    tipButtonWrap.className = 'relative w-14 h-14 overflow-visible pointer-events-auto';
    tipButtonWrap.style.display = 'none';

    const tipButton = document.createElement('button');
    tipButton.type = 'button';
    tipButton.className = 'btn btn-circle btn-warning shadow-lg absolute bottom-0 left-0';
    tipButton.setAttribute('aria-label', 'Open quick tutorial');
    tipButton.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 18h6M10 22h4M12 2a7 7 0 00-4 12.75V16a1 1 0 001 1h6a1 1 0 001-1v-1.25A7 7 0 0012 2z" />
      </svg>
    `;

    const tipPanel = document.createElement('div');
    tipPanel.className = 'hidden absolute bottom-16 left-0';
    tipPanel.style.transformOrigin = '1.6rem calc(100% + 0.9rem)';

    const applyIdleLampLook = () => {
      tipButton.style.boxShadow = lampIdleShadow;
      tipButton.style.filter = 'brightness(1.03) saturate(1.05)';
      tipButton.style.transform = '';
      tipButton.style.outline = lampOutlineColor;
      tipButton.style.outlineOffset = '2px';
      tipButton.style.backgroundColor = lampButtonBackground;
      tipButton.style.borderColor = lampButtonBorder;
      tipButton.style.color = lampIconColor;
    };

    applyIdleLampLook();

    const setButtonGlow = (isActive) => {
      if (lightbulbWidget.button && typeof lightbulbWidget.button.getAnimations === 'function') {
        lightbulbWidget.button.getAnimations().forEach((animation) => animation.cancel());
      }

      if (!tipButton) {
        return;
      }

      if (!isActive) {
        applyIdleLampLook();
        return;
      }

      tipButton.style.outline = lampOutlineColor;
      tipButton.style.outlineOffset = '2px';
      lightbulbWidget.glowAnimation = tipButton.animate(
        [
          {
            boxShadow: lampIdleShadow,
            filter: 'brightness(1.03) saturate(1.05)',
            transform: 'scale(1)',
          },
          {
            boxShadow: lampActiveShadow,
            filter: 'brightness(1.12) saturate(1.08)',
            transform: 'scale(1.03)',
          },
          {
            boxShadow: lampIdleShadow,
            filter: 'brightness(1.05) saturate(1.06)',
            transform: 'scale(1)',
          },
        ],
        {
          duration: 1200,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
          iterations: Infinity,
          fill: 'forwards',
        },
      );
    };

    const finishPanelAnimation = () => {
      if (lightbulbWidget.panelAnimation) {
        lightbulbWidget.panelAnimation.cancel();
        lightbulbWidget.panelAnimation = null;
      }
    };

    const openTipPanel = () => {
      if (lightbulbWidget.isOpen) {
        return;
      }

      finishPanelAnimation();
      tipPanel.classList.remove('hidden');
      tipPanel.style.pointerEvents = 'auto';
      lightbulbWidget.isOpen = true;
      setButtonGlow(true);

      const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (prefersReducedMotion) {
        tipPanel.style.opacity = '1';
        tipPanel.style.transform = 'translate3d(0, 0, 0) scale(1)';
        tipPanel.style.filter = 'blur(0px)';
        return;
      }

      lightbulbWidget.panelAnimation = tipPanel.animate(
        [
          {
            opacity: 0,
            transform: 'translate3d(0, 18px, 0) scale(0.18)',
            filter: 'blur(8px)',
          },
          {
            opacity: 1,
            transform: 'translate3d(0, -2px, 0) scale(1.03)',
            filter: 'blur(0.8px)',
            offset: 0.7,
          },
          {
            opacity: 1,
            transform: 'translate3d(0, 0, 0) scale(1)',
            filter: 'blur(0px)',
          },
        ],
        {
          duration: 420,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
          fill: 'forwards',
        },
      );

      lightbulbWidget.panelAnimation.onfinish = () => {
        lightbulbWidget.panelAnimation = null;
      };
    };

    const closeTipPanel = () => {
      if (!lightbulbWidget.isOpen && tipPanel.classList.contains('hidden')) {
        return;
      }

      finishPanelAnimation();
      lightbulbWidget.isOpen = false;
      setButtonGlow(false);

      const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (prefersReducedMotion) {
        tipPanel.classList.add('hidden');
        tipPanel.style.opacity = '';
        tipPanel.style.transform = '';
        tipPanel.style.filter = '';
        return;
      }

      lightbulbWidget.panelAnimation = tipPanel.animate(
        [
          {
            opacity: 1,
            transform: 'translate3d(0, 0, 0) scale(1)',
            filter: 'blur(0px)',
          },
          {
            opacity: 0.52,
            transform: 'translate3d(0, 8px, 0) scale(0.46)',
            filter: 'blur(1.4px)',
            offset: 0.62,
          },
          {
            opacity: 0,
            transform: 'translate3d(0, 18px, 0) scale(0.1)',
            filter: 'blur(7px)',
          },
        ],
        {
          duration: 300,
          easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
          fill: 'forwards',
        },
      );

      lightbulbWidget.panelAnimation.onfinish = () => {
        tipPanel.classList.add('hidden');
        tipPanel.style.opacity = '';
        tipPanel.style.transform = '';
        tipPanel.style.filter = '';
        lightbulbWidget.panelAnimation = null;
      };
    };

    const toggleTipPanel = () => {
      if (lightbulbWidget.isOpen) {
        closeTipPanel();
      } else {
        openTipPanel();
      }
    };

    const shouldUseMainTourCopy = pagePath === '/';

    const tipCard = createTutorialCard({
      title: shouldUseMainTourCopy ? 'Main Tour' : 'Quick Tip',
      body: resolveSubpageTip(),
      controls: [
        makeButton({
          label: shouldUseMainTourCopy ? 'Main Tour' : 'Ok',
          classes: 'btn btn-primary btn-sm',
          onClick: () => {
            if (shouldUseMainTourCopy) {
              localStorage.setItem(tourStorage.active, '1');
              localStorage.removeItem(tourStorage.neverShow);
              window.location.href = '/?walkthrough=1&step=0';
              return;
            }
            closeTipPanel();
          },
        }),
      ],
      onClose: () => {
        closeTipPanel();
      },
    });

    tipPanel.appendChild(tipCard);
    tipButton.addEventListener('click', () => {
      toggleTipPanel();
    });

    tipButtonWrap.appendChild(tipPanel);
    tipButtonWrap.appendChild(tipButton);
    getLightbulbFooterSlot().appendChild(tipButtonWrap);

    lightbulbWidget.wrap = tipButtonWrap;
    lightbulbWidget.button = tipButton;
    lightbulbWidget.panel = tipPanel;
    lightbulbWidget.card = tipCard;
    return lightbulbWidget;
  }

  function showLightbulbWidgetInFooter() {
    const widget = ensureLightbulbWidget();
    const slot = getLightbulbFooterSlot();
    if (typeof widget.wrap.getAnimations === 'function') {
      widget.wrap.getAnimations().forEach((animation) => animation.cancel());
    }
    if (widget.button && typeof widget.button.getAnimations === 'function') {
      widget.button.getAnimations().forEach((animation) => animation.cancel());
    }
    if (widget.wrap.parentElement !== slot) {
      slot.appendChild(widget.wrap);
    }
    widget.wrap.style.display = 'block';
    widget.wrap.style.position = 'relative';
    widget.wrap.style.left = '';
    widget.wrap.style.top = '';
    widget.wrap.style.transform = '';
    widget.wrap.style.opacity = '';
    widget.wrap.style.visibility = 'visible';
    widget.wrap.style.zIndex = '';
    widget.wrap.style.pointerEvents = 'auto';
    if (widget.button) {
      widget.button.style.visibility = '';
      widget.button.style.opacity = '';
      widget.button.style.transform = '';
      widget.button.style.boxShadow = lampIdleShadow;
      widget.button.style.filter = 'brightness(1.03) saturate(1.05)';
      widget.button.style.outline = lampOutlineColor;
      widget.button.style.outlineOffset = '2px';
      widget.button.style.backgroundColor = lampButtonBackground;
      widget.button.style.borderColor = lampButtonBorder;
      widget.button.style.color = lampIconColor;
    }
  }

  function hideLightbulbWidget() {
    const widget = ensureLightbulbWidget();
    widget.wrap.style.display = 'none';
    if (widget.panel) {
      widget.panel.classList.add('hidden');
      widget.panel.style.opacity = '';
      widget.panel.style.transform = '';
      widget.panel.style.filter = '';
    }
    if (widget.button) {
      widget.button.style.boxShadow = lampIdleShadow;
      widget.button.style.filter = 'brightness(1.03) saturate(1.05)';
      widget.button.style.transform = '';
      widget.button.style.outline = lampOutlineColor;
      widget.button.style.outlineOffset = '2px';
      widget.button.style.backgroundColor = lampButtonBackground;
      widget.button.style.borderColor = lampButtonBorder;
      widget.button.style.color = lampIconColor;
    }
    widget.isOpen = false;
  }

  const hideLightbulbNudge = () => {
    if (lightbulbNudge.autoTimer) {
      clearTimeout(lightbulbNudge.autoTimer);
      lightbulbNudge.autoTimer = null;
    }
    if (lightbulbNudge.card) {
      lightbulbNudge.card.remove();
      lightbulbNudge.card = null;
    }
    if (lightbulbNudge.veil) {
      lightbulbNudge.veil.remove();
      lightbulbNudge.veil = null;
    }
  };

  const showLightbulbNudge = () => {
    hideLightbulbNudge();
    const widget = ensureLightbulbWidget();
    if (!widget.button || !widget.wrap) {
      return;
    }

    const veil = document.createElement('div');
    veil.className = 'fixed inset-0 z-[92] bg-black/35 backdrop-blur-[1.5px]';

    const nudgeCard = document.createElement('div');
    nudgeCard.className = 'fixed z-[96] card bg-white border border-base-300 shadow-2xl w-[min(90vw,22rem)]';
    nudgeCard.style.outline = '2px solid rgba(255, 255, 255, 0.94)';
    nudgeCard.style.outlineOffset = '0px';
    nudgeCard.style.boxShadow = '0 0 0 8px rgba(255,255,255,0.24), 0 24px 42px rgba(0,0,0,0.4)';

    const body = document.createElement('div');
    body.className = 'card-body p-4 gap-2';

    const heading = document.createElement('h3');
    heading.className = 'card-title text-base text-primary';
    heading.textContent = 'Quick Tip';

    const message = document.createElement('p');
    message.className = 'text-sm text-base-content/80 leading-snug';
    message.textContent = 'Click on this lightbulb if you need tips.';

    const actions = document.createElement('div');
    actions.className = 'card-actions justify-end';

    const okButton = document.createElement('button');
    okButton.type = 'button';
    okButton.className = 'btn btn-primary btn-sm';
    okButton.textContent = 'Got it';
    okButton.addEventListener('click', hideLightbulbNudge);

    actions.appendChild(okButton);
    body.appendChild(heading);
    body.appendChild(message);
    body.appendChild(actions);
    nudgeCard.appendChild(body);

    const positionNudgeCard = () => {
      const rect = widget.wrap.getBoundingClientRect();
      const nudgeWidth = Math.min(window.innerWidth * 0.9, 352);
      const preferredLeft = rect.left - (nudgeWidth - rect.width);
      const clampedLeft = Math.max(12, Math.min(preferredLeft, window.innerWidth - nudgeWidth - 12));
      const top = Math.max(12, rect.top - 120);
      nudgeCard.style.left = `${Math.round(clampedLeft)}px`;
      nudgeCard.style.top = `${Math.round(top)}px`;
    };

    document.body.appendChild(veil);
    document.body.appendChild(nudgeCard);
    positionNudgeCard();

    const dismissOnBulbClick = () => {
      hideLightbulbNudge();
      widget.button.removeEventListener('click', dismissOnBulbClick);
    };

    widget.button.addEventListener('click', dismissOnBulbClick);
    veil.addEventListener('click', hideLightbulbNudge);
    lightbulbNudge.autoTimer = setTimeout(hideLightbulbNudge, 6000);
    window.addEventListener('resize', positionNudgeCard, { once: true });

    lightbulbNudge.veil = veil;
    lightbulbNudge.card = nudgeCard;
  };

  const pulseLightbulbOnce = (buttonElement) => {
    if (!buttonElement || typeof buttonElement.animate !== 'function') {
      return;
    }

    if (typeof buttonElement.getAnimations === 'function') {
      buttonElement.getAnimations().forEach((animation) => animation.cancel());
    }

    buttonElement.style.outline = lampOutlineColor;
    buttonElement.style.outlineOffset = '2px';

    const pulseAnimation = buttonElement.animate(
      [
        {
          boxShadow: lampIdleShadow,
          filter: 'brightness(1.03) saturate(1.05)',
          transform: 'scale(1)',
        },
        {
          boxShadow: lampActiveShadow,
          filter: 'brightness(1.12) saturate(1.08)',
          transform: 'scale(1.03)',
        },
        {
          boxShadow: lampIdleShadow,
          filter: 'brightness(1.03) saturate(1.05)',
          transform: 'scale(1)',
        },
      ],
      {
        duration: 520,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        iterations: 1,
        fill: 'forwards',
      },
    );

    pulseAnimation.onfinish = () => {
      buttonElement.style.boxShadow = lampIdleShadow;
      buttonElement.style.filter = 'brightness(1.03) saturate(1.05)';
      buttonElement.style.transform = '';
      buttonElement.style.outline = lampOutlineColor;
      buttonElement.style.outlineOffset = '2px';
      buttonElement.style.backgroundColor = lampButtonBackground;
      buttonElement.style.borderColor = lampButtonBorder;
      buttonElement.style.color = lampIconColor;
    };
  };

  const shouldRenderMainTour = isMainPage && (isTourActive || shouldForceStart || wasTourActive) && (!neverShowTour || shouldForceStart);

  if (shouldRenderMainTour && isSavedStepValid && !hasExplicitRequestedStep) {
    const savedTourStep = tourSteps[currentMainStepIndex];
    if (savedTourStep && savedTourStep.path !== pagePath) {
      window.location.href = `${savedTourStep.path}?walkthrough=1&step=${currentMainStepIndex}`;
      return;
    }
  }

  if (shouldRenderMainTour) {
    const panel = createPanelShell('bottom-4 right-4');
    const cardHost = document.createElement('div');
    panel.appendChild(cardHost);
    document.body.appendChild(panel);

    const endTour = () => {
      closeTourIntoLightbulb({ persistNeverShow: true, showNudge: true });
    };

    const dismissTour = () => {
      localStorage.removeItem(tourStorage.active);
      localStorage.removeItem(tourStorage.step);
      clearStepEmphasis();
      panel.remove();
    };

    const closeTourIntoLightbulb = ({ persistNeverShow = false, showNudge = false } = {}) => {
      if (persistNeverShow) {
        localStorage.setItem(tourStorage.neverShow, '1');
      }
      localStorage.removeItem(tourStorage.active);
      localStorage.removeItem(tourStorage.step);

      clearStepEmphasis();

      const widget = ensureLightbulbWidget();
      const mountedBulb = widget.button;

      const tourCard = cardHost.querySelector('.card');
      if (!tourCard) {
        panel.remove();
        showLightbulbWidgetInFooter();
        return;
      }

      showLightbulbWidgetInFooter();
      if (mountedBulb) {
        mountedBulb.style.visibility = 'hidden';
      }

      const restoreFallback = setTimeout(() => {
        showLightbulbWidgetInFooter();
      }, 1100);

      const cardRect = tourCard.getBoundingClientRect();
      const measuredRect = mountedBulb ? mountedBulb.getBoundingClientRect() : null;
      const bulbSize = measuredRect ? measuredRect.width : 48;
      const startCenterX = cardRect.left + (cardRect.width / 2);
      const startCenterY = cardRect.top + (cardRect.height / 2);
      const targetCenterX = measuredRect
        ? (measuredRect.left + (measuredRect.width / 2))
        : (16 + (bulbSize / 2));
      const targetLiftPx = 16;
      const targetCenterY = measuredRect
        ? (measuredRect.top + (measuredRect.height / 2) - targetLiftPx)
        : (window.innerHeight - 16 - (bulbSize / 2) - targetLiftPx);
      const deltaX = targetCenterX - startCenterX;
      const deltaY = targetCenterY - startCenterY;
      const startScale = Math.max(1.2, Math.min(4.4, (Math.min(cardRect.width, cardRect.height) / bulbSize) * 0.9));

      if (widget.panel) {
        widget.panel.classList.add('hidden');
      }

      widget.wrap.style.display = '';
      widget.wrap.style.position = 'fixed';
      widget.wrap.style.left = `${startCenterX - (bulbSize / 2)}px`;
      widget.wrap.style.top = `${startCenterY - (bulbSize / 2)}px`;
      widget.wrap.style.zIndex = '95';
      widget.wrap.style.pointerEvents = 'none';
      widget.wrap.style.transform = `translate3d(0,0,0) scale(${startScale})`;
      widget.wrap.style.opacity = '1';

      if (widget.wrap.parentElement !== document.body) {
        document.body.appendChild(widget.wrap);
      }

      if (mountedBulb) {
        mountedBulb.style.visibility = '';
        mountedBulb.style.opacity = '1';
      }

      tourCard.style.transformOrigin = 'center center';
      tourCard.style.willChange = 'transform, opacity, filter, border-radius';

      widget.wrap.animate(
        [
          {
            transform: `translate3d(0,0,0) scale(${startScale})`,
            opacity: 1,
          },
          {
            transform: `translate3d(${deltaX}px, ${deltaY}px, 0) scale(1)`,
            opacity: 1,
          },
        ],
        {
          duration: 760,
          easing: 'cubic-bezier(0.22, 0.7, 0.2, 1)',
          fill: 'forwards',
        },
      );

      const animation = tourCard.animate(
        [
          {
            transform: 'translate3d(0,0,0) scale(1)',
            borderRadius: '1.25rem',
            opacity: 1,
            filter: 'blur(0px)',
          },
          {
            transform: `translate3d(${deltaX * 0.36}px, ${deltaY * 0.36}px, 0) scale(0.82)`,
            borderRadius: '1.6rem',
            opacity: 0.7,
            filter: 'blur(0.5px)',
            offset: 0.44,
          },
          {
            transform: `translate3d(${deltaX * 0.68}px, ${deltaY * 0.68}px, 0) scale(0.46)`,
            borderRadius: '999px',
            opacity: 0.32,
            filter: 'blur(1.2px)',
            offset: 0.72,
          },
          {
            transform: `translate3d(${deltaX}px, ${deltaY}px, 0) scale(0.16)`,
            borderRadius: '999px',
            opacity: 0,
            filter: 'blur(2px)',
          },
        ],
        {
          duration: 720,
          easing: 'cubic-bezier(0.2, 0.9, 0.2, 1)',
          fill: 'forwards',
        },
      );

      animation.onfinish = () => {
        clearTimeout(restoreFallback);
        panel.remove();
        showLightbulbWidgetInFooter();
        widget.wrap.style.display = '';
        widget.wrap.style.opacity = '1';
        widget.wrap.style.visibility = 'visible';
        widget.wrap.style.transform = '';
        if (widget.button) {
          widget.button.style.visibility = '';
          widget.button.style.opacity = '';
          widget.button.style.transform = '';
          pulseLightbulbOnce(widget.button);
        }
        if (showNudge) {
          showLightbulbNudge();
        }
      };
    };

    const disableTourPermanently = () => {
      closeTourIntoLightbulb({ persistNeverShow: true });
    };

    const closeTourTemporarily = () => {
      closeTourIntoLightbulb({ persistNeverShow: false });
    };

    const goToStep = (nextIndex) => {
      if (nextIndex < 0 || nextIndex >= tourSteps.length) {
        return;
      }

      localStorage.setItem(tourStorage.active, '1');
      localStorage.setItem(tourStorage.step, String(nextIndex));
      const nextStep = tourSteps[nextIndex];
      if (nextStep.path === pagePath) {
        currentMainStepIndex = nextIndex;
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set('walkthrough', '1');
        nextUrl.searchParams.set('step', String(nextIndex));
        window.history.replaceState({}, '', nextUrl.toString());
        renderStep();
        return;
      }

      window.location.href = `${nextStep.path}?walkthrough=1&step=${nextIndex}`;
    };

    const renderStep = () => {
      const step = tourSteps[currentMainStepIndex];
      if (!step) {
        return;
      }

      localStorage.setItem(tourStorage.step, String(currentMainStepIndex));

      applyStepEmphasis(step);

      const controls = [];
      if (currentMainStepIndex === 0) {
        controls.push(makeButton({
          label: "Don't show again",
          classes: 'btn btn-ghost btn-sm',
          onClick: disableTourPermanently,
        }));
      } else {
        controls.push(makeButton({
          label: 'Skip',
          classes: 'btn btn-ghost btn-sm',
          onClick: closeTourTemporarily,
        }));
      }

      if (currentMainStepIndex > 0) {
        controls.push(makeButton({
          label: 'Back',
          classes: 'btn btn-outline btn-sm',
          onClick: () => goToStep(currentMainStepIndex - 1),
        }));
      }

      const isLastStep = currentMainStepIndex === tourSteps.length - 1;
      controls.push(makeButton({
        label: isLastStep ? 'Finish' : 'Next',
        classes: 'btn btn-primary btn-sm',
        onClick: () => {
          if (isLastStep) {
            endTour();
            return;
          }
          goToStep(currentMainStepIndex + 1);
        },
      }));

      cardHost.innerHTML = '';
      cardHost.appendChild(createTutorialCard({
        title: `Quick Tour (${currentMainStepIndex + 1}/${tourSteps.length}): ${step.title}`,
        body: step.body,
        controls,
        onClose: closeTourTemporarily,
      }));
    };

    renderStep();
  }

  const resolveSubpageTip = () => {
    if (pagePath === '/') {
      return 'Need help getting started? Use Main Tour for a fast walkthrough of Home, Search, and Insights.';
    }
    if (pagePath === '/insights') {
      return subpageTips['/insights'];
    }
    if (pagePath.startsWith('/athlete-dashboard/') && pagePath.includes('/result/')) {
      return subpageTips['/athlete-dashboard/result'];
    }
    if (pagePath.startsWith('/athlete-dashboard/')) {
      return subpageTips['/athlete-dashboard'];
    }
    if (pagePath.startsWith('/school-dashboard/')) {
      return subpageTips['/school-dashboard'];
    }
    if (pagePath === '/insights/percentiles') {
      return subpageTips['/insights/percentiles'];
    }
    if (pagePath === '/insights/sectional-trends') {
      return subpageTips['/insights/sectional-trends'];
    }
    if (pagePath === '/insights/hypothetical') {
      return subpageTips['/insights/hypothetical'];
    }
    if (pagePath === '/insights/hypothetical/result') {
      return subpageTips['/insights/hypothetical/result'];
    }
    if (pagePath === '/insights/reports/percentiles-summary') {
      return subpageTips['/insights/reports/percentiles-summary'];
    }
    if (pagePath === '/about') {
      return subpageTips['/about'];
    }
    return 'Need a quick orientation? Start the 3-step main walkthrough.';
  };

  const shouldShowLightbulb = !shouldRenderMainTour;

  if (shouldShowLightbulb) {
    showLightbulbWidgetInFooter();
  } else {
    hideLightbulbWidget();
  }

  // Helper function to escape HTML
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});