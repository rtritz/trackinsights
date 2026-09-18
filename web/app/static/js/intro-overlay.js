/* The Track Insights intro overlay.
 *
 * Moved out of base.html, which every page inherits. It hides itself once the page is ready, and skips entirely when a page\n * sets the ti-skip-intro flag -- switching a dashboard filter is a change of\n * view, not an arrival.
 */

document.addEventListener('DOMContentLoaded', function () {
  const overlay = document.getElementById('loading-overlay');
  const trackText = document.getElementById('track-text');
  const insightsText = document.getElementById('insights-text');

  if (!overlay) {
    return;
  }

  // Set by a page that is navigating within itself -- switching season or
  // gender on a dashboard, say. Those are changes of view, not arrivals, and
  // replaying the intro on each one makes the site feel slower than it is.
  // Read once and cleared, so it never suppresses a genuine visit.
  try {
    if (sessionStorage.getItem('ti-skip-intro')) {
      sessionStorage.removeItem('ti-skip-intro');
      overlay.remove();
      return;
    }
  } catch (error) {
    /* A browser without sessionStorage just gets the intro. */
  }

  const removeOverlay = () => {
    if (!overlay || !overlay.parentNode) {
      return;
    }
    overlay.remove();
  };

  const fallbackTimer = setTimeout(removeOverlay, 2200);

  const safeAnimate = (element, delay) => {
    if (!element) {
      return;
    }
    setTimeout(() => {
      element.classList.add('float-in');
    }, delay);
  };

  try {
    safeAnimate(trackText, 250);
    safeAnimate(insightsText, 500);

    setTimeout(() => {
      overlay.classList.add('slide-out');
      setTimeout(() => {
        clearTimeout(fallbackTimer);
        removeOverlay();
      }, 600);
    }, 700);
  } catch (_error) {
    clearTimeout(fallbackTimer);
    removeOverlay();
  }
});
