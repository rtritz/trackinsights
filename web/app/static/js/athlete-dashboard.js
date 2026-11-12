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

    function initializeAthleteCard(athlete, cards, problem) {
        // Share the public dashboard so scanned codes work away from this computer.
        const url = `https://www.trackinsights.org/athlete-dashboard/${athleteId}`;
        const name = athlete.full_name || 'Athlete';
        const status = document.getElementById('athlete-card-share-status');
        const setStatus = message => { status.textContent = message; };
        const detail = document.getElementById('athlete-card-detail');
        const stack = document.getElementById('athlete-card-stack');
        const position = document.getElementById('athlete-card-position');
        const previousButton = document.getElementById('athlete-card-previous');
        const nextButton = document.getElementById('athlete-card-next');
        const designButtons = [...document.querySelectorAll('.athlete-card-design')];
        const imageButtons = ['athlete-card-instagram', 'athlete-card-snapchat', 'athlete-card-download']
            .map(id => document.getElementById(id));
        const isMobile = Boolean(navigator.userAgentData?.mobile || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
            || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
        const downloadButton = document.getElementById('athlete-card-download');
        if (isMobile) {
            downloadButton.classList.add('athlete-card-mobile');
            downloadButton.querySelector('span').textContent = 'Add to Photos';
        }
        // Each card comes in two designs; the server renders the PNG once and caches it.
        const cardImages = new Map();
        let design = 'B';
        let selectedCard = 0;
        let sharingImage = false;

        const titleCase = value => String(value || '').toLowerCase()
            .replace(/(^|[\s'\-(])([a-z])/g, (match, lead, letter) => lead + letter.toUpperCase());
        const displayFirst = titleCase(athlete.first) || titleCase(name);
        document.getElementById('athlete-card-caption').textContent =
            `Share ${displayFirst}'s athlete cards.`;

        document.getElementById('athlete-card-copy').addEventListener('click', async () => {
            const copied = await copyTextToClipboard(url);
            setStatus(copied ? 'Athlete link copied!' : `Copy this link: ${url}`);
        });

        function updateImageButtons() {
            const image = cardImages.get(imageKey(selectedCard));
            imageButtons.forEach(button => {
                const needsImage = button.id === 'athlete-card-download';
                button.disabled = !cards.length || sharingImage || (needsImage && !image?.blob);
            });
        }

        if (problem || !cards.length) {
            const emptyMessage = problem
                ? 'Athlete cards cannot be drawn on this server yet: ' + problem
                : 'No postseason cards yet. Place at a sectional, regional, or state meet to earn one.';
            const empty = document.createElement('div');
            empty.className = 'athlete-card-empty';
            empty.textContent = emptyMessage;
            stack.replaceChildren(empty);
            position.textContent = '0 / 0';
            previousButton.disabled = true;
            nextButton.disabled = true;
            designButtons.forEach(button => { button.disabled = true; });
            detail.textContent = '';
            updateImageButtons();
            return;
        }

        function cardLabel(card) {
            const second = card.acc2 ? `, ${card.acc2}` : '';
            return `${card.year} ${card.meet_type} ${card.event}: ${card.acc1}${second}`;
        }

        function cardDetail(card) {
            const second = card.acc2 ? ` \u00b7 ${card.acc2}` : '';
            const meet = `${card.year} ${card.meet_type} \u00b7 ${card.event} \u00b7 ${card.result}`;
            return `<strong>${escapeHtml(card.acc1)}${escapeHtml(second)}</strong>${escapeHtml(meet)}`;
        }

        function imageKey(index) {
            return `${index}-${design}`;
        }

        // The card HTML is 1080px wide; scale it down to whatever width the deck has.
        function scaleFaces() {
            const width = stack.getBoundingClientRect().width;
            if (width > 0) stack.style.setProperty('--athlete-card-scale', (width - 6) / 1080);
        }
        if (typeof ResizeObserver === 'function') {
            new ResizeObserver(scaleFaces).observe(stack);
        } else {
            window.addEventListener('resize', scaleFaces);
        }

        let suppressClickUntil = 0;
        const cardButtons = cards.map((card, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'athlete-card-option';
            button.setAttribute('aria-label', cardLabel(card));
            const face = document.createElement('span');
            face.className = 'athlete-card-face';
            face.setAttribute('aria-hidden', 'true');
            const frame = document.createElement('iframe');
            frame.src = card.html_url[design];
            frame.title = cardLabel(card);
            frame.loading = 'lazy';
            frame.tabIndex = -1;
            frame.setAttribute('scrolling', 'no');
            face.appendChild(frame);
            button.appendChild(face);
            button.addEventListener('click', () => {
                if (Date.now() < suppressClickUntil) return;
                // Only the top card can be clicked to step forward.
                if (index !== selectedCard || cards.length < 2) return;
                selectCard((selectedCard + 1) % cards.length);
            });
            button.addEventListener('keydown', event => {
                let next;
                if (event.key === 'ArrowRight') next = (selectedCard + 1) % cards.length;
                if (event.key === 'ArrowLeft') next = (selectedCard - 1 + cards.length) % cards.length;
                if (event.key === 'Home') next = 0;
                if (event.key === 'End') next = cards.length - 1;
                if (next === undefined) return;
                event.preventDefault();
                selectCard(next);
                cardButtons[next].focus();
            });
            stack.appendChild(button);
            return button;
        });
        scaleFaces();

        function selectCard(index) {
            selectedCard = index;
            cardButtons.forEach((button, cardIndex) => {
                const depth = (cardIndex - index + cards.length) % cards.length;
                // Only the top few cards fan out; the rest wait behind them so a
                // long season does not push the deck across the page.
                button.style.setProperty('--stack-index', Math.min(depth, 3));
                button.classList.toggle('athlete-card-option-deep', depth > 3);
                button.setAttribute('aria-pressed', String(cardIndex === index));
            });
            position.textContent = `${index + 1} / ${cards.length}`;
            detail.innerHTML = cardDetail(cards[index]);
            prepareCardImage(index);
            // Warm the neighbours so the next step is instant.
            if (cards.length > 1) {
                prepareCardImage((index + 1) % cards.length);
                prepareCardImage((index - 1 + cards.length) % cards.length);
            }
            updateImageButtons();
        }

        function setDesign(next) {
            if (next === design) return;
            design = next;
            designButtons.forEach(button => {
                button.setAttribute('aria-pressed', String(button.dataset.design === design));
            });
            cardButtons.forEach((button, index) => {
                button.querySelector('iframe').src = cards[index].html_url[design];
            });
            prepareCardImage(selectedCard);
            updateImageButtons();
        }
        designButtons.forEach(button => {
            button.addEventListener('click', () => setDesign(button.dataset.design));
        });

        const stepCard = delta => selectCard((selectedCard + delta + cards.length) % cards.length);

        selectCard(0);
        if (cards.length === 1) {
            previousButton.disabled = true;
            nextButton.disabled = true;
        }
        previousButton.addEventListener('click', () => stepCard(-1));
        nextButton.addEventListener('click', () => stepCard(1));

        if (cards.length > 1) {
            // Swipe through the deck on touch screens and with a mouse drag.
            let dragStartX = null;
            let dragPointer = null;
            stack.addEventListener('pointerdown', event => {
                if (event.button !== undefined && event.button !== 0) return;
                dragStartX = event.clientX;
                dragPointer = event.pointerId;
                stack.classList.add('athlete-card-stack-dragging');
            });
            const endDrag = event => {
                if (dragStartX === null || event.pointerId !== dragPointer) return;
                const distance = event.clientX - dragStartX;
                dragStartX = null;
                dragPointer = null;
                stack.classList.remove('athlete-card-stack-dragging');
                if (Math.abs(distance) < 40) return;
                event.preventDefault();
                stepCard(distance < 0 ? 1 : -1);
                // A swipe must not also count as a tap on the card underneath.
                suppressClickUntil = Date.now() + 350;
            };
            stack.addEventListener('pointerup', endDrag);
            stack.addEventListener('pointercancel', () => {
                dragStartX = null;
                dragPointer = null;
                stack.classList.remove('athlete-card-stack-dragging');
            });

            // A horizontal wheel or trackpad swipe steps too, one card per gesture.
            let wheelBusyUntil = 0;
            stack.addEventListener('wheel', event => {
                if (Math.abs(event.deltaX) <= Math.abs(event.deltaY) || Math.abs(event.deltaX) < 12) return;
                event.preventDefault();
                const now = Date.now();
                if (now < wheelBusyUntil) return;
                wheelBusyUntil = now + 450;
                stepCard(event.deltaX > 0 ? 1 : -1);
            }, {passive: false});
        }

        function prepareCardImage(index) {
            const key = imageKey(index);
            const thisDesign = design;
            let image = cardImages.get(key);
            if (image) return image.pending;
            image = {blob: null, file: null, pending: null};
            cardImages.set(key, image);
            const card = cards[index];
            const filename = card.download_name[thisDesign];
            // Fetch before a tap: awaiting the download inside the click handler
            // can lose the transient activation required by iOS Safari's share sheet.
            image.pending = fetch(card.png_url[thisDesign]).then(response => {
                if (!response.ok) throw new Error(`Card image request failed (${response.status}).`);
                return response.blob();
            }).then(blob => {
                image.blob = blob;
                image.file = typeof File === 'function' ? new File([blob], filename, {type: 'image/png'}) : null;
            }).catch(error => {
                console.warn('Card image unavailable:', error);
                cardImages.delete(key);
                if (selectedCard === index && design === thisDesign) {
                    setStatus('The card image is not available right now. Try again in a moment.');
                }
            }).finally(updateImageButtons);
            return image.pending;
        }

        function downloadCardImage(image, filename) {
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

        // Snapchat's Creative Kit: no registration needed. Its SDK wires any
        // element with the snapchat-share-button class and deep links into
        // Snapchat with the share page attached (card as sticker, athlete link).
        const SNAP_SDK_ID = 'snapkit-creative-kit-sdk';
        if (!document.getElementById(SNAP_SDK_ID)) {
            const first = document.getElementsByTagName('script')[0];
            const script = document.createElement('script');
            script.id = SNAP_SDK_ID;
            script.src = 'https://sdk.snapkit.com/js/v1/create.js';
            script.async = true;
            first.parentNode.insertBefore(script, first);
        }
        const snapAnchor = document.getElementById('snapchat-share-anchor');
        const snapButtons = new Map();
        function snapKitButton(url) {
            if (snapButtons.has(url)) return snapButtons.get(url);
            const kit = window.snap && window.snap.creativekit;
            const init = kit && (kit.initalizeShareButtons || kit.initializeShareButtons);
            if (typeof init !== 'function') return null;
            const node = document.createElement('div');
            node.className = 'snapchat-share-button';
            node.setAttribute('data-share-url', url);
            snapAnchor.appendChild(node);
            init([node]);
            snapButtons.set(url, node);
            return node;
        }
        window.snapKitInit = () => {};

        // Desktop hand-off: a QR code straight to this card's one-tap share page.
        const handoff = document.getElementById('athlete-card-handoff');
        const handoffQr = document.getElementById('athlete-card-handoff-qr');
        const handoffLink = document.getElementById('athlete-card-handoff-link');
        const handoffText = document.getElementById('athlete-card-handoff-text');
        function showHandoff(platform, url) {
            handoffText.textContent = platform === 'Instagram'
                ? 'Instagram stories can only be posted from the app. Scan this with your phone\'s camera, then tap "Add to Instagram Story".'
                : 'Scan this with your phone\'s camera, then tap "Send to Snapchat" to open the card in Snapchat.';
            handoffLink.href = url;
            try {
                const code = qrcode(0, 'M');
                code.addData(url);
                code.make();
                handoffQr.innerHTML = code.createSvgTag({cellSize: 4, margin: 8, scalable: true});
            } catch (error) {
                console.warn('QR code failed', error);
                handoffQr.textContent = url;
            }
            if (typeof handoff.showModal === 'function') handoff.showModal();
            else window.open(url, '_blank', 'noopener');
        }

        const shareToApp = async platform => {
            const card = cards[selectedCard];
            const shareUrl = card.share_url[design];
            if (sharingImage) return;
            sharingImage = true;
            updateImageButtons();
            try {
                let image = cardImages.get(imageKey(selectedCard));
                if (isMobile && platform === 'Instagram' && !image?.file) {
                    // The image is usually prefetched; if a tap beats it, wait
                    // for it rather than bouncing to another page. The share
                    // sheet still opens inside the browser's activation window.
                    setStatus('Getting the card ready...');
                    await prepareCardImage(selectedCard);
                    image = cardImages.get(imageKey(selectedCard));
                }
                const canShareFile = Boolean(isMobile && image?.file && navigator.share && navigator.canShare
                    && navigator.canShare({files: [image.file]}));
                if (platform === 'Snapchat') {
                    const kitButton = /^https:/.test(shareUrl) ? snapKitButton(shareUrl) : null;
                    if (kitButton) {
                        // Snap's handler lives on this node; clicking it inside our
                        // tap keeps the user activation it needs to open the app.
                        kitButton.click();
                        setStatus(isMobile ? 'Opening Snapchat with your card.' : 'Scan the Snapcode with Snapchat to open the card there.');
                        return;
                    }
                }
                if (canShareFile) {
                    // The share sheet hands the image straight to the app; the
                    // story composer is the next tap. This is the most direct
                    // route a web page is allowed to take.
                    await navigator.share({files: [image.file], title: `${name} - Track Insights`});
                    setStatus(`Pick ${platform} in the sheet, then ${platform === 'Instagram' ? 'Your Story' : 'Story'} to post it.`);
                    return;
                }
                if (isMobile) {
                    window.location.href = shareUrl;
                    return;
                }
                showHandoff(platform, shareUrl);
                setStatus(`Scan the code with your phone to post the card to ${platform}.`);
            } catch (error) {
                if (error.name === 'AbortError') {
                    setStatus('Sharing canceled.');
                    return;
                }
                console.warn('Share failed', error);
                setStatus(error.name === 'NotAllowedError'
                    ? `Tap ${platform} again to open the share sheet.`
                    : `Unable to hand the card to ${platform}. Use Download and share it from your photos.`);
            } finally {
                sharingImage = false;
                updateImageButtons();
            }
        };
        document.getElementById('athlete-card-instagram').addEventListener('click', () => shareToApp('Instagram'));
        document.getElementById('athlete-card-snapchat').addEventListener('click', () => shareToApp('Snapchat'));

        function showPhotoSave(image) {
            const objectUrl = URL.createObjectURL(image.blob);
            const dialog = document.createElement('dialog');
            dialog.className = 'athlete-photo-save';
            dialog.setAttribute('aria-labelledby', 'athlete-photo-save-title');
            dialog.innerHTML = '<form method="dialog"><h2 id="athlete-photo-save-title">Add to Photos</h2>'
                + '<p>Touch and hold the card, then choose Save Image, Save to Photos, or Download image. The option depends on your browser.</p>'
                + '<button class="btn btn-primary" type="submit">Done</button></form>';
            const preview = document.createElement('img');
            preview.src = objectUrl;
            preview.alt = cardLabel(cards[selectedCard]);
            dialog.appendChild(preview);
            dialog.addEventListener('close', () => {
                URL.revokeObjectURL(objectUrl);
                dialog.remove();
            }, {once: true});
            document.body.appendChild(dialog);
            dialog.showModal();
            setStatus('Touch and hold the full-size card to save it to your photos.');
        }

        const saveToPhotos = image => {
            // The share sheet is the only road from a web page into the photo
            // library; a download link always lands in Files. It must be called
            // straight from the tap, with no await before it.
            const canShareFile = Boolean(isMobile && image?.file && navigator.share && navigator.canShare
                && navigator.canShare({files: [image.file]}));
            if (!canShareFile) return false;
            navigator.share({files: [image.file], title: `${name} - Track Insights`}).catch(error => {
                if (error.name === 'AbortError') { setStatus('Saving canceled.'); return; }
                console.warn('Share sheet failed', error);
                showPhotoSave(image);
            });
            setStatus('Tap Save Image in the sheet to add the card to your Photos.');
            return true;
        };

        downloadButton.addEventListener('click', () => {
            const image = cardImages.get(imageKey(selectedCard));
            if (!image?.blob) return;
            if (saveToPhotos(image)) return;
            if (isMobile) { showPhotoSave(image); return; }
            try {
                downloadCardImage(image, cards[selectedCard].download_name[design]);
                setStatus('Athlete card downloaded.');
            } catch {
                setStatus('Unable to download the card. Please try again.');
            }
        });
    }

    const stageConfigs = {
        sectional: {title: 'Sectionals'},
        regional: {title: 'Regionals'},
        state: {title: 'State'},
    };

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
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'medal-button';
        const label = entry.place_label || 'Q';
        button.setAttribute('aria-label', `${entry.year || ''} ${entry.event || 'Event'}, ${label}, ${entry.result || 'Qualified'}`);
        const tone = entry.place === 1 ? 'gold' : entry.place === 2 ? 'silver' : entry.place === 3 ? 'bronze' : 'dark';
        button.innerHTML = `<span class="medal-circle medal-${tone}">
            <svg viewBox="0 0 64 80" aria-hidden="true" focusable="false">
                <path d="M6 1h52a4 4 0 0 1 4 4v19L43 43H21L2 24V5a4 4 0 0 1 4-4Z" fill="#ff3344"/>
                <path d="M42 1h16a4 4 0 0 1 4 4v19L43 43h-1Z" fill="#df0027"/>
                <path d="M22 1h20v42H22Z" fill="#ffc4c8"/>
                <circle cx="32" cy="54" r="25" class="medal-outer"/>
                <path d="M32 29a25 25 0 0 1 0 50Z" fill="#000" opacity=".06"/>
                <circle cx="32" cy="54" r="17.5" class="medal-inner"/>
                <text x="32" y="55" dominant-baseline="middle" text-anchor="middle" class="medal-label">${escapeHtml(label)}</text>
            </svg></span>
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
        container.style.setProperty('--personal-best-count', Math.max(bests.length, 3));
        container.innerHTML = bests.map(best => {
            const relay = /^(.*?)\s+Relay$/i.exec(best.event);
            const label = relay
                ? `<span class="personal-best-distance">${escapeHtml(relay[1])}</span> <span class="personal-best-relay">Relay</span>`
                : escapeHtml(best.event);
            return `<div class="personal-best">
            <span class="personal-best-label">${label}</span>
            <span class="personal-best-value">${escapeHtml(best.result)}</span>
        </div>`;
        }).join('') || '<p class="dashboard-empty">No personal bests recorded yet.</p>';
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
        const eventOrder = new Map([
            '100 Meters', '100 Hurdles', '110 Hurdles', '4 x 100 Relay',
            '200 Meters', '300 Hurdles', '400 Meters', '4 x 400 Relay',
            '800 Meters', '4 x 800 Relay', '1600 Meters', '3200 Meters',
            'Long Jump', 'High Jump', 'Pole Vault', 'Shot Put', 'Discus',
        ].map((name, index) => [name, index]));
        const names = [...events.keys()].sort((a, b) =>
            (eventOrder.get(a) ?? Infinity) - (eventOrder.get(b) ?? Infinity)
            || a.localeCompare(b));
        tabs.classList.toggle('event-tabs-horizontal', names.length <= 2);
        if (!names.length) {
            tabs.hidden = true;
            panel.innerHTML = '<p class="dashboard-empty">No event results recorded yet.</p>';
            return;
        }
        const activate = index => {
            [...tabs.children].forEach((tab, tabIndex) => {
                tab.setAttribute('aria-selected', String(index === tabIndex));
                tab.tabIndex = names.length > 1 && index === tabIndex ? 0 : -1;
            });
            const name = names[index];
            panel.setAttribute('aria-labelledby', `event-tab-${index}`);
            const rows = events.get(name).sort((a, b) => b.year - a.year);
            const type = bests.find(best => best.event === name)?.event_type;
            const progression = renderProgression(name, rows, type);
            panel.innerHTML = `<div class="event-columns${progression ? '' : ' event-columns-results-only'}">
                <div class="event-results"><h3>${escapeHtml(name)} Results</h3>
                ${rows.length ? `<div class="event-table-scroll"><table><thead><tr><th scope="col">Year</th><th scope="col">Meet</th><th scope="col">${type === 'Field' || /jump|vault|throw|shot|discus/i.test(name) ? 'Mark' : 'Time'}</th><th scope="col">Place</th><th scope="col" title="Statewide rank for this event, year, gender and meet round">State Rank</th><th scope="col" title="Statewide rank among athletes in the same grade for this event, year, gender and meet round">Class Rank</th></tr></thead><tbody>
                ${rows.map(row => `<tr><td>${escapeHtml(row.year)}</td><td>${escapeHtml(row.meet_type)}${row.result_type === 'Prelim' ? ' <span class="prelim-marker" title="Prelim result only; no final recorded">(P)</span>' : ''}</td><td>${escapeHtml(row.result || '\u2014')}</td><td>${ordinal(row.place)}</td><td>${formatRank(row.state_rank)}</td><td title="${escapeHtml(row.class_rank?.grade || (row.is_relay ? 'Class rank is unavailable for relay teams' : ''))}">${formatRank(row.class_rank)}</td></tr>`).join('')}
                </tbody></table></div>` : '<p class="dashboard-empty">No playoff results recorded for this event.</p>'}</div>
                ${progression ? `<div class="event-progression"><h3>${escapeHtml(name)} Progression</h3>${progression}</div>` : ''}
            </div>`;
        };
        names.forEach((name, index) => {
            const tab = document.createElement('button');
            tab.type = 'button';
            tab.disabled = names.length === 1;
            tab.id = `event-tab-${index}`;
            tab.className = 'event-tab';
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-controls', 'event-panel');
            tab.textContent = name;
            tab.setAttribute('aria-label', name);
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
        const mobileTabs = window.matchMedia('(max-width: 767px)');
        const updateTabLabels = () => {
            [...tabs.children].forEach((tab, index) => {
                tab.textContent = mobileTabs.matches
                    ? names[index].replace(/\bMeters\b/gi, '').replace(/\s+/g, ' ').trim()
                    : names[index];
            });
        };
        mobileTabs.addEventListener('change', updateTabLabels);
        updateTabLabels();
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


            badgeCard.innerHTML = `
                    <div class="flex flex-wrap items-center gap-3 justify-between">
                        <div>
                            <h3>${config.title}</h3>
                        </div>
                    </div>
                    <div class="medal-grid" data-stage-medals="${stageKey}"></div>
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

        // The cards come last and from their own request, so a slow card query
        // or a rendering problem never holds up or hides the rest of the page.
        let athleteCards = [];
        let cardProblem = null;
        try {
            const cardsResponse = await fetch(`/api/athletes/${athleteId}/cards`);
            if (cardsResponse.ok) {
                const cardsPayload = await cardsResponse.json();
                athleteCards = cardsPayload.cards || [];
                cardProblem = cardsPayload.problem || null;
            }
        } catch (error) {
            console.warn('Unable to load athlete cards:', error);
        }
        initializeAthleteCard(data.athlete, athleteCards, cardProblem);

    } catch (error) {
        console.error('Error loading athlete data:', error);
        loadingState.classList.add('hidden');
        dashboardContent.classList.add('hidden');
        errorState.classList.remove('hidden');
    }
});
