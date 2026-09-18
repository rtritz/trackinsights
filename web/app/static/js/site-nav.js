/* Site navigation: the nav pills, cursor and hero behaviour.
 *
 * Moved out of base.html, which every page inherits. Shared by every page.
 */

// Flask owns the URLs, so they arrive on <body> rather than being
// templated into this file -- that is what lets it live here.
const HOME_URL = document.body.dataset.homeUrl || '/';
const SEARCH_URL = document.body.dataset.searchUrl || '/search';

document.addEventListener('DOMContentLoaded', function () {
  const scrollZone = document.getElementById('scroll-zone');
  const customCursor = document.getElementById('custom-cursor');
  const heroTitle = document.querySelector('.hero-title');
  const searchPill = document.getElementById('nav-search-pill');
  const searchInput = document.getElementById('navSearchInput');
  const searchClose = document.getElementById('nav-search-close');
  const searchForm = document.getElementById('navSearchForm');
  const resultsPanel = document.getElementById('nav-search-results');
  const queriesButton = document.getElementById('queries-toggle');
  const aboutButton = document.getElementById('about-toggle');
  const navbarEnd = document.querySelector('.desktop-nav');
  const mobileNavToggle = document.getElementById('mobile-nav-toggle');
  const mobileNavOverlay = document.getElementById('mobile-nav-overlay');
  const mobileNavClose = document.getElementById('mobile-nav-close');
  const mobileMenuLinks = Array.from(document.querySelectorAll('#mobile-nav-overlay .mobile-menu-link'));
  let isInZone = false;
  let isSearchOpen = false;
  let resultsPanelTimeoutId = null;

  const isMobileViewport = () => window.matchMedia('(max-width: 767px)').matches;
  const isHomePage = () => window.location.pathname === HOME_URL;
  const scrollToAbout = () => {
    const aboutSection = document.getElementById('about');
    if (!aboutSection) return;
    aboutSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  const redirectToSearchPage = () => {
    window.location.href = SEARCH_URL;
  };

  const openMobileMenu = () => {
    if (!mobileNavOverlay) return;
    mobileNavOverlay.classList.remove('hidden');
    mobileNavOverlay.classList.add('flex');
    document.body.style.overflow = 'hidden';
  };

  const closeMobileMenu = () => {
    if (!mobileNavOverlay) return;
    mobileNavOverlay.classList.add('hidden');
    mobileNavOverlay.classList.remove('flex');
    document.body.style.overflow = '';
  };

  if (mobileNavToggle) {
    mobileNavToggle.addEventListener('click', openMobileMenu);
  }

  if (mobileNavClose) {
    mobileNavClose.addEventListener('click', closeMobileMenu);
  }

  mobileMenuLinks.forEach(link => {
    if (link.textContent.trim().toLowerCase() === 'about') {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        closeMobileMenu();
        if (isHomePage()) {
          scrollToAbout();
        } else {
          window.location.href = HOME_URL + '#about';
        }
      });
    } else {
      link.addEventListener('click', closeMobileMenu);
    }
  });

  if (aboutButton) {
    aboutButton.addEventListener('click', function(e) {
      e.preventDefault();
      if (isHomePage()) {
        scrollToAbout();
      } else {
        window.location.href = HOME_URL + '#about';
      }
    });
  }

  const adjustResultsPanelBounds = () => {
    if (!resultsPanel || !searchPill || !aboutButton || !navbarEnd) return;

    const searchRect = searchPill.getBoundingClientRect();
    const aboutRect = aboutButton.getBoundingClientRect();
    const navbarRect = navbarEnd.getBoundingClientRect();

    const leftOffset = Math.max(0, searchRect.left - navbarRect.left);
    const width = Math.max(aboutRect.right - searchRect.left, 280);

    resultsPanel.style.setProperty('--results-left', `${leftOffset}px`);
    resultsPanel.style.setProperty('--results-width', `${width}px`);
  };

  const scheduleResultsPanelUpdate = () => {
    adjustResultsPanelBounds();
    requestAnimationFrame(adjustResultsPanelBounds);

    if (resultsPanelTimeoutId !== null) {
      clearTimeout(resultsPanelTimeoutId);
    }

    resultsPanelTimeoutId = setTimeout(() => {
      adjustResultsPanelBounds();
      resultsPanelTimeoutId = null;
    }, 380);
  };

  const setExpanded = (value) => {
    const expanded = value ? 'true' : 'false';
    if (searchPill) {
      searchPill.setAttribute('data-open', expanded);
      searchPill.setAttribute('aria-expanded', expanded);
      searchPill.classList.toggle('open', value);
    }
  };

  const openSearch = () => {
    if (!searchPill || isSearchOpen) return;
    isSearchOpen = true;
    setExpanded(true);
    scheduleResultsPanelUpdate();
    if (customCursor) {
      customCursor.classList.remove('active');
      customCursor.style.opacity = '0';
    }
    window.setTimeout(() => {
      if (searchInput) {
        searchInput.focus({ preventScroll: true });
        searchInput.select();
      }
    }, 180);
  };

  const closeSearch = () => {
    if (!searchPill || !isSearchOpen) return;
    isSearchOpen = false;
    setExpanded(false);
    if (resultsPanel) {
      resultsPanel.classList.remove('open');
    }
    if (searchInput) {
      searchInput.blur();
    }
  };

  if (searchPill) {
    searchPill.addEventListener('click', (event) => {
      if (event.target.closest('#nav-search-close')) {
        return;
      }
      if (!isSearchOpen) {
        openSearch();
      }
    });

    searchPill.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        if (!isSearchOpen) {
          event.preventDefault();
          openSearch();
        }
      }
    });
  }

  if (searchClose) {
    searchClose.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeSearch();
    });
  }

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isSearchOpen) {
      event.preventDefault();
      closeSearch();
    }
  });

  document.addEventListener('click', (event) => {
    if (!isSearchOpen || !searchPill) return;
    if (
      searchPill.contains(event.target) ||
      (resultsPanel && resultsPanel.contains(event.target)) ||
      (queriesButton && queriesButton.contains(event.target)) ||
      (aboutButton && aboutButton.contains(event.target))
    ) {
      return;
    }
    closeSearch();
  });

  const heroIsInteractive = () => heroTitle && !isMobileViewport() && !heroTitle.classList.contains('hero-title--static');

  if (heroTitle) {
    heroTitle.addEventListener('click', () => {
      if (!heroIsInteractive()) {
        return;
      }
      openSearch();
    });
    heroTitle.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        if (!heroIsInteractive()) {
          return;
        }
        openSearch();
      }
    });
  }

  if (scrollZone) {
    scrollZone.addEventListener('click', () => {
      if (isMobileViewport()) {
        redirectToSearchPage();
        return;
      }
      openSearch();
    });

    scrollZone.addEventListener('mouseenter', function () {
      isInZone = true;
      if (customCursor && !isSearchOpen) {
        customCursor.classList.add('active');
        customCursor.style.opacity = '1';
      }
    });

    scrollZone.addEventListener('mouseleave', function () {
      isInZone = false;
      if (customCursor) {
        customCursor.classList.remove('active');
        customCursor.style.opacity = '0';
      }
    });

    scrollZone.addEventListener('mousemove', function (e) {
      if (isInZone && customCursor) {
        customCursor.style.left = e.clientX + 'px';
        customCursor.style.top = e.clientY + 'px';
      }
    });
  }

  if (searchForm) {
    searchForm.addEventListener('submit', () => {
      if (resultsPanel && searchInput && searchInput.value.trim()) {
        resultsPanel.classList.add('open');
      }
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      if (!isSearchOpen) {
        openSearch();
      }
      if (!searchInput.value.trim() && resultsPanel) {
        resultsPanel.classList.remove('open');
      }
    });
  }

  window.addEventListener('resize', scheduleResultsPanelUpdate);

  scheduleResultsPanelUpdate();
  setExpanded(false);
});
