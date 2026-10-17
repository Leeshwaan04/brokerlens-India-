/* IPO event-alert signup card.
 *
 * Shown only on /ipo/ pages and only when the signup endpoint reports it is
 * configured (GET /api/subscribe -> {enabled:true}); otherwise nothing renders,
 * so there is never a form that cannot deliver a confirmation. Collects an email
 * address and an explicit consent tick, nothing else. The wording promises only
 * what the emails contain: factual IPO events, no tips, no grey-market prices.
 */
const path = location.pathname;
if (path.startsWith('/ipo')) {
  const source = path.replace(/^\/+|\/+$/g, '').replace(/[^a-z0-9/_-]/gi, '-').slice(0, 80) || 'ipo';
  fetch('/api/subscribe', { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : { enabled: false }))
    .then((cfg) => { if (cfg && cfg.enabled) mount(); })
    .catch(() => { /* endpoint unreachable: show nothing */ });
}

function mount() {
  const host = document.querySelector('main');
  if (!host || host.querySelector('.alerts-card')) return;
  const card = document.createElement('section');
  card.className = 'alerts-card';
  card.setAttribute('aria-labelledby', 'alerts-title');
  card.innerHTML = `
    <div class="alerts-copy">
      <h2 id="alerts-title">Get IPO alerts by email</h2>
      <p>A short email when an IPO opens, when it closes, and when its allotment and listing dates are due. Facts from the
      exchanges only: no tips, no grey-market prices, no recommendations. Free, and you can unsubscribe in one click.</p>
    </div>
    <form class="alerts-form" novalidate>
      <label class="alerts-label" for="alerts-email">Email address</label>
      <div class="alerts-row">
        <input id="alerts-email" name="email" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com" required maxlength="254">
        <button type="submit" class="btn btn-primary">Send me alerts</button>
      </div>
      <input class="alerts-hp" name="website" type="text" tabindex="-1" autocomplete="off" aria-hidden="true">
      <label class="alerts-consent"><input type="checkbox" name="consent" required>
        <span>I agree to receive IPO event emails from BrokerLens and accept the <a href="/privacy-policy">Privacy Policy</a>.
        We will email you once to confirm.</span></label>
      <p class="alerts-msg" role="status" aria-live="polite"></p>
    </form>`;
  const faq = [...host.querySelectorAll('h2')].find((h) => /^frequently/i.test(h.textContent.trim()));
  if (faq) faq.parentNode.insertBefore(card, faq); else host.appendChild(card);

  const form = card.querySelector('form');
  const msg = card.querySelector('.alerts-msg');
  const btn = card.querySelector('button');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    msg.className = 'alerts-msg';
    const email = form.email.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { msg.textContent = 'Please enter a valid email address.'; msg.classList.add('err'); form.email.focus(); return; }
    if (!form.consent.checked) { msg.textContent = 'Please tick the box to agree before we can send alerts.'; msg.classList.add('err'); return; }
    btn.disabled = true;
    msg.textContent = 'Sending...';
    try {
      const r = await fetch('/api/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ email, consent: true, source, website: form.website.value }),
      });
      if (r.ok) {
        form.reset();
        msg.textContent = 'Almost done: check your inbox and confirm your email to start receiving alerts.';
        msg.classList.add('ok');
      } else if (r.status === 429) {
        msg.textContent = 'Too many attempts. Please try again in a few minutes.'; msg.classList.add('err');
      } else if (r.status === 400) {
        msg.textContent = 'That email address does not look right. Please check it and try again.'; msg.classList.add('err');
      } else {
        msg.textContent = 'We could not save that just now. Please try again later.'; msg.classList.add('err');
      }
    } catch (err) {
      msg.textContent = 'We could not reach the server. Please try again later.'; msg.classList.add('err');
    } finally {
      btn.disabled = false;
    }
  });
}
