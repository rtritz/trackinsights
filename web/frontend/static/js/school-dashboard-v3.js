document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('school-dashboard-v3');
    if (!root) {
        return;
    }

    const schoolId = Number(root.dataset.schoolId);

    // Qualifier gem cut. Three to choose between -- swap the value and reload:
    //   sd3-gem-hex     six-sided stone with a facet across the crown
    //   sd3-gem-round   brilliant cut, a round stone with a highlight
    //   sd3-gem-kite    kite cut, a rotated square with a facet down one side
    const GEM_STYLE = 'sd3-gem-hex';
    const refs = {
        shell: document.getElementById('sd3-shell'),
        loading: document.getElementById('sd3-loading'),
        error: document.getElementById('sd3-error'),
        app: document.getElementById('sd3-app'),
        schoolName: document.getElementById('sd3-school-name'),
        schoolMeta: document.getElementById('sd3-school-meta'),
        filterRow: document.getElementById('sd3-filter-row'),
        logoWrap: document.getElementById('sd3-logo-wrap'),
        logo: document.getElementById('sd3-logo'),
        scorecardTitle: document.getElementById('sd3-scorecard-title'),
        rankHeadline: document.getElementById('sd3-rank-headline'),
        metricPlace: document.getElementById('sd3-metric-place'),
        metricPoints: document.getElementById('sd3-metric-points'),
        metricEntries: document.getElementById('sd3-metric-entries'),
        metricSectPlacers: document.getElementById('sd3-metric-sect-placers'),
        metricRegQualifiers: document.getElementById('sd3-metric-reg-qualifiers'),
        metricRegPlacers: document.getElementById('sd3-metric-reg-placers'),
        metricStateQualifiers: document.getElementById('sd3-metric-state-qualifiers'),
        metricStatePlacers: document.getElementById('sd3-metric-state-placers'),
        metricReturning: document.getElementById('sd3-metric-returning'),
        metricH2H: document.getElementById('sd3-metric-h2h'),
        rankSpark: document.getElementById('sd3-rank-spark'),
        closest: document.getElementById('sd3-closest'),
        regionalQualifiers: document.getElementById('sd3-regional-qualifiers'),
        stateQualifiers: document.getElementById('sd3-state-qualifiers'),
        positionBlock: document.getElementById('sd3-position-block'),
        rankDetails: document.getElementById('sd3-rank-details'),
        summarySection: document.getElementById('sd3-summary-section'),
        regionalSection: document.getElementById('sd3-regional-section'),
        regionalTabs: document.getElementById('sd3-regional-tabs'),
        stateSection: document.getElementById('sd3-state-section'),
        programRankSection: document.getElementById('sd3-program-rank-section'),
        returningSection: document.getElementById('sd3-returning-section'),
        h2hSection: document.getElementById('sd3-h2h-section'),
        scorecardSection: document.getElementById('sd3-scorecard-section'),
        scorecardStatus: document.getElementById('sd3-scorecard-status'),
        scorecard: document.getElementById('sd3-scorecard'),
        leaderboardModal: document.getElementById('sd3-leaderboard-modal'),
        leaderboardContent: document.getElementById('sd3-leaderboard-content'),
        leaderboardSubtitle: document.getElementById('sd3-leaderboard-subtitle'),
        leaderboardTitle: document.getElementById('sd3-leaderboard-title'),
        leaderboardEnrollment: document.getElementById('sd3-leaderboard-enrollment'),
        leaderboardCustom: document.getElementById('sd3-leaderboard-custom'),
        leaderboardJump: document.getElementById('sd3-leaderboard-jump'),
        leaderboardTop: document.getElementById('sd3-leaderboard-top'),
        detailModal: document.getElementById('sd3-detail-modal'),
        detailTitle: document.getElementById('sd3-detail-title'),
        detailSubtitle: document.getElementById('sd3-detail-subtitle'),
        detailContent: document.getElementById('sd3-detail-content'),
        detailEnrollment: document.getElementById('sd3-detail-enrollment'),
        detailCustom: document.getElementById('sd3-detail-custom'),
        detailJump: document.getElementById('sd3-detail-jump'),
        detailTop: document.getElementById('sd3-detail-top'),
    };

    const state = {
        gender: 'Boys',
        season: null,
        core: null,
        scorecard: null,
        leaderboard: null,
        // Which event group the leaderboard is scoped to, '' for the composite.
        leaderboardGroup: '',
        // Which of the two regional views is showing. Held here so a gender or
        // season change leaves the reader on the tab they chose.
        regionalView: 'qualifiers',
        // The event the detail popup is showing. Held here because the popup
        // reloads on every filter change, not only when it is opened.
        detailEvent: null,
        lastFocusedElement: null,
        requestId: 0,
    };

    const esc = function (value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    };

    const buildQuery = function (params) {
        const query = new URLSearchParams();
        Object.keys(params).forEach(function (key) {
            const value = params[key];
            if (value !== undefined && value !== null && value !== '') {
                query.set(key, value);
            }
        });
        return query.toString();
    };

    const showError = function (message) {
        refs.loading.classList.add('sd3-hidden');
        refs.app.classList.add('sd3-hidden');
        refs.error.classList.remove('sd3-hidden');
        refs.error.querySelector('p').textContent = message || "We couldn't load this postseason school profile.";
    };

    const prefersReducedMotion = function () {
        return !!(window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    };

    // The page behind a dialog stops scrolling while it is up.
    //
    // Without this a wheel over the dim surround scrolled the page, and a scroll
    // that reached the end of the list carried on into the page behind it -- the
    // stall-then-lurch that read as the list hesitating.
    const scrollLock = { depth: 0, overflow: '', paddingRight: '' };

    const lockPageScroll = function () {
        if (scrollLock.depth++) {
            return;
        }
        const root = document.documentElement;
        // The scrollbar goes with the overflow, and the page would jump sideways
        // by its width as it went. Hold the width open with padding instead.
        const gap = window.innerWidth - root.clientWidth;
        scrollLock.overflow = root.style.overflow;
        scrollLock.paddingRight = root.style.paddingRight;
        root.style.overflow = 'hidden';
        if (gap > 0) {
            root.style.paddingRight = gap + 'px';
        }
    };

    const unlockPageScroll = function () {
        if (!scrollLock.depth || --scrollLock.depth) {
            return;
        }
        const root = document.documentElement;
        root.style.overflow = scrollLock.overflow;
        root.style.paddingRight = scrollLock.paddingRight;
    };

    // Only the controls that will actually accept focus.
    //
    // The raw selector matches the disabled "Jump to us" button and the
    // enrollment box that is display:none until Custom is chosen. Handing the
    // Tab wrap-around to either of those focuses nothing, which drops
    // document.activeElement onto the body -- and from the body the next Tab
    // walks the page behind the dialog. That is the "focus is on the background
    // page" symptom, and this filter is the fix.
    const focusableIn = function (modal) {
        return Array.prototype.filter.call(
            modal.querySelectorAll(
                'button, [href], input, select, [tabindex]:not([tabindex="-1"])'),
            function (element) {
                return !element.disabled && element.getClientRects().length > 0;
            }
        );
    };

    const openModal = function (modal) {
        state.lastFocusedElement = document.activeElement;
        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        lockPageScroll();
        // Everything behind the dialog stops taking pointer, focus and screen
        // reader attention. The modals are siblings of the shell, so this cannot
        // reach into the dialog itself.
        if (refs.shell && 'inert' in refs.shell) {
            refs.shell.inert = true;
        }
        // The dialog takes focus, not the first control inside it: a screen
        // reader then announces the dialog rather than a Close button, and Tab
        // starts at the top of the dialog instead of one control in. On the next
        // frame, because an element cannot be focused until the style change
        // that revealed it has been applied.
        const card = modal.querySelector('.sd3-modal-card');
        // A dialog that reopens where it was last left -- 200 rows down a list
        // that has since been reloaded -- reads as a rendering fault.
        if (card) {
            card.scrollTop = 0;
        }
        window.requestAnimationFrame(function () {
            if (!modal.hidden && card && typeof card.focus === 'function') {
                card.focus();
            }
        });
    };

    const closeModal = function (modal) {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        unlockPageScroll();
        if (refs.shell && 'inert' in refs.shell) {
            refs.shell.inert = false;
        }
        // The control that opened the dialog may have been re-rendered while it
        // was up -- the rank headline is rebuilt on every ranking payload. A
        // detached element accepts focus() and does nothing with it, leaving the
        // body focused, so it is checked for rather than trusted.
        const previous = state.lastFocusedElement;
        state.lastFocusedElement = null;
        if (previous && typeof previous.focus === 'function' &&
                document.body.contains(previous)) {
            previous.focus();
        }
    };

    const trapModalFocus = function (event) {
        const modal = event.currentTarget;
        if (event.key === 'Escape') {
            closeModal(modal);
            return;
        }
        if (event.key !== 'Tab') {
            return;
        }
        const focusable = focusableIn(modal);
        if (!focusable.length) {
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        // Focus sitting on the card itself, or having escaped to the body, both
        // mean the cycle has to be restarted rather than wrapped.
        if (focusable.indexOf(active) === -1) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
            return;
        }
        if (event.shiftKey && active === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && active === last) {
            event.preventDefault();
            first.focus();
        }
    };

    const fetchJson = async function (url) {
        const response = await fetch(url);
        if (!response.ok) {
            const payload = await response.json().catch(function () { return {}; });
            throw new Error(payload.error || 'Request failed');
        }
        return response.json();
    };

    // One panel shape for all three summaries, so three independent loaders cannot
    // drift into three different layouts. Rows are key / value / extra, which is the
    // shape each of them naturally has: a meet, a season, a measure.
    // A year-over-year move, in the one format the whole page uses. Rank and
    // place improve downwards while points improve upwards, so the caller says
    // which direction counts as better rather than the helper guessing.
    // "up 1 from 2025", coloured on the move and muted on the season -- the same
    // line the statewide rank uses, so a reader learns it once. No unit: it sits
    // directly under the figure it moved, which already says places or points.
    // Whether the trend is open is a per-reader preference, and a coach who wants
    // it would otherwise re-open it on every visit. Storage can throw outright in a
    // private window or with site data blocked, so every access is guarded and the
    // page renders correctly when it returns nothing.
    const TREND_KEY = 'sd3.trend.open';
    // Open unless the reader has closed it. The plot is the whole of the Season
    // Trends section now, so a collapsed default leaves that section rendering as
    // a heading over the word "Trend Graph".
    const trendPreference = function () {
        try {
            const stored = window.localStorage.getItem(TREND_KEY);
            return stored === null ? true : stored === '1';
        } catch (error) {
            return true;
        }
    };
    const rememberTrend = function (isOpen) {
        try {
            window.localStorage.setItem(TREND_KEY, isOpen ? '1' : '0');
        } catch (error) {
            // A reader who cannot store preferences still gets a working toggle.
        }
    };

    // A year-over-year move: an arrow, the size of the move, and the season it
    // is measured against.
    //
    // The arrow and the figure were a glyph and a digit separated by an ordinary
    // word space, and at the size this rendered "▼ 4" came across as two marks
    // of similar weight pointing opposite ways rather than as one reading.
    // Three changes fix it: the arrow is deliberately smaller than the figure it
    // qualifies rather than its equal, the gap between them is a real one, and
    // the pair sits in a single coloured token -- so what is coloured is exactly
    // what moved, and the season stays muted outside it.
    const movementArrow = function (value) {
        return '<span class="sd3-move ' + (value > 0 ? 'sd3-move-up' : 'sd3-move-down') + '">' +
            '<span class="sd3-move-arrow" aria-hidden="true">' +
                (value > 0 ? '▲' : '▼') + '</span>' +
            '<span>' + Math.abs(value) + '</span>' +
        '</span>';
    };

    const movementLine = function (value, season, title) {
        if (value === null || value === undefined || !season) {
            return '';
        }
        const body = value === 0
            ? '<span class="sd3-move-flat">no change</span>'
            : movementArrow(value);
        return '<div class="sd3-move-line"' + (title ? ' title="' + esc(title) + '"' : '') + '>' +
            body + '<span class="sd3-move-since"> from ' + esc(season) + '</span></div>';
    };

    // ---------------------------------------------------------------- Playoffs
    // One slot of the metric row: a figure, the noun that says what it counts,
    // and a line of context under it.
    //
    // The header label is gone: "PLACE" over "7th of 16" spent a line naming
    // what the next line already said. Carrying the noun inline reads as a
    // sentence -- "7th of 16 place" -- and gives the figure the height back.
    // One slot of the metric row: a label, a value with an optional inline
    // denominator, and a line of context. Three lines in every slot, so the five
    // read as one row and the large numerals stay flush left where they form a
    // scannable line across the card.
    //
    // The unit rode with the value for a while -- "7th of 14 place" -- which
    // only parses when the unit is a noun completing the phrase, as in "42
    // points". For the other four it read as a fragment.
    const metricSlot = function (target, spec) {
        if (!target) {
            return;
        }
        const den = (spec.denominator === null || spec.denominator === undefined)
            ? ''
            : '<span class="sd3-metric-den"> of ' + esc(spec.denominator) + '</span>';
        const context = spec.contextHtml !== undefined && spec.contextHtml !== ''
            ? spec.contextHtml
            : esc(spec.context || '—');
        target.innerHTML =
            '<div class="sd3-metric-label">' + esc(spec.label) + '</div>' +
            '<div class="sd3-metric-value' + (spec.tone ? ' ' + spec.tone : '') + '"' +
                (spec.title ? ' title="' + esc(spec.title) + '"' : '') + '>' +
                esc(spec.value) + den +
            '</div>' +
            '<div class="sd3-metric-context"' +
                (spec.contextTitle ? ' title="' + esc(spec.contextTitle) + '"' : '') + '>' +
                context +
            '</div>';
    };

    // A slot with nothing to show keeps its label and its three lines, so the
    // row stays a row while one of its four loaders is still in flight.
    const emptySlot = function (target, label, reason) {
        metricSlot(target, { label: label, value: '—', context: reason });
    };

    const plural = function (count, word) {
        return count + ' ' + word + (count === 1 ? '' : 's');
    };

    // One of the two forward-looking readings: a figure, the phrase that finishes
    // it, and a line of context under it.
    //
    // The same three parts, in the same order and at the same sizes, as every
    // slot in the summary card -- so the page has one way of presenting a
    // reading rather than two. These were a small uppercase label over a single
    // 13px line carrying the figure, its denominator and a second ratio at one
    // weight: "8 of 15 athletes · 42 of 60 individual points" gave equal
    // billing to the answer and its footnote, and neither read as the reading.
    //
    // The label those carried is gone: each of these now sits under its own
    // section heading, which says the same thing one line higher up.
    const lookaheadSlot = function (target, spec) {
        if (!target) {
            return;
        }
        target.innerHTML =
            '<div class="sd3-lookahead"' +
                (spec.title ? ' title="' + esc(spec.title) + '"' : '') + '>' +
                '<div class="sd3-metric-value' + (spec.tone ? ' ' + spec.tone : '') + '">' +
                    spec.valueHtml +
                    (spec.qualifier
                        ? '<span class="sd3-metric-den"> ' + esc(spec.qualifier) + '</span>'
                        : '') +
                '</div>' +
                (spec.context
                    ? '<div class="sd3-metric-context">' + esc(spec.context) + '</div>'
                    : '') +
            '</div>';
    };

    // Nothing to show keeps the panel's shape: the em dash sits where the figure
    // goes and the reason sits where its context would.
    const emptyLookahead = function (target, reason) {
        lookaheadSlot(target, { valueHtml: '&mdash;', context: reason });
    };

    const GRADE_WORD = {
        FR: 'Freshman', SO: 'Sophomore', JR: 'Junior', SR: 'Senior — graduating',
    };

    // The class year as a pill, in the letters coaches use. It is what ties
    // these rows to the Returning slot: a sophomore a second off the cut is a
    // different story from a senior at the same margin.
    //
    // The results table emits this same helper's class, so one fact keeps one
    // marking across the page without two rules having to be kept in step.
    const gradeChip = function (grade) {
        if (!grade) {
            return '';
        }
        return '<span class="sd3-grade' + (grade === 'SR' ? ' is-sr' : '') +
            '" title="' + esc(GRADE_WORD[grade] || grade) + '">' +
            esc(String(grade).toUpperCase()) + '</span>';
    };

    // Roman numerals stay as they are; JR and SR are words.
    const ROMAN_SUFFIX = /^(?:II|III|IV|V)$/;
    const GEN_SUFFIX = /^(JR|SR)(\.?)$/;

    // Names are stored shouting. All-caps is measurably slower to read and this
    // page is already dense, but the naive fix -- lowercase, then capitalise the
    // first letter -- misspells real people: O'Brien becomes O'brien and McBride
    // becomes Mcbride. Checked against all 27,115 names in the database.
    const titleName = function (value) {
        if (!value) {
            return '';
        }
        return String(value).split(' ').map(function (word) {
            if (!word) {
                return word;
            }
            const bare = word.toUpperCase();
            if (ROMAN_SUFFIX.test(bare)) {
                return bare;
            }
            const gen = GEN_SUFFIX.exec(bare);
            if (gen) {
                return gen[1].charAt(0) + gen[1].charAt(1).toLowerCase() + gen[2];
            }
            return word.split('-').map(function (part) {
                const lower = part.toLowerCase();
                if (!lower) {
                    return part;
                }
                // The first *letter*, not the first character: a nickname in
                // quotes or a name in brackets opens with punctuation.
                let out = lower.replace(/[a-z]/, function (c) { return c.toUpperCase(); });
                // Mc, but never Mac. MACIAS, MACKENZIE and MACEY are ordinary
                // names that happen to begin with those three letters, and
                // MacIas would be a misspelling; MC- is reliably the prefix.
                out = out.replace(/^(\W*)Mc([a-z])/, function (m, pre, c) {
                    return pre + 'Mc' + c.toUpperCase();
                });
                // O'Brien and A'Lee take a capital after the apostrophe;
                // Ahli'yla does not. One letter before it is what separates them.
                out = out.replace(/^(\W*[A-Za-z])'([a-z])/, function (m, a, b) {
                    return a + "'" + b.toUpperCase();
                });
                return out;
            }).join('-');
        }).join(' ');
    };

    // What to print in the name column of any entry row.
    //
    // Only athlete names get title-cased: those are stored shouting, which is what
    // titleName exists for.
    //
    // A relay is named "Relay", not by its school. The payload carries the school
    // name -- which on this page is the school whose dashboard the reader is
    // already on, printed once per relay row under a masthead that says it. It
    // also had to be printed as filed rather than title-cased, because running
    // "21st Century Charter School" through titleName produced "21St". One word
    // instead answers what the cell is actually for: this entry is a squad, not
    // a person, so there is no name to click.
    const entryName = function (row) {
        const isRelay = row.entry_type === 'relay' || !row.athlete_id;
        return isRelay ? 'Relay' : titleName(row.name);
    };

    // The athlete cell shared by the three lists. A relay has no legs on record,
    // so it names itself rather than standing empty -- an empty leading cell
    // reads as a broken row.
    const whoCell = function (row) {
        if (row.entry_type === 'relay' || !row.athlete_id) {
            return '<span class="sd3-qual-relay">' + esc(entryName(row)) + '</span>';
        }
        return '<a class="sd3-link" href="/athlete-dashboard/' + row.athlete_id + '">' +
            esc(entryName(row)) + '</a>' + gradeChip(row.grade);
    };

    // The stage cells a school reached, keyed by stage name.
    const stagesOf = function (core) {
        const byStage = {};
        (((core && core.stage_results) || {}).stages || []).forEach(function (stage) {
            byStage[stage.stage] = stage;
        });
        return byStage;
    };

    // Rank history. Rank 1 is best but smallest, so a bare line is ambiguous.
    // The seasons sit under each point, the line is drawn inverted so better is
    // higher, and it is toned green when the recent seasons are moving up the
    // table and amber otherwise. Each point carries its exact rank on hover.
    //
    // The SVG scales to whatever height its panel gives it rather than carrying a
    // fixed one, so the plot breathes instead of being flattened into a strip.
    const buildRankSpark = function (history) {
        if (!history || history.length < 2) {
            return '';
        }
        // Spanning the whole box, so the viewBox is wide: at this width a squarer
        // one would render the plot taller than everything above it.
        const W = 900;
        const H = 132;
        const PAD_X = 26;
        const PAD_Y = 16;
        const ranks = history.map(function (h) { return h.rank; });
        const best = Math.min.apply(null, ranks);
        const worst = Math.max.apply(null, ranks);
        const span = Math.max(1, worst - best);
        const pts = history.map(function (h, i) {
            return {
                x: PAD_X + (i / (history.length - 1)) * (W - PAD_X * 2),
                y: PAD_Y + ((h.rank - best) / span) * (H - PAD_Y * 2),
                h: h,
            };
        });
        const line = pts.map(function (pt, i) {
            return (i ? 'L' : 'M') + pt.x.toFixed(1) + ' ' + pt.y.toFixed(1);
        }).join(' ');
        // Every point is the same size: the most recent season is already the one
        // the year labels end on, and sizing it larger read as a different kind of
        // data point rather than the same measure one year later.
        const dots = pts.map(function (pt) {
            return '<circle cx="' + pt.x.toFixed(1) + '" cy="' + pt.y.toFixed(1) +
                '" r="3.4" fill="currentColor">' +
                '<title>' + esc(pt.h.season + ': ' + ordinalOf(pt.h.rank) + ' of ' +
                    pt.h.total_schools) + '</title></circle>';
        }).join('');
        const years = pts.map(function (pt) {
            return '<span style="left:' + ((pt.x / W) * 100).toFixed(2) + '%">' +
                esc(pt.h.season) + '</span>';
        }).join('');
        // Toned on the recent seasons, not on the whole span. A program that was
        // 60th eight years ago and has slid every season since still ends the
        // span ahead of where it started, and a green line over a plot that has
        // been falling for four years says the opposite of what the plot shows.
        // The window is the last three points -- one season is noise, and the
        // history is rarely long enough for more.
        const RECENT_SEASONS = 3;
        const from = history[Math.max(0, history.length - RECENT_SEASONS)];
        // Rank 1 is best, so an improvement is a fall in the number. Flat counts
        // as amber with the rest: "nothing is improving" is one message to a
        // coach, whether the line is level or falling.
        const tone = from.rank - history[history.length - 1].rank > 0 ? 'is-up' : 'is-down';

        // Collapsed by default: it is the one element here a reader consults rather
        // than scans, and open it costs more vertical room than everything above it.
        return '<details class="sd3-trend-details"' + (trendPreference() ? ' open' : '') + '>' +
            '<summary class="sd3-trend-summary">Trend Graph</summary>' +
            // The hint belongs with the plot it explains, not on the closed
            // summary where it describes something the reader cannot see.
            '<div class="sd3-spark-caption">Statewide rank across ' + history.length +
                ' seasons <span class="sd3-spark-hint">\u2014 higher is better</span></div>' +
            '<div class="sd3-spark-plot">' +
                // Uniform scaling: stretching the viewBox to fill the panel would
                // squash the dots into ovals. A 2:1 viewBox at full width gives
                // the height the plot needs without distorting anything.
                '<svg class="sd3-spark-svg ' + tone + '" viewBox="0 0 ' + W + ' ' + H +
                    '" role="img" ' +
                    'aria-label="Statewide rank by season, best rank at the top">' +
                    '<path d="' + line + '" fill="none" stroke="currentColor" ' +
                        'stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round" ' +
                        'opacity="0.85" />' +
                    dots +
                '</svg>' +
            '</div>' +
            '<div class="sd3-spark-years">' + years + '</div>' +
        '</details>';
    };

    const renderHeader = function (core) {
        const school = core.school;
        const enrollmentLabel = school.enrollment == null
            ? 'Enrollment unavailable'
            : school.enrollment_is_exact
                ? 'Enrollment ' + school.enrollment + ' (' + school.enrollment_source_year + ')'
                : 'Enrollment ' + school.enrollment + ' (nearest ' + school.enrollment_source_year + ')';

        refs.schoolName.textContent = school.name || 'Unknown school';
        refs.schoolMeta.innerHTML = [
            school.city ? '<span>' + esc(school.city) + '</span>' : '',
            school.school_type ? '<span>' + esc(school.school_type) + '</span>' : '',
            '<span>' + esc(enrollmentLabel) + '</span>',
        ].filter(Boolean).join('<span class="sd3-meta-separator" aria-hidden="true">|</span>');
        if (school.logo_url) {
            refs.logo.src = school.logo_url;
            refs.logoWrap.classList.remove('sd3-hidden');
        } else {
            refs.logoWrap.classList.add('sd3-hidden');
        }

    };

    const renderFilters = function (core) {
        const filters = core.filters;
        const selectedGender = filters.selected_gender;
        const selectedSeason = String(filters.selected_season);

        // Years this school actually has postseason results for.
        const schoolYears = new Set(
            filters.seasons.filter(function (value) { return value !== 'all-time'; }).map(String)
        );
        // The axis we draw: every year the DB covers for this gender, so years the
        // school is missing show as struck-through gaps rather than disappearing.
        const axis = (filters.covered_seasons && filters.covered_seasons.length
            ? filters.covered_seasons
            : Array.from(schoolYears).sort()
        ).map(String);

        const genderButtons = filters.genders.map(function (gender) {
            const isOn = gender === selectedGender;
            return '<button type="button" role="radio" data-gender="' + esc(gender) + '"' +
                ' aria-checked="' + (isOn ? 'true' : 'false') + '"' +
                ' tabindex="' + (isOn ? '0' : '-1') + '">' + esc(gender) + '</button>';
        }).join('');

        // A season still being run is offered but not selectable: qualifying cutoffs
        // are read off the finished bracket, so a partial season would produce
        // confident-looking wrong numbers.
        const incomplete = filters.incomplete_seasons || {};
        const seasonPills = axis.map(function (year) {
            const hasData = schoolYears.has(year);
            const inProgress = Object.prototype.hasOwnProperty.call(incomplete, year);
            const usable = hasData && !inProgress;
            const isOn = year === selectedSeason;
            let title;
            if (inProgress) {
                title = incomplete[year];
            } else if (hasData) {
                title = year + ' postseason';
            } else {
                title = 'No postseason results for this program in ' + year;
            }
            return '<button type="button" role="radio" class="sd3-season-pill' +
                (inProgress ? ' is-in-progress' : '') + '" data-season="' + esc(year) + '"' +
                (usable ? '' : ' disabled') +
                ' aria-checked="' + (isOn ? 'true' : 'false') + '"' +
                ' tabindex="' + (isOn ? '0' : '-1') + '"' +
                ' title="' + esc(title) + '">' +
                esc(year) + (inProgress ? '<span class="sd3-pill-flag">in progress</span>' : '') +
                '</button>';
        }).join('');

        const allTimeOn = selectedSeason === 'all-time';
        const allTimeLabel = filters.season_labels['all-time'] || 'All-Time';

        // Re-rendering the row destroys the focused control, so remember which
        // group had focus and hand it back to that group's new selection.
        const focusedGroup = document.activeElement
            && refs.filterRow.contains(document.activeElement)
            && document.activeElement.closest('[role="radiogroup"]');
        const focusedGroupLabel = focusedGroup ? focusedGroup.getAttribute('aria-label') : null;

        refs.filterRow.innerHTML =
            '<div class="sd3-segmented" role="radiogroup" aria-label="Gender">' + genderButtons + '</div>' +
            '<div class="sd3-seasons" role="radiogroup" aria-label="Season">' +
                seasonPills +
                '<span class="sd3-season-divider" aria-hidden="true"></span>' +
                '<button type="button" role="radio" class="sd3-season-pill" data-season="all-time"' +
                    ' aria-checked="' + (allTimeOn ? 'true' : 'false') + '"' +
                    ' tabindex="' + (allTimeOn ? '0' : '-1') + '"' +
                    ' title="Program bests across every covered season">' + esc(allTimeLabel) + '</button>' +
            '</div>';

        if (focusedGroupLabel) {
            const restored = refs.filterRow.querySelector(
                '[role="radiogroup"][aria-label="' + focusedGroupLabel + '"] [aria-checked="true"]'
            );
            if (restored) {
                restored.focus();
            }
        }
    };

    // Arrow-key navigation within either radiogroup, per the WAI-ARIA radio pattern.
    const moveRadioFocus = function (group, current, step) {
        const options = Array.prototype.filter.call(
            group.querySelectorAll('[role="radio"]'),
            function (option) { return !option.disabled; }
        );
        if (!options.length) {
            return;
        }
        const index = options.indexOf(current);
        const next = options[(index + step + options.length) % options.length];
        next.focus();
        next.click();
    };

    // The three rounds, as one summary. Sectional place and points come from the
    // team score; every other reading is a count of entries or of scoring
    // finishes, which the stage summary already computes for all three rounds --
    // so nothing here is a second definition of anything.
    //
    // Every slot carries last season's move under it when there is one to carry.
    // Counts compare against zero perfectly well (no regional qualifiers to five
    // is a real move), so they only need the program to have run a postseason
    // last season; place and points need it to have reached the same round, which
    // is what the backend's `comparable` flag says.
    const SUMMARY_COUNT_SLOTS = [
        {
            ref: 'metricSectPlacers', stage: 'Sectional', label: 'Placers',
            countKey: 'scoring_finishes', deltaKey: 'placers_delta',
            title: 'Entries that finished in a scoring position -- the top 8 -- at ' +
                'the sectional. One relay counts once, however many athletes ran it.',
        },
        {
            ref: 'metricRegQualifiers', stage: 'Regional', label: 'Qualifiers',
            countKey: 'entries', deltaKey: 'entries_delta',
            title: 'Entries that advanced out of the sectional and competed at the ' +
                'regional. One relay counts as one entry.',
        },
        {
            ref: 'metricRegPlacers', stage: 'Regional', label: 'Placers',
            countKey: 'scoring_finishes', deltaKey: 'placers_delta',
            title: 'Entries that finished in a scoring position -- the top 8 -- at ' +
                'the regional.',
        },
        {
            ref: 'metricStateQualifiers', stage: 'State', label: 'Qualifiers',
            countKey: 'entries', deltaKey: 'entries_delta',
            title: 'Entries that advanced out of the regional and competed at the ' +
                'state finals. One relay counts as one entry.',
        },
        {
            ref: 'metricStatePlacers', stage: 'State', label: 'Placers',
            countKey: 'scoring_finishes', deltaKey: 'placers_delta',
            title: 'Entries that finished in a scoring position -- the top 9 -- at ' +
                'the state finals.',
        },
    ];

    // Every slot the summary owns, so a season with no postseason at all can
    // blank the whole card in one pass rather than naming eight ids twice.
    const SUMMARY_SLOTS = [
        { ref: 'metricPlace', label: 'Place' },
        { ref: 'metricPoints', label: 'Points' },
        { ref: 'metricEntries', label: 'Entries' },
    ].concat(SUMMARY_COUNT_SLOTS.map(function (slot) {
        return { ref: slot.ref, label: slot.label };
    }));

    const blankSummary = function (reason) {
        SUMMARY_SLOTS.forEach(function (slot) {
            emptySlot(refs[slot.ref], slot.label, reason);
        });
    };

    const renderStages = function (core) {
        const covered = (core.filters && core.filters.covered_seasons) || [];
        const firstSeason = covered.length ? Math.min.apply(null, covered) : null;
        refs.scorecardTitle.textContent = core.stage_results
            ? 'Complete Playoff Results'
            : 'School Playoff Records' + (firstSeason ? ' (from ' + firstSeason + ')' : '');

        if (!core.stage_results) {
            // All-Time hides the whole summary section, so there is nothing to
            // fill -- and filling it would leave last season's figures behind it.
            return;
        }
        const byStage = stagesOf(core);
        const deltas = core.stage_deltas || {};
        const lead = byStage.Sectional;
        if (!lead || !lead.attended) {
            blankSummary('No postseason meets attended.');
            return;
        }
        const d = deltas.Sectional || {};
        // Named even when there is nothing to compare against, so the third line
        // can say which season is missing rather than going blank.
        const priorSeason = d.season || (core.stage_results.year - 1);

        const placeMove = d.comparable
            ? movementLine(d.place_delta, d.season,
                'Placed ' + ordinalOf(d.prior_rank) + ' of ' + d.prior_total_teams +
                ' in ' + d.season +
                (d.field_changed
                    ? '. The field was a different size that season, so part of this '
                      + 'move is the field rather than the team.'
                    : ', same size field.'))
            : '';
        const pointMove = d.comparable
            ? movementLine(d.point_delta, d.season,
                'Scored ' + d.prior_points_display + ' at the sectional in ' + d.season +
                '. Points do not depend on how many teams turned up.')
            : '';
        const noPrior = 'No ' + priorSeason + ' result';

        metricSlot(refs.metricPlace, {
            label: 'Place',
            value: ordinalOf(lead.team_rank),
            denominator: lead.total_teams,
            title: lead.scoring_finishes +
                (lead.scoring_finishes === 1 ? ' scoring finish' : ' scoring finishes') +
                ' out of ' + lead.entries +
                (lead.entries === 1 ? ' entry.' : ' entries.'),
            contextHtml: placeMove,
            context: noPrior,
        });

        metricSlot(refs.metricPoints, {
            label: 'Points',
            value: lead.points_display,
            // No denominator: a sectional has no points ceiling a reader could
            // measure this against, and inventing one would imply there is.
            denominator: null,
            title: 'Sectional team points. Places one through eight score ' +
                '10-8-6-5-4-3-2-1, with ties splitting the slots they occupy.',
            contextHtml: pointMove,
            context: noPrior,
        });

        SUMMARY_COUNT_SLOTS.forEach(function (slot) {
            const cell = byStage[slot.stage] || {};
            const delta = deltas[slot.stage] || {};
            const priorCount = slot.countKey === 'entries'
                ? delta.prior_entries
                : delta.prior_scoring_finishes;
            const move = delta.count_comparable
                ? movementLine(delta[slot.deltaKey], delta.season,
                    priorCount + ' in ' + delta.season + '.')
                : '';
            metricSlot(refs[slot.ref], {
                label: slot.label,
                value: cell[slot.countKey] || 0,
                denominator: null,
                title: slot.title,
                contextHtml: move,
                context: noPrior,
            });
        });

        renderEntriesSlot();
    };

    // Entry slots filled, out of the capacity a school may enter.
    //
    // Two loaders feed this one slot -- capacity arrives with the ranking
    // payload and the stage counts with core -- so it is drawn from state by
    // whichever of them lands second rather than by either one directly.
    //
    // How many of those entries went on is the Regionals group's Qualifiers
    // reading, one row down, so this slot no longer carries it.
    const renderEntriesSlot = function () {
        const target = refs.metricEntries;
        if (!target || !state.core || !state.core.stage_results) {
            return;
        }
        const byStage = stagesOf(state.core);
        const lead = byStage.Sectional;
        if (!lead || !lead.attended) {
            return;
        }
        // Slots, not meet entries, and the word matters: this pair counts slots
        // holding a ranked mark, against the capacity a school may enter. The
        // Qualifiers readings below are meet entries. They agree for all but a
        // handful of school-seasons -- a DQ is an entry filling no slot -- which
        // is why the two carry separate nouns rather than being offered as a
        // fraction of each other.
        const slots = state.entrySlots;
        const delta = (state.core.stage_deltas || {}).Sectional || {};
        metricSlot(target, {
            label: 'Entries',
            value: slots ? slots.filled : lead.entries,
            denominator: slots ? slots.total : null,
            title: slots
                ? 'A school may enter two athletes per individual event and one relay ' +
                  'team, so a full sectional is ' + slots.total + ' slots. A slot counts ' +
                  'here once it holds a ranked mark.'
                : lead.entries + ' entries at the sectional.',
            // Year over year, like every other slot in the summary, so the eight
            // read on one basis. Capacity is the same every season, so this
            // moves only when the school enters or scores differently.
            contextHtml: (slots && typeof slots.prior_filled === 'number' && slots.prior_season)
                ? movementLine(slots.filled - slots.prior_filled, slots.prior_season,
                    slots.prior_filled + ' of this school\u2019s slots held a ranked ' +
                    'mark in ' + slots.prior_season + '.')
                : (delta.count_comparable
                    ? movementLine(delta.entries_delta, delta.season,
                        delta.prior_entries + ' sectional entries in ' + delta.season + '.')
                    : ''),
            context: 'No ' + ((slots && slots.prior_season) ||
                (state.core.stage_results.year - 1)) + ' result',
        });
    };

    // The overall statewide rank, and nothing else.
    //
    // The bar that placed it against the field and the six event-group gauges
    // have gone; the ranking behind them is untouched and still sorts on the same
    // depth-weighted composite. The rank itself is the doorway to the full
    // statewide table now, which is where the bar used to lead.
    const renderProgramRank = function (programRank) {
        if (!programRank) {
            refs.rankHeadline.innerHTML = '';
            refs.positionBlock.innerHTML = '';
            refs.rankDetails.innerHTML = '';
            refs.rankSpark.innerHTML = '';
            return;
        }

        // How the ranking is built, in two paragraphs. It describes the method
        // rather than this school, so it is fixed copy rather than anything the
        // payload carries -- info_text on the payload said the same thing in the
        // API's own words, and the two drifted.
        const slots = programRank.entry_slots;
        const METHOD = [
            'Every participant in each event is ranked statewide using their ' +
            'best playoff mark. Each ranking is then converted to a score from ' +
            '1–100, with the top-ranked athlete receiving a score of 100. ' +
            'This process is repeated for every event.',
            'A team’s Composite Score is the average of its normalized ' +
            'scores across all events. A higher Composite Score indicates ' +
            'stronger overall performance across the events.',
        ].map(function (para, i) {
            return '<p class="sd3-subtle" style="margin-top:' +
                (i ? '0.8rem' : '0.6rem') + ';">' + esc(para) + '</p>';
        }).join('');

        // The method, and nothing else. This school's own composite score used to
        // close the panel; it is the ranking's internal working, and printing it
        // under an explainer invited the reader to compare a number they cannot
        // compare -- there is no second school's score on screen to weigh it
        // against, and the rank itself already says where the program stands.
        const explainer =
            '<div class="sd3-details"><details><summary>How this works</summary>' +
                METHOD +
            '</details></div>';

        if (!programRank.is_ranked) {
            refs.rankHeadline.innerHTML =
                '<div class="sd3-rank-headline-value">Not ranked</div>' +
                '<div class="sd3-rank-headline-move">No valid postseason marks this season, ' +
                'so this program is absent from the statewide table rather than scored zero.</div>';
            refs.rankSpark.innerHTML = '';
            refs.positionBlock.innerHTML = '';
            refs.rankDetails.innerHTML = explainer;
            return;
        }

        // The arrow and the trend are the same measurement at two time-scales,
        // and they disagree for 30% of programs -- so the arrow says which season
        // it is measured against rather than standing as a bare verdict.
        const movement = (typeof programRank.rank_movement === 'number' && programRank.prior_rank)
            ? (programRank.rank_movement === 0
                ? '<span class="sd3-move-flat">unchanged</span>'
                : movementArrow(programRank.rank_movement) + ' places') +
              '<span class="sd3-move-since"> from ' + esc(programRank.prior_rank.season) + '</span>'
            : '';
        // Just the reading. The section heading already says what the figure is,
        // so repeating it in front of the number spent the headline's width on a
        // label. Clicking it opens the table the rank came out of, and it is
        // underlined so that it looks like something to click -- it is the only
        // way in now that the bar beneath it is inert.
        //
        // The percentile rides beside it, outside the link: the rank says where
        // in the order, the percentile says how far up the field, and "166th"
        // means nothing on its own without knowing the field is 394 deep. It is
        // the same figure the bar under it draws, so the two cannot disagree.
        const openLabel = 'Statewide rank out of ' +
            programRank.total_schools + ' ranked programs. See the full table.';
        const pct = rankPercent(programRank.rank, programRank.total_schools);
        const pctLabel = pct === null
            ? ''
            : ' <span class="sd3-rank-pct" title="' +
                esc('This rank sits above ' + pct.toFixed(1) + '% of the ' +
                    programRank.total_schools + ' ranked programs.') + '">(' +
                pct.toFixed(1) + ' percentile)</span>';
        refs.rankHeadline.innerHTML =
            '<button type="button" class="sd3-rank-headline-value" data-open-leaderboard ' +
                'title="' + esc(openLabel) + '">' +
                esc(ordinalOf(programRank.rank) + ' of ' + programRank.total_schools) +
            '</button>' + pctLabel +
            (movement ? '<div class="sd3-rank-headline-move">' + movement + '</div>' : '');

        if (refs.rankSpark) {
            refs.rankSpark.innerHTML = buildRankSpark(programRank.rank_history);
            const trend = refs.rankSpark.querySelector('.sd3-trend-details');
            if (trend && trend.addEventListener) {
                trend.addEventListener('toggle', function () {
                    rememberTrend(trend.open);
                });
            }
        }

        // Entry slots and the method note explain the rank rather than competing
        // with it, so they sit quietly under it.
        refs.rankDetails.innerHTML = explainer;

        // Capacity arrives with this payload but is drawn in the Entries slot of
        // the summary card, so that slot is repainted from here. Whichever of the
        // two loaders lands second is the one that completes it.
        state.entrySlots = slots || null;
        renderEntriesSlot();

        // The bar reads, it does not act. It was a second way in to the same
        // table, which put a hover state and a modal on a gauge a reader is
        // looking at rather than reaching for; the underlined rank above it is
        // the one door.
        refs.positionBlock.innerHTML = programRank.standing
            ? buildScaleBar(programRank.rank, programRank.total_schools)
            : '';

        const link = refs.rankHeadline.querySelector('[data-open-leaderboard]');
        if (link) {
            link.addEventListener('click', function () {
                state.leaderboardGroup = null;
                openModal(refs.leaderboardModal);
                void loadLeaderboard();
            });
        }
    };

    const scorecardSort = { key: 'event', dir: 1 };

    const ordinalOf = function (value) {
        const n = Number(value);
        if (!n) { return ''; }
        const mod100 = n % 100;
        if (mod100 >= 11 && mod100 <= 13) { return n + 'th'; }
        return n + (['th', 'st', 'nd', 'rd'][n % 10] || 'th');
    };

    // Rank to a share of the field: 1st fills the track, last leaves it empty.
    const rankPercent = function (rank, total) {
        if (!rank || !total) {
            return null;
        }
        return (100 * (total - rank + 1)) / total;
    };

    // The gauge under the rank. "157th of 394" does not say on its own whether
    // that is good; the fill does. It draws the share of the field this rank is
    // ahead of -- pairing a fill with the rank number instead made the bar grow
    // as the number shrank. The fill ends in a cap so the stopping point is
    // exact.
    //
    // The percentile rides the end of the fill. It is the same number the
    // headline carries, but positioned: up there it is a reading, down here it
    // labels where the bar stops, which is the one thing the bar says that a
    // figure on its own cannot. A fixed corner would not do that job -- the point
    // is that the number and the stopping point are the same place.
    const buildScaleBar = function (rank, total) {
        const pct = rankPercent(rank, total);
        if (pct === null) {
            return '';
        }
        const width = Math.max(0, Math.min(100, pct));
        // Not "ahead of total - rank": that silently overstates whenever schools
        // tie. Two sharing 1st are each ahead of 392 of 394, not 393, and this
        // helper is given only a rank and a total -- it cannot know how many
        // share the place, so it does not make a claim it cannot verify.
        const title = ordinalOf(rank) + ' of ' + total + ' ranked schools — ' +
            'ahead of ' + width.toFixed(1) + '% of the field.';

        // Near the extremes the label tucks against the edge instead of hanging
        // off the end of the track.
        let anchor;
        if (width < 12) {
            anchor = 'left:0; transform:none;';
        } else if (width > 88) {
            anchor = 'left:100%; transform:translateX(-100%);';
        } else {
            anchor = 'left:' + width.toFixed(1) + '%; transform:translateX(-50%);';
        }

        return '<span class="sd3-scale" title="' + esc(title) + '">' +
            '<span class="sd3-scale-track' + (width < 50 ? ' is-below' : '') + '">' +
                '<span class="sd3-scale-fill" style="width:' + width.toFixed(1) + '%;">' +
                    '<span class="sd3-scale-cap"></span>' +
                '</span>' +
            '</span>' +
            '<span class="sd3-scale-values">' +
                '<span class="sd3-scale-pct" style="' + anchor + '">' +
                    width.toFixed(1) + '%</span>' +
            '</span>' +
        '</span>';
    };

    const renderScorecard = function (scorecard) {
        if (!scorecard || !scorecard.rows || !scorecard.rows.length) {
            refs.scorecard.innerHTML = '<div class="sd3-note sd3-subtle">No postseason results available.</div>';
            return;
        }

        const rows = scorecard.rows.slice();

        if (scorecardSort.key === 'name') {
            rows.sort(function (a, b) {
                return String(a.name || '~').localeCompare(String(b.name || '~')) * scorecardSort.dir;
            });
        } else if (String(scorecardSort.key).indexOf('stage:') === 0) {
            // Sort on that stage's place; rows that never reached it sort last.
            const stageKey = String(scorecardSort.key).slice(6);
            rows.sort(function (a, b) {
                const ac = (a.stages || {})[stageKey];
                const bc = (b.stages || {})[stageKey];
                const ap = ac && ac.place ? ac.place : Number.MAX_SAFE_INTEGER;
                const bp = bc && bc.place ? bc.place : Number.MAX_SAFE_INTEGER;
                return (ap - bp) * scorecardSort.dir;
            });
        } else if (scorecardSort.key === 'sectional') {
            // Furthest stage first, then place within it, so the column sorts the
            // way it reads. No postseason result sorts last either way.
            const stageRank = { State: 0, Regional: 1, Sectional: 2 };
            rows.sort(function (a, b) {
                const as = stageRank[a.final_stage];
                const bs = stageRank[b.final_stage];
                const asafe = as === undefined ? 99 : as;
                const bsafe = bs === undefined ? 99 : bs;
                if (asafe !== bsafe) {
                    return (asafe - bsafe) * scorecardSort.dir;
                }
                const ap = a.final_place || Number.MAX_SAFE_INTEGER;
                const bp = b.final_place || Number.MAX_SAFE_INTEGER;
                return (ap - bp) * scorecardSort.dir;
            });
        } else if (scorecardSort.key === 'rank') {
            // Unentered events sort last whichever way the column is pointed.
            rows.sort(function (a, b) {
                const ar = a.rank || Number.MAX_SAFE_INTEGER;
                const br = b.rank || Number.MAX_SAFE_INTEGER;
                return (ar - br) * scorecardSort.dir;
            });
        }
        // key 'event' keeps the backend order: events in schedule order, best athlete first.

        // All-Time is a records board: no season, so no stages and no statewide
        // rank -- the columns that mean something are who holds the mark and when.
        const isRecords = scorecard.mode === 'records';
        // Only the stages this school reached. A State column is dead space for 58%
        // of schools, and a column that appears only when earned says something by
        // being there at all.
        const stages = isRecords ? [] : (scorecard.stages_present || []);

        const head = isRecords
            ? '<thead><tr>' +
                '<th data-sort="event">Event</th>' +
                '<th data-sort="name">Athlete</th>' +
                '<th>Mark</th>' +
                '<th>Season</th>' +
              '</tr></thead>'
            : '<thead><tr>' +
                '<th data-sort="event">Event</th>' +
                '<th data-sort="name">Athlete</th>' +
                stages.map(function (stage) {
                    return '<th data-sort="stage:' + esc(stage) + '" class="sd3-stage-col"' +
                        ' title="Mark and place at the ' + esc(stage) +
                        '. Where a season ended, how far off the qualifying mark.">' +
                        esc(stage) + ' Result</th>';
                }).join('') +
                '<th data-sort="rank" title="Where the best of these marks placed among every athlete in the state who contested the event. The bold cell is the mark being ranked.">State Rank</th>' +
              '</tr></thead>';

        // One stage, one cell: the mark on top, what it earned underneath. The gap
        // sits in the cell where the season ended, which is the only place it can
        // mean anything.
        const stageCell = function (row, stage) {
            const cell = (row.stages || {})[stage];
            if (!cell) {
                return '<td data-label="' + esc(stage) + '" class="sd3-stage-cell is-blank">' +
                    '<span class="sd3-of">&mdash;</span></td>';
            }
            const isBest = row.best_stage === stage;
            // A sentinel (NT, DQ) is shown as itself: they were at this meet, and a
            // blank cell would claim they never got there.
            const noMark = cell.has_mark === false;
            const place = cell.place ? ordinalOf(cell.place) : '';
            let note = '';
            if (cell.round === 'Prelim') {
                note = '<span class="sd3-sect-note">in prelims</span>';
            } else if (row.final_stage === stage) {
                const barNote = row.cutoff_path === 'auto'
                    ? esc(row.cutoff_display) + ' took the last automatic spot at this meet'
                    : esc(row.cutoff_display) + ' took the last callback slot';
                if (row.qualified_did_not_compete) {
                    note = '<span class="sd3-sect-qualified" title="Had the mark to advance (' +
                        barNote + ') but does not appear at the next round.">qualified, did not run</span>';
                } else if (row.tied_cutoff) {
                    note = '<span class="sd3-sect-note" title="Equalled the qualifying mark (' + barNote +
                        '). Which tied athletes advanced was settled by misses, which the results do not record.">' +
                        'tied the cutoff</span>';
                } else if (row.gap_display) {
                    note = '<span class="sd3-sect-gap" title="' + barNote + '">' +
                        esc(row.gap_display) + ' off cut</span>';
                }
            }
            // Mark on top, what it earned beneath. Side by side the three stage
            // columns ran too wide to scan, and the mark is the thing the eye wants
            // first.
            const sub = (place ? esc(place) : '') + note;
            return '<td data-label="' + esc(stage) + '" class="sd3-stage-cell' +
                    (isBest ? ' is-best' : '') + (noMark ? ' is-nomark' : '') + '">' +
                '<span class="sd3-stage-mark"' +
                    (noMark ? ' title="Competed here but posted no valid mark"' : '') +
                    (isBest ? ' title="Best of this athlete\u2019s postseason marks -- the one the statewide rank uses"' : '') +
                    '>' + esc(cell.mark_display) + '</span>' +
                (sub ? '<span class="sd3-stage-sub">' + sub + '</span>' : '') +
            '</td>';
        };

        let lastEvent = null;
        const body = rows.map(function (row) {
            const newEvent = row.event !== lastEvent;
            lastEvent = row.event;
            // On the records board the row carrying the event name is tinted, so each
            // event's records read as a block headed by its own first line.
            const band = isRecords && newEvent ? ' is-event-head' : '';

            if (row.entry_type === 'none') {
                if (isRecords) {
                    return '<tr class="sd3-athlete-row is-empty' + band + '">' +
                        '<td data-label="Event">' + esc(row.event) + '</td>' +
                        '<td colspan="3" class="sd3-no-entry">no mark on record</td>' +
                    '</tr>';
                }
                return '<tr class="sd3-athlete-row is-empty">' +
                    '<td data-label="Event">' + esc(row.event) + '</td>' +
                    '<td data-label="Athlete" colspan="' + (stages.length + 1) +
                        '" class="sd3-no-entry">no entry &mdash; no points available here</td>' +
                    '<td data-label="State Rank" class="sd3-rank-cell"><span class="sd3-of">&mdash;</span></td>' +
                '</tr>';
            }

            const name = row.athlete_id
                ? '<a class="sd3-link" href="/athlete-dashboard/' + row.athlete_id + '">' +
                  esc(entryName(row)) + '</a>'
                : esc(entryName(row));
            // Through the shared helper, so the table and the playoffs card
            // cannot render this fact two different ways.
            const grade = gradeChip(row.grade);
            // Same gauge as the group tiles: a wide track, a notch at the state
            // median, a triangle at this mark, and the numbers underneath.
            // No bar here. A rank is a position, so a fill beside it always ran the
            // opposite way to the number; and with three stage columns already in the
            // row, the plain figure is both lighter and unambiguous. The gauges stay
            // on the group tiles, where the question is "roughly where" rather than
            // "exactly who".
            const rank = row.rank
                ? '<button type="button" class="sd3-rank-num" data-open-event-rankings="' +
                  esc(row.event) + '" title="' +
                  esc('See all ' + row.rank_total + ' ranked on ' + row.event + '.') + '">' +
                  esc(row.rank) +
                  ' <span class="sd3-of">/ ' + esc(row.rank_total) + '</span></button>'
                : '<span class="sd3-of">&mdash;</span>';

            const eventCell = '<td data-label="Event">' +
                (newEvent
                    ? esc(row.event)
                    : '<span class="sd3-event-cont">' + esc(row.event) + '</span>') + '</td>';

            if (isRecords) {
                return '<tr class="sd3-athlete-row' + (newEvent ? ' is-event-start' : '') + band + '">' +
                    eventCell +
                    '<td data-label="Athlete">' +
                        (row.record_position
                            ? '<span class="sd3-record-pos">' + esc(row.record_position) + '</span>'
                            : '') +
                        name + '</td>' +
                    '<td data-label="Mark" class="sd3-num">' + esc(row.mark_display) + '</td>' +
                    '<td data-label="Season" class="sd3-num sd3-of">' + esc(row.year || '—') + '</td>' +
                '</tr>';
            }

            // RQ / ST rather than one trophy. The stage columns already carry the
            // fact, so this is recognition rather than analysis -- and a badge beside
            // a name is the part an athlete actually wants to see.
            const cells = row.stages || {};
            // The letters carry the meaning at a glance; the cut and the colour
            // carry the rank of it. The stone is a separate element from the label
            // because the clip-path that cuts the gem would cut the text with it.
            // GEM_STYLE at the top of this file switches between the three cuts.
            const gem = function (kind, letters, label) {
                return ' <span class="sd3-qual-badge is-' + kind + '" title="' + esc(label) +
                    '" aria-label="' + esc(label) + '">' +
                    '<span class="sd3-gem ' + GEM_STYLE + '"></span>' +
                    '<span class="sd3-gem-label">' + letters + '</span>' +
                '</span>';
            };
            const badge = cells.State
                ? gem('state', 'SQ', 'State Finals qualifier')
                : (cells.Regional ? gem('regional', 'RQ', 'Regional qualifier') : '');
            return '<tr class="sd3-athlete-row' + (newEvent ? ' is-event-start' : '') + '">' +
                eventCell +
                '<td data-label="Athlete"><span class="sd3-name-cell">' +
                    name + grade + badge + '</span></td>' +
                stages.map(function (stage) { return stageCell(row, stage); }).join('') +
                '<td data-label="State Rank" class="sd3-rank-cell">' + rank + '</td>' +
            '</tr>';
        }).join('');

        refs.scorecard.innerHTML =
            '<div class="sd3-table-scroll"><table class="sd3-scorecard-table">' +
            head + '<tbody>' + body + '</tbody></table></div>';


        refs.scorecard.querySelectorAll('th[data-sort]').forEach(function (th) {
            th.addEventListener('click', function () {
                const key = th.getAttribute('data-sort');
                scorecardSort.dir = scorecardSort.key === key ? -scorecardSort.dir : 1;
                scorecardSort.key = key;
                renderScorecard(scorecard);
            });
        });
    };

    // No column header: the line above the figure says what is being compared, and
    // says it in full -- this season's sectional team against that season's, not
    // some abstract "head to head".
    // The simulated dual, as a footer reading. It answers a question the place
    // and points deltas cannot: those are contaminated by how the rest of the
    // sectional changed, while this holds the opponent fixed and isolates the
    // roster. But it is not a result, so it sits below the three that are.
    const renderSeasonH2H = function (payload) {
        const target = refs.metricH2H;
        if (!target) {
            return;
        }
        if (!payload || !payload.available || !payload.seasons.length) {
            emptyLookahead(target,
                (payload && payload.reason) || 'No earlier season to compare against.');
            return;
        }
        const latest = payload.seasons[0];
        const margin = latest.points_for - latest.points_against;
        const tone = margin > 0 ? 'is-up' : (margin < 0 ? 'is-down' : '');
        const letter = latest.result === 'WIN' ? 'W'
            : (latest.result === 'LOSS' ? 'L' : 'T');
        lookaheadSlot(target, {
            // Spaced, as a score is written. Closed up around an en dash,
            // "55–47" read as one hyphenated figure rather than as two
            // scores facing each other across a result.
            valueHtml: esc(letter) + ' <span class="sd3-score">' +
                esc(latest.points_for + ' – ' + latest.points_against) + '</span>',
            qualifier: 'vs ' + latest.season + ' roster',
            // Required. The number is hypothetical and has to announce itself as
            // such, or it reads as a meet that happened.
            context: 'Simulated dual · ' + plural(latest.events_won, 'event') +
                ' won, ' + latest.events_lost + ' lost',
            tone: tone,
            title: payload.year + ' sectional team vs ' + latest.season + ', both ' +
                'built from their sectional marks and scored as a dual meet: ' +
                '5-3-1 for individual events, 5 for a relay. ' +
                'These two teams never met.',
        });
    };

    // Who comes back, as a footer reading. Athletes lead and points follow,
    // because the points denominator is incomplete: relay legs are not recorded,
    // so relay points cannot be credited to a class year. The word "individual"
    // is load-bearing -- a bare points ratio over a partial denominator is
    // wrong, and it is exactly the kind of wrong a coach checks.
    const renderReturning = function (payload) {
        const target = refs.metricReturning;
        if (!target) {
            return;
        }
        if (!payload || !payload.available) {
            emptyLookahead(target,
                (payload && payload.reason) || 'Nothing to project for this season.');
            return;
        }
        const ret = payload.retention;
        const pts = payload.points || {};
        const hasPoints = pts.percent !== null && pts.percent !== undefined;
        // "All 15" rather than "15 of 15": a ratio whose halves are equal is a
        // subtraction the reader should not have to do to find out that nothing
        // was lost.
        const points = !hasPoints
            ? 'No points scored'
            : (pts.points_returning === pts.points_total
                ? 'All ' + pts.points_total + ' individual points return'
                : pts.points_returning + ' of ' + pts.points_total +
                  ' individual points return');
        // The count is the figure and the denominator rides with it, the way the
        // summary card writes "7th of 14". The points ratio is a second, partial
        // measure of the same thing, so it sits under as context rather than
        // beside it at the same weight.
        lookaheadSlot(target, {
            valueHtml: esc(String(ret.athletes_returning)),
            qualifier: 'of ' + ret.athletes_total + ' athletes',
            context: points,
            title: 'Athletes holding a sectional scoring slot this season who ' +
                'are not seniors, so return in ' + payload.next_year + '.' +
                (hasPoints
                    ? ' Individual events only — relay legs are not recorded ' +
                      'for every season, so relay points cannot be credited to a ' +
                      'class year.'
                    : ''),
        });
    };

    // A section with nothing to show is hidden rather than rendered empty. Most
    // seasons end at the sectional, and a standing empty "State Qualifiers" panel
    // would render the ordinary case as a failure state. The counts in the
    // summary above already say, in a fixed position, that the number is zero.
    const showSection = function (section, visible) {
        if (section) {
            section.classList.toggle('sd3-hidden', !visible);
        }
    };

    // The payload name is "First Last", so the surname is the last token --
    // unless a generational suffix trails it, which is why Darin Brooks Jr.
    // files under Brooks rather than under Jr.
    const surnameKey = function (name) {
        const parts = String(name || '').trim().split(/\s+/);
        while (parts.length > 1) {
            const tail = parts[parts.length - 1].toUpperCase();
            if (!ROMAN_SUFFIX.test(tail) && !GEN_SUFFIX.test(tail)) {
                break;
            }
            parts.pop();
        }
        return (parts[parts.length - 1] || '').toLowerCase();
    };

    // "4 x 800 Relay" -> 800, so the three relays read in distance order rather
    // than in whatever order the meet results happened to arrive.
    const relayDistance = function (event) {
        const m = /x\s*(\d+)/i.exec(String(event || ''));
        return m ? Number(m[1]) : 9999;
    };

    // Running events read in distance order, field events alphabetically after
    // them. Sorted as plain strings, "1600 Meters" files before "800 Meters",
    // which is the one ordering a coach would notice immediately.
    const eventSortKey = function (event) {
        const m = /^(\d+)/.exec(String(event || ''));
        return m ? [0, Number(m[1]), ''] : [1, 0, String(event || '')];
    };

    const byEvent = function (a, b) {
        const ka = eventSortKey(a);
        const kb = eventSortKey(b);
        return (ka[0] - kb[0]) || (ka[1] - kb[1]) ||
            (ka[2] < kb[2] ? -1 : (ka[2] > kb[2] ? 1 : 0));
    };

    // Entries that carry a real result, as against the placeholder rows the
    // results table keeps for events nobody entered.
    const enteredRows = function (scorecard) {
        return ((scorecard && scorecard.rows) || []).filter(function (row) {
            return row.entry_type && row.entry_type !== 'none';
        });
    };

    // What one entry did at one round: the mark, and what it earned under it.
    //
    // The mark leads and the place sits beneath it in small type -- the same
    // two-line cell the results table builds, down to the same classes, so a
    // mark and its place cannot end up formatted two ways on one page. It was
    // "4:27.49 (3rd)" on one line here and stacked there, which made two tables
    // holding the same fact look like two different kinds of reading.
    //
    // A place from a prelim is a standing in the prelim field rather than a
    // finish, and says so -- reading it as a finish is the one mistake this cell
    // can cause.
    const stageResultCell = function (cell, label) {
        if (!cell) {
            return '<td data-label="' + esc(label) + '" class="sd3-qual-result sd3-stage-cell">' +
                '<span class="sd3-of">&mdash;</span></td>';
        }
        // A sentinel (NT, DQ) is shown as itself: they were at this meet, and a
        // blank cell would claim they never got there.
        const noMark = cell.has_mark === false;
        const place = cell.place
            ? ordinalOf(cell.place) + (cell.round === 'Prelim' ? ' in prelims' : '')
            : (cell.round === 'Prelim' ? 'prelims' : '');
        return '<td data-label="' + esc(label) + '" class="sd3-qual-result sd3-stage-cell' +
                (noMark ? ' is-nomark' : '') + '">' +
            '<span class="sd3-stage-mark"' +
                (noMark ? ' title="Competed here but posted no valid mark"' : '') + '>' +
                esc(cell.mark_display) + '</span>' +
            (place ? '<span class="sd3-stage-sub">' + esc(place) + '</span>' : '') +
        '</td>';
    };

    // Who reached a round: the athlete, what they qualified in, and how that
    // entry then went at the round itself.
    //
    // The result column overlaps the results table below, but as a filter rather
    // than a repeat: that table carries every sectional entry across three stages,
    // so "how did our regional qualifiers do" meant scanning past everyone who
    // did not qualify. One stage, and only the entries that got there.
    const renderQualifierTable = function (target, scorecard, stage) {
        if (!target) {
            return 0;
        }
        const rows = enteredRows(scorecard);
        const entries = (scorecard && scorecard.mode === 'records')
            ? []
            : rows.filter(function (row) { return (row.stages || {})[stage]; });
        if (!entries.length) {
            target.innerHTML = '';
            return 0;
        }

        // One row per qualifying entry, not per athlete. An athlete who qualified
        // in two events is two entries, and the Qualifiers reading in the summary
        // counts entries -- collapsing them here would leave a five-row table
        // under a heading that says six.
        //
        // Surname, then the full name, then the event -- otherwise two Thomases
        // order by whichever the meet results listed first, which changes between
        // seasons for no reason a reader could see. Relays last: the named
        // athletes are what the eye is looking for, so they hold the front.
        const people = entries.filter(function (row) {
            return row.entry_type !== 'relay' && row.athlete_id;
        }).sort(function (x, y) {
            const nx = titleName(x.name);
            const ny = titleName(y.name);
            const kx = surnameKey(nx);
            const ky = surnameKey(ny);
            if (kx !== ky) { return kx < ky ? -1 : 1; }
            if (nx !== ny) { return nx < ny ? -1 : 1; }
            return byEvent(x.event, y.event);
        });
        const relays = entries.filter(function (row) {
            return row.entry_type === 'relay' || !row.athlete_id;
        }).sort(function (x, y) {
            return relayDistance(x.event) - relayDistance(y.event);
        });

        // A relay is its own event, so the event cell names it and the athlete
        // cell names the squad that ran it.
        const resultLabel = stage + ' Result';
        const body = people.concat(relays).map(function (row) {
            return '<tr>' +
                '<td data-label="Athlete" class="sd3-qual-who">' + whoCell(row) + '</td>' +
                '<td data-label="Event">' + esc(row.event) + '</td>' +
                stageResultCell((row.stages || {})[stage], resultLabel) +
            '</tr>';
        }).join('');

        target.innerHTML =
            '<div class="sd3-table-scroll"><table class="sd3-table sd3-qual-table">' +
                '<thead><tr>' +
                    '<th>Athlete</th><th>Event</th>' +
                    '<th title="' + esc('Mark and finishing place at the ' + stage +
                        '. A place from a prelim is a standing in the prelim field, ' +
                        'not a finish, and is labelled as such.') + '">' +
                        esc(resultLabel) + '</th>' +
                '</tr></thead>' +
                '<tbody>' + body + '</tbody>' +
            '</table></div>';
        return people.length + relays.length;
    };

    // The entries that came closest to the regional.
    //
    // Ranked by the gap as a share of the cutoff, not by the raw gap. Raw gaps
    // are not comparable across events -- 0.29 seconds in the 100 and 10 inches
    // in the long jump are not the same distance from qualifying -- and sorting
    // on them would put the sprints on top every time simply because their
    // numbers are smaller. Both are shown: the raw margin is what a coach quotes,
    // the share is what the order is built on.
    //
    // How many to show: everyone within CLOSEST_SHARE of the cutoff, but never
    // fewer than CLOSEST_MIN and never more than CLOSEST_MAX.
    //
    // A flat top three was the wrong shape at both ends. Across the 2026
    // postseason, 69% of school-seasons had a third-closest entry more than 3%
    // off the cut -- listed under a heading about coming closest to qualifying,
    // those read as near misses when they were not. At the other end a deep
    // program can have six entries genuinely on the edge, and three of them were
    // being cut.
    //
    // A threshold alone fails the other way: at 3% it leaves 28% of
    // school-seasons with an empty section, and at 2% it empties 42% of them --
    // and "nobody was close" is exactly when a coach still wants to know who came
    // nearest. Hence the floor, and hence the greying: a padded row is shown but
    // does not get to claim it was close.
    //
    // 3% is where the margin stops meaning "had a shot", measured against the
    // thing it is standing in for: how many places out of the cut an entry
    // finished. Across the 2026 sectionals the regional cut falls at a median
    // place of 4th, and the entry one place past it misses by a median of 2.0%;
    // two places past, 3.75%; four places past, 6.9%.
    //
    // At 3%, 47% of the entries listed finished exactly one place out of the cut
    // and 10% finished four or more places out. At 5% that is 35% and 20% -- a
    // fifth of the list nowhere near advancing, under a heading about coming
    // closest to it.
    const CLOSEST_MIN = 3;
    const CLOSEST_MAX = 8;
    const CLOSEST_SHARE = 0.03;

    const renderClosest = function (scorecard) {
        const target = refs.closest;
        if (!target) {
            return;
        }
        const rows = enteredRows(scorecard);
        if (!rows.length || !state.core || !state.core.stage_results ||
                (scorecard && scorecard.mode === 'records')) {
            target.innerHTML = '';
            return 0;
        }
        const ranked = rows.filter(function (row) {
            return row.final_stage === 'Sectional' &&
                typeof row.gap_value === 'number' && row.gap_value > 0 &&
                typeof row.cutoff_value === 'number' && row.cutoff_value > 0;
        }).map(function (row) {
            return { row: row, share: row.gap_value / row.cutoff_value };
        }).sort(function (x, y) { return x.share - y.share; });

        // Everyone inside the threshold, then padded up to the floor and trimmed
        // to the cap. The padding rows are marked rather than silently mixed in:
        // they are here to answer "who came nearest" when the answer is "nobody
        // came close", which is a different question from the one the rest of the
        // list answers.
        const inside = ranked.filter(function (item) {
            return item.share <= CLOSEST_SHARE;
        }).length;
        const misses = ranked.slice(0,
            Math.min(CLOSEST_MAX, Math.max(CLOSEST_MIN, inside)));

        if (!misses.length) {
            target.innerHTML = '';
            return 0;
        }

        const body = misses.map(function (item) {
            const row = item.row;
            const share = (item.share * 100).toFixed(1);
            // Outside the threshold, and so only here to fill the floor. Muted,
            // because the heading says these entries came closest -- and at this
            // margin that is true only in the sense that somebody had to.
            const far = item.share > CLOSEST_SHARE;
            const why = row.mark_display + ' against a cutoff of ' + row.cutoff_display +
                ', ' + share + '% off the line' +
                (row.cutoff_path === 'auto'
                    ? ' (the last automatic spot at this meet)'
                    : (row.cutoff_path === 'callback'
                        ? ' (the last callback slot)' : '')) +
                (far
                    ? '. One of this program\u2019s nearest misses, but too far ' +
                      'off the line to have been in contention.'
                    : '.');
            // Margin on top, the share beneath -- matching the mark-over-place
            // cell in the qualifier table this one sits behind. The two views swap
            // in the same space, so a row that changes height between them reads
            // as the table reloading rather than as the same list seen from the
            // other side of the cut.
            return '<tr' + (far ? ' class="is-far"' : '') + '>' +
                '<td data-label="Athlete" class="sd3-qual-who">' + whoCell(row) + '</td>' +
                '<td data-label="Event">' + esc(row.event) + '</td>' +
                '<td data-label="Margin" class="sd3-margin-cell sd3-stage-cell" title="' +
                        esc(why) + '">' +
                    '<span class="sd3-stage-mark">' + esc(row.gap_display || '—') + '</span>' +
                    '<span class="sd3-stage-sub">' + share + '% off the cut</span>' +
                '</td>' +
            '</tr>';
        }).join('');

        target.innerHTML =
            '<div class="sd3-table-scroll"><table class="sd3-table sd3-qual-table">' +
                '<thead><tr>' +
                    '<th>Athlete</th><th>Event</th>' +
                    '<th title="' +
                        esc('How far short of the advancement standard, and that ' +
                            'margin as a share of the standard. The share is what ' +
                            'this list is ordered by, closest first: a raw margin ' +
                            'is not comparable across events -- 7 inches in the ' +
                            'shot and 1.84s in the 3200 have no common scale. ' +
                            'Every entry within ' + (CLOSEST_SHARE * 100).toFixed(0) +
                            '% of the cut is listed, up to ' + CLOSEST_MAX + '. Where ' +
                            'fewer than ' + CLOSEST_MIN + ' were that close, the ' +
                            'nearest ' + CLOSEST_MIN + ' are shown and the ones ' +
                            'outside the line are greyed.') +
                    '">Margin</th>' +
                '</tr></thead>' +
                '<tbody>' + body + '</tbody>' +
            '</table></div>';
        return misses.length;
    };

    // Which side of the regional cut is showing.
    //
    // Both views are named in the heading, divided by a rule, and the one showing
    // is the one carrying the heading's weight. They are the same question asked
    // from either side of the cut, so neither is the other's footnote -- and a
    // reader can see that the second view exists without having to work out what
    // a link beside a heading would switch them to.
    //
    // A view with nothing in it is never offered: a school with no near misses
    // would otherwise get a label that opens an empty panel. If the remembered
    // view is the empty one the other takes over, and if both are empty the whole
    // section goes -- most seasons end at the sectional, and a standing empty
    // panel renders the ordinary case as a failure state.
    const REGIONAL_VIEW_TITLE = {
        qualifiers: 'Entries that advanced to the regional',
        closest: 'Entries that finished nearest the regional cut without advancing',
    };

    const syncRegionalView = function (counts) {
        const available = {
            qualifiers: counts.qualifiers > 0,
            closest: counts.closest > 0,
        };
        let view = state.regionalView;
        if (!available[view]) {
            view = available.qualifiers ? 'qualifiers' : 'closest';
        }
        state.regionalView = view;

        if (refs.regionalQualifiers) {
            refs.regionalQualifiers.classList.toggle('sd3-hidden', view !== 'qualifiers');
        }
        if (refs.closest) {
            refs.closest.classList.toggle('sd3-hidden', view !== 'closest');
        }
        if (refs.regionalTabs) {
            refs.regionalTabs.querySelectorAll('[data-regional-view]').forEach(
                function (tab) {
                    const key = tab.getAttribute('data-regional-view');
                    tab.setAttribute('aria-pressed', key === view ? 'true' : 'false');
                    tab.title = REGIONAL_VIEW_TITLE[key];
                    // Hidden rather than disabled: a greyed-out label beside a
                    // heading reads as part of the heading rather than as a
                    // control that is off.
                    tab.classList.toggle('sd3-hidden', !available[key]);
                }
            );
            // The divider goes with the missing label, or it hangs off the end of
            // a heading with nothing on the other side of it.
            refs.regionalTabs.classList.toggle('is-single',
                !(available.qualifiers && available.closest));
        }
        showSection(refs.regionalSection, available.qualifiers || available.closest);
    };

    const renderQualifiers = function (scorecard) {
        const counts = {
            qualifiers: renderQualifierTable(refs.regionalQualifiers, scorecard, 'Regional'),
            closest: renderClosest(scorecard),
        };
        syncRegionalView(counts);
        showSection(refs.stateSection,
            renderQualifierTable(refs.stateQualifiers, scorecard, 'State') > 0);
    };

    // Who was in the points for one event group at the sectional.
    //
    // The statewide field for one event -- the list this school's rank came out
    // of. Same shape and the same two controls as the statewide leaderboard,
    // because it answers the same question at a different scale.
    const renderEventRankings = function (payload) {
        refs.detailTitle.textContent = payload.event;
        const unit = payload.is_relay ? ' relays' : ' athletes';
        refs.detailSubtitle.textContent = state.gender + ' • ' + payload.year +
            ' postseason • ' + (payload.is_filtered
                ? payload.filtered_total + unit + ' in this filter, of ' + payload.total
                : payload.total + unit + ' ranked');
        // The in-filter column only appears when something is filtered:
        // unfiltered it would repeat the statewide rank in every row.
        const filtered = !!payload.is_filtered;
        const whoLabel = payload.is_relay ? 'School' : 'Athlete';
        refs.detailContent.innerHTML =
            '<div class="sd3-table-scroll"><table class="sd3-table"><thead><tr>' +
                '<th title="Rank among every ranked mark statewide.">Rank</th>' +
                (filtered
                    ? '<th title="Rank among the ' + esc(payload.filtered_total) +
                      ' marks from schools matching this filter.">In filter</th>'
                    : '') +
                '<th>' + whoLabel + '</th>' +
                (payload.is_relay ? '' : '<th>School</th>') +
                '<th>Mark</th><th>Best at</th><th>Enrollment</th>' +
            '</tr></thead><tbody>' +
            (payload.rows || []).map(function (row) {
                const who = row.athlete_id
                    ? '<a class="sd3-link" href="/athlete-dashboard/' + row.athlete_id + '">' +
                      esc(titleName(row.name)) + '</a>'
                    : esc(row.name || '');
                const enrollment = row.enrollment == null
                    ? '—' : String(row.enrollment);
                const enrollmentTitle = row.enrollment == null
                    ? 'No enrollment on file.'
                    : (row.enrollment_is_exact
                        ? 'Enrollment as filed for ' + row.enrollment_source_year + '.'
                        : 'Nearest year on file: ' + row.enrollment_source_year + '.');
                return '<tr' + (row.is_focus ? ' class="sd3-highlight-row"' : '') + '>' +
                    '<td data-label="Rank" class="sd3-num">' + esc(row.rank) + '</td>' +
                    (filtered
                        ? '<td data-label="In filter" class="sd3-num">' +
                            // A pinned row sits outside the filter, so it has no
                            // place within it -- a number there would be invented.
                            (row.filtered_rank == null
                                ? '<span class="sd3-of">—</span>'
                                : esc(row.filtered_rank)) +
                          '</td>'
                        : '') +
                    '<td data-label="' + whoLabel + '">' + who +
                        (row.is_pinned ? ' <span class="sd3-subtle">(pinned)</span>' : '') +
                    '</td>' +
                    (payload.is_relay
                        ? ''
                        : '<td data-label="School">' + esc(row.school_name || '') + '</td>') +
                    '<td data-label="Mark" class="sd3-num">' + esc(row.mark_display || '') + '</td>' +
                    '<td data-label="Best at" class="sd3-of">' + esc(row.stage || '') + '</td>' +
                    '<td data-label="Enrollment" class="sd3-num" title="' +
                        esc(enrollmentTitle) + '">' + esc(enrollment) + '</td>' +
                '</tr>';
            }).join('') +
            '</tbody></table></div>' +
            (payload.focus_filtered_out
                ? '<div class="sd3-pinned-note">This school is outside the current ' +
                  'enrollment filter; its marks are pinned to the end.</div>'
                : '');
    };

    // ------------------------------------------------------- the two field lists
    //
    // The statewide leaderboard and the per-event field answer the same question
    // -- where do we sit, and who is around us -- so they carry the same two
    // controls and share the code behind them.

    // The enrollment maximum a filter row is currently set to, as the API wants
    // it. "custom" with nothing typed yet is not a filter, it is a half-finished
    // one, so it reads as unfiltered rather than as zero.
    const enrollmentValue = function (select, custom) {
        if (!select) {
            return null;
        }
        if (select.value !== 'custom') {
            return select.value === 'all' ? null : select.value;
        }
        const typed = (custom && custom.value || '').trim();
        return typed ? typed : null;
    };

    // Scroll this school's row into the middle of the list and flash it. Without
    // it the answer to "who is around us" sits 200 rows down, which is the whole
    // reason these lists are not truncated.
    const jumpToFocus = function (container) {
        if (!container) {
            return;
        }
        const row = container.querySelector('.sd3-highlight-row');
        if (!row) {
            return;
        }
        if (row.scrollIntoView) {
            // scrollIntoView takes its own behaviour and ignores the CSS
            // scroll-behavior the reduced-motion block sets, so it is asked here.
            row.scrollIntoView({
                block: 'center',
                behavior: prefersReducedMotion() ? 'auto' : 'smooth',
            });
        }
        // Restarted rather than simply added: a second click on an element that
        // already carries the class would not replay the animation.
        row.classList.remove('sd3-jump-flash');
        if (row.offsetWidth !== undefined) {
            void row.offsetWidth;
        }
        row.classList.add('sd3-jump-flash');
    };

    // Filled in by wireJump below, and read here rather than named directly:
    // syncJump is defined above that wiring, so a direct reference would depend
    // on a declaration order that only happens to work.
    const jumpTopSync = {};

    // A jump with nowhere to land is worse than no jump: it looks broken. The
    // control is disabled instead, and says why on hover.
    const syncJump = function (button, container, reason) {
        if (!button) {
            return;
        }
        const has = !!(container && container.querySelector('.sd3-highlight-row'));
        button.disabled = !has;
        button.title = has
            ? 'Scroll to this school in the list'
            : (reason || 'This school is not in the current list.');
        // A freshly loaded list is back at the top, so the return control goes
        // with the scroll position that justified it.
        const sync = jumpTopSync[button.id];
        if (sync) {
            sync();
        }
    };

    const renderLeaderboard = function (payload) {
        refs.leaderboardTitle.textContent = payload.group
            ? payload.group + ' Leaderboard'
            : 'Statewide Leaderboard';
        refs.leaderboardSubtitle.textContent = state.gender + ' \u2022 ' + state.season +
            ' postseason \u2022 ' + (payload.filtered_schools || 0) + ' schools' +
            (payload.is_filtered ? ' in this filter' : '');
        const rows = payload.rows || [];
        if (!rows.length) {
            refs.leaderboardContent.innerHTML = '<div class="sd3-note sd3-subtle">No schools matched this filter.</div>';
            return;
        }

        // The filtered column only appears when something is filtered: unfiltered
        // it would repeat the statewide rank in every row.
        const filtered = !!payload.is_filtered;
        // Ranking on one group instead of the composite: same table, different
        // column sorted on, so the score shown has to change with it.
        const group = payload.group || null;
        const table = '<div class="sd3-table-scroll"><table class="sd3-table"><thead><tr>' +
                '<th title="Rank among all ranked programs statewide.">Rank</th>' +
                (filtered
                    ? '<th title="Rank among the ' + esc(payload.filtered_total) +
                      ' schools matching this filter.">In filter</th>'
                    : '') +
                '<th>School</th>' +
                '<th title="' + esc(group
                    ? group + ' score: the average statewide percentile of this ' +
                      'program\u2019s marks in that group.'
                    : 'Depth-weighted score across all entry slots.') + '">' +
                    esc(group || 'Composite') + '</th>' +
                '<th>Enrollment</th>' +
            '</tr></thead><tbody>' +
            rows.map(function (row) {
                const highlight = row.school_id === state.core.school.id ? ' class="sd3-highlight-row"' : '';
                // The column header says what these are; the denominator is the
                // same on every row and the enrollment year belongs on hover.
                const enrollment = row.enrollment == null ? '\u2014' : String(row.enrollment);
                const enrollmentTitle = row.enrollment == null
                    ? 'No enrollment on file.'
                    : (row.enrollment_is_exact
                        ? 'Enrollment as filed for ' + row.enrollment_source_year + '.'
                        : 'Nearest year on file: ' + row.enrollment_source_year + '.');
                return '<tr' + highlight + '>' +
                    '<td data-label="Rank">' + esc(row.rank) + '</td>' +
                    (filtered
                        ? '<td data-label="In filter">' +
                            // A pinned row sits outside the filter, so it has no
                            // place within it -- a number there would be invented.
                            (row.filtered_rank == null
                                ? '<span class="sd3-of">\u2014</span>'
                                : esc(row.filtered_rank)) +
                          '</td>'
                        : '') +
                    '<td data-label="School">' + esc(row.school_name) + (row.is_pinned ? ' <span class="sd3-subtle">(pinned)</span>' : '') + '</td>' +
                    '<td data-label="' + esc(group || 'Composite') + '">' +
                        esc((group ? (row.group_score || 0) : row.composite_score).toFixed(1)) +
                    '</td>' +
                    '<td data-label="Enrollment" title="' + esc(enrollmentTitle) + '">' +
                        esc(enrollment) + '</td>' +
                '</tr>';
            }).join('') +
        '</tbody></table></div>';

        const note = payload.selected_school_filtered_out
            ? '<div class="sd3-pinned-note">The focus school is outside the current enrollment filter.</div>'
            : '<div class="sd3-pinned-note">Top rows stay sorted by statewide composite rank. The focus school is highlighted and pinned when needed.</div>';

        refs.leaderboardContent.innerHTML = table + note;
    };

    const loadCore = async function (gender, season) {
        const requestId = ++state.requestId;
        try {
            refs.loading.classList.remove('sd3-hidden');
            refs.app.classList.add('sd3-hidden');
            refs.error.classList.add('sd3-hidden');
            state.scorecard = null;
            state.programRank = null;
            state.leaderboard = null;
            refs.scorecard.innerHTML = '';
            refs.scorecardStatus.textContent = '';
            [refs.regionalQualifiers, refs.closest, refs.stateQualifiers]
                .forEach(function (target) {
                    if (target) { target.innerHTML = ''; }
                });
            showSection(refs.regionalSection, false);
            showSection(refs.stateSection, false);

            const query = buildQuery({
                gender: gender || state.gender,
                season: season,
            });
            // The four panel loaders below need core's resolved season -- but the
            // server resolves it from the same arguments for every one of these
            // endpoints (_v3_scope), so the URLs are already known here. Their
            // requests start now and are awaited after core lands, which turns a
            // serial core-then-panels page into one round trip's worth of
            // waiting. Rendering still happens strictly after core, so nothing
            // reads state.core before it is set.
            //
            // Each carries a no-op catch from the moment it is created: if core
            // fails these are never awaited, and an unhandled rejection in a
            // request nobody is listening to would surface as a console error.
            const panelUrl = function (name) {
                return '/api/v3/schools/' + schoolId + '/dashboard/' + name + '?' + query;
            };
            const pending = {};
            ['ranking', 'season-h2h', 'returning', 'athletes'].forEach(function (name) {
                const request = fetchJson(panelUrl(name));
                request.catch(function () {});
                pending[name] = request;
            });

            const core = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/core?' + query);
            if (requestId !== state.requestId) {
                return;
            }
            state.core = core;
            state.gender = core.filters.selected_gender;
            state.season = String(core.filters.selected_season);

            renderHeader(core);
            renderFilters(core);
            renderStages(core);

            refs.loading.classList.add('sd3-hidden');
            refs.app.classList.remove('sd3-hidden');

            if (core.stage_results) {
                void loadSeasonH2H(requestId, pending['season-h2h']);
                void loadReturning(requestId, pending['returning']);
                void loadScorecard(requestId, pending['athletes']);
                showSection(refs.summarySection, true);
                showSection(refs.scorecardSection, true);
                showSection(refs.programRankSection, true);
                showSection(refs.returningSection, true);
                showSection(refs.h2hSection, true);
                // The three entry lists show themselves once the scorecard lands:
                // a season with no regional qualifiers gets no such section, and
                // leaving them on here would flash an empty panel first.
                refs.rankHeadline.innerHTML =
                    '<div class="sd3-rank-headline-move">Loading…</div>';
                void loadRanking(requestId, pending['ranking']);
            } else {
                // All-Time still has a table -- the records board -- even though
                // there is no single season to rank.
                showSection(refs.scorecardSection, true);
                void loadScorecard(requestId);
                // Summary, rank, head-to-head and returning are all questions
                // about a single season. Hiding them beats four "not applicable"
                // panels -- and stops the previous season's figures lingering
                // here.
                showSection(refs.summarySection, false);
                showSection(refs.programRankSection, false);
                showSection(refs.returningSection, false);
                showSection(refs.h2hSection, false);
            }
        } catch (error) {
            showError(error.message);
        }
    };

    const loadRanking = async function (requestId, pending) {
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const ranking = await (pending || fetchJson('/api/v3/schools/' + schoolId + '/dashboard/ranking?' + query));
            if (requestId === state.requestId) {
                // Kept so a group-filter click can re-render the strip without refetching.
                state.programRank = ranking;
                renderProgramRank(ranking);
            }
        } catch (error) {
            if (requestId === state.requestId) {
                refs.rankHeadline.innerHTML =
                    '<div class="sd3-rank-headline-move">' + esc(error.message) + '</div>';
            }
        }
    };

    const loadSeasonH2H = async function (requestId, pending) {

        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const payload = await (pending || fetchJson('/api/v3/schools/' + schoolId + '/dashboard/season-h2h?' + query));
            if (requestId !== state.requestId) { return; }
            renderSeasonH2H(payload);
        } catch (error) {
            emptyLookahead(refs.metricH2H, error.message);
        }
    };

    const loadReturning = async function (requestId, pending) {
        emptyLookahead(refs.metricReturning, 'Loading…');
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const payload = await (pending || fetchJson('/api/v3/schools/' + schoolId + '/dashboard/returning?' + query));
            if (requestId !== state.requestId) { return; }
            renderReturning(payload);
        } catch (error) {
            emptyLookahead(refs.metricReturning, error.message);
        }
    };

    // Takes requestId like the other three loaders. Without it a fast gender or
    // season switch could let a stale response land on top of a newer one.
    const loadScorecard = async function (requestId, pending) {
        if (state.scorecard) {
            renderScorecard(state.scorecard);
            renderQualifiers(state.scorecard);
            return;
        }
        refs.scorecardStatus.textContent = '';
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const payload = await (pending || fetchJson('/api/v3/schools/' + schoolId + '/dashboard/athletes?' + query));
            if (requestId !== undefined && requestId !== state.requestId) { return; }
            state.scorecard = payload;
            refs.scorecardStatus.textContent = '';
            renderScorecard(state.scorecard);
            renderQualifiers(state.scorecard);
        } catch (error) {
            if (requestId !== undefined && requestId !== state.requestId) { return; }
            refs.scorecardStatus.textContent = error.message;
        }
    };

    // Re-entered on every filter change as well as on open, so the event it is
    // showing is held in state rather than passed down from the click each time.
    const loadEventRankings = async function (eventName) {
        if (!refs.detailModal) {
            return;
        }
        if (eventName) {
            state.detailEvent = eventName;
        }
        const event = state.detailEvent;
        if (!event) {
            return;
        }
        refs.detailTitle.textContent = event;
        refs.detailContent.innerHTML =
            '<div class="sd3-note sd3-subtle">Loading statewide rankings\u2026</div>';
        const requestId = state.requestId;
        try {
            const query = buildQuery({
                gender: state.gender,
                season: state.season,
                enrollment_max: enrollmentValue(
                    refs.detailEnrollment, refs.detailCustom),
            });
            const payload = await fetchJson('/api/v3/schools/' + schoolId +
                '/dashboard/event-rankings/' + encodeURIComponent(event) + '?' + query);
            if (requestId !== state.requestId) { return; }
            renderEventRankings(payload);
            syncJump(refs.detailJump, refs.detailContent,
                'This school is outside the current enrollment filter.');
        } catch (error) {
            refs.detailContent.innerHTML =
                '<div class="sd3-note sd3-subtle">' + esc(error.message) + '</div>';
            syncJump(refs.detailJump, refs.detailContent);
        }
    };

    const loadLeaderboard = async function () {
        const group = state.leaderboardGroup || '';
        refs.leaderboardContent.innerHTML = '<div class="sd3-note sd3-subtle">Loading leaderboard…</div>';
        try {
            const query = buildQuery({
                gender: state.gender,
                season: state.season,
                enrollment_max: enrollmentValue(
                    refs.leaderboardEnrollment, refs.leaderboardCustom),
                group: group,
            });
            state.leaderboard = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/leaderboard?' + query);
            renderLeaderboard(state.leaderboard);
            syncJump(refs.leaderboardJump, refs.leaderboardContent,
                'This school is outside the current enrollment filter.');
        } catch (error) {
            refs.leaderboardContent.innerHTML = '<div class="sd3-note sd3-subtle">' + esc(error.message) + '</div>';
            syncJump(refs.leaderboardJump, refs.leaderboardContent);
        }
    };

    refs.filterRow.addEventListener('click', function (event) {
        const genderButton = event.target.closest('[data-gender]');
        if (genderButton) {
            if (genderButton.getAttribute('data-gender') !== state.gender) {
                loadCore(genderButton.getAttribute('data-gender'), null);
            }
            return;
        }
        const seasonButton = event.target.closest('[data-season]');
        if (seasonButton && !seasonButton.disabled) {
            const season = seasonButton.getAttribute('data-season');
            if (season !== state.season) {
                loadCore(state.gender, season);
            }
        }
    });

    // The two sides of the regional cut. The chosen view is held in state, so a
    // gender or season change leaves the reader where they were rather than
    // snapping back.
    if (refs.regionalTabs) {
        refs.regionalTabs.addEventListener('click', function (event) {
            const tab = event.target.closest('[data-regional-view]');
            if (!tab) {
                return;
            }
            state.regionalView = tab.getAttribute('data-regional-view');
            syncRegionalView({
                qualifiers: refs.regionalQualifiers && refs.regionalQualifiers.innerHTML ? 1 : 0,
                closest: refs.closest && refs.closest.innerHTML ? 1 : 0,
            });
        });
    }

    refs.filterRow.addEventListener('keydown', function (event) {
        const option = event.target.closest('[role="radio"]');
        if (!option) {
            return;
        }
        const group = option.closest('[role="radiogroup"]');
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
            event.preventDefault();
            moveRadioFocus(group, option, 1);
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
            event.preventDefault();
            moveRadioFocus(group, option, -1);
        }
    });

    // The rank in the results table opens the statewide field that rank came out
    // of. Delegated, because the table is re-rendered on every gender or season
    // change and a handler bound to the buttons would go with it.
    if (refs.scorecard) {
        refs.scorecard.addEventListener('click', function (event) {
            const cell = event.target.closest('[data-open-event-rankings]');
            if (!cell) {
                return;
            }
            refs.detailSubtitle.textContent = '';
            syncJump(refs.detailJump, null);
            openModal(refs.detailModal);
            void loadEventRankings(cell.getAttribute('data-open-event-rankings'));
        });
    }

    // One wiring for both filter rows: the two lists answer the same question,
    // so they behave identically down to when they choose to reload.
    const wireEnrollment = function (select, custom, reload) {
        if (!select || !custom) {
            return;
        }
        select.addEventListener('change', function () {
            const isCustom = select.value === 'custom';
            custom.classList.toggle('sd3-hidden', !isCustom);
            if (isCustom) {
                // Nothing to filter on until a number is typed, so wait for it
                // rather than reloading the unfiltered list on the way past.
                custom.focus();
                return;
            }
            void reload();
        });
        custom.addEventListener('change', function () {
            if (select.value === 'custom') {
                void reload();
            }
        });
    };

    wireEnrollment(refs.leaderboardEnrollment, refs.leaderboardCustom,
        function () { return loadLeaderboard(); });
    wireEnrollment(refs.detailEnrollment, refs.detailCustom,
        function () { return loadEventRankings(); });

    // The jump is a return trip. Landing 200 rows into a list with no way back
    // meant scrolling all the way up by hand, which is most of the reason these
    // lists are not truncated in the first place.
    //
    // Its own control rather than a second mode on the jump button: once the
    // list is scrolled a reader may want either destination, and a toggle can
    // only ever offer one of them. It stays hidden until there is something to
    // come back from.
    const wireJump = function (jumpButton, topButton, content) {
        if (!content) {
            return;
        }
        const card = content.closest ? content.closest('.sd3-modal-card') : null;
        const behavior = function () {
            return prefersReducedMotion() ? 'auto' : 'smooth';
        };
        // Roughly the height of the dialog header and its filter row: below that
        // the top of the list is already on screen and the control is a no-op.
        const SCROLLED = 120;
        const syncTop = function () {
            if (!topButton || !card) {
                return;
            }
            topButton.classList.toggle('sd3-hidden', (card.scrollTop || 0) <= SCROLLED);
        };
        if (jumpButton) {
            jumpTopSync[jumpButton.id] = syncTop;
            jumpButton.addEventListener('click', function () {
                jumpToFocus(content);
                // The smooth scroll is still running, so the control cannot be
                // synced from this frame's scrollTop.
                window.setTimeout(syncTop, 600);
            });
        }
        if (topButton && card) {
            topButton.addEventListener('click', function () {
                if (card.scrollTo) {
                    card.scrollTo({ top: 0, behavior: behavior() });
                } else {
                    card.scrollTop = 0;
                }
                window.setTimeout(syncTop, 600);
            });
            // Passive: this only reads scrollTop, and a listener that cannot
            // preventDefault does not hold the scroll up while it runs.
            card.addEventListener('scroll', syncTop, { passive: true });
        }
    };

    wireJump(refs.leaderboardJump, refs.leaderboardTop, refs.leaderboardContent);
    wireJump(refs.detailJump, refs.detailTop, refs.detailContent);

    root.querySelectorAll('[data-close-modal]').forEach(function (button) {
        button.addEventListener('click', function () {
            closeModal(document.getElementById(button.getAttribute('data-close-modal')));
        });
    });

    [refs.leaderboardModal, refs.detailModal].forEach(function (modal) {
        if (!modal) {
            return;
        }
        modal.addEventListener('keydown', trapModalFocus);
        modal.addEventListener('click', function (event) {
            if (event.target === modal) {
                closeModal(modal);
            }
        });
    });

    if (!Number.isFinite(schoolId) || schoolId <= 0) {
        showError('Invalid school identifier.');
        return;
    }

    loadCore(state.gender, null);
});
