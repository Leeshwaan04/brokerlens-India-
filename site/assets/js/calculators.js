/* Static /calculators/:slug/ pages ship zero inline script (CSP here is
 * script-src 'self' with no unsafe-inline, so an inline <script> block would
 * be silently blocked and every button would do nothing) - this file is the
 * one thing every calculator page loads, dispatching on body.dataset.calc so
 * one file serves all six pages instead of six near-duplicate scripts. */

function num(id) {
  const el = document.getElementById(id);
  const v = el ? Number(el.value) : NaN;
  return Number.isFinite(v) ? v : 0;
}

function inr(n) {
  return '₹' + Math.round(n).toLocaleString('en-IN');
}

function pct(n, digits = 2) {
  return n.toFixed(digits) + '%';
}

function brokerCta() {
  return `
    <div style="grid-column:1/-1;margin-top:16px;padding:16px 18px;background:var(--bg-sub);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:var(--r);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;box-shadow:var(--shadow-sm)">
      <div>
        <div style="font-weight:700;font-size:var(--fs-sm);color:var(--text)">Invest with Zero Brokerage on Equity Delivery</div>
        <div class="xs muted" style="margin-top:3px">Open a free paperless Demat account with flat Rs 11 F&amp;O orders and zero account opening fee on Indiabulls Securities.</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <a href="https://indiabullssecurities.onelink.me/Kaqz/brokerlens" target="_blank" rel="sponsored noopener" class="btn btn-primary btn-sm" style="font-weight:600">Open Free Demat Account &rarr;</a>
        <a href="/compare" class="btn btn-outline btn-sm">Compare Brokers &rarr;</a>
      </div>
    </div>`;
}

function showResult(html) {
  const out = document.getElementById('calc-result');
  if (out) { out.innerHTML = html + brokerCta(); out.hidden = false; }
}

function donut(l1, v1, l2, v2) {
  const total = v1 + v2;
  if (total <= 0) return '';
  const pct1 = Math.max(1, Math.min(99, Math.round((v1 / total) * 100)));
  const pct2 = 100 - pct1;
  const dash1 = pct1;
  const dash2 = pct2;
  return `
    <div style="grid-column:1/-1;margin-top:14px;padding:12px 16px;background:var(--bg-sub);border:1px solid var(--border);border-radius:var(--r);display:flex;align-items:center;gap:18px">
      <svg width="68" height="68" viewBox="0 0 42 42" style="transform:rotate(-90deg);flex-shrink:0" aria-hidden="true">
        <circle cx="21" cy="21" r="15.9155" fill="transparent" stroke="var(--accent)" stroke-width="4.5" stroke-dasharray="${dash1} ${100 - dash1}" stroke-dashoffset="0"></circle>
        <circle cx="21" cy="21" r="15.9155" fill="transparent" stroke="var(--up)" stroke-width="4.5" stroke-dasharray="${dash2} ${100 - dash2}" stroke-dashoffset="${-dash1}"></circle>
      </svg>
      <div style="display:flex;flex-direction:column;gap:6px;font-size:var(--fs-xs)">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--accent)"></span>
          <span class="muted">${l1}:</span>
          <strong>${inr(v1)} (${pct1}%)</strong>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--up)"></span>
          <span class="muted">${l2}:</span>
          <strong>${inr(v2)} (${pct2}%)</strong>
        </div>
      </div>
    </div>`;
}

