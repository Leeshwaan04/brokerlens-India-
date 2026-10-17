/* Header speaker button: play / stop a looping theme track.
 *
 * The button ships hidden and is only revealed once the audio file is
 * confirmed to exist and be served as audio, so a deploy without the file
 * never shows a dead control. Nothing autoplays: browsers block it and it is
 * unwelcome on a finance site; playback starts only on a click. The file is
 * not fetched until then (preload none).
 */
const btn = document.getElementById('audio-toggle');
const SRC = '/assets/audio/scam-1992-theme.mp3';
const KEY = 'bl-audio';

if (btn) {
  let audio = null;
  const iconOn = btn.querySelector('.ico-on');
  const iconOff = btn.querySelector('.ico-off');

  const store = {
    get() { try { return JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) { return null; } },
    set(v) { try { sessionStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* storage blocked */ } },
  };

  function paint(on) {
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = on ? 'Stop music' : 'Play music';
    btn.setAttribute('aria-label', btn.title);
    if (iconOn) iconOn.style.display = on ? '' : 'none';
    if (iconOff) iconOff.style.display = on ? 'none' : '';
  }

  function ensureAudio() {
    if (!audio) {
      audio = new Audio();
      audio.preload = 'none';
      audio.loop = true;
      audio.volume = 0.5;
      audio.src = SRC;
      audio.addEventListener('error', () => { btn.hidden = true; store.set({ on: false, t: 0 }); });
    }
    return audio;
  }

  function play(from) {
    window.dispatchEvent(new CustomEvent('bl:media', { detail: 'music' }));
    const a = ensureAudio();
    if (from > 0) { try { a.currentTime = from; } catch (e) { /* not seekable yet */ } }
    const p = a.play();
    paint(true);
    if (p && p.catch) p.catch(() => { paint(false); store.set({ on: false, t: 0 }); });
  }

  function stop() {
    if (audio) { audio.pause(); audio.currentTime = 0; }
    paint(false);
    store.set({ on: false, t: 0 });
  }

  // The footer film announces itself too: one soundtrack at a time.
  window.addEventListener('bl:media', (e) => { if (e.detail !== 'music' && btn.getAttribute('aria-pressed') === 'true') stop(); });

  btn.addEventListener('click', () => {
    if (btn.getAttribute('aria-pressed') === 'true') stop(); else play(0);
  });

  // Keep the position across full-page navigations on the static pages. A new
  // document cannot autoplay without a fresh click, so a blocked resume
  // simply leaves the button in its "off" state.
  window.addEventListener('pagehide', () => {
    if (audio && !audio.paused) store.set({ on: true, t: audio.currentTime });
  });

  fetch(SRC, { method: 'HEAD' }).then((r) => {
    if (!r.ok || !/audio|mpeg|octet/i.test(r.headers.get('content-type') || '')) return;
    btn.hidden = false;
    const s = store.get();
    if (s && s.on) play(s.t || 0);
  }).catch(() => { /* offline or blocked: stay hidden */ });

  paint(false);
}
