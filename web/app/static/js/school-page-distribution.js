/* Values are individual numeric observations. Bin widths, markers, and
 * cutoffs use the same units; better performances appear on the right.
 * The SVG is drawn at the container's pixel width so text renders at its
 * true size on phones and desktops alike. */
(function () {
    'use strict';

    const NS = 'http://www.w3.org/2000/svg';
    let nextId = 0;

    function svg(tag, attributes, text) {
        const node = document.createElementNS(NS, tag);
        Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
        if (text != null) node.textContent = text;
        return node;
    }

    function number(value) {
        return Number(value.toPrecision(6)).toString();
    }

    function formatMark(value, unit) {
        if (unit === 'inches') {
            const inches = Math.round(value * 100) / 100;
            const feet = Math.floor(inches / 12);
            return `${feet}' ${number(inches - feet * 12)}"`;
        }
        if (unit === 'seconds') {
            const hundredths = Math.round(value * 100);
            if (hundredths >= 6000) {
                const minutes = Math.floor(hundredths / 6000);
                return `${minutes}:${((hundredths % 6000) / 100).toFixed(2).padStart(5, '0')}`;
            }
            return (hundredths / 100).toFixed(2);
        }
        return number(value);
    }

    // Axis tick labels: round values, shorter than full marks.
    function formatTick(value, unit, step) {
        if (unit === 'inches') {
            const feet = Math.floor(value / 12 + 1e-9);
            const inches = Math.round((value - feet * 12) * 100) / 100;
            return inches ? `${feet}' ${number(inches)}"` : `${feet}'`;
        }
        if (unit === 'seconds') {
            const digits = step < 0.1 ? 2 : step < 1 ? 1 : 0;
            if (value >= 60) {
                const minutes = Math.floor(value / 60);
                return `${minutes}:${(value - minutes * 60).toFixed(digits).padStart(digits ? digits + 3 : 2, '0')}`;
            }
            return value.toFixed(digits);
        }
        return number(value);
    }

    function niceStep(raw, unit) {
        const steps = unit === 'inches'
            ? [0.5, 1, 2, 3, 6, 12, 24, 36, 60, 120, 240]
            : [0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
        return steps.find(step => step >= raw) || steps[steps.length - 1];
    }

    function render(container, config) {
        config = config || {};
        const raw = Array.isArray(config.values) ? config.values : [];
        const samples = raw.filter(value => typeof value === 'number' && Number.isFinite(value));
        container.replaceChildren();
        if (!samples.length) {
            const empty = document.createElement('p');
            empty.className = 'text-sm text-base-content/70';
            empty.textContent = 'No statewide marks are available for this event.';
            container.appendChild(empty);
            return;
        }

        const markers = (Array.isArray(config.markers) ? config.markers : [])
            .filter(item => item && typeof item.value === 'number' && Number.isFinite(item.value));
        const cutoffs = [
            { item: config.regionalCutoff, name: 'Regional', color: 'var(--color-secondary)' },
            { item: config.stateCutoff, name: 'State', color: 'var(--color-accent)' },
        ].filter(entry => entry.item && typeof entry.item.value === 'number' && Number.isFinite(entry.item.value));
        const sorted = samples.slice().sort((a, b) => a - b);
        const quantile = p => {
            if (sorted.length === 1) return sorted[0];
            const n = sorted.length - 1;
            const index = Math.min(n, Math.max(0, p * n));
            const low = Math.floor(index);
            const high = Math.ceil(index);
            const mix = index - low;
            return sorted[low] + (sorted[high] - sorted[low]) * mix;
        };
        const hardMin = sorted[0];
        const hardMax = sorted[sorted.length - 1];
        // Keep the full good-performance end; clip only statistical outliers
        // on the poor/slow side using the one-sided Tukey 1.5-IQR fence.
        const q1 = quantile(0.25), q3 = quantile(0.75);
        const iqr = q3 - q1;
        let min = config.lowerIsBetter ? hardMin : Math.max(hardMin, q1 - 1.5 * iqr);
        let max = config.lowerIsBetter ? Math.min(hardMax, q3 + 1.5 * iqr) : hardMax;
        if (!(max > min)) {
            min = sorted[0];
            max = sorted[sorted.length - 1];
        }
        const range = max - min;
        let binSize = typeof config.binSize === 'number' && Number.isFinite(config.binSize) && config.binSize > 0
            ? config.binSize : (range || Math.abs(min) || 1) / 12;
        // Bound allocation while retaining the actual width in the tooltip.
        if (range / binSize > 199) binSize = range / 199;
        const start = min - binSize / 2;
        const binCount = Math.max(1, Math.ceil((max - start) / binSize));
        const end = start + binCount * binSize;
        const counts = Array(binCount).fill(0);
        const shownSamples = samples.filter(value => value >= start && value <= end);
        shownSamples.forEach(value => { counts[Math.min(binCount - 1, Math.floor((value - start) / binSize))]++; });
        if (config.lowerIsBetter) counts.reverse();

        const requested = Number(config.width);
        const width = Math.round(Math.max(300, Math.min(960, Number.isFinite(requested) && requested > 0 ? requested : 600)));
        const left = 44, right = width - 16, plotWidth = right - left;
        const toX = value => {
            const clamped = Math.max(start, Math.min(end, value));
            return left + (config.lowerIsBetter ? (end - clamped) : (clamped - start)) / (end - start) * plotWidth;
        };

        // Marker boxes are sized to their text (approx. 6.4px per bold 11px glyph).
        const boxHeight = 20, rowHeight = 26;
        const labelFor = marker => `${marker.name || 'Marker'} ${marker.mark ?? marker.value}`;
        const laneEnds = [];
        const placed = markers.map(marker => {
            const x = toX(marker.value);
            const w = Math.min(plotWidth, Math.ceil(labelFor(marker).length * 6.4 + 14));
            return { marker, x, w, center: Math.max(left + w / 2, Math.min(right - w / 2, x)) };
        }).sort((a, b) => a.center - b.center);
        placed.forEach(entry => {
            const startX = entry.center - entry.w / 2;
            let lane = laneEnds.findIndex(endX => startX >= endX + 4);
            if (lane < 0) lane = laneEnds.length;
            laneEnds[lane] = startX + entry.w;
            entry.lane = lane;
        });

        // Median, not mean: these fields are skewed by a long tail of slower
        // marks, and the median is the mark half the state beat.
        const middle = quantile(0.5);
        const axisItems = [{ name: 'State median', value: middle, mark: formatMark(middle, config.unit), color: 'currentColor' }]
            .concat(cutoffs.map(entry => ({ name: entry.name === 'Regional' ? 'Reg. cut' : 'State cut', value: entry.item.value,
                mark: entry.item.mark ?? formatMark(entry.item.value, config.unit), color: entry.color })));

        const top = 16 + laneEnds.length * rowHeight;
        const plotHeight = width < 480 ? 150 : 180;
        const bottom = top + plotHeight;
        const tickY = bottom + 16;
        const annotationY = tickY + 26;

        // Average and cut labels share one row. Each label starts centred on
        // its value; crowded labels are pushed apart and joined back to the
        // axis with a (diagonal) leader line.
        const gap = 8;
        const placedAxisItems = axisItems.map(item => {
            const x = toX(item.value);
            const w = Math.ceil(Math.max(item.name.length * 6.2, String(item.mark).length * 5.8)) + 6;
            return { ...item, x, w, center: x };
        }).sort((a, b) => a.x - b.x);
        placedAxisItems.forEach((item, i) => {
            const min = i ? placedAxisItems[i - 1].center + placedAxisItems[i - 1].w / 2 + gap + item.w / 2 : left + item.w / 2;
            item.center = Math.max(item.center, min);
        });
        for (let i = placedAxisItems.length - 1; i >= 0; i--) {
            const item = placedAxisItems[i];
            const next = placedAxisItems[i + 1];
            const max = next ? next.center - next.w / 2 - gap - item.w / 2 : right - item.w / 2;
            item.center = Math.min(item.center, max);
        }
        const directionY = annotationY + 32;
        const height = directionY + 6;

        const maxCount = Math.max(...counts, 1);
        const toY = count => bottom - count / maxCount * (bottom - top);
        const id = ++nextId;
        const chart = svg('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'font-size': '11',
            'aria-labelledby': `school-dist-title-${id} school-dist-desc-${id}`, class: 'block w-full h-auto text-base-content' });
        chart.appendChild(svg('title', { id: `school-dist-title-${id}` }, `${config.event || 'Performance'} statewide distribution`));
        const unit = config.unit || 'units';
        const countLabel = config.countLabel || 'athletes';
        const binDescription = `Each bin spans approximately ${number(binSize)} ${unit}; the curve connects bin counts.`;
        const details = [`${samples.length} statewide ${countLabel}. Better results are toward the right.`, binDescription, 'The axis clips only poor/slow-end outliers beyond the one-sided 1.5-IQR fence.'];
        cutoffs.forEach(entry => details.push(`${entry.name} cut: ${entry.item.mark ?? entry.item.value}.`));
        markers.forEach(item => details.push(`${item.fullName || item.name || 'Marker'}${item.year ? ` (${item.year})` : ''}: ${item.mark ?? item.value}.`));

        const gridStep = Math.max(1, Math.ceil(maxCount / 4));
        for (let count = 0; count <= maxCount; count += gridStep) {
            const y = toY(count);
            chart.appendChild(svg('line', { x1: left, x2: right, y1: y, y2: y, stroke: 'currentColor', 'stroke-opacity': '0.12' }));
            chart.appendChild(svg('text', { x: left - 6, y, 'text-anchor': 'end', 'dominant-baseline': 'middle', fill: 'currentColor', 'fill-opacity': '0.65' }, count));
        }
        const yMid = (top + bottom) / 2;
        const yTitle = svg('text', { x: 12, y: yMid, transform: `rotate(-90 12 ${yMid})`, 'text-anchor': 'middle', fill: 'currentColor', 'fill-opacity': '0.65' }, `# ${countLabel}`);
        yTitle.appendChild(svg('title', {}, binDescription));
        chart.appendChild(yTitle);

        const points = counts.map((count, i) => [left + (i + 0.5) * plotWidth / binCount, toY(count)]);
        let curve = `M ${left} ${bottom} L ${points[0][0]} ${points[0][1]}`;
        for (let i = 0; i < points.length - 1; i++) {
            const p = points[i], q = points[i + 1];
            curve += ` Q ${p[0]} ${p[1]} ${(p[0] + q[0]) / 2} ${(p[1] + q[1]) / 2}`;
        }
        const last = points[points.length - 1];
        curve += ` L ${last[0]} ${last[1]} L ${right} ${bottom} Z`;
        const clipId = `school-dist-clip-${id}`;
        const defs = svg('defs');
        const clip = svg('clipPath', { id: clipId });
        clip.appendChild(svg('path', { d: curve }));
        defs.appendChild(clip);
        chart.appendChild(defs);

        // Counts use actual observations, not the interpolated curve's area.
        const boundaries = cutoffs.map(entry => ({ ...entry, x: toX(entry.item.value) }))
            .sort((a, b) => a.x - b.x || (a.name === 'State' ? 1 : -1));
        const zones = [{ x: left, name: boundaries.length ? 'Did not reach a cut' : 'All marks', color: 'var(--color-primary)' }]
            .concat(boundaries.map(entry => ({ x: entry.x, name: `${entry.name} cut or better`, color: entry.color })));
        zones.forEach((zone, i) => {
            const zoneEnd = i + 1 < zones.length ? zones[i + 1].x : right;
            const count = samples.filter(value => {
                const x = toX(value);
                return x >= zone.x && (i === zones.length - 1 ? x <= zoneEnd : x < zoneEnd);
            }).length;
            zone.count = count;
            const description = `${zone.name}: ${count} ${countLabel}.`;
            details.push(description);
            if (zoneEnd <= zone.x) return;
            const area = svg('rect', { x: zone.x, y: top, width: zoneEnd - zone.x, height: bottom - top, fill: zone.color, 'fill-opacity': '0.35', 'clip-path': `url(#${clipId})`, tabindex: '0', 'aria-label': description });
            area.appendChild(svg('title', {}, description));
            chart.appendChild(area);
        });
        chart.appendChild(svg('path', { d: curve, fill: 'none', stroke: 'var(--color-primary)', 'stroke-width': '2', 'pointer-events': 'none' }));

        // X axis with round-number tick labels.
        chart.appendChild(svg('line', { x1: left, x2: right, y1: bottom, y2: bottom, stroke: 'currentColor', 'stroke-opacity': '0.4' }));
        const tickTarget = Math.max(2, Math.floor(plotWidth / 90));
        const tickStep = niceStep((end - start) / tickTarget, config.unit);
        for (let value = Math.ceil(start / tickStep) * tickStep; value <= end + 1e-9; value += tickStep) {
            const x = toX(value);
            if (x < left + 10 || x > right - 10) continue;
            // Leave room for the leader lines of the avg/cut labels.
            // (the leader's horizontal run crosses this row, so clear its whole span).
            if (placedAxisItems.some(item => x > Math.min(item.x, item.center) - 18 && x < Math.max(item.x, item.center) + 18)) continue;
            chart.appendChild(svg('line', { x1: x, x2: x, y1: bottom, y2: bottom + 4, stroke: 'currentColor', 'stroke-opacity': '0.4' }));
            chart.appendChild(svg('text', { x, y: tickY, 'text-anchor': 'middle', fill: 'currentColor', 'fill-opacity': '0.6', 'font-size': '10' }, formatTick(value, config.unit, tickStep)));
        }

        // Draw connectors before boxes so no connector obscures another label.
        placed.forEach(entry => {
            const y = 4 + entry.lane * rowHeight;
            chart.appendChild(svg('path', { d: `M ${entry.center} ${y + boxHeight} L ${entry.x} ${top} L ${entry.x} ${bottom}`, fill: 'none', stroke: 'var(--color-primary)', 'stroke-width': '1.5', 'pointer-events': 'none' }));
        });
        placed.forEach(entry => {
            const { marker, center, w } = entry;
            const y = 4 + entry.lane * rowHeight;
            const description = `${marker.fullName || marker.name || 'Marker'}${marker.year ? ` (${marker.year})` : ''}: ${marker.mark ?? marker.value}`;
            const label = svg('g', { tabindex: '0', 'aria-label': description });
            label.appendChild(svg('title', {}, description));
            label.appendChild(svg('rect', { x: center - w / 2, y, width: w, height: boxHeight, rx: 4, fill: 'white', stroke: 'var(--color-primary)' }));
            label.appendChild(svg('text', { x: center, y: y + 14, 'text-anchor': 'middle', fill: 'currentColor', 'font-weight': '600' }, labelFor(marker)));
            chart.appendChild(label);
        });

        // Average and cut annotations below the tick labels.
        placedAxisItems.forEach(item => {
            const labelY = annotationY;
            // Straight down when the label sits on its value; when it was pushed
            // aside, down half way, across, then down the rest (right angles only).
            const drop = labelY - 12;
            const mid = (bottom + drop) / 2;
            const route = Math.abs(item.center - item.x) < 1
                ? `M ${item.x} ${bottom} V ${drop}`
                : `M ${item.x} ${bottom} V ${mid} H ${item.center} V ${drop}`;
            chart.appendChild(svg('path', { d: route, fill: 'none', stroke: item.color, 'stroke-width': '1.25', 'stroke-opacity': '0.8' }));
            chart.appendChild(svg('text', { x: item.center, y: labelY, 'text-anchor': 'middle', fill: item.color, 'font-weight': '600' }, item.name));
            const mark = svg('text', { x: item.center, y: labelY + 13, 'text-anchor': 'middle', fill: item.color }, item.mark);
            mark.appendChild(svg('title', {}, `${item.name}: ${item.mark}`));
            chart.appendChild(mark);
        });

        // One wording for every event: better marks are always drawn on the right.
        chart.appendChild(svg('text', { x: left, y: directionY, fill: 'currentColor', 'fill-opacity': '0.5', 'font-size': '10' }, '← Worse'));
        chart.appendChild(svg('text', { x: right, y: directionY, 'text-anchor': 'end', fill: 'currentColor', 'fill-opacity': '0.75', 'font-size': '10', 'font-weight': '600' }, 'Better →'));

        chart.insertBefore(svg('desc', { id: `school-dist-desc-${id}` }, details.join(' ')), chart.children[1]);
        container.appendChild(chart);
    }

    window.SchoolDistribution = { render };
}());
