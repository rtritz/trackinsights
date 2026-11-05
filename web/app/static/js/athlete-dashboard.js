/* Athlete dashboard.
 *
 * Moved out of athlete-dashboard.html, where it sat as 413 lines inside a
 * <script> tag. Living here it gets syntax checking, it can be cached by the
 * browser, and "where is the code for this page?" has the obvious answer: the
 * file named after the page.
 *
 * It takes the athlete from a data- attribute on the page rather than from a
 * Jinja expression, which is what made moving it safe -- keep it that way.
 */

// @ts-nocheck
document.addEventListener('DOMContentLoaded', async function () {
const loadingState = document.getElementById('loading-state');
const errorState = document.getElementById('error-state');
const dashboardContent = document.getElementById('dashboard-content');
const athleteId = Number(dashboardContent?.dataset?.athleteId);
const shareButton = document.getElementById('copy-dashboard-link');
const shareStatus = document.getElementById('share-dashboard-status');

    if (!Number.isFinite(athleteId) || athleteId <= 0) {
        console.error('Invalid athlete identifier for dashboard view.');
        loadingState.classList.add('hidden');
        errorState.classList.remove('hidden');
        return;
    }

    const copyTextToClipboard = async (text) => {
        const fallbackCopy = () => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.setAttribute('readonly', 'true');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                const successful = document.execCommand('copy');
                document.body.removeChild(textarea);
                return successful;
            } catch (error) {
                document.body.removeChild(textarea);
                return false;
            }
        };

        if (navigator?.clipboard?.writeText && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (error) {
                console.warn('Clipboard copy failed, falling back', error);
                return fallbackCopy();
            }
        }

        return fallbackCopy();
    };

    const setShareStatus = (message, tone = 'muted') => {
        if (!shareStatus) {
            return;
        }
        shareStatus.textContent = message;
        shareStatus.classList.remove('text-green-600', 'text-red-600', 'text-gray-600');
        const toneClass = tone === 'success' ? 'text-green-600' : tone === 'error' ? 'text-red-600' : 'text-gray-600';
        shareStatus.classList.add('text-xs', toneClass);
    };

    const resetShareButton = () => {
        if (!shareButton) {
            return;
        }
        shareButton.disabled = false;
        shareButton.textContent = 'Copy share link';
    };

    const handleShareButtonClick = async () => {
        if (!shareButton) {
            return;
        }
        const url = window.location.href.split('#')[0];
        shareButton.disabled = true;
        const succeeded = await copyTextToClipboard(url);
        if (succeeded) {
            shareButton.textContent = 'Link copied!';
            setShareStatus('Copied to clipboard', 'success');
        } else {
            shareButton.textContent = 'Copy failed';
            setShareStatus('Unable to copy link', 'error');
        }
        setTimeout(resetShareButton, 1800);
    };

    if (shareButton) {
        shareButton.addEventListener('click', handleShareButtonClick);
    }

    function initializeAthleteCard(athlete) {
        // Share the public dashboard so scanned codes work away from this computer.
        const url = `https://www.trackinsights.org/athlete-dashboard/${athleteId}`;
        const name = athlete.full_name || 'Athlete';
        const status = document.getElementById('athlete-card-share-status');
        const setStatus = message => { status.textContent = message; };
        const designs = [
            {name: 'Black', color: '#000000'},
            {name: 'Burgundy', color: '#a60942'},
            {name: 'Navy', color: '#173b67'},
            {name: 'Green', color: '#17664e'},
        ];
        const filename = `${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || `athlete-${athleteId}`}-athlete-card.png`;
        const cardImages = designs.map(() => ({blob: null, file: null, pending: null}));
        const imageButtons = ['athlete-card-instagram', 'athlete-card-snapchat', 'athlete-card-download']
            .map(id => document.getElementById(id));
        const isMobile = Boolean(navigator.userAgentData?.mobile || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
            || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
        let sharingImage = false;
        const stack = document.getElementById('athlete-card-stack');
        let selectedCard = 0;
        const cardButtons = designs.map((design, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'athlete-card-option';
            button.setAttribute('aria-label', `${design.name} athlete card`);
            button.style.setProperty('--card-color', design.color);
            button.innerHTML = '<span class="athlete-card-face" aria-hidden="true"></span>';
            button.addEventListener('click', () => selectCard(index));
            button.addEventListener('keydown', event => {
                let next;
                if (event.key === 'ArrowRight') next = (selectedCard + 1) % designs.length;
                if (event.key === 'ArrowLeft') next = (selectedCard - 1 + designs.length) % designs.length;
                if (event.key === 'Home') next = 0;
                if (event.key === 'End') next = designs.length - 1;
                if (next === undefined) return;
                event.preventDefault();
                selectCard(next);
                cardButtons[next].focus();
            });
            stack.appendChild(button);
            return button;
        });
        function selectCard(index) {
            selectedCard = index;
            cardButtons.forEach((button, cardIndex) => {
                button.style.setProperty('--stack-index', (cardIndex - index + designs.length) % designs.length);
                button.setAttribute('aria-pressed', String(cardIndex === index));
            });
            document.getElementById('athlete-card-position').textContent = `${index + 1} / ${designs.length}`;
            prepareCardImage(index);
            updateImageButtons();
        }
        selectCard(0);
        document.getElementById('athlete-card-previous').addEventListener('click', () => selectCard((selectedCard - 1 + designs.length) % designs.length));
        document.getElementById('athlete-card-next').addEventListener('click', () => selectCard((selectedCard + 1) % designs.length));
        document.getElementById('athlete-card-caption').textContent =
            `Scan or share ${athlete.first || name}'s athlete card.`;
        const qrLink = document.getElementById('athlete-card-qr-link');
        qrLink.href = url;
        qrLink.setAttribute('aria-label', `Open ${name}'s athlete dashboard`);

        try {
            const code = qrcode(0, 'H');
            code.addData(url);
            code.make();
            document.getElementById('athlete-card-qr-code').innerHTML = code.createSvgTag({
                cellSize: 5, margin: 20, scalable: true,
            });
            const logo = document.getElementById('athlete-card-qr-logo');
            if (athlete.logo_url) {
                logo.onerror = () => { logo.hidden = true; };
                logo.src = athlete.logo_url;
                logo.alt = `${athlete.school || 'School'} logo`;
                logo.hidden = false;
            }
        } catch (error) {
            console.error('Unable to generate athlete QR code:', error);
            setStatus('QR code unavailable. Use Copy Link to share this athlete.');
        }

        document.getElementById('athlete-card-copy').addEventListener('click', async () => {
            const copied = await copyTextToClipboard(url);
            setStatus(copied ? 'Athlete link copied!' : `Copy this link: ${url}`);
        });

        function updateImageButtons() {
            const disabled = !cardImages[selectedCard].blob || sharingImage;
            imageButtons.forEach(button => { button.disabled = disabled; });
        }

        function prepareCardImage(index) {
            const image = cardImages[index];
            if (image.pending) return image.pending;
            // Render before a tap: awaiting canvas.toBlob inside the click handler
            // can lose the transient activation required by iOS Safari's share sheet.
            image.pending = new Promise((resolve, reject) => {
                const canvas = document.createElement('canvas');
                canvas.width = 750;
                canvas.height = 1050;
                const context = canvas.getContext('2d');
                if (!context) throw new Error('Card rendering is unavailable.');
                context.fillStyle = designs[index].color;
                context.fillRect(0, 0, canvas.width, canvas.height);
                canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('PNG generation failed.')), 'image/png');
            }).then(blob => {
                image.blob = blob;
                image.file = typeof File === 'function' ? new File([blob], filename, {type: 'image/png'}) : null;
            }).catch(() => {
                if (selectedCard === index) setStatus('Unable to prepare the card image. Reload to try again.');
            }).finally(updateImageButtons);
            return image.pending;
        }

        function downloadCardImage(image) {
            const objectUrl = URL.createObjectURL(image.blob);
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            // Give mobile browsers time to start reading the download.
            setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
        }

        const shareToApp = async platform => {
            const image = cardImages[selectedCard];
            if (!image.blob || sharingImage) return;
            sharingImage = true;
            updateImageButtons();
            try {
                // Call share directly in the tap handler, with the prepared PNG.
                // File support must be checked separately from text/link support.
                if (isMobile && image.file && navigator.share && navigator.canShare
                    && navigator.canShare({files: [image.file]})) {
                    await navigator.share({files: [image.file], title: `${name} - Track Insights`});
                    setStatus('Athlete card shared.');
                    return;
                }
            } catch (error) {
                if (error.name === 'AbortError') {
                    setStatus('Sharing canceled.');
                    return;
                }
                // Unsupported or blocked image sharing falls back to the same PNG.
            } finally {
                sharingImage = false;
                updateImageButtons();
            }
            try {
                downloadCardImage(image);
                setStatus(platform === 'Instagram'
                    ? 'Card downloaded. Save it to your photos, then add it to an Instagram Story.'
                    : 'Card downloaded. Save it to your photos, then choose it in Snapchat Memories.');
            } catch {
                setStatus('Unable to download the card. Please try again.');
            }
        };
        document.getElementById('athlete-card-instagram').addEventListener('click', () => shareToApp('Instagram'));
        document.getElementById('athlete-card-snapchat').addEventListener('click', () => shareToApp('Snapchat'));

        document.getElementById('athlete-card-download').addEventListener('click', () => {
            const image = cardImages[selectedCard];
            if (image.blob) {
                try {
                    downloadCardImage(image);
                    setStatus('Athlete card downloaded.');
                } catch {
                    setStatus('Unable to download the card. Please try again.');
                }
            }
        });
        // There are only four designs; warming each once also covers rapid changes.
        designs.forEach((_, index) => prepareCardImage(index));
    }

    const stageConfigs = {
        sectional: {
            title: 'Sectionals',
            accent: 'text-rose-700',
            encouragements: [
                'A finals appearance is within reach. Keep pushing!',
                'Your next PR will land you in the sectional finals.',
                'Stay focused and keep training hard!'
            ],
        },
        regional: {
            title: 'Regionals',
            accent: 'text-rose-700',
            encouragements: [
                'Regional history gets written by grinders like you.',
                'You’re one race away from owning the regional stage.',
                'Stay patient; the regional badge is saving you a spot.',
            ],
        },
        state: {
            title: 'State',
            accent: 'text-rose-700',
            encouragements: [
                'State is calling. Answer with your next PR.',
                'Can\'t wait to see you on the big stage.',
                'The state heat sheets have room for your name. Keep pushing.',
            ],
        },
    };

    const fallbackEncouragement = 'Keep grinding—your next milestone is closer than you think.';

    function getStageEncouragement(stageKey) {
        if (stageKey === 'state' && Math.random() < 0.01) {
            return 'John Pork wants you here...!';
        }

        const options = stageConfigs[stageKey]?.encouragements;
        if (Array.isArray(options) && options.length > 0) {
            const randomIndex = Math.floor(Math.random() * options.length);
            return options[randomIndex];
        }
        return fallbackEncouragement;
    }

    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[character]);

    function resultLink(result) {
        const event = encodeURIComponent(result.event);
        const type = encodeURIComponent(result.result_type || 'Final');
        return `/athlete-dashboard/${athleteId}/result/${result.meet_id}/${event}?result_type=${type}`;
    }

    function ordinal(place) {
        if (!place || place < 1) return '\u2014';
        const remainder = place % 100;
        return `${place}${remainder >= 11 && remainder <= 13 ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[place % 10] || 'th')}`;
    }

    function createMedalElement(entry) {
        const button = document.createElement('a');
        button.href = resultLink(entry);
        button.className = 'medal-button';
        const label = entry.place_label || 'Q';
        button.setAttribute('aria-label', `${entry.year || ''} ${entry.event || 'Event'}, ${label}, ${entry.result || 'Qualified'}`);
        const tone = entry.place === 1 ? 'gold' : entry.place === 2 ? 'silver' : entry.place === 3 ? 'bronze' : entry.place > 3 ? 'blue' : 'qualified';
        button.innerHTML = `<span class="medal-circle medal-${tone}">${escapeHtml(label)}</span>
            <span class="medal-details" role="tooltip"><strong>${escapeHtml(entry.event || 'Event')}</strong>
            ${escapeHtml(entry.year || '')}${entry.is_relay ? ' &middot; Relay' : ''}<br>
            Result: ${escapeHtml(entry.result || 'Qualified')}<br>Place: ${escapeHtml(label)}</span>`;
        button.addEventListener('mouseenter', () => button.style.zIndex = '40');
        button.addEventListener('mouseleave', () => button.style.zIndex = '');
        button.addEventListener('focus', () => button.style.zIndex = '40');
        button.addEventListener('blur', () => button.style.zIndex = '');
        return button;
    }

    function renderPersonalBests(bests) {
        const container = document.getElementById('personal-bests-container');
        container.style.setProperty('--personal-best-count', Math.max(bests.length, 1));
        container.innerHTML = bests.map(best => `<div class="personal-best">
            <span class="personal-best-label">${escapeHtml(best.event)}</span>
            <span class="personal-best-value">${escapeHtml(best.result)}</span>
        </div>`).join('') || '<p class="dashboard-empty">No personal bests recorded yet.</p>';
    }

    function renderProgression(eventName, rows, eventType) {
        const fieldEvent = eventType === 'Field' || /jump|vault|throw|shot|discus|javelin/i.test(eventName);
        const yearly = new Map();
        rows.forEach(row => {
            const value = row.result_value;
            if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value >= 9999 || !row.year) return;
            const current = yearly.get(row.year);
            if (!current || (fieldEvent ? value > current.result_value : value < current.result_value)) yearly.set(row.year, row);
        });
        const points = [...yearly.values()].sort((a, b) => a.year - b.year);
        if (points.length < 2) return '';
        const values = points.map(point => point.result_value);
        const low = Math.min(...values), high = Math.max(...values);
        const pad = Math.max((high - low) * 0.45, high * 0.015, 0.1);
        const min = Math.max(0, low - pad), max = high + pad;
        const x = year => points.length === 1 ? 228 : 66 + (year - points[0].year) / (points.at(-1).year - points[0].year) * 316;
        const y = value => 166 - (value - min) / (max - min) * 124;
        const format = value => {
            if (fieldEvent) return `${Math.floor(value / 12)}\u2032 ${Number((value % 12).toFixed(1))}\u2033`;
            if (value >= 60) return `${Math.floor(value / 60)}:${(value % 60).toFixed(1).padStart(4, '0')}`;
            return value.toFixed(2);
        };
        const ticks = Array.from({length: 5}, (_, index) => min + (max - min) * index / 4);
        return `<svg class="progression-chart" viewBox="0 0 420 220" role="img" aria-label="${escapeHtml(eventName)} yearly best playoff progression">
            <title>${escapeHtml(eventName)} progression</title>
            <desc>${escapeHtml(points.map(point => `${point.year}: ${point.result}`).join('; '))}</desc>
            ${ticks.map(value => `<line x1="60" x2="400" y1="${y(value)}" y2="${y(value)}" stroke="#e4e8ef"/><text x="53" y="${y(value) + 4}" text-anchor="end">${format(value)}</text>`).join('')}
            <text transform="translate(13 105) rotate(-90)" text-anchor="middle">${fieldEvent ? 'Distance (feet / inches)' : 'Time (seconds)'}</text>
            <polyline points="${points.map(point => `${x(point.year)},${y(point.result_value)}`).join(' ')}" fill="none" stroke="#ad0a46" stroke-width="3" stroke-linejoin="round"/>
            ${points.map((point, index) => `<circle cx="${x(point.year)}" cy="${y(point.result_value)}" r="4.5" fill="#ad0a46"><title>${escapeHtml(`${point.year}: ${point.result}`)}</title></circle>
            <text class="point-label" x="${x(point.year)}" y="${y(point.result_value) - (index % 2 ? 13 : 15)}" text-anchor="middle">${escapeHtml(point.result)}</text>`).join('')}
            ${points.filter((point, index) => points.length <= 6 || index % Math.ceil(points.length / 6) === 0 || index === points.length - 1).map(point => `<text x="${x(point.year)}" y="194" text-anchor="middle">${point.year}</text>`).join('')}
        </svg>`;
    }

    function formatRank(rank) {
        return rank && Number.isInteger(rank.rank) && Number.isInteger(rank.total)
            ? `${rank.rank}/${rank.total}` : '\u2014';
    }

    function renderEventFolders(history, bests) {
        const tabs = document.getElementById('event-tabs');
        const panel = document.getElementById('event-panel');
        const events = new Map();
        history.forEach(row => {
            if (!events.has(row.event)) events.set(row.event, []);
            ['state', 'regional', 'sectional'].forEach(stage => {
                if (row[stage]) events.get(row.event).push({...row[stage], year: row.year});
            });
        });
        // Include personal-best events even when there is no playoff history.
        bests.forEach(best => { if (!events.has(best.event)) events.set(best.event, []); });
        const names = [...events.keys()].sort((a, b) => a.localeCompare(b));
        if (!names.length) {
            tabs.hidden = true;
            panel.innerHTML = '<p class="dashboard-empty">No event results recorded yet.</p>';
            return;
        }
        const activate = index => {
            [...tabs.children].forEach((tab, tabIndex) => {
                tab.setAttribute('aria-selected', String(index === tabIndex));
                tab.tabIndex = index === tabIndex ? 0 : -1;
            });
            const name = names[index];
            panel.setAttribute('aria-labelledby', `event-tab-${index}`);
            const rows = events.get(name).sort((a, b) => b.year - a.year);
            const type = bests.find(best => best.event === name)?.event_type;
            const progression = renderProgression(name, rows, type);
            panel.innerHTML = `<div class="event-columns${progression ? '' : ' event-columns-results-only'}">
                <div class="event-results"><h3>${escapeHtml(name)} Results</h3>
                ${rows.length ? `<div class="event-table-scroll"><table><thead><tr><th scope="col">Year</th><th scope="col">Meet</th><th scope="col">${type === 'Field' || /jump|vault|throw|shot|discus/i.test(name) ? 'Mark' : 'Time'}</th><th scope="col">Place</th><th scope="col" title="Statewide rank for this event, year, gender and meet round">State Rank</th><th scope="col" title="Statewide rank among athletes in the same grade for this event, year, gender and meet round">Class Rank</th></tr></thead><tbody>
                ${rows.map(row => `<tr><td>${escapeHtml(row.year)}</td><td>${escapeHtml(row.meet_type)}${row.result_type === 'Prelim' ? ' <span class="prelim-marker" title="Prelim result only; no final recorded">(P)</span>' : ''}</td><td>${row.has_detail ? `<a href="${resultLink(row)}">${escapeHtml(row.result || '\u2014')}</a>` : escapeHtml(row.result || '\u2014')}</td><td>${ordinal(row.place)}</td><td>${formatRank(row.state_rank)}</td><td title="${escapeHtml(row.class_rank?.grade || (row.is_relay ? 'Class rank is unavailable for relay teams' : ''))}">${formatRank(row.class_rank)}</td></tr>`).join('')}
                </tbody></table></div>` : '<p class="dashboard-empty">No playoff results recorded for this event.</p>'}</div>
                ${progression ? `<div class="event-progression"><h3>${escapeHtml(name)} Progression</h3>${progression}</div>` : ''}
            </div>`;
        };
        names.forEach((name, index) => {
            const tab = document.createElement('button');
            tab.type = 'button';
            tab.id = `event-tab-${index}`;
            tab.className = 'event-tab';
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-controls', 'event-panel');
            tab.textContent = name;
            tab.addEventListener('click', () => activate(index));
            tab.addEventListener('keydown', event => {
                let next;
                if (event.key === 'ArrowRight') next = (index + 1) % names.length;
                if (event.key === 'ArrowLeft') next = (index - 1 + names.length) % names.length;
                if (event.key === 'Home') next = 0;
                if (event.key === 'End') next = names.length - 1;
                if (next === undefined) return;
                event.preventDefault();
                activate(next);
                tabs.children[next].focus();
                tabs.children[next].scrollIntoView({block: 'nearest', inline: 'nearest'});
            });
            tabs.appendChild(tab);
        });
        activate(0);
    }

    try {
        // Fetch athlete dashboard data from API
        const response = await fetch(`/api/athletes/${athleteId}/dashboard`);

        if (!response.ok) {
            throw new Error('Athlete not found');
        }

        const data = await response.json();

        // Hide loading, show content
        loadingState.classList.add('hidden');
        dashboardContent.classList.remove('hidden');

        // Populate athlete info
        document.getElementById('athlete-name').textContent = data.athlete.full_name;
        const schoolEl = document.getElementById('athlete-school');
        if (data.athlete.school && data.athlete.school_id) {
            schoolEl.textContent = data.athlete.school;
            schoolEl.href = `/school-dashboard/${data.athlete.school_id}`;
        } else {
            schoolEl.textContent = data.athlete.school || 'No school';
            schoolEl.removeAttribute('href');
            schoolEl.style.textDecoration = 'none';
            schoolEl.style.cursor = 'default';
        }

        // Show school logo if available
        if (data.athlete.logo_url) {
            const logoImg = document.getElementById('school-logo');
            const logoContainer = document.getElementById('school-logo-container');
            const logoLink = document.getElementById('school-logo-link');
            logoImg.src = data.athlete.logo_url;
            logoImg.alt = (data.athlete.school || 'School') + ' logo';
            if (data.athlete.school_id) {
                logoLink.href = `/school-dashboard/${data.athlete.school_id}`;
            } else {
                logoLink.removeAttribute('href');
                logoLink.style.cursor = 'default';
            }
            logoContainer.classList.remove('hidden');
        }

        // Set gender badge
        const genderBadge = document.getElementById('athlete-gender');
        if (data.athlete.gender) {
            const genderText = data.athlete.gender === 'M' ? 'Boys' : data.athlete.gender === 'F' ? 'Girls' : data.athlete.gender;
            const genderClass = genderText === 'Boys'
                ? 'font-bold px-2 py-0.5 border-2 border-blue-500 text-blue-600 rounded-full'
                : genderText === 'Girls'
                    ? 'font-bold px-2 py-0.5 border-2 border-pink-500 text-pink-600 rounded-full'
                    : 'font-bold px-2 py-0.5 border-2 border-gray-400 text-gray-600 rounded-full';
            genderBadge.textContent = genderText;
            genderBadge.className = genderClass;
        } else {
            genderBadge.classList.add('hidden');
        }

        // Set class year badge
        const classBadge = document.getElementById('athlete-class');
        if (data.athlete.graduation_year) {
            classBadge.textContent = `Class of ${data.athlete.graduation_year}`;
        } else {
            classBadge.classList.add('hidden');
        }

        // Populate badges
        const badgesContainer = document.getElementById('badges-container');
        badgesContainer.innerHTML = '';

        const badgeStages = ['sectional', 'regional', 'state'];
        badgeStages.forEach(stageKey => {
            const stageData = data.badges[stageKey];
            const config = stageConfigs[stageKey];

            const badgeCard = document.createElement('div');
            badgeCard.className = 'achievement-card';

            const headingLabel = stageData?.label || `${stageKey.charAt(0).toUpperCase()}${stageKey.slice(1)} Stage`;
            const emptyStateText = getStageEncouragement(stageKey);

            badgeCard.innerHTML = `
                    <div class="flex flex-wrap items-center gap-3 justify-between">
                        <div>
                            <h3>${config.title}</h3>
                            <p class="hidden text-sm text-gray-600">${headingLabel}</p>
                        </div>
                    </div>
                    <div class="medal-grid" data-stage-medals="${stageKey}"></div>
                    ${(!stageData || !stageData.entries || stageData.entries.length === 0)
                    ? `<p class="text-sm text-gray-500 italic">${emptyStateText}</p>`
                    : ''}
                `;

            const medalWrap = badgeCard.querySelector(`[data-stage-medals="${stageKey}"]`);
            if (stageData?.entries?.length) {
                stageData.entries.forEach(entry => {
                    medalWrap.appendChild(createMedalElement(entry));
                });
            }

            badgesContainer.appendChild(badgeCard);
        });

        renderPersonalBests(data.personal_bests || []);
        renderEventFolders(data.playoff_history || [], data.personal_bests || []);
        initializeAthleteCard(data.athlete);

    } catch (error) {
        console.error('Error loading athlete data:', error);
        loadingState.classList.add('hidden');
        dashboardContent.classList.add('hidden');
        errorState.classList.remove('hidden');
    }
});
