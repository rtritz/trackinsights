document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('school-dashboard-v2');
    if (!root) {
        return;
    }

    const schoolId = Number(root.dataset.schoolId);
    const refs = {
        loading: document.getElementById('sd2-loading'),
        error: document.getElementById('sd2-error'),
        app: document.getElementById('sd2-app'),
        schoolName: document.getElementById('sd2-school-name'),
        schoolMeta: document.getElementById('sd2-school-meta'),
        filterRow: document.getElementById('sd2-filter-row'),
        logoWrap: document.getElementById('sd2-logo-wrap'),
        logo: document.getElementById('sd2-logo'),
        stageGrid: document.getElementById('sd2-stage-grid'),
        allTimeIntro: document.getElementById('sd2-all-time-intro'),
        programRankSection: document.getElementById('sd2-program-rank-section'),
        programRank: document.getElementById('sd2-program-rank'),
        loadScorecard: document.getElementById('sd2-load-scorecard'),
        scorecardStatus: document.getElementById('sd2-scorecard-status'),
        scorecard: document.getElementById('sd2-scorecard'),
        qualifiersSection: document.getElementById('sd2-qualifiers-section'),
        qualifiers: document.getElementById('sd2-qualifiers'),
        leaderboardOpen: document.getElementById('sd2-leaderboard-open'),
        leaderboardModal: document.getElementById('sd2-leaderboard-modal'),
        leaderboardContent: document.getElementById('sd2-leaderboard-content'),
        leaderboardSubtitle: document.getElementById('sd2-leaderboard-subtitle'),
        leaderboardEnrollment: document.getElementById('sd2-leaderboard-enrollment'),
        leaderboardCustom: document.getElementById('sd2-leaderboard-custom'),
        leaderboardTopN: document.getElementById('sd2-leaderboard-topn'),
        leaderboardApply: document.getElementById('sd2-leaderboard-apply'),
        eventModal: document.getElementById('sd2-event-modal'),
        eventTitle: document.getElementById('sd2-event-title'),
        eventSubtitle: document.getElementById('sd2-event-subtitle'),
        eventContent: document.getElementById('sd2-event-content'),
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
        refs.loading.classList.add('sd2-hidden');
        refs.app.classList.add('sd2-hidden');
        refs.error.classList.remove('sd2-hidden');
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
        ].filter(Boolean).join('<span class="sd2-meta-separator" aria-hidden="true">|</span>');
        if (school.logo_url) {
            refs.logo.src = school.logo_url;
            refs.logoWrap.classList.remove('sd2-hidden');
        } else {
            refs.logoWrap.classList.add('sd2-hidden');
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
            return '<button type="button" role="radio" class="sd2-season-pill" data-season="' + esc(year) + '"' +
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
            '<div class="sd2-segmented" role="radiogroup" aria-label="Gender">' + genderButtons + '</div>' +
            '<div class="sd2-seasons" role="radiogroup" aria-label="Season">' +
                seasonPills +
                '<span class="sd2-season-divider" aria-hidden="true"></span>' +
                '<button type="button" role="radio" class="sd2-season-pill" data-season="all-time"' +
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
        refs.allTimeIntro.classList.toggle('sd2-hidden', core.stage_results !== null);
        refs.qualifiersSection.classList.toggle('sd2-hidden', core.stage_results === null);

        if (!core.stage_results) {
            refs.allTimeIntro.textContent = core.all_time_intro || 'All-Time mode shows covered postseason program bests only.';
            return;
        }

        core.stage_results.stages.forEach(function (stage) {
            const card = document.createElement('div');
            card.className = 'sd2-stage-card';
            card.innerHTML =
                '<div class="sd2-stage-label">' + esc(stage.stage) + '</div>' +
                '<div class="sd2-stage-rank">' + esc(stage.team_rank_display) + '</div>' +
                '<div class="sd2-stage-points">' + (stage.attended ? esc(stage.points_display + ' points') : '—') + '</div>';
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

        // Percentile bar with the median as a fixed centerline. Because the axis is
        // "share of programs you beat", the median sits at 50% by construction --
        // no distorted scale needed to put it in the middle.
        const buildPercentileBar = function (percentile) {
            if (typeof percentile !== 'number') {
                return '';
            }
            return '<div class="sd2-rank-bar" aria-hidden="true">' +
                '<span style="width:' + clamp(percentile) + '%;"></span>' +
                '<span class="sd2-rank-median" style="left:50%;" title="State median"></span>' +
            '</div>';
        };

        const groupPercentiles = programRank.group_percentiles || {};

        // Sorted by percentile, not raw score. Each group has its own distribution,
        // so raw scores are not comparable across groups -- a 57.2 in Jumps can beat
        // more of the field than a 59.5 in Hurdles.
        const groupItems = Object.keys(programRank.group_scores || {})
            .sort(function (a, b) {
                return (groupPercentiles[b] || 0) - (groupPercentiles[a] || 0);
            })
            .map(function (group) {
                const score = programRank.group_scores[group];
                const percentile = groupPercentiles[group];
                const standing = typeof percentile === 'number'
                    ? '<div class="sd2-rank-delta ' + (percentile >= 50 ? 'is-above' : 'is-below') + '">' +
                        'Beats ' + Math.round(percentile) + '% of programs' +
                      '</div>'
                    : '';
                return '<button type="button" class="sd2-breakdown-item" data-ranking-group="' + esc(group) + '">' +
                    '<div class="sd2-breakdown-label">' + esc(group) + '</div>' +
                    '<div class="sd2-breakdown-value">' + esc(score.toFixed(1)) + ' / 100</div>' +
                    buildPercentileBar(percentile) +
                    standing +
                '</button>';
            }).join('');

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
                segments += '<div class="sd2-quartile-seg" style="width:' + width + '%;" title="' +
                    esc(labels[i]) + ': scores ' + esc(stops[i].toFixed(1)) + '-' + esc(stops[i + 1].toFixed(1)) +
                    '">' + esc(labels[i]) + '</div>';
            }
            const you = typeof myScore === 'number'
                ? '<span class="sd2-quartile-you" style="left:' + clamp(myScore) + '%;" title="This program: ' + esc(myScore.toFixed(1)) + '"></span>'
                : '';
            return '<p class="sd2-subtle" style="margin-top:0.8rem;">Where the 0-100 score sits against the field. Each block holds a quarter of all programs &mdash; they are uneven because most programs score low, which is why a 50 is well above the middle.</p>' +
                '<div class="sd2-quartile-strip">' + segments + you + '</div>' +
                '<div class="sd2-quartile-axis"><span>' + esc(dist.min.toFixed(1)) + '</span>' +
                '<span>median ' + esc(dist.median.toFixed(1)) + '</span>' +
                '<span>' + esc(dist.max.toFixed(1)) + '</span></div>';
        };

        // The composite lives here rather than in the headline. It is a mean of
        // per-slot percentiles with empty slots counted as zero, so it is largely a
        // depth measure -- kept visible so the ranking stays auditable, but not
        // presented as a verdict on how fast anyone ran.
        const slots = programRank.entry_slots;
        const depthNote = (typeof programRank.composite_score === 'number')
            ? '<p class="sd2-subtle" style="margin-top:0.8rem;">' +
                'Depth-weighted score: <strong>' + esc(programRank.composite_score.toFixed(1)) + ' / 100</strong>' +
                ' &mdash; the average statewide percentile across all ' + (slots ? slots.total : '') + ' entry slots, ' +
                'counting ' + (slots ? plural(slots.total - slots.filled, 'unfilled slot') : 'unfilled slots') + ' as zero. ' +
                'This is the value the statewide ranking sorts on, so a program with few entries scores low even when its athletes place well.' +
              '</p>'
            : '';

        const explainer =
            '<div class="sd2-details"><details><summary>How this works</summary>' +
                '<p class="sd2-subtle" style="margin-top:0.6rem;">' + esc(programRank.info_text) + '</p>' +
                depthNote +
                buildQuartileStrip(programRank.score_distribution, programRank.composite_score) +
            '</details></div>';

        if (!programRank.is_ranked) {
            refs.programRank.innerHTML =
                '<div class="sd2-rank-top"><div>' +
                    '<div class="sd2-subtle">Statewide ranking</div>' +
                    '<div class="sd2-rank-value" style="font-size:1.3rem;">Not ranked</div>' +
                    '<div class="sd2-rank-sub">This program has no valid postseason marks for this season, so it is absent from the statewide table rather than scored zero.</div>' +
                '</div></div>' + explainer;
            return;
        }

        const standing = programRank.standing;
        const percentile = programRank.percentile;
        const peer = programRank.peer_standing;

        // Both counts are shown at once so neither number has to be read as the
        // complement of the other -- the source of the "166th yet ahead of 57%?" jolt.
        const positionBlock = standing
            ? '<div class="sd2-position">' +
                '<div class="sd2-position-labels">' +
                    '<span class="sd2-position-behind">' + plural(standing.behind, 'program') + ' behind</span>' +
                    '<span class="sd2-position-ahead">' + plural(standing.ahead, 'program') + ' ahead</span>' +
                '</div>' +
                '<div class="sd2-position-bar">' +
                    '<span class="sd2-position-fill" style="width:' + clamp(percentile) + '%;"></span>' +
                    '<span class="sd2-position-median" style="left:50%;" title="State median"></span>' +
                    '<span class="sd2-position-marker" style="left:' + clamp(percentile) + '%;" title="This program"></span>' +
                '</div>' +
                '<div class="sd2-position-scale">' +
                    '<span>Weakest</span><span>State median</span><span>Strongest</span>' +
                '</div>' +
                (standing.tied
                    ? '<div class="sd2-position-note">' + plural(standing.tied, 'program') + ' tied on score.</div>'
                    : '') +
              '</div>'
            : '';

        refs.programRank.innerHTML =
            '<div class="sd2-rank-top">' +
                '<div>' +
                    '<div class="sd2-subtle">Statewide ranking</div>' +
                    '<div class="sd2-rank-value">' + esc(programRank.rank_display) + '</div>' +
                    // Statewide rank is heavily driven by enrollment, so the same
                    // finish means very different things at a 400- and a 2,400-student
                    // school. This is the size-controlled read of the same season.
                    (peer
                        ? '<div class="sd2-rank-sub" title="Compared with the ' + peer.total +
                            ' schools nearest this one by enrollment (' + peer.enrollment_min +
                            '-' + peer.enrollment_max + ' students)">' +
                            '#' + peer.rank + ' of ' + peer.total + ' among like-size schools' +
                          '</div>'
                        : '') +
                '</div>' +
                // The rank's two ingredients, shown separately so it reads as
                // "few entries" or "slow marks" rather than one opaque verdict.
                (slots
                    ? '<div>' +
                        '<div class="sd2-subtle">Entry slots filled</div>' +
                        '<div class="sd2-rank-value" style="font-size:1.3rem;">' + slots.filled + ' of ' + slots.total + '</div>' +
                        (slots.entered > slots.filled
                            ? '<div class="sd2-rank-sub">' +
                                (slots.entered - slots.filled === 1 ? '1 entry' : (slots.entered - slots.filled) + ' entries') +
                                ' scored 0 (DQ/DNF/no mark)</div>'
                            : '') +
                      '</div>'
                    : '') +
                (typeof programRank.posted_mark_percentile === 'number'
                    ? '<div>' +
                        '<div class="sd2-subtle">Marks posted</div>' +
                        '<div class="sd2-rank-value" style="font-size:1.3rem;">' + esc(ordinal(programRank.posted_mark_percentile)) + '</div>' +
                        '<div class="sd2-rank-sub">average percentile statewide</div>' +
                      '</div>'
                    : '') +
            '</div>' +
            positionBlock +
            explainer +
            '<div class="sd2-breakdown-grid">' + groupItems + '</div>';
    };

    const renderScorecard = function (scorecard) {
        if (!scorecard || !scorecard.rows.length) {
            refs.scorecard.innerHTML = '<div class="sd2-note sd2-subtle">No postseason event strength data available.</div>';
            return;
        }

        const isAllTime = String(scorecard.season) === 'all-time';
        const header = '<div class="sd2-score-row" style="color:var(--sd2-muted); text-transform:uppercase; font-size:0.78rem; letter-spacing:0.08em; border-bottom:1px solid var(--sd2-border);">' +
            '<div>Event</div><div>Best mark</div><div>Name</div><div>Statewide rank</div><div>' + (isAllTime ? 'Season' : 'School Best vs. Prior Season') + '</div>' +
            '</div>';

        const rows = scorecard.rows.map(function (row) {
            const holder = row.holder_type === 'athlete' && row.holder_athlete_id
                ? '<a class="sd2-link" href="/athlete-dashboard/' + row.holder_athlete_id + '">' + esc(row.holder_name) + '</a>'
                : esc(row.holder_name || '—');
            const statusClass = row.status ? 'sd2-status-' + (row.status.tone || 'muted') : 'sd2-status-muted';
            const statusText = isAllTime ? (row.achieved_year || '—') : (row.status ? row.status.label : '—');
            const statusTitle = isAllTime ? 'Covered postseason season achieved' : (row.status ? row.status.tooltip : '');
            const content = '<div class="sd2-score-row">' +
                '<div><strong>' + esc(row.event) + '</strong><div class="sd2-mobile-note">' + esc(row.group) + '</div></div>' +
                '<div>' + esc(row.mark_display) + '</div>' +
                '<div>' + holder + '</div>' +
                '<div>' + esc(row.rank_display) + '</div>' +
                '<div class="' + statusClass + '" title="' + esc(statusTitle) + '">' + esc(statusText) + '</div>' +
            '</div>';

            if (isAllTime) {
                return '<div class="sd2-row-button" role="presentation">' + content + '</div>';
            }

            return '<button type="button" class="sd2-row-button" data-event-name="' + esc(row.event) + '">' + content + '</button>';
        }).join('');

        refs.scorecard.innerHTML = header + rows;
        refs.scorecard.querySelectorAll('[data-event-name]').forEach(function (button) {
            button.addEventListener('click', function () {
                loadEventDetail(button.getAttribute('data-event-name'));
            });
        });
    };

    const renderQualifierStage = function (stage) {
        const renderRows = function (rows, isRelay) {
            if (!rows.length) {
                return '<p class="sd2-subtle">' + esc(stage.empty_text) + '</p>';
            }
            return '<table class="sd2-table"><thead><tr><th>Name</th><th>Event</th><th>Mark</th><th>Source</th><th>Type</th></tr></thead><tbody>' +
                rows.map(function (row) {
                    const name = row.athlete_id
                        ? '<a class="sd2-link" href="/athlete-dashboard/' + row.athlete_id + '">' + esc(row.name) + '</a>'
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

        return '<div class="sd2-panel sd2-qualifier-panel">' +
            '<div class="sd2-section-head"><div><div class="sd2-section-title">' + esc(stage.stage) + '</div><div class="sd2-subtle">' + esc(stage.status || '') + '</div></div></div>' +
            '<div><div class="sd2-subtle" style="margin-bottom:0.4rem;">Individuals</div>' + renderRows(stage.individual, false) + '</div>' +
            '<div style="margin-top:1rem;"><div class="sd2-subtle" style="margin-bottom:0.4rem;">Relays</div>' + renderRows(stage.relay, true) + '</div>' +
        '</div>';
    };

    const renderQualifiers = function (qualifiers) {
        if (!qualifiers || !qualifiers.available) {
            refs.qualifiers.innerHTML = '<div class="sd2-panel sd2-note sd2-subtle">Qualifier lists are not available for this season.</div>';
            return;
        }
        refs.qualifiers.innerHTML = renderQualifierStage(qualifiers.regional) + renderQualifierStage(qualifiers.state);
    };

    const buildTrendChart = function (detail) {
        const points = detail.trend_points || [];
        if (!points.length) {
            return '<div class="sd2-note sd2-subtle">No trend points available.</div>';
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

        return '<div class="sd2-chart-wrap sd2-panel">' +
            '<svg viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Season-by-season postseason trend chart">' +
                '<rect x="' + leftPad + '" y="' + topPad + '" width="' + plotWidth + '" height="' + plotHeight + '" fill="#131920" stroke="#2a3440"></rect>' +
                guideLines +
                '<line x1="' + leftPad + '" y1="' + (topPad + plotHeight) + '" x2="' + (leftPad + plotWidth) + '" y2="' + (topPad + plotHeight) + '" stroke="#56616d"></line>' +
                '<line x1="' + leftPad + '" y1="' + topPad + '" x2="' + leftPad + '" y2="' + (topPad + plotHeight) + '" stroke="#56616d"></line>' +
                dots +
                xLabels +
            '</svg>' +
            '<div class="sd2-chart-list">' +
                points.map(function (point) {
                    const text = esc(point.year + ' • ' + point.holder_name + ' • ' + point.mark_display + ' • ' + point.stage + ' • place ' + (point.place || '—'));
                    if (point.holder_athlete_id) {
                        return '<a href="/athlete-dashboard/' + point.holder_athlete_id + '" class="sd2-link">' + text + '</a>';
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
                ? '<a class="sd2-link" href="/athlete-dashboard/' + row.athlete_id + '">' + esc(row.athlete_name) + '</a>'
                : esc(row.team_name || state.core.school.name);
            return '<tr>' +
                '<td data-label="Name">' + name + '</td>' +
                '<td data-label="Mark">' + esc(row.mark) + '</td>' +
                '<td data-label="Stage">' + esc(row.stage + (row.result_type ? ' • ' + row.result_type : '')) + '</td>' +
                '<td data-label="Place">' + esc(row.place || '—') + '</td>' +
            '</tr>';
        }).join('');

        refs.eventContent.innerHTML =
            '<div class="sd2-section-title">All Marks</div>' +
            '<div class="sd2-panel"><table class="sd2-table"><thead><tr><th>Name</th><th>Mark</th><th>Stage</th><th>Place</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
            '<div class="sd2-section" style="margin-top:1rem;"><div class="sd2-section-title">Season-by-Season Trend</div>' + buildTrendChart(detail) + '</div>';
    };

    const renderLeaderboard = function (payload) {
        refs.leaderboardSubtitle.textContent = state.gender + ' • ' + state.season + ' postseason';
        const rows = payload.rows || [];
        if (!rows.length) {
            refs.leaderboardContent.innerHTML = '<div class="sd2-note sd2-subtle">No schools matched this filter.</div>';
            return;
        }

        const table = '<table class="sd2-table"><thead><tr><th>Rank</th><th>School</th><th>Composite</th><th>Enrollment</th></tr></thead><tbody>' +
            rows.map(function (row) {
                const highlight = row.school_id === state.core.school.id ? ' class="sd2-highlight-row"' : '';
                const enrollment = row.enrollment == null
                    ? '—'
                    : row.enrollment_is_exact
                        ? row.enrollment + ' (' + row.enrollment_source_year + ')'
                        : row.enrollment + ' (nearest ' + row.enrollment_source_year + ')';
                return '<tr' + highlight + '>' +
                    '<td data-label="Rank">' + esc(row.rank_display) + '</td>' +
                    '<td data-label="School">' + esc(row.school_name) + (row.is_pinned ? ' <span class="sd2-subtle">(pinned)</span>' : '') + '</td>' +
                    '<td data-label="Composite">' + esc(row.composite_score.toFixed(1)) + '</td>' +
                    '<td data-label="Enrollment">' + esc(enrollment) + '</td>' +
                '</tr>';
            }).join('') +
        '</tbody></table>';

        const note = payload.selected_school_filtered_out
            ? '<div class="sd2-pinned-note">The focus school is outside the current enrollment filter.</div>'
            : '<div class="sd2-pinned-note">Top rows stay sorted by statewide composite rank. The focus school is highlighted and pinned when needed.</div>';

        refs.leaderboardContent.innerHTML = table + note;
    };

    const loadCore = async function (gender, season) {
        const requestId = ++state.requestId;
        try {
            refs.loading.classList.remove('sd2-hidden');
            refs.app.classList.add('sd2-hidden');
            refs.error.classList.add('sd2-hidden');
            state.scorecard = null;
            state.leaderboard = null;
            refs.scorecard.innerHTML = '';
            refs.scorecardStatus.textContent = '';

            const query = buildQuery({
                gender: gender || state.gender,
                season: season,
            });
            const core = await fetchJson('/api/v2/schools/' + schoolId + '/dashboard/core?' + query);
            if (requestId !== state.requestId) {
                return;
            }
            state.core = core;
            state.gender = core.filters.selected_gender;
            state.season = String(core.filters.selected_season);

            renderHeader(core);
            renderFilters(core);
            renderStages(core);

            refs.loading.classList.add('sd2-hidden');
            refs.app.classList.remove('sd2-hidden');

            if (core.stage_results) {
                refs.programRankSection.classList.remove('sd2-hidden');
                refs.programRank.innerHTML = '<div class="sd2-subtle">Loading ranking…</div>';
                refs.qualifiers.innerHTML = '<div class="sd2-panel sd2-note sd2-subtle">Loading qualifier lists…</div>';
                void loadRanking(requestId);
                void loadQualifiers(requestId);
            } else {
                refs.programRankSection.classList.add('sd2-hidden');
                refs.qualifiers.innerHTML = '';
            }
        } catch (error) {
            showError(error.message);
        }
    };

    const loadRanking = async function (requestId) {
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            const ranking = await fetchJson('/api/v2/schools/' + schoolId + '/dashboard/ranking?' + query);
            if (requestId === state.requestId) {
                renderProgramRank(ranking);
            }
        } catch (error) {
            if (requestId === state.requestId) {
                refs.programRank.innerHTML = '<div class="sd2-subtle">' + esc(error.message) + '</div>';
            }
        }
    };

    const loadQualifiers = async function (requestId) {
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            state.qualifiers = await fetchJson('/api/v2/schools/' + schoolId + '/dashboard/qualifiers?' + query);
            if (requestId === state.requestId) {
                renderQualifiers(state.qualifiers);
            }
        } catch (error) {
            if (requestId === state.requestId) {
                refs.qualifiers.innerHTML = '<div class="sd2-panel sd2-note sd2-subtle">' + esc(error.message) + '</div>';
            }
        }
    };

    const loadScorecard = async function () {
        if (state.scorecard) {
            renderScorecard(state.scorecard);
            return;
        }
        refs.scorecardStatus.textContent = 'Loading event scorecard…';
        try {
            const query = buildQuery({ gender: state.gender, season: state.season });
            state.scorecard = await fetchJson('/api/v2/schools/' + schoolId + '/dashboard/scorecard?' + query);
            refs.scorecardStatus.textContent = '';
            renderScorecard(state.scorecard);
        } catch (error) {
            refs.scorecardStatus.textContent = error.message;
        }
    };

    const loadEventDetail = async function (eventName) {
        try {
            refs.eventContent.innerHTML = '<div class="sd2-note sd2-subtle">Loading event detail…</div>';
            openModal(refs.eventModal);
            const query = buildQuery({ gender: state.gender, season: state.season });
            const detail = await fetchJson('/api/v2/schools/' + schoolId + '/dashboard/events/' + encodeURIComponent(eventName) + '?' + query);
            renderEventDetail(detail);
        } catch (error) {
            refs.eventContent.innerHTML = '<div class="sd2-note sd2-subtle">' + esc(error.message) + '</div>';
        }
    };

    const loadLeaderboard = async function () {
        refs.leaderboardContent.innerHTML = '<div class="sd2-note sd2-subtle">Loading leaderboard…</div>';
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
            state.leaderboard = await fetchJson('/api/v2/schools/' + schoolId + '/dashboard/leaderboard?' + query);
            renderLeaderboard(state.leaderboard);
        } catch (error) {
            refs.leaderboardContent.innerHTML = '<div class="sd2-note sd2-subtle">' + esc(error.message) + '</div>';
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

    refs.loadScorecard.addEventListener('click', function () {
        loadScorecard();
    });

    refs.leaderboardOpen.addEventListener('click', function () {
        openModal(refs.leaderboardModal);
        loadLeaderboard();
    });

    refs.leaderboardEnrollment.addEventListener('change', function () {
        refs.leaderboardCustom.classList.toggle('sd2-hidden', refs.leaderboardEnrollment.value !== 'custom');
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
