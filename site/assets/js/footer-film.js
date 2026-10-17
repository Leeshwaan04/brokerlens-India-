/* Footer film: "The two forces behind every trade" (25 s, bull vs bear).
 *
 * Built client-side and appended as the very last block of the site footer,
 * so one script serves every page that has a footer and the static HTML
 * carries no extra weight. It is deliberately a *click-to-play* piece:
 *  - nothing but the poster is fetched until the visitor presses play
 *    (preload none); the film has a soundtrack, so it never autoplays;
 *  - it pauses when scrolled out of view or the tab is hidden, and stops the
 *    header music button so two soundtracks never overlap;
 *  - the glow around the frame samples the video's own edge colours, and is
 *    switched off for people who prefer reduced motion;
 *  - the chapters, the seek bar, the transcript and the on-screen disclosures
 *    all come from the film's actual scenes and text.
 */
const SRC = '/assets/video/bull-bear-film.mp4?v=57f325312b';
const POSTER = '/assets/video/bull-bear-film-poster.jpg?v=c6993be29b';
const DURATION = 25;

// Start times (seconds) measured from the film itself.
const CHAPTERS = [
  { t: 0,    name: 'Two forces',   line: 'Every market has two forces.' },
  { t: 2.5,  name: 'Optimism',     line: 'The bull stands for optimism.' },
  { t: 5,    name: 'Fear',         line: 'The bear stands for fear.' },
  { t: 7,    name: 'They meet',    line: 'They meet every single day.' },
  { t: 11.5, name: 'Every trade',  line: 'Every tick. Every trade.' },
  { t: 17.5, name: 'Discipline',   line: 'Only discipline decides who wins.' },
  { t: 20.5, name: 'The takeaway', line: 'Trade the market. Not your emotions.' },
];
const TRANSCRIPT = [
  'Every market has two forces.',
  'Optimism. Fear.',
  'They meet every single day.',
  'Every tick. Every trade.',
  'Only discipline decides who wins.',
  'Trade the market. Not your emotions.',
  'Investments in securities market are subject to market risks. Read all the related documents carefully before investing.',
  'Visuals are AI-generated.',
];

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
const fmt = (s) => { s = Math.max(0, Math.floor(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const ICON = {
  play: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/></svg>',
  replay: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 5V2L7 6l5 4V7a5 5 0 11-5 5H5a7 7 0 107-7z" fill="currentColor"/></svg>',
  sound: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M3 9h4l5-4v14l-5-4H3z" fill="currentColor"/><path d="M15.5 8.5a5 5 0 010 7M18 6a8.5 8.5 0 010 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  muted: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M3 9h4l5-4v14l-5-4H3z" fill="currentColor"/><path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  full: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

function build(host) {
  const section = document.createElement('section');
  section.className = 'film';
  section.setAttribute('aria-labelledby', 'film-title');
  section.innerHTML = `
    <div class="film-head">
      <span class="film-eyebrow">BrokerLens Film &middot; 0:25</span>
      <h2 id="film-title">The two forces behind every trade</h2>
    </div>
    <div class="film-grid">
      <div class="film-left">
        <div class="film-stage" data-state="idle">
          <div class="film-glow" aria-hidden="true"></div>
          <div class="film-frame">
            <video class="film-video" playsinline preload="none" poster="${POSTER}"
                   aria-label="Bull versus bear: a 25-second film about trading discipline"></video>
            <button type="button" class="film-play">
              <span class="film-play-disc">${ICON.play}</span>
              <span class="film-play-text">Watch the film <em>25 sec &middot; sound on</em></span>
            </button>
            <div class="film-end" aria-hidden="true">
              <p class="film-end-line">Trade the market.<br><span>Not your emotions.</span></p>
              <div class="film-end-actions">
                <button type="button" class="film-replay">${ICON.replay} Replay</button>
                <a class="film-link" href="/compare">Compare brokers &rarr;</a>
                <a class="film-link" href="/calculator">Cost calculator &rarr;</a>
              </div>
              <p class="film-end-risk">Investments in securities market are subject to market risks. Read all the related documents carefully before investing. Visuals are AI-generated.</p>
            </div>
            <div class="film-controls">
              <button type="button" class="film-btn film-toggle" aria-label="Play" aria-keyshortcuts="K">${ICON.play}</button>
              <span class="film-time" aria-hidden="true">0:00 / 0:25</span>
              <div class="film-track">
                <div class="film-segs" aria-hidden="true">${CHAPTERS.map((c, i) => {
                  const end = i + 1 < CHAPTERS.length ? CHAPTERS[i + 1].t : DURATION;
                  return `<span class="film-seg" style="flex:${end - c.t} 1 0"><i></i></span>`;
                }).join('')}</div>
                <input class="film-seek" type="range" min="0" max="${DURATION * 10}" step="10" value="0"
                       aria-label="Seek" aria-valuetext="0:00 of 0:25">
              </div>
              <button type="button" class="film-btn film-mute" aria-label="Mute" aria-pressed="false" aria-keyshortcuts="M">${ICON.sound}</button>
              <button type="button" class="film-btn film-fs" aria-label="Full screen" aria-keyshortcuts="F">${ICON.full}</button>
            </div>
          </div>
        </div>
        <p class="film-sr" role="status" aria-live="polite"></p>
        <details class="film-transcript">
          <summary>Read the film's text</summary>
          <ul>${TRANSCRIPT.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>
        </details>
      </div>
      <ol class="film-chapters" aria-label="Chapters">
        ${CHAPTERS.map((c, i) => `
          <li><button type="button" class="film-chap" data-i="${i}" data-t="${c.t}">
            <span class="film-chap-time">${fmt(c.t)}</span>
            <span class="film-chap-body"><strong>${esc(c.name)}</strong><span>${esc(c.line)}</span></span>
            <i class="film-chap-fill" aria-hidden="true"></i>
          </button></li>`).join('')}
      </ol>
    </div>
    <p class="film-note">Visuals are AI-generated. BrokerLens is an information service, not an investment adviser; this film is not a recommendation to buy or sell anything.</p>
  `;
  host.appendChild(section);
  return section;
}

function init(section) {
  const $ = (s) => section.querySelector(s);
  const stage = $('.film-stage');
  const frame = $('.film-frame');
  const video = $('.film-video');
  const glow = $('.film-glow');
  const playBig = $('.film-play');
  const toggle = $('.film-toggle');
  const replay = $('.film-replay');
  const timeEl = $('.film-time');
  const seek = $('.film-seek');
  const mute = $('.film-mute');
  const fsBtn = $('.film-fs');
  const segs = [...section.querySelectorAll('.film-seg i')];
  const chaps = [...section.querySelectorAll('.film-chap')];
  const endCard = $('.film-end');
  const status = $('.film-sr');
  let dragging = false;
  let lastValueText = '';

  let loaded = false;
  let raf = 0;
  let glowTimer = 0;
  const setState = (s) => { stage.dataset.state = s; endCard.setAttribute('aria-hidden', s === 'ended' ? 'false' : 'true'); };

  function ensureLoaded() {
    if (!loaded) { video.preload = 'auto'; video.src = SRC; video.volume = 0.7; loaded = true; }
  }

  function paintTime() {
    const t = video.currentTime || 0;
    timeEl.textContent = fmt(t) + ' / ' + fmt(DURATION);
    if (!dragging) seek.value = String(Math.round(t * 10));
    const vt = fmt(t) + ' of ' + fmt(DURATION);
    if (vt !== lastValueText) { lastValueText = vt; seek.setAttribute('aria-valuetext', vt); }
    let active = 0;
    CHAPTERS.forEach((c, i) => { if (t >= c.t) active = i; });
    segs.forEach((el, i) => {
      const start = CHAPTERS[i].t;
      const end = i + 1 < CHAPTERS.length ? CHAPTERS[i + 1].t : DURATION;
      const f = t >= end ? 1 : t <= start ? 0 : (t - start) / (end - start);
      el.style.transform = 'scaleX(' + f.toFixed(4) + ')';
      if (chaps[i]) chaps[i].style.setProperty('--fill', (f * 100).toFixed(1) + '%');
    });
    chaps.forEach((b, i) => {
      if (i === active) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
  }
  function loop() { paintTime(); raf = requestAnimationFrame(loop); }

  // Ambient glow: sample the frame's four edges into CSS colours.
  const cv = document.createElement('canvas');
  cv.width = 16; cv.height = 9;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  function sampleGlow() {
    if (!cx || reduced.matches) return;
    try {
      cx.drawImage(video, 0, 0, 16, 9);
      const d = cx.getImageData(0, 0, 16, 9).data;
      const avg = (x0, x1, y0, y1) => {
        let r = 0, g = 0, b = 0, n = 0;
        for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const i = (y * 16 + x) * 4; r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
        // lift the near-black frames slightly so the glow never disappears entirely
        return 'rgb(' + Math.min(255, Math.round(r / n * 1.5 + 6)) + ',' + Math.min(255, Math.round(g / n * 1.5 + 6)) + ',' + Math.min(255, Math.round(b / n * 1.5 + 6)) + ')';
      };
      glow.style.setProperty('--g-l', avg(0, 3, 0, 9));
      glow.style.setProperty('--g-r', avg(13, 16, 0, 9));
      glow.style.setProperty('--g-t', avg(0, 16, 0, 2));
      glow.style.setProperty('--g-b', avg(0, 16, 7, 9));
    } catch (e) { /* canvas unavailable: keep the static glow */ }
  }

  function announce() { window.dispatchEvent(new CustomEvent('bl:media', { detail: 'film' })); }

  function play() {
    ensureLoaded();
    announce();
    const p = video.play();
    if (p && p.catch) p.catch(() => setState(video.currentTime > 0 ? 'paused' : 'idle'));
  }
  function pause() { video.pause(); }

  video.addEventListener('play', () => {
    setState('playing');
    status.textContent = '';
    if (document.activeElement === playBig || document.activeElement === replay) toggle.focus({ preventScroll: true });
    toggle.innerHTML = ICON.pause; toggle.setAttribute('aria-label', 'Pause');
    cancelAnimationFrame(raf); raf = requestAnimationFrame(loop);
    clearInterval(glowTimer); glowTimer = setInterval(sampleGlow, 140);
  });
  video.addEventListener('pause', () => {
    if (video.ended) return;
    setState('paused');
    toggle.innerHTML = ICON.play; toggle.setAttribute('aria-label', 'Play');
    cancelAnimationFrame(raf); clearInterval(glowTimer); paintTime();
  });
  video.addEventListener('ended', () => {
    setState('ended');
    status.textContent = 'The film has ended. Replay, Compare brokers and Cost calculator are available.';
    if (frame.contains(document.activeElement) || document.activeElement === document.body) replay.focus({ preventScroll: true });
    toggle.innerHTML = ICON.play; toggle.setAttribute('aria-label', 'Play again');
    cancelAnimationFrame(raf); clearInterval(glowTimer); paintTime();
  });
  video.addEventListener('error', () => {
    const code = video.error && video.error.code;
    if (code === 4 && !video.currentTime) { section.remove(); return; }   // file absent / unsupported: drop the block
    // network or decode hiccup: let the visitor try again instead of losing the film
    cancelAnimationFrame(raf); clearInterval(glowTimer);
    loaded = false; video.removeAttribute('src');
    setState('idle');
    toggle.innerHTML = ICON.play; toggle.setAttribute('aria-label', 'Play');
    status.textContent = 'The film could not be loaded. Press play to try again.';
  });

  playBig.addEventListener('click', play);
  toggle.addEventListener('click', () => { if (video.ended) { video.currentTime = 0; } video.paused ? play() : pause(); });
  replay.addEventListener('click', () => { video.currentTime = 0; play(); });
  video.addEventListener('click', () => { video.paused ? play() : pause(); });

  mute.addEventListener('click', () => {
    video.muted = !video.muted;
    mute.innerHTML = video.muted ? ICON.muted : ICON.sound;
    mute.setAttribute('aria-pressed', video.muted ? 'true' : 'false');   // label stays "Mute"; pressed = muted
  });

  fsBtn.addEventListener('click', () => {
    const el = frame;
    if (document.fullscreenElement) { document.exitFullscreen(); return; }
    if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
    else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();   // iOS Safari
  });
  document.addEventListener('fullscreenchange', () => {
    const on = document.fullscreenElement === frame;
    section.classList.toggle('is-fs', on);
    fsBtn.setAttribute('aria-label', on ? 'Exit full screen' : 'Full screen');
  });

  seek.addEventListener('pointerdown', () => { dragging = true; });
  const endDrag = () => { dragging = false; };
  seek.addEventListener('pointerup', endDrag);
  seek.addEventListener('pointercancel', endDrag);
  seek.addEventListener('change', endDrag);
  seek.addEventListener('input', () => {
    ensureLoaded();
    video.currentTime = Number(seek.value) / 10;
    paintTime();
  });

  chaps.forEach((b) => b.addEventListener('click', () => {
    ensureLoaded();
    // Setting currentTime before metadata arrives is allowed: it becomes the start position.
    video.currentTime = Number(b.dataset.t);
    play();
  }));

  // Keyboard: K/space-like toggle, M mute, F full screen, when focus is in the player.
  frame.addEventListener('keydown', (e) => {
    if (e.target.matches('input, a') || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'k') { e.preventDefault(); video.paused ? play() : pause(); }
    else if (k === 'm') { e.preventDefault(); mute.click(); }
    else if (k === 'f') { e.preventDefault(); fsBtn.click(); }
  });

  // Never leave it running unseen.
  if ('IntersectionObserver' in window) {
    new IntersectionObserver((es) => {
      if (!es.some((e) => e.isIntersecting) && !video.paused) pause();
    }, { threshold: 0.2 }).observe(section);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && !video.paused) { pause(); }
  });
  // One soundtrack at a time: the header music button announces itself too.
  window.addEventListener('bl:media', (e) => { if (e.detail !== 'film' && !video.paused) pause(); });

  paintTime();
}

function boot() {
  const host = document.querySelector('footer.site .wrap');
  if (!host || host.querySelector('.film')) return;
  init(build(host));
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