const CALCULATORS = {
  sip() {
    const monthly = num('sip-monthly');
    const rate = num('sip-rate') / 100 / 12;
    const months = num('sip-years') * 12;
    if (monthly <= 0 || months <= 0) return;
    const fv = rate > 0
      ? monthly * ((Math.pow(1 + rate, months) - 1) / rate) * (1 + rate)
      : monthly * months;
    const invested = monthly * months;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Invested amount</div><div style="margin-top:2px">${inr(invested)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Est. returns</div><div style="margin-top:2px">${inr(fv - invested)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total value</div><div style="margin-top:2px;font-weight:700">${inr(fv)}</div></div>
      ${donut('Invested', invested, 'Est. Returns', fv - invested)}`);
  },

  lumpsum() {
    const principal = num('ls-principal');
    const rate = num('ls-rate') / 100;
    const years = num('ls-years');
    if (principal <= 0 || years <= 0) return;
    const fv = principal * Math.pow(1 + rate, years);
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Invested amount</div><div style="margin-top:2px">${inr(principal)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Est. returns</div><div style="margin-top:2px">${inr(fv - principal)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total value</div><div style="margin-top:2px;font-weight:700">${inr(fv)}</div></div>
      ${donut('Principal', principal, 'Est. Returns', fv - principal)}`);
  },

  emi() {
    const principal = num('emi-principal');
    const rate = num('emi-rate') / 100 / 12;
    const months = num('emi-years') * 12;
    if (principal <= 0 || months <= 0) return;
    const emi = rate > 0
      ? (principal * rate * Math.pow(1 + rate, months)) / (Math.pow(1 + rate, months) - 1)
      : principal / months;
    const total = emi * months;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Monthly EMI</div><div style="margin-top:2px;font-weight:700">${inr(emi)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total interest</div><div style="margin-top:2px">${inr(total - principal)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total payment</div><div style="margin-top:2px">${inr(total)}</div></div>
      ${donut('Principal loan', principal, 'Total interest', total - principal)}`);
  },

  cagr() {
    const start = num('cagr-start');
    const end = num('cagr-end');
    const years = num('cagr-years');
    if (start <= 0 || end <= 0 || years <= 0) return;
    const cagr = (Math.pow(end / start, 1 / years) - 1) * 100;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">CAGR</div><div style="margin-top:2px;font-weight:700">${pct(cagr)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Absolute gain</div><div style="margin-top:2px">${inr(end - start)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Gain multiple</div><div style="margin-top:2px">${(end / start).toFixed(2)}×</div></div>`);
  },

  compound() {
    const principal = num('ci-principal');
    const rate = num('ci-rate') / 100;
    const n = num('ci-freq');
    const years = num('ci-years');
    if (principal <= 0 || years <= 0 || n <= 0) return;
    const fv = principal * Math.pow(1 + rate / n, n * years);
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Principal</div><div style="margin-top:2px">${inr(principal)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Interest earned</div><div style="margin-top:2px">${inr(fv - principal)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Maturity value</div><div style="margin-top:2px;font-weight:700">${inr(fv)}</div></div>
      ${donut('Principal', principal, 'Interest', fv - principal)}`);
  },

  'capital-gains'() {
    const buy = num('cg-buy');
    const sell = num('cg-sell');
    const days = num('cg-days');
    if (buy <= 0 || sell <= 0) return;
    const gain = sell - buy;
    const longTerm = days > 365;
    let tax = 0, note = '';
    if (gain <= 0) {
      note = 'No tax on a loss (it may be usable to offset other capital gains - see a tax professional).';
    } else if (longTerm) {
      const exemption = 125000;
      const taxable = Math.max(0, gain - exemption);
      tax = taxable * 0.125;
      note = `LTCG: 12.5% on gains above the ₹1,25,000 annual exemption (FY 2025-26 rate for listed equity/equity mutual funds; excludes cess and surcharge).`;
    } else {
      tax = gain * 0.20;
      note = 'STCG: 20% flat on the full gain (FY 2025-26 rate for listed equity/equity mutual funds; excludes cess and surcharge).';
    }
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Gain / loss</div><div style="margin-top:2px">${inr(gain)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Holding treated as</div><div style="margin-top:2px">${longTerm ? 'Long-term' : 'Short-term'}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Estimated tax</div><div style="margin-top:2px;font-weight:700">${inr(tax)}</div></div>
      <p class="xs faint" style="grid-column:1/-1;margin-top:4px">${note} Not tax advice - confirm current rates and your own situation before filing.</p>`);
  },

  'simple-interest'() {
    const principal = num('si-principal');
    const rate = num('si-rate');
    const years = num('si-years');
    if (principal <= 0 || years <= 0) return;
    const interest = (principal * rate * years) / 100;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Principal</div><div style="margin-top:2px">${inr(principal)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Simple interest</div><div style="margin-top:2px">${inr(interest)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total amount</div><div style="margin-top:2px;font-weight:700">${inr(principal + interest)}</div></div>`);
  },

  'stepup-sip'() {
    const monthly0 = num('ssip-monthly');
    const stepUp = num('ssip-stepup') / 100;
    const rate = num('ssip-rate') / 100 / 12;
    const years = num('ssip-years');
    if (monthly0 <= 0 || years <= 0) return;
    let balance = 0, invested = 0, current = monthly0;
    for (let m = 1; m <= years * 12; m++) {
      balance = balance * (1 + rate) + current;
      invested += current;
      if (m % 12 === 0) current *= (1 + stepUp);
    }
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Total invested</div><div style="margin-top:2px">${inr(invested)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Est. returns</div><div style="margin-top:2px">${inr(balance - invested)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total value</div><div style="margin-top:2px;font-weight:700">${inr(balance)}</div></div>
      ${donut('Total invested', invested, 'Est. Returns', balance - invested)}`);
  },

  'direct-regular'() {
    const monthly = num('dr-monthly');
    const rate = num('dr-rate');
    const gap = num('dr-gap');
    const years = num('dr-years');
    if (monthly <= 0 || years <= 0) return;
    const fv = (annualPct) => {
      const r = annualPct / 100 / 12;
      const n = years * 12;
      if (Math.abs(r) < 1e-12) return monthly * n;
      return monthly * ((Math.pow(1 + r, n) - 1) / r) * (1 + r);
    };
    const invested = monthly * years * 12;
    const direct = fv(rate);
    const regular = fv(rate - gap);
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Direct plan value</div><div style="margin-top:2px">${inr(direct)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Regular plan value</div><div style="margin-top:2px">${inr(regular)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Cost of the gap</div><div style="margin-top:2px;font-weight:700">${inr(direct - regular)}</div></div>
      <p class="xs faint" style="grid-column:1/-1;margin-top:4px">Total invested ${inr(invested)} in both plans. Regular plan return used: ${pct(rate - gap)} a year. Illustration of the expense gap you entered, not a recommendation of either plan.</p>`);
  },

  swp() {
    const corpus = num('swp-corpus');
    const withdrawal = num('swp-withdrawal');
    const rate = num('swp-rate') / 100 / 12;
    const years = num('swp-years');
    if (corpus <= 0 || withdrawal <= 0 || years <= 0) return;
    let balance = corpus, withdrawn = 0, monthsLasted = 0;
    const totalMonths = years * 12;
    for (let m = 0; m < totalMonths; m++) {
      balance = balance * (1 + rate) - withdrawal;
      withdrawn += withdrawal;
      monthsLasted = m + 1;
      if (balance <= 0) { balance = 0; break; }
    }
    const depleted = balance <= 0 && monthsLasted < totalMonths;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Total withdrawn</div><div style="margin-top:2px">${inr(withdrawn)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">${depleted ? 'Corpus lasted' : 'Remaining after ' + years + ' yr'}</div><div style="margin-top:2px">${depleted ? Math.floor(monthsLasted / 12) + 'y ' + (monthsLasted % 12) + 'm' : inr(balance)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Starting corpus</div><div style="margin-top:2px;font-weight:700">${inr(corpus)}</div></div>`);
  },

  inflation() {
    const cost = num('infl-cost');
    const rate = num('infl-rate') / 100;
    const years = num('infl-years');
    if (cost <= 0 || years <= 0) return;
    const future = cost * Math.pow(1 + rate, years);
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Cost today</div><div style="margin-top:2px">${inr(cost)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Extra cost from inflation</div><div style="margin-top:2px">${inr(future - cost)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Future cost</div><div style="margin-top:2px;font-weight:700">${inr(future)}</div></div>`);
  },

  retirement() {
    const expense = num('ret-expense');
    const yearsToRetire = num('ret-years-to');
    const inflation = num('ret-inflation') / 100;
    const yearsInRetirement = num('ret-years-in');
    const postReturn = num('ret-return') / 100;
    if (expense <= 0 || yearsInRetirement <= 0) return;
    const futureExpense = expense * Math.pow(1 + inflation, yearsToRetire);
    const realMonthlyRate = ((1 + postReturn) / (1 + inflation)) - 1;
    const n = yearsInRetirement * 12;
    const corpus = Math.abs(realMonthlyRate) < 1e-9
      ? futureExpense * n
      : futureExpense * (1 - Math.pow(1 + realMonthlyRate, -n)) / realMonthlyRate;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Monthly expense at retirement</div><div style="margin-top:2px">${inr(futureExpense)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Retirement duration</div><div style="margin-top:2px">${yearsInRetirement} years</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Corpus needed at retirement</div><div style="margin-top:2px;font-weight:700">${inr(corpus)}</div></div>`);
  },

  ppf() {
    const deposit = num('ppf-deposit');
    const years = num('ppf-years');
    const rate = 7.1 / 100;
    if (deposit <= 0 || years <= 0) return;
    let balance = 0;
    for (let y = 0; y < years; y++) balance = (balance + deposit) * (1 + rate);
    const invested = deposit * years;
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Total invested</div><div style="margin-top:2px">${inr(invested)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Interest earned</div><div style="margin-top:2px">${inr(balance - invested)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Maturity value</div><div style="margin-top:2px;font-weight:700">${inr(balance)}</div></div>
      ${donut('Total invested', invested, 'Interest earned', balance - invested)}
      <p class="xs faint" style="grid-column:1/-1;margin-top:4px">At the PPF rate of 7.1% p.a. for Jul-Sep 2026, compounded annually. This rate is revised quarterly by the Ministry of Finance - verify the current rate before relying on this.</p>`);
  },

  gst() {
    const amount = num('gst-amount');
    const rate = num('gst-rate');
    const mode = (document.querySelector('input[name="gst-mode"]:checked') || {}).value || 'exclusive';
    if (amount <= 0) return;
    let base, gst, total;
    if (mode === 'inclusive') {
      base = amount / (1 + rate / 100);
      gst = amount - base;
      total = amount;
    } else {
      base = amount;
      gst = amount * rate / 100;
      total = amount + gst;
    }
    showResult(`
      <div class="mega-seg"><div class="mega-seg-label">Base amount</div><div style="margin-top:2px">${inr(base)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">GST (${rate}%)</div><div style="margin-top:2px">${inr(gst)}</div></div>
      <div class="mega-seg"><div class="mega-seg-label">Total</div><div style="margin-top:2px;font-weight:700">${inr(total)}</div></div>`);
  },

  /* Stock pages: "What-if price calculator". Pure arithmetic on numbers the
   * visitor types (starting price, their own growth assumption, years). It
   * never reads or implies a forecast and, unlike showResult(), adds no broker
   * call to action beside the result. Every value written into the page is a
   * number formatted here, never raw input text. */
  'price-whatif'() {
    const out = document.getElementById('calc-result');
    if (!out) return;
    const say = (msg) => {
      out.innerHTML = `<p class="small" role="alert">${msg}</p>`;
      out.hidden = false;
    };
    const priceRaw = (document.getElementById('pw-price') || {}).value;
    const growthRaw = (document.getElementById('pw-growth') || {}).value;
    const yearsRaw = (document.getElementById('pw-years') || {}).value;
    const price = Number(priceRaw);
    const growth = Number(growthRaw);
    const years = Math.round(Number(yearsRaw));
    if (!priceRaw || !Number.isFinite(price) || price <= 0) { say('Enter a starting price above zero.'); return; }
    if (growthRaw === '' || growthRaw == null || !Number.isFinite(growth)) { say('Enter your own growth assumption in percent a year. It is left empty on purpose.'); return; }
    if (growth < -90 || growth > 100) { say('Use a yearly growth assumption between -90 and 100 percent.'); return; }
    if (!yearsRaw || !Number.isFinite(years) || years < 1 || years > 30) { say('Enter a number of years from 1 to 30.'); return; }
    const factor = 1 + growth / 100;
    const at = (y) => price * Math.pow(factor, y);
    const rs = (n) => '₹' + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const end = at(years);
    if (!Number.isFinite(end)) { say('That combination is too large to show. Try fewer years or a lower rate.'); return; }
    const changePct = (end / price - 1) * 100;
    const marks = [1, 3, 5, 10];
    if (marks.indexOf(years) < 0) marks.push(years);
    marks.sort((a, b) => a - b);
    const rows = marks.map((y) => {
      const v = at(y);
      return `<tr${y === years ? ' style="font-weight:700"' : ''}><td>${y} year${y === 1 ? '' : 's'}</td><td>${rs(v)}</td><td>${((v / price - 1) * 100).toFixed(1)}%</td></tr>`;
    }).join('');
    out.innerHTML = `
      <div class="grid g3">
        <div class="mega-seg"><div class="mega-seg-label">Starting price</div><div style="margin-top:2px">${rs(price)}</div></div>
        <div class="mega-seg"><div class="mega-seg-label">Your assumption</div><div style="margin-top:2px">${growth.toFixed(1)}% a year</div></div>
        <div class="mega-seg"><div class="mega-seg-label">Value after ${years} year${years === 1 ? '' : 's'}</div><div style="margin-top:2px;font-weight:700">${rs(end)}</div><div class="xs faint" style="margin-top:2px">${changePct.toFixed(1)}% in total</div></div>
      </div>
      <div class="table-scroll"><table class="data"><thead><tr><th>After</th><th>Value under your assumption</th><th>Total change</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    out.hidden = false;
  },
};

function initCalculator() {
  const container = document.querySelector('[data-calc]');
  const kind = container && container.dataset.calc;
  const fn = kind && CALCULATORS[kind];
  const btn = document.getElementById('calc-btn');
  if (!fn || !btn) return;
  btn.addEventListener('click', fn);
  if (kind === 'price-whatif') {
    // Enter in any field runs the calculation, like pressing the button.
    container.querySelectorAll('input').forEach((el) => {
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); fn(); } });
    });
    // Preset growth buttons
    container.querySelectorAll('[data-preset-growth]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const input = document.getElementById('pw-growth');
        if (input) {
          input.value = el.dataset.presetGrowth;
          fn();
        }
      });
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCalculator);
} else {
  initCalculator();
}
