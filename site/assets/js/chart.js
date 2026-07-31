/* Canvas charts, ~7KB, no dependencies.
 *
 * Deliberately not TradingView Lightweight Charts: this site plots monthly
 * broker series and categorical comparisons, not OHLC candles at tick
 * resolution. A purpose-built renderer avoids a 160KB bundle, keeps the strict
 * self-hosted CSP intact, and reads its palette straight from the CSS tokens so
 * light/dark and theme switches need no JS wiring.
 */

const css = (name, fallback) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
};

const palette = () => [
  css('--c1', '#2f4a8f'), css('--c2', '#0f7a4d'), css('--c3', '#b8621b'),
  css('--c4', '#7a3e9d'), css('--c5', '#1f6a8f'), css('--c6', '#a03050'),
  css('--c7', '#5c6b1f'), css('--c8', '#7d5a3c'),
];

function setup(canvas, h) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || canvas.parentElement.clientWidth || 320;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

const niceMax = (v) => {
  if (!v || v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
};

/* ------------------------------------------------------------------ sparkline */

export function sparkline(canvas, values, opts = {}) {
  const vals = (values || []).filter((v) => v != null);
  if (vals.length < 2) return;
  const { ctx, w, h } = setup(canvas, opts.height || 22);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const pad = 2;
  const x = (i) => (i / (vals.length - 1)) * (w - pad * 2) + pad;
  const y = (v) => h - pad - ((v - min) / span) * (h - pad * 2);
  const rising = vals[vals.length - 1] >= vals[0];
  const color = opts.color || (rising ? css('--up', '#0f7a4d') : css('--down', '#c0392b'));

  ctx.beginPath();
  vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.4;
  ctx.lineJoin = 'round';
  ctx.stroke();

  if (opts.fill !== false) {
    ctx.lineTo(x(vals.length - 1), h);
    ctx.lineTo(x(0), h);
    ctx.closePath();
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  ctx.beginPath();
  ctx.arc(x(vals.length - 1), y(vals[vals.length - 1]), 1.8, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
}

/* ----------------------------------------------------------------- line chart */

export function lineChart(canvas, series, opts = {}) {
  const height = opts.height || 240;
  const { ctx, w, h } = setup(canvas, height);
  const sets = (series || []).filter((s) => (s.data || []).length);
  if (!sets.length) return;

  const padL = opts.padL ?? 52, padR = 12, padT = 12, padB = 26;
  const labels = sets[0].data.map((d) => d[0]);
  const allVals = sets.flatMap((s) => s.data.map((d) => d[1])).filter((v) => v != null);
  let lo = opts.zero ? 0 : Math.min(...allVals);
  let hi = Math.max(...allVals);
  if (opts.zero) { hi = niceMax(hi); } else { const p = (hi - lo) * 0.08 || 1; lo -= p; hi += p; }
  const span = hi - lo || 1;
  const n = Math.max(...sets.map((s) => s.data.length));
  const X = (i) => padL + (i / Math.max(n - 1, 1)) * (w - padL - padR);
  const Y = (v) => padT + (1 - (v - lo) / span) * (h - padT - padB);
  const cols = palette();
  const grid = css('--border', '#e3e3df'), muted = css('--text-muted', '#6b6b64');

  // gridlines + y labels
  ctx.font = '10px ' + css('--font-mono', 'monospace');
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'right';
  const ticks = 4;
  for (let t = 0; t <= ticks; t++) {
    const v = lo + (span * t) / ticks;
    const y = Y(v);
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, y + 0.5);
    ctx.lineTo(w - padR, y + 0.5);
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.fillText(opts.fmtY ? opts.fmtY(v) : String(Math.round(v)), padL - 7, y);
  }

  // x labels: first, middle, last only — monthly series get crowded fast
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => {
    if (labels[i] == null) return;
    ctx.fillStyle = muted;
    ctx.fillText(String(labels[i]), X(i), h - padB + 7);
  });

  sets.forEach((s, si) => {
    const color = s.color || cols[si % cols.length];
    ctx.beginPath();
    let started = false;
    s.data.forEach((d, i) => {
      if (d[1] == null) return;
      const px = X(i), py = Y(d[1]);
      started ? ctx.lineTo(px, py) : (ctx.moveTo(px, py), (started = true));
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.stroke();

    if (opts.area && sets.length === 1) {
      ctx.lineTo(X(s.data.length - 1), h - padB);
      ctx.lineTo(X(0), h - padB);
      ctx.closePath();
      const g = ctx.createLinearGradient(0, padT, 0, h - padB);
      g.addColorStop(0, color + '33');
      g.addColorStop(1, color + '00');
      ctx.fillStyle = g;
      ctx.fill();
    }
  });

  attachTooltip(canvas, { X, Y, sets, labels, n, padL, padR, w, h, padT, padB, fmt: opts.fmtTip || opts.fmtY });
}

function attachTooltip(canvas, s) {
  const box = canvas.parentElement;
  if (!box) return;
  let tip = box.querySelector('.chart-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'chart-tip';
    box.appendChild(tip);
  }
  const move = (ev) => {
    const r = canvas.getBoundingClientRect();
    const x = ev.clientX - r.left;
    const i = Math.round(((x - s.padL) / (s.w - s.padL - s.padR)) * (s.n - 1));
    if (i < 0 || i >= s.n) { tip.classList.remove('on'); return; }
    const rows = s.sets
      .map((set) => {
        const d = set.data[i];
        if (!d || d[1] == null) return null;
        return `${set.label ? set.label + ': ' : ''}${s.fmt ? s.fmt(d[1]) : d[1]}`;
      })
      .filter(Boolean);
    if (!rows.length) { tip.classList.remove('on'); return; }
    tip.innerHTML = `<strong>${s.labels[i] ?? ''}</strong><br>${rows.join('<br>')}`;
    tip.classList.add('on');
    const tw = tip.offsetWidth;
    tip.style.left = Math.min(Math.max(s.X(i) - tw / 2, 0), s.w - tw) + 'px';
    tip.style.top = '4px';
  };
  canvas.onmousemove = move;
  canvas.onmouseleave = () => tip.classList.remove('on');
}

/* ------------------------------------------------------------------ bar chart */

export function barChart(canvas, rows, opts = {}) {
  const height = opts.height || 240;
  const { ctx, w, h } = setup(canvas, height);
  const data = (rows || []).filter((r) => r.value != null);
  if (!data.length) return;

  const horizontal = opts.horizontal !== false;
  const cols = palette();
  const muted = css('--text-muted', '#6b6b64');
  const max = niceMax(Math.max(...data.map((r) => Math.abs(r.value))));
  ctx.font = '11px ' + css('--font', 'sans-serif');

  if (horizontal) {
    const labelW = opts.labelW || 108;
    const barH = Math.max(10, Math.min(26, (h - 8) / data.length - 6));
    const gap = (h - data.length * barH) / Math.max(data.length, 1);
    data.forEach((r, i) => {
      const y = gap / 2 + i * (barH + gap);
      const bw = (Math.abs(r.value) / max) * (w - labelW - 58);
      ctx.fillStyle = r.color || cols[i % cols.length];
      const rad = Math.min(3, barH / 2);
      roundRect(ctx, labelW, y, Math.max(bw, 1.5), barH, rad);
      ctx.fill();
      ctx.fillStyle = css('--text', '#1a1a18');
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(clip(ctx, r.label, labelW - 10), labelW - 8, y + barH / 2);
      ctx.fillStyle = muted;
      ctx.textAlign = 'left';
      ctx.font = '11px ' + css('--font-mono', 'monospace');
      ctx.fillText(opts.fmt ? opts.fmt(r.value) : String(r.value), labelW + bw + 6, y + barH / 2);
      ctx.font = '11px ' + css('--font', 'sans-serif');
    });
  } else {
    const padB = 30, padT = 8;
    const bw = (w / data.length) * 0.62;
    data.forEach((r, i) => {
      const x = (i + 0.5) * (w / data.length) - bw / 2;
      const bh = (Math.abs(r.value) / max) * (h - padB - padT);
      ctx.fillStyle = r.color || cols[i % cols.length];
      roundRect(ctx, x, h - padB - bh, bw, bh, 3);
      ctx.fill();
      ctx.fillStyle = muted;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(clip(ctx, r.label, w / data.length), x + bw / 2, h - padB + 6);
    });
  }
}

/* ---------------------------------------------------------------- donut chart */

export function donut(canvas, rows, opts = {}) {
  const size = opts.size || 168;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  canvas.style.width = size + 'px';
  canvas.style.height = size + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, size, size);

  const data = (rows || []).filter((r) => r.value > 0);
  const total = data.reduce((a, r) => a + r.value, 0);
  if (!total) return;
  const cols = palette();
  const cx = size / 2, cy = size / 2, R = size / 2 - 4, r = R * 0.62;
  let a0 = -Math.PI / 2;

  data.forEach((row, i) => {
    const a1 = a0 + (row.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, R, a0, a1);
    ctx.arc(cx, cy, r, a1, a0, true);
    ctx.closePath();
    ctx.fillStyle = row.color || cols[i % cols.length];
    ctx.fill();
    a0 = a1;
  });

  if (opts.center) {
    ctx.fillStyle = css('--text', '#1a1a18');
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '600 17px ' + css('--font-mono', 'monospace');
    ctx.fillText(opts.center, cx, cy - 6);
    if (opts.centerSub) {
      ctx.font = '10px ' + css('--font', 'sans-serif');
      ctx.fillStyle = css('--text-muted', '#6b6b64');
      ctx.fillText(opts.centerSub, cx, cy + 11);
    }
  }
}

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function clip(ctx, text, maxW) {
  let t = String(text ?? '');
  if (ctx.measureText(t).width <= maxW) return t;
  while (t.length > 1 && ctx.measureText(t + '…').width > maxW) t = t.slice(0, -1);
  return t + '…';
}

/* Redraw everything on resize and on theme change — canvases are raster, so
 * they must be re-rendered rather than restyled. */
const redrawers = new Set();
export function registerRedraw(fn) { redrawers.add(fn); return () => redrawers.delete(fn); }
export function clearRedraws() { redrawers.clear(); }

let t;
const kick = () => { clearTimeout(t); t = setTimeout(() => redrawers.forEach((f) => { try { f(); } catch (_) {} }), 120); };
window.addEventListener('resize', kick);
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', kick);
export const redrawAll = kick;
