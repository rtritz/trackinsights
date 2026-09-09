document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('school-dashboard-v3');
    if (!root) {
        return;
    }

    const schoolId = Number(root.dataset.schoolId);
    const refs = {
        loading: document.getElementById('sd3-loading'),
        error: document.getElementById('sd3-error'),
        app: document.getElementById('sd3-app'),
        schoolName: document.getElementById('sd3-school-name'),
        schoolMeta: document.getElementById('sd3-school-meta'),
        filterRow: document.getElementById('sd3-filter-row'),
        logoWrap: document.getElementById('sd3-logo-wrap'),
        logo: document.getElementById('sd3-logo'),
        stageGrid: document.getElementById('sd3-stage-grid'),
        allTimeIntro: document.getElementById('sd3-all-time-intro'),
        returningSection: document.getElementById('sd3-returning-section'),
        returning: document.getElementById('sd3-returning'),
        programRankSection: document.getElementById('sd3-program-rank-section'),
        programRank: document.getElementById('sd3-program-rank'),
        h2hSection: document.getElementById('sd3-h2h-section'),
        h2h: document.getElementById('sd3-h2h'),
        scorecardStatus: document.getElementById('sd3-scorecard-status'),
        scorecard: document.getElementById('sd3-scorecard'),
        qualifiersSection: document.getElementById('sd3-qualifiers-section'),
        qualifiers: document.getElementById('sd3-qualifiers'),
        leaderboardModal: document.getElementById('sd3-leaderboard-modal'),
        leaderboardContent: document.getElementById('sd3-leaderboard-content'),
        leaderboardSubtitle: document.getElementById('sd3-leaderboard-subtitle'),
        leaderboardEnrollment: document.getElementById('sd3-leaderboard-enrollment'),
        leaderboardCustom: document.getElementById('sd3-leaderboard-custom'),
        leaderboardTopN: document.getElementById('sd3-leaderboard-topn'),
        leaderboardApply: document.getElementById('sd3-leaderboard-apply'),
        eventModal: document.getElementById('sd3-event-modal'),
        eventTitle: document.getElementById('sd3-event-title'),
        eventSubtitle: document.getElementById('sd3-event-subtitle'),
        eventContent: document.getElementById('sd3-event-content'),
    };

    const state = {
        gender: 'Boys',
        season: null,
        core: null,
        scorecard: null,
        qualifiers: null,
        leaderboard: null,
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

    const openModal = function (modal) {
        state.lastFocusedElement = document.activeElement;
        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        const focusable = modal.querySelector('button, [href], input, select, [tabindex]:not([tabindex="-1"])');
        if (focusable) {
            focusable.focus();
        }
    };

    const closeModal = function (modal) {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        if (state.lastFocusedElement && typeof state.lastFocusedElement.focus === 'function') {
            state.lastFocusedElement.focus();
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
        const focusable = modal.querySelectorAll('button, [href], input, select, [tabindex]:not([tabindex="-1"])');
        if (!focusable.length) {
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
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

        const seasonPills = axis.map(function (year) {
            const hasData = schoolYears.has(year);
            const isOn = year === selectedSeason;
            return '<button type="button" role="radio" class="sd3-season-pill" data-season="' + esc(year) + '"' +
                (hasData ? '' : ' disabled') +
                ' aria-checked="' + (isOn ? 'true' : 'false') + '"' +
                ' tabindex="' + (isOn ? '0' : '-1') + '"' +
                ' title="' + (hasData
                    ? esc(year) + ' postseason'
                    : 'No postseason results for this program in ' + esc(year)) + '">' +
                esc(year) + '</button>';
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

    const renderStages = function (core) {
        refs.stageGrid.innerHTML = '';
        refs.allTimeIntro.classList.toggle('sd3-hidden', core.stage_results !== null);
        refs.qualifiersSection.classList.toggle('sd3-hidden', core.stage_results === null);

        if (!core.stage_results) {
            refs.allTimeIntro.textContent = core.all_time_intro || 'All-Time mode shows covered postseason program bests only.';
            return;
        }

        core.stage_results.stages.forEach(function (stage) {
            const card = document.createElement('div');
            card.className = 'sd3-stage-card';
            card.innerHTML =
                '<div class="sd3-stage-label">' + esc(stage.stage) + '</div>' +
                '<div class="sd3-stage-rank">' + esc(stage.team_rank_display) + '</div>' +
                '<div class="sd3-stage-points">' + (stage.attended ? esc(stage.points_display + ' points') : '—') + '</div>';
            refs.stageGrid.appendChild(card);
        });
    };

    const renderProgramRank = function (programRank) {
        if (!programRank) {
            refs.programRank.innerHTML = '';
            return;
        }

        const clamp = function (value) { return Math.max(0, Math.min(100, value)); };
        const plural = function (count, word) { return count + ' ' + word + (count === 1 ? '' : 's'); };
        const ordinal = function (value) {
            const n = Math.round(value);
            const rem100 = n % 100;
            if (rem100 >= 11 && rem100 <= 13) {
                return n + 'th';
            }
            return n + (['th', 'st', 'nd', 'rd'][n % 10] || 'th');
        };



        // Quartile strip on the score axis: segment widths are proportional to the
        // score range each quarter of the field occupies, so the bunching is visible.
        const buildQuartileStrip = function (dist, myScore) {
            if (!dist) {
                return '';
            }
            const stops = [0, dist.q1, dist.median, dist.q3, 100];
            const labels = ['Bottom 25%', '25-50%', '50-75%', 'Top 25%'];
            let segments = '';
            for (let i = 0; i < 4; i += 1) {
                const width = Math.max(0, stops[i + 1] - stops[i]).toFixed(2);
                segments += '<div class="sd3-quartile-seg" style="width:' + width + '%;" title="' +
                    esc(labels[i]) + ': scores ' + esc(stops[i].toFixed(1)) + '-' + esc(stops[i + 1].toFixed(1)) +
                    '">' + esc(labels[i]) + '</div>';
            }
            const you = typeof myScore === 'number'
                ? '<span class="sd3-quartile-you" style="left:' + clamp(myScore) + '%;" title="This program: ' + esc(myScore.toFixed(1)) + '"></span>'
                : '';
            return '<p class="sd3-subtle" style="margin-top:0.8rem;">Where the 0-100 score sits against the field. Each block holds a quarter of all programs &mdash; they are uneven because most programs score low, which is why a 50 is well above the middle.</p>' +
                '<div class="sd3-quartile-strip">' + segments + you + '</div>' +
                '<div class="sd3-quartile-axis"><span>' + esc(dist.min.toFixed(1)) + '</span>' +
                '<span>median ' + esc(dist.median.toFixed(1)) + '</span>' +
                '<span>' + esc(dist.max.toFixed(1)) + '</span></div>';
        };

        // The composite lives here rather than in the headline. It is a mean of
        // per-slot percentiles with empty slots counted as zero, so it is largely a
        // depth measure -- kept visible so the ranking stays auditable, but not
        // presented as a verdict on how fast anyone ran.
        const slots = programRank.entry_slots;
        const depthNote = (typeof programRank.composite_score === 'number')
            ? '<p class="sd3-subtle" style="margin-top:0.8rem;">' +
                'Depth-weighted score: <strong>' + esc(programRank.composite_score.toFixed(1)) + ' / 100</strong>' +
                ' &mdash; the average statewide percentile across all ' + (slots ? slots.total : '') + ' entry slots, ' +
                'counting ' + (slots ? plural(slots.total - slots.filled, 'unfilled slot') : 'unfilled slots') + ' as zero. ' +
                'This is the value the statewide ranking sorts on, so a program with few entries scores low even when its athletes place well.' +
              '</p>'
            : '';

        const explainer =
            '<div class="sd3-details"><details><summary>How this works</summary>' +
                '<p class="sd3-subtle" style="margin-top:0.6rem;">' + esc(programRank.info_text) + '</p>' +
                depthNote +
                buildQuartileStrip(programRank.score_distribution, programRank.composite_score) +
            '</details></div>';

        if (!programRank.is_ranked) {
            refs.programRank.innerHTML =
                '<div class="sd3-rank-top"><div>' +
                    '<div class="sd3-subtle">Statewide ranking</div>' +
                    '<div class="sd3-rank-value" style="font-size:1.3rem;">Not ranked</div>' +
                    '<div class="sd3-rank-sub">This program has no valid postseason marks for this season, so it is absent from the statewide table rather than scored zero.</div>' +
                '</div></div>' + explainer;
            return;
        }

        const standing = programRank.standing;
        const percentile = programRank.percentile;

        // Both counts are shown at once so neither number has to be read as the
        // complement of the other -- the source of the "166th yet ahead of 57%?" jolt.
        const positionBlock = standing
            ? '<div class="sd3-position">' +
                '<div class="sd3-position-bar">' +
                    '<span class="sd3-position-fill' + (clamp(percentile) < 50 ? ' is-below' : '') +
                        '" style="width:' + clamp(percentile) + '%;"></span>' +
                    '<span class="sd3-position-median" style="left:50%;" title="State median"></span>' +
                    '<span class="sd3-position-marker" style="left:' + clamp(percentile) + '%;">' +
                        '<span class="sd3-position-flag">YOU</span>' +
                    '</span>' +
                '</div>' +
                '<div class="sd3-position-scale">' +
                    '<span>Weakest</span><span>State median</span><span>Strongest</span>' +
                '</div>' +
              '</div>'
            : '';

        refs.programRank.innerHTML =
            '<div class="sd3-rank-top">' +
                '<div>' +
                    '<div class="sd3-subtle">Statewide ranking</div>' +
                    // The rank itself opens the leaderboard: the number is the thing
                    // you want to click, and it needs no separate button.
                    '<button type="button" class="sd3-rank-value sd3-rank-link" data-open-leaderboard' +
                        ' title="See the statewide leaderboard">' + esc(programRank.rank_display) + '</button>' +
                    (typeof programRank.rank_movement === 'number' && programRank.prior_rank
                        ? '<div class="sd3-rank-sub">' +
                            (programRank.rank_movement > 0
                                ? '<span class="sd3-move-up">&#9650; up ' + programRank.rank_movement + '</span>'
                                : (programRank.rank_movement < 0
                                    ? '<span class="sd3-move-down">&#9660; down ' + Math.abs(programRank.rank_movement) + '</span>'
                                    : '<span>unchanged</span>')) +
                            ' from ' + esc(programRank.prior_rank.season) +
                          '</div>'
                        : '') +
                '</div>' +
                (slots
                    ? '<div>' +
                        '<div class="sd3-subtle">Entry slots filled</div>' +
                        '<div class="sd3-rank-value" style="font-size:1.3rem;">' + slots.filled + ' of ' + slots.total + '</div>' +
                        (slots.entered > slots.filled
                            ? '<div class="sd3-rank-sub">' +
                                (slots.entered - slots.filled === 1 ? '1 entry' : (slots.entered - slots.filled) + ' entries') +
                                ' scored 0 (DQ/DNF/no mark)</div>'
                            : '') +
                      '</div>'
                    : '') +
            '</div>' +
            positionBlock +
            explainer +
            renderGroupStrip(programRank.group_standings);

        const rankLink = refs.programRank.querySelector('[data-open-leaderboard]');
        if (rankLink) {
            rankLink.addEventListener('click', function () {
                openModal(refs.leaderboardModal);
                loadLeaderboard();
            });
        }

        refs.programRank.querySelectorAll('[data-group]').forEach(function (tile) {
            tile.addEventListener('click', function () {
                const name = tile.getAttribute('data-group');
                applyGroupFilter(scorecardFilter.group === name ? null : name);
            });
        });
    };

    const scorecardSort = { key: 'event', dir: 1 };
    // Group strip doubles as the event table's filter, so groups stay a
    // signal and a navigation aid without opening a third drill-down level.
    const scorecardFilter = { group: null, events: null };

    // One bar for the whole page: event-group rank, per-event rank in the athlete
    // table, and retention in the next-season tiles all draw through here. Fuller
    // is better in every case, so the shape means one thing wherever it appears.
    const buildBar = function (pct, options) {
        const opts = options || {};
        const title = opts.title ? ' title="' + esc(opts.title) + '"' : '';
        if (pct === null) {
            return '<span class="sd3-bar is-empty' +
                (opts.className ? ' ' + opts.className : '') + '"' + title + '></span>';
        }
        const width = Math.max(0, Math.min(100, pct));
        // Derived here, never passed in: every bar on the page turns amber at the
        // same place, so the colour cannot mean different things in different
        // sections. Below halfway is below the middle of the field.
        // Ordered component, modifier, state -- the modifier stays adjacent to the
        // component so "sd3-bar sd3-bar-inline" is one contiguous selector.
        const tone = width < 50 ? ' is-below' : '';
        return '<span class="sd3-bar' +
            (opts.className ? ' ' + opts.className : '') + tone + '" aria-hidden="true"' + title + '>' +
            '<span style="width:' + width.toFixed(1) + '%;"></span></span>';
    };

    // Rank to a percentile fill. Denominators vary 2.7x across events (258 to 695
    // for Boys 2026), so "165 / 690" and "173 / 506" look alike while sitting 10
    // percentile points apart -- the bar makes rows comparable at a glance, the
    // number keeps the precision a coach needs. Full bar = 1st in the state.
    const rankPercent = function (rank, total) {
        if (!rank || !total) {
            return null;
        }
        return (100 * (total - rank + 1)) / total;
    };

    const buildRankBar = function (rank, total) {
        return buildBar(rankPercent(rank, total), {
            className: 'sd3-bar-inline',
            title: rank && total ? null : 'No entry in this event',
        });
    };

    const renderScorecard = function (scorecard) {
        if (!scorecard || !scorecard.rows || !scorecard.rows.length) {
            refs.scorecard.innerHTML = '<div class="sd3-note sd3-subtle">No postseason results available.</div>';
            return;
        }

        let rows = scorecard.rows.slice();
        if (scorecardFilter.events) {
            rows = rows.filter(function (row) {
                return scorecardFilter.events.indexOf(row.event) !== -1;
            });
        }

        if (scorecardSort.key === 'name') {
            rows.sort(function (a, b) {
                return String(a.name || '~').localeCompare(String(b.name || '~')) * scorecardSort.dir;
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

        // All-Time is a records board: no season, so no sectional and no statewide
        // rank -- the columns that mean something are who holds the mark and when.
        const isRecords = scorecard.mode === 'records';

        const head = isRecords
            ? '<thead><tr>' +
                '<th data-sort="event">Event</th>' +
                '<th data-sort="name">Athlete</th>' +
                '<th>Mark</th>' +
                '<th>Season</th>' +
              '</tr></thead>'
            : '<thead><tr>' +
                '<th data-sort="event">Event</th>' +
                '<th data-sort="name">Name</th>' +
                '<th>Best mark</th>' +
                '<th data-sort="sectional" title="Where the season ended, the place there, and for those who did not go further, how far off the last mark that did advance out of that meet.">Postseason</th>' +
                '<th data-sort="rank" title="This mark ranked against every athlete in the state who contested the event. A fuller bar means a higher finish; a full bar is 1st.">Rank</th>' +
              '</tr></thead>';

        const ordinal = function (value) {
            const n = Number(value);
            if (!n) { return ''; }
            const mod100 = n % 100;
            if (mod100 >= 11 && mod100 <= 13) { return n + 'th'; }
            return n + (['th', 'st', 'nd', 'rd'][n % 10] || 'th');
        };

        // Where the season ended, the place there, and how close to going further.
        // Reporting the *final* stage rather than always the sectional keeps one
        // meaning per row: the column goes quiet exactly when an athlete goes
        // furthest if it only ever looks at the sectional.
        const postseasonCell = function (row) {
            if (!row.final_stage) {
                return '<span class="sd3-of">&mdash;</span>';
            }
            const stageClass = row.final_stage === 'State'
                ? ' is-state'
                : (row.final_stage === 'Regional' ? ' is-regional' : '');
            const stage = '<span class="sd3-stage-tag' + stageClass + '">' + esc(row.final_stage) + '</span>';
            if (!row.final_place) {
                return stage;
            }
            const place = '<span class="sd3-sect-place">' + esc(ordinal(row.final_place)) + '</span>';
            if (row.final_round === 'Prelim') {
                return stage + place + '<span class="sd3-sect-note"> in prelims</span>';
            }
            if (row.gap_display) {
                return stage + place + '<span class="sd3-sect-gap" title="' +
                    esc(row.cutoff_display + ' was the last mark to advance out of this meet') + '">' +
                    esc(row.gap_display) + ' back</span>';
            }
            return stage + place;
        };

        // Which meet the best mark came from -- shown only when it differs from the
        // stage in the Postseason column, which is exactly when the two numbers
        // would otherwise be read as describing the same day.
        const markStageTag = function (row) {
            if (!row.mark_stage || row.mark_stage === row.final_stage) {
                return '';
            }
            const short = { Sectional: 'SEC', Regional: 'REG', State: 'STATE' }[row.mark_stage] || row.mark_stage;
            return ' <span class="sd3-mark-stage" title="Set at the ' + esc(row.mark_stage) + '">' +
                esc(short) + '</span>';
        };

        let lastEvent = null;
        const body = rows.map(function (row) {
            const newEvent = row.event !== lastEvent;
            lastEvent = row.event;

            if (row.entry_type === 'none') {
                if (isRecords) {
                    return '<tr class="sd3-athlete-row is-empty">' +
                        '<td data-label="Event">' + esc(row.event) + '</td>' +
                        '<td colspan="3" class="sd3-no-entry">no mark on record</td>' +
                    '</tr>';
                }
                // Empty track rather than a blank cell, so the gap stays visible in
                // the same visual column as everything else.
                return '<tr class="sd3-athlete-row is-empty">' +
                    '<td data-label="Event">' + esc(row.event) + '</td>' +
                    '<td data-label="Name" colspan="3" class="sd3-no-entry">no entry &mdash; no points available here</td>' +
                    '<td data-label="Rank" class="sd3-rank-cell">' + buildRankBar(null, null) + '</td>' +
                '</tr>';
            }

            const name = row.athlete_id
                ? '<a class="sd3-link" href="/athlete-dashboard/' + row.athlete_id + '">' + esc(row.name) + '</a>'
                : esc(row.name || '—');
            // Class year is on 100% of result rows, so the cheapest possible answer to
            // "who is back next year" belongs right next to the name. Only SR is
            // colour-coded -- it is the one class that changes next season.
            const grade = row.grade
                ? '<span class="sd3-grade' + (row.grade === 'SR' ? ' is-sr' : '') + '"' +
                  ' title="' + esc(row.grade === 'SR' ? 'Senior - graduating' : row.grade) + '">' +
                  esc(row.grade) + '</span>'
                : '';
            const rank = buildRankBar(row.rank, row.rank_total) +
                (row.rank
                    ? '<span class="sd3-rank-num">' + esc(row.rank) + ' <span class="sd3-of">/ ' + esc(row.rank_total) + '</span></span>'
                    : '<span class="sd3-rank-num sd3-of">—</span>');

            const eventCell = '<td data-label="Event">' +
                (newEvent ? esc(row.event) : '<span class="sd3-event-cont">&nbsp;</span>') + '</td>';
            const relayTag = row.entry_type === 'relay' ? ' <span class="sd3-relay-tag">relay</span>' : '';

            if (isRecords) {
                return '<tr class="sd3-athlete-row' + (newEvent ? ' is-event-start' : '') + '">' +
                    eventCell +
                    '<td data-label="Athlete">' +
                        (row.record_position
                            ? '<span class="sd3-record-pos">' + esc(row.record_position) + '</span>'
                            : '') +
                        name + relayTag + '</td>' +
                    '<td data-label="Mark" class="sd3-num">' + esc(row.mark_display) + '</td>' +
                    '<td data-label="Season" class="sd3-num sd3-of">' + esc(row.year || '—') + '</td>' +
                '</tr>';
            }

            return '<tr class="sd3-athlete-row' + (newEvent ? ' is-event-start' : '') + '">' +
                eventCell +
                '<td data-label="Name">' + name + grade + relayTag + '</td>' +
                '<td data-label="Best mark" class="sd3-num">' + esc(row.mark_display) + markStageTag(row) + '</td>' +
                '<td data-label="Postseason" class="sd3-sect-cell">' + postseasonCell(row) + '</td>' +
                '<td data-label="Rank" class="sd3-rank-cell">' + rank + '</td>' +
            '</tr>';
        }).join('');

        const filterNote = scorecardFilter.group
            ? '<div class="sd3-filter-note">Showing <strong>' + esc(scorecardFilter.group) + '</strong> only ' +
              '<button type="button" class="sd3-link-button" data-clear-filter>show all events</button></div>'
            : '';
        const modeNote = isRecords
            ? '<div class="sd3-filter-note">Program bests across every covered season &mdash; ' +
              'top ' + esc(scorecard.records_per_event || 3) + ' per event. Postseason meets only.</div>'
            : '';
        refs.scorecard.innerHTML = modeNote + filterNote +
            '<table class="sd3-scorecard-table">' + head + '<tbody>' + body + '</tbody></table>';

        const clear = refs.scorecard.querySelector('[data-clear-filter]');
        if (clear) {
            clear.addEventListener('click', function () { applyGroupFilter(null); });
        }

        refs.scorecard.querySelectorAll('th[data-sort]').forEach(function (th) {
            th.addEventListener('click', function () {
                const key = th.getAttribute('data-sort');
                scorecardSort.dir = scorecardSort.key === key ? -scorecardSort.dir : 1;
                scorecardSort.key = key;
                renderScorecard(scorecard);
            });
        });
    };

    const renderGroupStrip = function (standings) {
        if (!standings || !standings.length) {
            return '';
        }
        // Ranked strongest-first so the answer to "what are we good at" is the reading order.
        const ordered = standings.slice().sort(function (a, b) {
            return (a.rank || Number.MAX_SAFE_INTEGER) - (b.rank || Number.MAX_SAFE_INTEGER);
        });
        const tiles = ordered.map(function (group) {
            const active = scorecardFilter.group === group.group ? ' is-active' : '';
            const rank = group.rank
                ? esc(group.rank) + ' <span class="sd3-of">/ ' + esc(group.rank_total) + '</span>'
                : '<span class="sd3-of">—</span>';
            // Same bar as the table below and the tiles above. All six groups share
            // one denominator, so the six lengths are directly comparable -- which
            // is the point: strengths and weaknesses read as a shape, not six numbers.
            const bar = buildBar(rankPercent(group.rank, group.rank_total), {
                className: 'sd3-bar-tile',
            });
            return '<button type="button" class="sd3-group-tile' + active + '" data-group="' + esc(group.group) + '"' +
                ' title="Filter the event scorecard to ' + esc(group.group) + '">' +
                '<div class="sd3-group-name">' + esc(group.group) + '</div>' +
                '<div class="sd3-group-rank">' + rank + '</div>' + bar +
            '</button>';
        }).join('');
        return '<div class="sd3-group-strip-label">Event groups &mdash; statewide rank, strongest first. ' +
            'Select one to filter the scorecard below.</div>' +
            '<div class="sd3-group-strip">' + tiles + '</div>';
    };

    const applyGroupFilter = function (groupName) {
        const standings = (state.programRank && state.programRank.group_standings) || [];
        const found = standings.filter(function (g) { return g.group === groupName; })[0];
        scorecardFilter.group = found ? groupName : null;
        scorecardFilter.events = found ? found.events : null;
        if (state.programRank) {
            renderProgramRank(state.programRank);
        }
        if (state.scorecard) {
            renderScorecard(state.scorecard);
        }
    };

    const renderSeasonH2H = function (payload) {
        if (!payload || !payload.available || !payload.seasons.length) {
            refs.h2h.innerHTML = '<div class="sd3-note sd3-subtle">' +
                esc((payload && payload.reason) || 'No earlier season to compare against.') + '</div>';
            return;
        }
        const cards = payload.seasons.map(function (season) {
            const cls = season.result === 'WIN' ? 'is-win' : (season.result === 'LOSS' ? 'is-loss' : 'is-tie');
            const tip = 'Won ' + season.events_won + ' events, lost ' + season.events_lost +
                (season.uncontested_points
                    ? '. ' + season.uncontested_points + ' of ' + season.points_for +
                      ' came from events the ' + season.season + ' team did not contest.'
                    : '');
            return '<div class="sd3-h2h-row" title="' + esc(tip) + '">' +
                '<span class="sd3-h2h-season">vs ' + esc(season.season) + '</span>' +
                '<span class="sd3-h2h-pill ' + cls + '">' + esc(season.result) + '</span>' +
                '<span class="sd3-h2h-score">' + esc(season.points_for) + ' – ' + esc(season.points_against) + '</span>' +
            '</div>';
        }).join('');
        refs.h2h.innerHTML = cards +
            '<div class="sd3-h2h-note">Scored as a dual meet (5-3-1 individual, 5 relay) using each ' +
            'season&rsquo;s best postseason marks. Postseason meets only, so these are not full-season bests.</div>';
    };

    // Graduation is the one thing the season head-to-head cannot see: it looks
    // backward, and a coach plans forward. Scoring the returning athletes with the
    // same dual-meet routine keeps both blocks on one scale, so "we beat 2025 and
    // our core still would" and "we beat 2025, but our core would lose to it by 40"
    // are told in the same sentence shape.
    const renderReturning = function (payload) {
        if (!payload || !payload.available) {
            refs.returning.innerHTML = '<div class="sd3-note sd3-subtle">' +
                esc((payload && payload.reason) || 'Nothing to project for this season.') + '</div>';
            return;
        }
        const ret = payload.retention;
        const tile = function (label, kept, total, title) {
            const pct = total ? (100 * kept) / total : 0;
            return '<div class="sd3-ret-tile" title="' + esc(title) + '">' +
                '<div class="sd3-ret-tile-label">' + esc(label) + '</div>' +
                '<div class="sd3-ret-tile-value">' + kept +
                    ' <span class="sd3-of">of ' + total + '</span></div>' +
                buildBar(pct, { className: 'sd3-bar-tile' }) +
            '</div>';
        };

        const tiles = '<div class="sd3-ret-tiles">' +
            tile('Athletes returning', ret.athletes_returning, ret.athletes_total,
                 'Athletes holding a scoring slot this season who are not seniors.') +
            tile('Entry slots returning', ret.marks_returning, ret.marks_total,
                 'Of the individual entry slots filled this season, how many a returning athlete holds.') +
            tile('Event bests returning', ret.event_bests_returning, ret.event_bests_total,
                 'Events whose best mark this season belongs to a returning athlete.') +
        '</div>';

        let grads;
        if (!payload.graduating.length) {
            grads = '<div class="sd3-ret-block-title">Graduating</div>' +
                '<div class="sd3-ret-none">Nobody in a scoring slot is a senior &mdash; the whole scoring team returns.</div>';
        } else {
            grads = '<div class="sd3-ret-block-title">Graduating (' + payload.graduating.length + ')</div>' +
                payload.graduating.map(function (athlete) {
                    const marks = athlete.marks.map(function (mark) {
                        return '<span class="sd3-ret-mark">' + esc(mark.event) + ' <strong>' +
                            esc(mark.mark_display) + '</strong>' +
                            (mark.rank ? ' &middot; ' + esc(mark.rank) + ' / ' + esc(mark.rank_total) : '') +
                            (mark.is_event_best ? '<span class="sd3-ret-best">TEAM BEST</span>' : '') +
                        '</span>';
                    }).join('');
                    const name = athlete.athlete_id
                        ? '<a href="/athlete-dashboard/' + esc(athlete.athlete_id) + '">' + esc(athlete.name) + '</a>'
                        : esc(athlete.name);
                    return '<div class="sd3-ret-grad">' +
                        '<span class="sd3-ret-grad-name">' + name + '</span>' + marks +
                    '</div>';
                }).join('');
        }

        let core = '';
        if (payload.core_h2h && payload.core_h2h.length) {
            core = '<div class="sd3-ret-block-title">The ' + esc(payload.next_year) +
                    ' returning core, scored against past seasons</div>' +
                payload.core_h2h.map(function (season) {
                    const cls = season.result === 'WIN' ? 'is-win' : (season.result === 'LOSS' ? 'is-loss' : 'is-tie');
                    const tip = 'Won ' + season.events_won + ' events, lost ' + season.events_lost + '.';
                    return '<div class="sd3-h2h-row" title="' + esc(tip) + '">' +
                        '<span class="sd3-h2h-season">vs ' + esc(season.season) + '</span>' +
                        '<span class="sd3-h2h-pill ' + cls + '">' + esc(season.result) + '</span>' +
                        '<span class="sd3-h2h-score">' + esc(season.points_for) + ' \u2013 ' + esc(season.points_against) + '</span>' +
                    '</div>';
                }).join('');
        }

        refs.returning.innerHTML = tiles + grads + core +
            '<div class="sd3-ret-note">' + esc(payload.note) + '</div>';
    };

    const renderQualifierStage = function (stage) {
        const renderRows = function (rows, isRelay) {
            if (!rows.length) {
                return '<p class="sd3-subtle">' + esc(stage.empty_text) + '</p>';
            }
            return '<table class="sd3-table"><thead><tr><th>Name</th><th>Event</th><th>Mark</th><th>Source</th><th>Type</th></tr></thead><tbody>' +
                rows.map(function (row) {
                    const name = row.athlete_id
                        ? '<a class="sd3-link" href="/athlete-dashboard/' + row.athlete_id + '">' + esc(row.name) + '</a>'
                        : esc(row.name);
                    return '<tr>' +
                        '<td data-label="Name">' + name + '</td>' +
                        '<td data-label="Event">' + esc(row.event) + '</td>' +
                        '<td data-label="Mark">' + esc(row.mark) + '</td>' +
                        '<td data-label="Source">' + esc(row.source_label || '—') + '</td>' +
                        '<td data-label="Type">' + esc(row.qualifier_type || (isRelay ? 'relay' : 'individual')) + '</td>' +
                    '</tr>';
                }).join('') +
            '</tbody></table>';
        };

        return '<div class="sd3-panel sd3-qualifier-panel">' +
            '<div class="sd3-section-head"><div><div class="sd3-section-title">' + esc(stage.stage) + '</div><div class="sd3-subtle">' + esc(stage.status || '') + '</div></div></div>' +
            '<div><div class="sd3-subtle" style="margin-bottom:0.4rem;">Individuals</div>' + renderRows(stage.individual, false) + '</div>' +
            '<div style="margin-top:1rem;"><div class="sd3-subtle" style="margin-bottom:0.4rem;">Relays</div>' + renderRows(stage.relay, true) + '</div>' +
        '</div>';
    };

    const renderQualifiers = function (qualifiers) {
        if (!qualifiers || !qualifiers.available) {
            refs.qualifiers.innerHTML = '<div class="sd3-panel sd3-note sd3-subtle">Qualifier lists are not available for this season.</div>';
            return;
        }
        refs.qualifiers.innerHTML = renderQualifierStage(qualifiers.regional) + renderQualifierStage(qualifiers.state);
    };

    const buildTrendChart = function (detail) {
        const points = detail.trend_points || [];
        if (!points.length) {
            return '<div class="sd3-note sd3-subtle">No trend points available.</div>';
        }

        const years = Array.from(new Set(points.map(function (point) { return point.year; }))).sort();
        const values = points.map(function (point) { return point.mark_value; });
        const minValue = Math.min.apply(null, values);
        const maxValue = Math.max.apply(null, values);
        const width = 920;
        const height = 280;
        const leftPad = 48;
        const rightPad = 18;
        const topPad = 18;
        const bottomPad = 42;
        const plotWidth = width - leftPad - rightPad;
        const plotHeight = height - topPad - bottomPad;
        const xForYear = function (year) {
            if (years.length === 1) {
                return leftPad + plotWidth / 2;
            }
            return leftPad + ((year - years[0]) / (years[years.length - 1] - years[0])) * plotWidth;
        };
        const yForValue = function (value) {
            if (maxValue === minValue) {
                return topPad + plotHeight / 2;
            }
            const ratio = detail.chart_inverts_axis
                ? (value - minValue) / (maxValue - minValue)
                : (maxValue - value) / (maxValue - minValue);
            return topPad + ratio * plotHeight;
        };

        const offsets = {};
        const dots = points.map(function (point, index) {
            const key = point.year + '|' + point.mark_value;
            const offsetIndex = offsets[key] || 0;
            offsets[key] = offsetIndex + 1;
            const jitter = offsetIndex === 0 ? 0 : (offsetIndex % 2 === 0 ? 10 : -10);
            const cx = xForYear(point.year) + jitter;
            const cy = yForValue(point.mark_value);
            const radius = point.is_selected_season ? 7 : 5;
            const fill = point.is_selected_season ? '#6ea8fe' : '#f5f7fa';
            const stroke = point.is_selected_season ? '#f5f7fa' : '#6ea8fe';
            const title = esc(point.year + ' • ' + point.holder_name + ' • ' + point.mark_display + ' • ' + point.stage + ' • place ' + (point.place || '—'));
            const href = point.holder_athlete_id ? '/athlete-dashboard/' + point.holder_athlete_id : null;
            const anchorStart = href ? '<a xlink:href="' + href + '" href="' + href + '" tabindex="0">' : '';
            const anchorEnd = href ? '</a>' : '';
            return anchorStart +
                '<circle cx="' + cx + '" cy="' + cy + '" r="' + radius + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="2"><title>' + title + '</title></circle>' +
                anchorEnd;
        }).join('');

        const xLabels = years.map(function (year) {
            return '<text x="' + xForYear(year) + '" y="' + (height - 14) + '" text-anchor="middle" fill="#a5b0bc" font-size="12">' + year + '</text>';
        }).join('');
        const guideLines = years.map(function (year) {
            return '<line x1="' + xForYear(year) + '" y1="' + topPad + '" x2="' + xForYear(year) + '" y2="' + (topPad + plotHeight) + '" stroke="#2a3440" stroke-dasharray="3 4" />';
        }).join('');

        return '<div class="sd3-chart-wrap sd3-panel">' +
            '<svg viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Season-by-season postseason trend chart">' +
                '<rect x="' + leftPad + '" y="' + topPad + '" width="' + plotWidth + '" height="' + plotHeight + '" fill="#131920" stroke="#2a3440"></rect>' +
                guideLines +
                '<line x1="' + leftPad + '" y1="' + (topPad + plotHeight) + '" x2="' + (leftPad + plotWidth) + '" y2="' + (topPad + plotHeight) + '" stroke="#56616d"></line>' +
                '<line x1="' + leftPad + '" y1="' + topPad + '" x2="' + leftPad + '" y2="' + (topPad + plotHeight) + '" stroke="#56616d"></line>' +
                dots +
                xLabels +
            '</svg>' +
            '<div class="sd3-chart-list">' +
                points.map(function (point) {
                    const text = esc(point.year + ' • ' + point.holder_name + ' • ' + point.mark_display + ' • ' + point.stage + ' • place ' + (point.place || '—'));
                    if (point.holder_athlete_id) {
                        return '<a href="/athlete-dashboard/' + point.holder_athlete_id + '" class="sd3-link">' + text + '</a>';
                    }
                    return '<span>' + text + '</span>';
                }).join('') +
            '</div>' +
        '</div>';
    };

    const renderEventDetail = function (detail) {
        refs.eventTitle.textContent = detail.event;
        refs.eventSubtitle.textContent = state.core.school.name + ' • ' + state.gender + ' • ' + state.season;

        const rows = (detail.all_marks || []).map(function (row) {
            const name = row.row_type === 'individual'
                ? '<a class="sd3-link" href="/athlete-dashboard/' + row.athlete_id + '">' + esc(row.athlete_name) + '</a>'
                : esc(row.team_name || state.core.school.name);
            return '<tr>' +
                '<td data-label="Name">' + name + '</td>' +
                '<td data-label="Mark">' + esc(row.mark) + '</td>' +
                '<td data-label="Stage">' + esc(row.stage + (row.result_type ? ' • ' + row.result_type : '')) + '</td>' +
                '<td data-label="Place">' + esc(row.place || '—') + '</td>' +
            '</tr>';
        }).join('');

        refs.eventContent.innerHTML =
            '<div class="sd3-section-title">All Marks</div>' +
            '<div class="sd3-panel"><table class="sd3-table"><thead><tr><th>Name</th><th>Mark</th><th>Stage</th><th>Place</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
            '<div class="sd3-section" style="margin-top:1rem;"><div class="sd3-section-title">Season-by-Season Trend</div>' + buildTrendChart(detail) + '</div>';
    };

    const renderLeaderboard = function (payload) {
        refs.leaderboardSubtitle.textContent = state.gender + ' • ' + state.season + ' postseason';
        const rows = payload.rows || [];
        if (!rows.length) {
            refs.leaderboardContent.innerHTML = '<div class="sd3-note sd3-subtle">No schools matched this filter.</div>';
            return;
        }

        const table = '<table class="sd3-table"><thead><tr><th>Rank</th><th>School</th><th>Composite</th><th>Enrollment</th></tr></thead><tbody>' +
            rows.map(function (row) {
                const highlight = row.school_id === state.core.school.id ? ' class="sd3-highlight-row"' : '';
                const enrollment = row.enrollment == null
                    ? '—'
                    : row.enrollment_is_exact
                        ? row.enrollment + ' (' + row.enrollment_source_year + ')'
                        : row.enrollment + ' (nearest ' + row.enrollment_source_year + ')';
                return '<tr' + highlight + '>' +
                    '<td data-label="Rank">' + esc(row.rank_display) + '</td>' +
                    '<td data-label="School">' + esc(row.school_name) + (row.is_pinned ? ' <span class="sd3-subtle">(pinned)</span>' : '') + '</td>' +
                    '<td data-label="Composite">' + esc(row.composite_score.toFixed(1)) + '</td>' +
                    '<td data-label="Enrollment">' + esc(enrollment) + '</td>' +
                '</tr>';
            }).join('') +
        '</tbody></table>';

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
            scorecardFilter.group = null;
            scorecardFilter.events = null;
            state.leaderboard = null;
            refs.scorecard.innerHTML = '';
            refs.scorecardStatus.textContent = '';

            const query = buildQuery({
                gender: gender || state.gender,
                season: season,
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
                refs.h2hSection.classList.remove('sd3-hidden');
                refs.returningSection.classList.remove('sd3-hidden');
                void loadSeasonH2H(requestId);
                void loadReturning(requestId);
                void loadScorecard();
                refs.programRankSection.classList.remove('sd3-hidden');
                refs.programRank.innerHTML = '<div class="sd3-subtle">Loading ranking…</div>';
                refs.qualifiers.innerHTML = '<div class="sd3-panel sd3-note sd3-subtle">Loading qualifier lists…</div>';
                void loadRanking(requestId);
                void loadQualifiers(requestId);
            } else {
                refs.h2hSection.classList.add('sd3-hidden');
                refs.returningSection.classList.add('sd3-hidden');
                void loadScorecard();
                refs.programRankSection.classList.add('sd3-hidden');
                refs.qualifiers.innerHTML = '';
            }
        } catch (error) {
            showError(error.message);
        }
    };

    const loadRanking = async function (requestId) {
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const ranking = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/ranking?' + query);
            if (requestId === state.requestId) {
                // Kept so a group-filter click can re-render the strip without refetching.
                state.programRank = ranking;
                renderProgramRank(ranking);
            }
        } catch (error) {
            if (requestId === state.requestId) {
                refs.programRank.innerHTML = '<div class="sd3-subtle">' + esc(error.message) + '</div>';
            }
        }
    };

    const loadQualifiers = async function (requestId) {
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            state.qualifiers = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/qualifiers?' + query);
            if (requestId === state.requestId) {
                renderQualifiers(state.qualifiers);
            }
        } catch (error) {
            if (requestId === state.requestId) {
                refs.qualifiers.innerHTML = '<div class="sd3-panel sd3-note sd3-subtle">' + esc(error.message) + '</div>';
            }
        }
    };

    const loadSeasonH2H = async function (requestId) {
        refs.h2h.innerHTML = '<div class="sd3-subtle">Loading season comparison…</div>';
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const payload = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/season-h2h?' + query);
            if (requestId !== state.requestId) { return; }
            renderSeasonH2H(payload);
        } catch (error) {
            refs.h2h.innerHTML = '<div class="sd3-note sd3-subtle">' + esc(error.message) + '</div>';
        }
    };

    const loadReturning = async function (requestId) {
        refs.returning.innerHTML = '<div class="sd3-subtle">Loading next-season outlook\u2026</div>';
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const payload = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/returning?' + query);
            if (requestId !== state.requestId) { return; }
            renderReturning(payload);
        } catch (error) {
            refs.returning.innerHTML = '<div class="sd3-note sd3-subtle">' + esc(error.message) + '</div>';
        }
    };

    const loadScorecard = async function () {
        if (state.scorecard) {
            renderScorecard(state.scorecard);
            return;
        }
        refs.scorecardStatus.textContent = '';
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            state.scorecard = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/athletes?' + query);
            refs.scorecardStatus.textContent = '';
            renderScorecard(state.scorecard);
        } catch (error) {
            refs.scorecardStatus.textContent = error.message;
        }
    };

    const loadEventDetail = async function (eventName) {
        try {
            refs.eventContent.innerHTML = '<div class="sd3-note sd3-subtle">Loading event detail…</div>';
            openModal(refs.eventModal);
            const query = buildQuery({ gender: state.gender, season: state.season });
            const detail = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/events/' + encodeURIComponent(eventName) + '?' + query);
            renderEventDetail(detail);
        } catch (error) {
            refs.eventContent.innerHTML = '<div class="sd3-note sd3-subtle">' + esc(error.message) + '</div>';
        }
    };

    const loadLeaderboard = async function () {
        refs.leaderboardContent.innerHTML = '<div class="sd3-note sd3-subtle">Loading leaderboard…</div>';
        const enrollmentValue = refs.leaderboardEnrollment.value === 'custom'
            ? refs.leaderboardCustom.value
            : refs.leaderboardEnrollment.value;
        try {
            const query = buildQuery({
                gender: state.gender,
                season: state.season,
                top_n: refs.leaderboardTopN.value,
                enrollment_max: enrollmentValue,
            });
            state.leaderboard = await fetchJson('/api/v3/schools/' + schoolId + '/dashboard/leaderboard?' + query);
            renderLeaderboard(state.leaderboard);
        } catch (error) {
            refs.leaderboardContent.innerHTML = '<div class="sd3-note sd3-subtle">' + esc(error.message) + '</div>';
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

    refs.leaderboardEnrollment.addEventListener('change', function () {
        refs.leaderboardCustom.classList.toggle('sd3-hidden', refs.leaderboardEnrollment.value !== 'custom');
    });

    refs.leaderboardApply.addEventListener('click', function () {
        loadLeaderboard();
    });

    root.querySelectorAll('[data-close-modal]').forEach(function (button) {
        button.addEventListener('click', function () {
            closeModal(document.getElementById(button.getAttribute('data-close-modal')));
        });
    });

    [refs.leaderboardModal, refs.eventModal].forEach(function (modal) {
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
