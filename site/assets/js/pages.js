/* Page renderers. Each export returns an HTML string and optionally registers
 * post-render work (chart draws, event wiring) via the `after` queue.
 */

import {
  cls, count, esc, full, initials, inr, loadAlgo, loadBroker, loadOverview,
  loadRegistry, loadSources, markColor, month, pct, provDot, safeUrl,
  SEGMENT_LABEL, TYPE_LABEL,
} from './store.js';
import { barChart, donut, lineChart, registerRedraw, sparkline } from './chart.js';

const after = [];
export const runAfter = () => { while (after.length) { try { after.shift()(); } catch (e) { console.error(e); } } };
const onMount = (fn) => after.push(fn);

/* ------------------------------------------------------------- shared bits */

/* Says plainly what the site does not yet publish, and why, instead of leaving
 * an empty chart or a table of dashes that reads as a broken page. */
function pending(what, detail) {
  return `<div class="pending">
    <strong>${esc(what)} not published yet</strong>
    ${esc(detail)} We publish a figure only once it comes from the primary source,
    so this section is empty rather than estimated.
    <a href="/sources" data-link>What is live today</a>.
  </div>`;
}

const HAS = (o, key) => Boolean(o?.metadata?.data_status?.[key]);

function sampleBanner(meta) {
  const s = meta?.sample_data || {};
  const which = Object.entries(s).filter(([, v]) => v).map(([k]) => k.replace(/_/g, ' '));
  if (!which.length) return '';
  return `<div class="banner">
    <span>⚠</span>
    <div><strong>Sample data in use for: ${esc(which.join(', '))}.</strong>
    These are placeholder figures generated to exercise the interface — not facts about any broker.
    Regulator-sourced fields (legal entity, SEBI registration, exchange memberships, defaulter status)
    are real. See <a href="/sources" data-link>sources</a> for what is live.</div>
  </div>`;
}

const badge = (b) => {
  const out = [];
  if (b.tier === 'featured') out.push('<span class="badge badge-featured">Featured</span>');
  else if (b.claimed) out.push('<span class="badge badge-verified">Claimed</span>');
  if (b.verified) out.push('<span class="badge badge-verified" title="Legal entity and SEBI registration matched to the SEBI register">SEBI ✓</span>');
  if (b.flagged) out.push('<span class="badge badge-warn" title="Named in an exchange circular or on the SEBI defaulter list">⚑ Flagged</span>');
  return out.join(' ');
};

const brokerLink = (b) =>
  `<a href="/broker/${esc(b.id)}" data-link>${esc(b.brand)}</a>`;

const mark = (id, name, size = 26) =>
  `<span style="width:${size}px;height:${size}px;border-radius:6px;flex:none;display:grid;place-items:center;
   background:${markColor(id)};color:#fff;font-size:${Math.round(size * 0.42)}px;font-weight:700">${esc(initials(name))}</span>`;

function sparkCell(b) {
  const id = `sp-${b.id}-${Math.random().toString(36).slice(2, 7)}`;
  onMount(() => {
    const c = document.getElementById(id);
    if (c) {
      const draw = () => sparkline(c, b.spark);
      draw();
      registerRedraw(draw);
    }
  });
  return `<canvas class="spark" id="${id}" aria-hidden="true"></canvas>`;
}

function statTile(label, value, sub, extra = '') {
  return `<div class="card stat">
    <div class="stat-label">${esc(label)} ${extra}</div>
    <div class="stat-value">${value}</div>
    ${sub ? `<div class="stat-sub">${sub}</div>` : ''}
  </div>`;
}

/* --------------------------------------------------------------- ad slot */

function adSlot(overview, placement) {
  const featured = (overview.brokers || []).filter((b) => b.tier === 'featured');
  if (!featured.length) return '';
  const b = featured[Math.floor(Math.random() * featured.length)];
  return `<div class="ad-slot">
    <div class="ad-tag">Sponsored — ${esc(placement)}</div>
    <div class="row" style="margin-top:8px">
      ${mark(b.id, b.brand, 34)}
      <div class="grow">
        <div style="font-weight:600">${esc(b.brand)}</div>
        <div class="xs muted">${count(b.clients)} active clients · ${esc(TYPE_LABEL[b.type] || b.type || '')}</div>
      </div>
      <a class="btn btn-sm btn-primary" href="/broker/${esc(b.id)}" data-link>View</a>
    </div>
  </div>`;
}

/* =========================================================== HOME */

export async function home() {
  const o = await loadOverview();
  const m = o.market || {}, agg = o.aggregates || {}, meta = o.metadata || {};
  const hasClients = HAS(o, 'active_clients');
  const top = hasClients
    ? [...(o.brokers || [])].sort((a, b) => (b.clients || 0) - (a.clients || 0)).slice(0, 12)
    : [...(o.brokers || [])].sort((a, b) => String(a.brand).localeCompare(String(b.brand))).slice(0, 12);
  const conc = agg.concentration || {};

  onMount(() => {
    const c = document.getElementById('mkt-total');
    if (c && (agg.total_series || []).length) {
      const draw = () => lineChart(c, [{ label: 'Active clients', data: agg.total_series }], {
        height: 200, area: true, fmtY: (v) => count(v), fmtTip: (v) => full(v),
      });
      draw(); registerRedraw(draw);
    }
    const d = document.getElementById('mkt-share');
    if (d) {
      const rows = top.slice(0, 6).map((b) => ({ label: b.brand, value: b.share || 0 }));
      const rest = 100 - rows.reduce((a, r) => a + r.value, 0);
      if (rest > 0) rows.push({ label: 'Everyone else', value: Number(rest.toFixed(2)) });
      const draw = () => donut(d, rows, { size: 168, center: `${(conc.top5_pct ?? 0).toFixed(1)}%`, centerSub: 'top 5 share' });
      draw(); registerRedraw(draw);
      document.getElementById('share-legend').innerHTML = rows
        .map((r, i) => `<span><i style="background:var(--c${(i % 8) + 1})"></i>${esc(r.label)} ${r.value.toFixed(1)}%</span>`)
        .join('');
    }
    const dl = document.getElementById('bse-delivery');
    if (dl && (m.bse_delivery || []).length) {
      const draw = () => lineChart(dl, [{
        label: 'Delivery %', data: m.bse_delivery.map((r) => [r.date.slice(5), r.delivery_pct]),
      }], { height: 160, fmtY: (v) => v.toFixed(0) + '%', fmtTip: (v) => v.toFixed(2) + '%' });
      draw(); registerRedraw(draw);
    }
  });

  const nifty = (m.nse?.indices || [])[0];
  const breadth = m.nse?.breadth;
  const delivery = (m.bse_delivery || []).slice(-1)[0];

  return `
  ${sampleBanner(meta)}

  <section class="pitch" style="margin-top:16px">
    <h1 style="max-width:22ch">Every Indian stock broker, measured the same way.</h1>
    <p class="muted" style="max-width:62ch;margin-top:12px">
      ${meta.broker_count} brokers tracked in depth and ${count(o.registry_count)} SEBI-registered entities on file.
      ${hasClients
        ? 'Active clients, market share, investor-complaint records, regulatory registrations and real cost, assembled from NSE, BSE and SEBI primary disclosures, not from marketing pages.'
        : 'Legal entities, SEBI registration numbers, exchange memberships and regulatory standing, taken straight from the regulator\'s own register rather than from marketing pages.'}
    </p>
    <div class="row-wrap" style="margin-top:18px">
      <a class="btn btn-primary" href="/brokers" data-link>Browse brokers</a>
      <a class="btn" href="/compare" data-link>Compare side by side</a>
      ${hasClients ? '<a class="btn" href="/calculator" data-link>What will it cost me?</a>'
                   : '<a class="btn" href="/registry" data-link>Search the SEBI register</a>'}
    </div>
  </section>

  <div class="grid g4" style="margin-top:24px">
    ${hasClients
      ? `${statTile('Total active clients', count(agg.total_active_clients),
            `<span class="${cls(agg.total_yoy_pct)}">${pct(agg.total_yoy_pct)}</span> year on year`,
            provDot(meta.sample_data?.active_clients ? 'sample' : 'nse'))}
         ${statTile('Top 5 brokers hold', pct(conc.top5_pct, { sign: false }),
            `top 1 is ${pct(conc.top1_pct, { sign: false })} · top 10 is ${pct(conc.top10_pct, { sign: false })}`)}
         ${statTile('Market concentration', (agg.hhi ?? 0).toFixed(0),
            'HHI, above 1,500 is moderately concentrated')}`
      : `${statTile('Brokers profiled', String(meta.broker_count),
            'matched to the SEBI register', provDot('sebi_registry'))}
         ${statTile('Entity records verified', String(meta.verified_count),
            'legal name and registration confirmed', provDot('sebi_registry'))}
         ${statTile('Defaulter records on file', count(o.defaulter_count ?? 0),
            'firms declared defaulter or expelled', provDot('sebi_registry'))}`}
    ${statTile('SEBI-registered on file', count(o.registry_count),
      `${meta.verified_count} tracked brokers matched to the register`, provDot('sebi_registry'))}
  </div>

  ${hasClients ? `<div class="grid g-main" style="margin-top:16px">
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">Total active clients across tracked brokers</div>
          <div class="xs faint">Monthly, ${(agg.total_series || []).length} months to ${month((agg.total_series || []).slice(-1)[0]?.[0])}</div>
        </div>
      </div>
      <div class="chart-box"><canvas id="mkt-total"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Share of active clients</div>
      <div class="row" style="margin-top:12px;align-items:center;gap:16px">
        <canvas id="mkt-share"></canvas>
      </div>
      <div class="legend" id="share-legend" style="margin-top:12px"></div>
    </div>
  </div>` : `<div style="margin-top:16px">${pending('Client and complaint statistics',
      'NSE publishes member-wise active-client counts monthly, and every broker must publish its complaint record in SEBI\'s Annexure-B format. Both are being brought in from those primary sources.')}</div>`}

  <div class="grid g-main" style="margin-top:16px">
    <div>
      <div class="section-title"><h2>${hasClients ? 'Largest brokers by active clients' : 'Brokers on the SEBI register'}</h2>
        <a class="small" href="/brokers" data-link>All ${meta.broker_count} →</a></div>
      <div class="table-scroll">
        <table class="data">
          <thead><tr>
            ${hasClients
              ? `<th>#</th><th>Broker</th><th class="right">Active clients</th><th class="right">Share</th>
                 <th class="right">12-month</th><th>Trend</th><th class="right">Complaints /10k</th><th class="right">Reliability</th>`
              : `<th>Broker</th><th>Registration</th><th>Type</th><th>Segments</th><th>Head office</th>`}
          </tr></thead>
          <tbody>
            ${top.map((b) => hasClients ? `<tr>
              <td class="rank-cell">${b.rank ?? '—'}</td>
              <td><div class="bname">${mark(b.id, b.brand)}<span>${brokerLink(b)}</span> ${badge(b)}</div></td>
              <td class="right num">${count(b.clients)}</td>
              <td class="right num">${pct(b.share, { sign: false })}</td>
              <td class="right num ${cls(b.clients_yoy)}">${pct(b.clients_yoy)}</td>
              <td>${sparkCell(b)}</td>
              <td class="right num">${b.complaints_per_10k?.toFixed(2) ?? '—'}</td>
              <td class="right num">${b.reliability?.toFixed(1) ?? '—'}</td>
            </tr>` : `<tr>
              <td><div class="bname">${mark(b.id, b.brand)}<span>${brokerLink(b)}</span> ${badge(b)}</div></td>
              <td class="small num">${esc(b.sebi_reg_no || '—')}</td>
              <td class="small">${esc(TYPE_LABEL[b.type] || b.type || '—')}</td>
              <td class="xs muted">${(b.segments || []).map((x) => esc(SEGMENT_LABEL[x] || x)).join(' · ') || '—'}</td>
              <td class="small">${esc(b.hq || '—')}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>

    <div class="stack">
      ${adSlot(o, 'homepage rail')}

      <div class="card">
        <div class="card-title">Market snapshot</div>
        <dl class="kv" style="margin-top:10px">
          ${nifty ? `<dt>NIFTY 50</dt><dd class="num">${full(nifty.last)}
            <span class="${cls(nifty.change_pct)}">${pct(nifty.change_pct)}</span></dd>` : ''}
          ${breadth ? `<dt>NSE breadth</dt><dd class="num"><span class="up">${full(breadth.advances)} ▲</span> /
            <span class="down">${full(breadth.declines)} ▼</span></dd>` : ''}
          ${delivery ? `<dt>BSE delivery</dt><dd class="num">${delivery.delivery_pct.toFixed(2)}%</dd>` : ''}
          ${m.universe?.nse_symbols ? `<dt>NSE symbols</dt><dd class="num">${full(m.universe.nse_symbols)}</dd>` : ''}
          ${(m.turnover || []).length ? `<dt>NSE CM turnover</dt><dd class="num">${inr(m.turnover.slice(-1)[0].turnover_inr)}</dd>` : ''}
        </dl>
        <div class="xs faint" style="margin-top:10px">${provDot('nse')} Live from NSE and BSE at last build.</div>
      </div>

      ${(m.bse_delivery || []).length ? `<div class="card">
        <div class="card-title">BSE delivery % — investors vs churn</div>
        <div class="chart-box"><canvas id="bse-delivery"></canvas></div>
      </div>` : ''}

    </div>
  </div>

  <div class="section-title"><h2>Rankings</h2><a class="small" href="/leaderboards" data-link>All rankings →</a></div>
  <div class="grid g3">
    ${(o.leaderboards || []).slice(0, 3).map((bd) => leaderCard(bd)).join('')}
  </div>`;
}

function leaderCard(bd) {
  return `<div class="card">
    <div class="card-title">${esc(bd.title)}</div>
    <table class="data" style="margin-top:8px">
      <tbody>${(bd.rows || []).slice(0, 6).map((r) => `<tr>
        <td class="rank-cell">${r.rank}</td>
        <td><a href="/broker/${esc(r.id)}" data-link>${esc(r.brand)}</a></td>
        <td class="right num">${fmtBoard(bd, r.value)}</td>
      </tr>`).join('')}</tbody>
    </table>
  </div>`;
}

function fmtBoard(bd, v) {
  if (v == null) return '—';
  if (bd.unit === 'clients') return count(v);
  if (bd.unit === '%') return pct(v);
  if (bd.unit === 'bps') return `${v > 0 ? '+' : ''}${v.toFixed(0)}`;
  if (bd.unit === 'INR/month') return inr(v, { decimals: 0 });
  if (bd.unit === '/100') return v.toFixed(1);
  return v.toFixed(2);
}

/* =========================================================== DIRECTORY */

const dirState = { q: '', type: '', segment: '', sort: 'clients', dir: -1, claimedOnly: false };

export async function brokers(params) {
  const o = await loadOverview();
  if (params?.get('q')) dirState.q = params.get('q');

  onMount(() => {
    const render = () => {
      const rows = filterSort(o.brokers || []);
      document.getElementById('dir-body').innerHTML = rows.length
        ? rows.map(dirRow).join('')
        : `<tr><td colspan="9" class="empty">No broker matches those filters.</td></tr>`;
      document.getElementById('dir-count').textContent = `${rows.length} of ${o.brokers.length}`;
      runAfter();
    };
    document.getElementById('dir-q').addEventListener('input', (e) => { dirState.q = e.target.value; render(); });
    document.querySelectorAll('[data-filter]').forEach((el) => {
      el.addEventListener('click', () => {
        const [k, v] = el.dataset.filter.split(':');
        dirState[k] = dirState[k] === v ? '' : v;
        document.querySelectorAll('[data-filter]').forEach((x) => {
          const [xk, xv] = x.dataset.filter.split(':');
          x.setAttribute('aria-pressed', String(dirState[xk] === xv));
        });
        render();
      });
    });
    document.querySelectorAll('th[data-sort]').forEach((th) => {
      th.addEventListener('click', () => {
        const k = th.dataset.sort;
        if (dirState.sort === k) dirState.dir *= -1;
        else { dirState.sort = k; dirState.dir = k === 'brand' ? 1 : -1; }
        document.querySelectorAll('th[data-sort]').forEach((x) => x.classList.toggle('sorted', x.dataset.sort === dirState.sort));
        render();
      });
    });
    render();
  });

  return `
  ${sampleBanner(o.metadata)}
  <div class="spread" style="margin-top:16px">
    <div><h1>Brokers</h1>
      <p class="muted small">${o.metadata.broker_count} brokers tracked in depth.
      Looking for a smaller firm? <a href="/registry" data-link>Search all ${count(o.registry_count)} SEBI-registered entities</a>.</p>
    </div>
    <a class="btn" href="/compare" data-link>Compare selected →</a>
  </div>

  <p class="xs faint" style="margin-top:8px">Browse by category:
    ${Object.entries(TYPE_LABEL).map(([k, v]) =>
      `<a href="/brokers-by/type/${k.replace(/_/g, '-')}/">${esc(v)}</a>`).join(' &middot; ')}
    &nbsp;|&nbsp;
    ${Object.entries(SEGMENT_LABEL).map(([k, v]) =>
      `<a href="/brokers-by/segment/${k.replace(/_/g, '-')}/">${esc(v)}</a>`).join(' &middot; ')}
  </p>

  <div class="card" style="margin-top:16px">
    <div class="row-wrap">
      <div class="grow" style="min-width:220px">
        <input type="search" id="dir-q" placeholder="Search broker or legal entity…" value="${esc(dirState.q)}">
      </div>
      <div class="chips">
        ${Object.entries(TYPE_LABEL).map(([k, v]) =>
          `<button class="chip" data-filter="type:${k}" aria-pressed="${dirState.type === k}">${esc(v)}</button>`).join('')}
        ${Object.entries(SEGMENT_LABEL).map(([k, v]) =>
          `<button class="chip" data-filter="segment:${k}" aria-pressed="${dirState.segment === k}">${esc(v)}</button>`).join('')}
      </div>
      <span class="small faint" id="dir-count"></span>
    </div>
  </div>

  <div class="table-scroll" style="margin-top:16px">
    <table class="data">
      <thead><tr>
        <th data-tip="Rank by active clients. A dash means the client count is not available yet.">#</th>
        <th class="sortable" data-sort="brand"
          data-tip="Consumer brand. The SEBI badge means we matched the legal entity and registration number to SEBI's own register; a flag means the broker appears in an exchange circular or on the defaulter list.">Broker <span class="arrow">↕</span></th>
        <th class="sortable right sorted" data-sort="clients"
          data-tip="Unique clients who placed at least one trade in the last 12 months, as reported to the exchange (NSE UCC data). The standard measure of a broker's real, active user base; L is lakh (100,000).">Active clients <span class="arrow">↕</span></th>
        <th class="sortable right" data-sort="clients_yoy"
          data-tip="Change in active clients over the last 12 months, in percent. Positive means the broker is gaining active users; negative means clients are leaving or going inactive.">12-month <span class="arrow">↕</span></th>
        <th data-tip="Active client count month by month over the last 12 months, so you can see whether growth is steady, recent or fading.">Trend</th>
        <th class="sortable right" data-sort="complaints_per_10k"
          data-tip="Investor complaints received in the last 12 months per 10,000 active clients, from SEBI-mandated disclosures. Dividing by size lets small and large brokers be compared fairly. Lower is better.">Complaints /10k <span class="arrow">↕</span></th>
        <th class="sortable right tip-end" data-sort="reliability"
          data-tip="BrokerLens composite score out of 100: complaint rate vs peers (40%), complaint resolution rate (20%), regulatory record (20%), complaint backlog (10%) and years in business (10%). Built only from regulator and exchange disclosures; full formula on the methodology page.">Reliability <span class="arrow">↕</span></th>
        <th class="sortable right tip-end" data-sort="cost"
          data-tip="Estimated brokerage for a fixed monthly basket (4 delivery trades, 10 intraday, 10 F&O orders) plus AMC, priced on each broker's published charges. Statutory taxes are excluded since they are identical across brokers. Shows 'unverified' until a broker publishes charges on its claimed profile.">Cost /month <span class="arrow">↕</span></th>
        <th class="tip-end"
          data-tip="Business model. Discount: flat per-order fee, app first. Full service: research, advisory and branch network. Bank backed: the broking arm of a bank, usually with a 3-in-1 account.">Type</th>
      </tr></thead>
      <tbody id="dir-body"></tbody>
    </table>
  </div>
  <p class="xs faint" style="margin-top:10px">
    ${provDot('nse')} exchange/regulator sourced · ${provDot('curated')} curated or broker-supplied ·
    ${provDot('sample')} sample pending ingest. Cost is a fixed basket of trades — see
    <a href="/methodology" data-link>methodology</a>.
  </p>`;
}

function filterSort(list) {
  const q = dirState.q.trim().toLowerCase();
  let rows = list.filter((b) => {
    if (q && !(`${b.brand} ${b.sebi_reg_no || ''} ${b.hq || ''}`.toLowerCase().includes(q))) return false;
    if (dirState.type && b.type !== dirState.type) return false;
    if (dirState.segment && !(b.segments || []).includes(dirState.segment)) return false;
    return true;
  });
  const k = dirState.sort;
  rows.sort((a, b) => {
    let av = a[k], bv = b[k];
    if (k === 'brand') return String(av).localeCompare(String(bv)) * dirState.dir;
    if (av == null) return 1;
    if (bv == null) return -1;
    return (av - bv) * dirState.dir;
  });
  // Featured listings surface above equally-ranked peers; never above a broker
  // that genuinely ranks higher on the sorted metric.
  return rows;
}

function dirRow(b) {
  return `<tr class="${b.tier === 'featured' ? 'promoted' : ''}">
    <td class="rank-cell">${b.rank ?? '—'}</td>
    <td><div class="bname">${mark(b.id, b.brand)}<span>${brokerLink(b)}</span> ${badge(b)}</div>
      <div class="xs faint">${esc(b.hq || '')}${b.founded ? ` · est. ${b.founded}` : ''}</div></td>
    <td class="right num">${count(b.clients)}</td>
    <td class="right num ${cls(b.clients_yoy)}">${pct(b.clients_yoy)}</td>
    <td>${sparkCell(b)}</td>
    <td class="right num">${b.complaints_per_10k?.toFixed(2) ?? '—'}</td>
    <td class="right num">${b.reliability?.toFixed(1) ?? '—'}</td>
    <td class="right num">${b.cost != null ? inr(b.cost, { decimals: 0 }) : '<span class="faint">unverified</span>'}</td>
    <td class="small">${esc(TYPE_LABEL[b.type] || b.type || '')}</td>
  </tr>`;
}

/* =========================================================== PROFILE */

export async function broker(id) {
  let b;
  try { b = await loadBroker(id); } catch { return notFound(`No broker profile for “${esc(id)}”.`); }
  const o = await loadOverview();
  const p = b.profile, c = b.clients || {}, k = b.complaints || {}, rel = b.reliability || {}, cost = b.cost || {};
  const flags = b.regulatory_flags || {};

  onMount(() => {
    const cc = document.getElementById('p-clients');
    if (cc && (c.series || []).length) {
      const draw = () => lineChart(cc, [{ label: 'Active clients', data: c.series }],
        { height: 220, area: true, fmtY: (v) => count(v), fmtTip: (v) => full(v) });
      draw(); registerRedraw(draw);
    }
    const kc = document.getElementById('p-complaints');
    if (kc && (k.series || []).length) {
      const draw = () => lineChart(kc, [
        { label: 'Received', data: k.series },
        { label: 'Pending at month end', data: k.pending_series },
      ], { height: 200, zero: true, fmtY: (v) => String(Math.round(v)) });
      draw(); registerRedraw(draw);
    }
    const rc = document.getElementById('p-rel');
    if (rc && Object.keys(rel.components || {}).length) {
      const draw = () => barChart(rc, Object.entries(rel.components).map(([kk, v]) => ({
        label: kk.replace(/_/g, ' '), value: v,
      })), { height: 150, fmt: (v) => v.toFixed(0), labelW: 100 });
      draw(); registerRedraw(draw);
    }
  });

  const shareOfMkt = c.market_share_pct;
  const relColor = rel.score == null ? 'var(--text-faint)'
    : rel.score >= 75 ? 'var(--up)' : rel.score >= 55 ? 'var(--warn)' : 'var(--down)';

  return `
  ${sampleBanner(o.metadata)}

  <div class="hero" style="margin-top:16px">
    <div class="hero-mark" style="background:${markColor(p.id)}">${esc(initials(p.brand))}</div>
    <div class="grow">
      <div class="row-wrap">
        <h1>${esc(p.brand)}</h1>
        ${badge({ tier: b.listing?.tier, claimed: b.listing?.claimed, verified: p.legal_name_verified, flagged: flags.defaulter || (flags.circulars || []).length })}
      </div>
      <p class="muted small" style="margin-top:6px">
        ${esc(p.legal_name || '')}${p.sebi_reg_no ? ` · SEBI ${esc(p.sebi_reg_no)}` : ''}
        ${p.legal_name_verified ? '' : ' · <span class="badge badge-warn">entity not yet matched to SEBI register</span>'}
      </p>
      <div class="row-wrap" style="margin-top:10px">
        ${safeUrl(p.website) ? `<a class="btn btn-sm" href="${safeUrl(p.website)}" rel="nofollow noopener external" target="_blank">Website ↗</a>` : ''}
        <a class="btn btn-sm" href="/compare?b=${esc(p.id)}" data-link>Compare</a>
        <a class="btn btn-sm" href="/calculator?b=${esc(p.id)}" data-link>Cost for my trades</a>
      </div>
    </div>
    <div class="card" style="min-width:200px">
      <div class="stat-label">Reliability score</div>
      <div class="stat-value" style="color:${relColor}">${rel.score?.toFixed(1) ?? '—'}<span class="muted" style="font-size:var(--fs-base)">/100</span></div>
      <div class="meter" style="margin-top:8px"><i style="width:${rel.score ?? 0}%;background:${relColor}"></i></div>
      <div class="xs faint" style="margin-top:6px">confidence: ${esc(rel.confidence || 'none')} ·
        <a href="/methodology" data-link>how it is built</a></div>
    </div>
  </div>

  ${flags.defaulter ? `<div class="banner" style="margin-top:16px"><span>⚑</span><div>
    <strong>This entity appears on SEBI's defaulter / expelled broker list.</strong>
    Matched names: ${esc((flags.defaulter_names || []).join('; '))}. Verify directly with SEBI before proceeding.
  </div></div>` : ''}

  <div class="grid g4" style="margin-top:20px">
    ${statTile('Active clients', count(c.active_clients),
      `${month(c.as_of)} · rank ${b.rank ?? '—'} of ${o.metadata.broker_count}`,
      provDot(b.provenance?.active_clients))}
    ${statTile('Market share', pct(shareOfMkt, { sign: false }),
      c.market_share_change_1y_bps != null
        ? `<span class="${cls(c.market_share_change_1y_bps)}">${c.market_share_change_1y_bps > 0 ? '+' : ''}${c.market_share_change_1y_bps.toFixed(0)} bps</span> in 12 months` : '')}
    ${statTile('12-month growth', pct(c.yoy_pct),
      c.net_adds_12m != null ? `${c.net_adds_12m > 0 ? '+' : ''}${count(c.net_adds_12m)} clients` : '')}
    ${statTile('Complaints per 10k clients', k.per_10k_clients_12m?.toFixed(2) ?? '—',
      k.available ? `${full(k.received_12m)} in 12 months · ${k.resolution_rate_pct?.toFixed(1) ?? '—'}% resolved` : 'no disclosure ingested',
      provDot(b.provenance?.complaints))}
  </div>

  <div class="grid g-main" style="margin-top:16px">
    <div class="card">
      <div class="card-head"><div>
        <div class="card-title">Active clients</div>
        <div class="xs faint">${(c.series || []).length} months to ${month(c.as_of)}</div>
      </div></div>
      <div class="chart-box"><canvas id="p-clients"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Registration &amp; entity</div>
      <dl class="kv" style="margin-top:10px">
        <dt>Type</dt><dd>${esc(TYPE_LABEL[p.type] || p.type || '—')}</dd>
        <dt>Head office</dt><dd>${esc(p.sebi_city || p.hq || '—')}</dd>
        ${p.founded ? `<dt>Founded</dt><dd class="num">${p.founded}</dd>` : ''}
        ${p.sebi_validity ? `<dt>Registration</dt><dd class="small">${esc(p.sebi_validity)}</dd>` : ''}
        ${p.listed_company ? '<dt>Listed</dt><dd>Yes — publicly traded</dd>' : ''}
        <dt>Segments</dt><dd class="small">${(p.segments || []).map((s) => esc(SEGMENT_LABEL[s] || s)).join(', ') || '—'}</dd>
        ${(p.apps || []).length ? `<dt>Apps</dt><dd class="small">${(p.apps).map(esc).join(', ')}</dd>` : ''}
      </dl>
      ${(p.dp_registrations || []).length ? `<hr class="sep">
        <div class="card-title">Depository participant</div>
        <div class="small" style="margin-top:6px">${p.dp_registrations.map((d) =>
          `${esc(d.depository)} — <span class="num">${esc(d.reg_no)}</span>`).join('<br>')}</div>` : ''}
      ${(p.sebi_exchanges || []).length ? `<hr class="sep">
        <div class="card-title">Exchange memberships (SEBI register)</div>
        <div class="xs muted" style="margin-top:6px">${p.sebi_exchanges.map(esc).join(' · ')}</div>` : ''}
    </div>
  </div>

  ${(p.sebi_entities || []).length > 1 ? `<div class="card" style="margin-top:16px">
    <div class="card-title">Registered entities under this brand</div>
    <p class="xs faint" style="margin-top:4px">A single consumer brand often operates through more than one registered
    company. All registrations matched to ${esc(p.brand)}:</p>
    <div class="table-scroll" style="margin-top:8px"><table class="data">
      <thead><tr><th>Legal entity</th><th>Registration</th><th>Register</th><th>Validity</th></tr></thead>
      <tbody>${p.sebi_entities.map((e) => `<tr>
        <td>${esc(e.legal_name)}</td>
        <td class="num">${esc(e.reg_no)}</td>
        <td class="small">${(e.categories || []).map((x) => esc(x.replace(/_/g, ' '))).join(', ')}</td>
        <td class="small">${esc(e.validity || '—')}</td>
      </tr>`).join('')}</tbody>
    </table></div>
  </div>` : ''}

  <div class="grid g-main" style="margin-top:16px">
    <div class="card">
      <div class="card-head"><div>
        <div class="card-title">Investor complaints</div>
        <div class="xs faint">SEBI-mandated monthly disclosure ${provDot(b.provenance?.complaints)}</div>
      </div></div>
      ${k.available ? `
        <div class="grid g3" style="margin-bottom:12px">
          <div class="stat"><div class="stat-label">Received 12m</div><div class="stat-value sm">${full(k.received_12m)}</div></div>
          <div class="stat"><div class="stat-label">Resolved</div><div class="stat-value sm">${k.resolution_rate_pct?.toFixed(1) ?? '—'}%</div></div>
          <div class="stat"><div class="stat-label">Pending</div><div class="stat-value sm">${full(k.pending_latest)}</div></div>
        </div>
        <div class="chart-box"><canvas id="p-complaints"></canvas></div>
        <div class="legend" style="margin-top:8px">
          <span><i style="background:var(--c1)"></i>Received</span>
          <span><i style="background:var(--c2)"></i>Pending at month end</span>
        </div>`
        : `<div class="empty">No complaint disclosure ingested for this broker yet.</div>`}
    </div>

    <div class="stack">
      <div class="card">
        <div class="card-title">Reliability breakdown</div>
        <div class="chart-box" style="margin-top:8px"><canvas id="p-rel"></canvas></div>
        <div class="xs faint">Each component is 0–100. Weights: ${Object.entries(rel.weights || {})
          .map(([kk, v]) => `${esc(kk.replace(/_/g, ' '))} ${(v * 100).toFixed(0)}%`).join(' · ') || '—'}</div>
      </div>

      <div class="card">
        <div class="card-title">Cost of a standard month</div>
        ${cost.monthly_total != null ? `
          <div class="stat" style="margin-top:8px">
            <div class="stat-value">${inr(cost.monthly_total, { decimals: 0 })}</div>
            <div class="stat-sub">brokerage + AMC on the standard basket</div>
          </div>
          <dl class="kv" style="margin-top:12px">
            <dt>Delivery</dt><dd class="num">${inr(cost.delivery, { decimals: 0 })}</dd>
            <dt>Intraday</dt><dd class="num">${inr(cost.intraday, { decimals: 0 })}</dd>
            <dt>F&amp;O</dt><dd class="num">${inr(cost.fno, { decimals: 0 })}</dd>
            <dt>AMC (monthly)</dt><dd class="num">${inr(cost.amc_monthly, { decimals: 0 })}</dd>
          </dl>
          <div class="xs faint" style="margin-top:8px">${provDot(b.provenance?.charges)} Statutory charges excluded —
            identical at every broker. <a href="/methodology" data-link>Basket definition</a></div>`
          : `<p class="small muted" style="margin-top:8px">This broker has not published verified pricing here yet, so we
             show nothing rather than guess. Check the broker's own website for current charges.</p>`}
      </div>
    </div>
  </div>

  ${(flags.circulars || []).length ? `<div class="card" style="margin-top:16px">
    <div class="card-title">Exchange circulars naming this member</div>
    <p class="xs faint" style="margin-top:4px">Automatically matched from the NSE circular feed. Context matters — a
    mention is not by itself an adverse finding.</p>
    <table class="data" style="margin-top:8px"><tbody>
      ${flags.circulars.slice(0, 8).map((x) => `<tr>
        <td class="small nowrap faint">${esc(x.date || '')}</td>
        <td class="small">${esc(x.subject || '')}</td>
        <td>${safeUrl(x.url) ? `<a class="small" href="${safeUrl(x.url)}" rel="nofollow noopener external" target="_blank">PDF ↗</a>` : ''}</td>
      </tr>`).join('')}
    </tbody></table>
  </div>` : ''}

  <div class="grid g-main" style="margin-top:16px">
    <div class="card">
      <div class="card-title">Open an account with ${esc(p.brand)}</div>
      <p class="small muted" style="margin-top:6px">BrokerLens does not open accounts or forward your details to
      anyone. Account opening happens on the broker's own website, where their current charges and terms apply.</p>
      ${safeUrl(p.website) ? `<a class="btn btn-primary" style="margin-top:10px" href="${safeUrl(p.website)}"
        rel="nofollow noopener external" target="_blank">Visit ${esc(p.brand)} \u2197</a>` : ''}
      <p class="xs faint" style="margin-top:10px">Not a recommendation. Verify charges and registration status
      with the broker and with SEBI before opening an account.</p>
    </div>
    <div class="card">
      <div class="card-title">Closest comparable brokers</div>
      <table class="data" style="margin-top:8px"><tbody>
        ${(b.peers || []).map((x) => `<tr>
          <td><div class="bname">${mark(x.id, x.brand, 22)}<a href="/broker/${esc(x.id)}" data-link>${esc(x.brand)}</a></div></td>
          <td class="right num">${count(x.clients)}</td>
          <td class="right num">${x.reliability?.toFixed(1) ?? '—'}</td>
          <td class="right"><a class="small" href="/compare?b=${esc(p.id)},${esc(x.id)}" data-link>vs</a></td>
        </tr>`).join('') || '<tr><td class="empty">No peers computed.</td></tr>'}
      </tbody></table>
    </div>
  </div>`;
}

/* =========================================================== COMPARE */

export async function compare(params) {
  const o = await loadOverview();
  const ids = (params?.get('b') || '').split(',').map((s) => s.trim()).filter(Boolean).slice(0, 4);
  const loaded = await Promise.all(ids.map((id) => loadBroker(id).catch(() => null)));
  const list = loaded.filter(Boolean);

  onMount(() => {
    const sel = document.getElementById('cmp-add');
    if (sel) sel.addEventListener('change', () => {
      const next = [...ids, sel.value].filter(Boolean).slice(0, 4);
      history.pushState({}, '', `/compare?b=${next.join(',')}`);
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    document.querySelectorAll('[data-remove]').forEach((btn) => btn.addEventListener('click', () => {
      const next = ids.filter((x) => x !== btn.dataset.remove);
      history.pushState({}, '', next.length ? `/compare?b=${next.join(',')}` : '/compare');
      window.dispatchEvent(new PopStateEvent('popstate'));
    }));
    const c = document.getElementById('cmp-chart');
    if (c && list.length) {
      const draw = () => lineChart(c, list.map((b) => ({ label: b.profile.brand, data: b.clients.series })),
        { height: 260, fmtY: (v) => count(v), fmtTip: (v) => full(v) });
      draw(); registerRedraw(draw);
    }
  });

  const opts = (o.brokers || [])
    .filter((b) => !ids.includes(b.id))
    .sort((a, b) => (b.clients || 0) - (a.clients || 0))
    .map((b) => `<option value="${esc(b.id)}">${esc(b.brand)}</option>`).join('');

  if (!list.length) {
    return `<h1 style="margin-top:16px">Compare brokers</h1>
      <p class="muted">Pick two to four brokers to see them side by side on clients, growth, complaints, reliability and cost.</p>
      <div class="card" style="max-width:420px;margin-top:16px">
        <label for="cmp-add">Add a broker</label>
        <select id="cmp-add"><option value="">Select…</option>${opts}</select>
      </div>`;
  }

  const rows = [
    ['Active clients', (b) => count(b.clients.active_clients), 'num'],
    ['Market share', (b) => pct(b.clients.market_share_pct, { sign: false }), 'num'],
    ['12-month growth', (b) => `<span class="${cls(b.clients.yoy_pct)}">${pct(b.clients.yoy_pct)}</span>`, 'num'],
    ['Clients added 12m', (b) => count(b.clients.net_adds_12m), 'num'],
    ['Complaints /10k clients', (b) => b.complaints.per_10k_clients_12m?.toFixed(2) ?? '—', 'num'],
    ['Complaint resolution', (b) => b.complaints.resolution_rate_pct != null ? b.complaints.resolution_rate_pct.toFixed(1) + '%' : '—', 'num'],
    ['Reliability score', (b) => b.reliability.score?.toFixed(1) ?? '—', 'num'],
    ['Cost / month (basket)', (b) => b.cost?.monthly_total != null ? inr(b.cost.monthly_total, { decimals: 0 }) : '<span class="faint">unverified</span>', 'num'],
    ['Delivery brokerage', (b) => b.charges?.delivery ? fmtPlan(b.charges.delivery) : '<span class="faint">—</span>', ''],
    ['Intraday brokerage', (b) => b.charges?.intraday ? fmtPlan(b.charges.intraday) : '<span class="faint">—</span>', ''],
    ['F&O brokerage', (b) => b.charges?.fno ? fmtPlan(b.charges.fno) : '<span class="faint">—</span>', ''],
    ['Demat AMC / year', (b) => b.charges?.demat_amc_annual != null ? inr(b.charges.demat_amc_annual, { decimals: 0 }) : '<span class="faint">—</span>', 'num'],
    ['Type', (b) => esc(TYPE_LABEL[b.profile.type] || b.profile.type || '—'), ''],
    ['Head office', (b) => esc(b.profile.sebi_city || b.profile.hq || '—'), ''],
    ['Founded', (b) => b.profile.founded ?? '—', 'num'],
    ['SEBI registration', (b) => b.profile.sebi_reg_no ? `<span class="num">${esc(b.profile.sebi_reg_no)}</span>` : '<span class="badge badge-warn">unmatched</span>', ''],
    ['Segments', (b) => (b.profile.segments || []).length, 'num'],
    ['On SEBI defaulter list', (b) => b.regulatory_flags?.defaulter ? '<span class="down">Yes</span>' : 'No', ''],
  ];

  return `
  ${sampleBanner(o.metadata)}
  <div class="spread" style="margin-top:16px">
    <h1>Comparing ${list.length} broker${list.length > 1 ? 's' : ''}</h1>
    ${list.length < 4 ? `<div style="min-width:200px"><select id="cmp-add"><option value="">Add a broker…</option>${opts}</select></div>` : ''}
  </div>

  <div class="table-scroll" style="margin-top:16px">
    <table class="data">
      <thead><tr><th style="min-width:170px">Metric</th>
        ${list.map((b) => `<th class="right"><div class="row" style="justify-content:flex-end;gap:6px">
          ${mark(b.profile.id, b.profile.brand, 22)}
          <a href="/broker/${esc(b.profile.id)}" data-link>${esc(b.profile.brand)}</a>
          <button class="chip" data-remove="${esc(b.profile.id)}" title="Remove">×</button>
        </div></th>`).join('')}
      </tr></thead>
      <tbody>
        ${rows.map(([label, fn, klass]) => `<tr>
          <td class="muted small">${esc(label)}</td>
          ${list.map((b) => `<td class="right ${klass}">${fn(b)}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
  </div>

  <div class="card" style="margin-top:16px">
    <div class="card-title">Active clients over time</div>
    <div class="chart-box"><canvas id="cmp-chart"></canvas></div>
    <div class="legend" style="margin-top:8px">
      ${list.map((b, i) => `<span><i style="background:var(--c${(i % 8) + 1})"></i>${esc(b.profile.brand)}</span>`).join('')}
    </div>
  </div>`;
}

function fmtPlan(plan) {
  if (!plan) return '—';
  const bits = [];
  if (plan.flat_per_order != null) bits.push(plan.flat_per_order === 0 ? 'Free' : `₹${plan.flat_per_order}/order`);
  if (plan.pct_of_turnover != null) bits.push(`${plan.pct_of_turnover}%`);
  if (plan.cap_per_order != null) bits.push(`max ₹${plan.cap_per_order}`);
  return esc(bits.join(', ') || '—');
}

/* =========================================================== LEADERBOARDS */

export async function leaderboards() {
  const o = await loadOverview();
  onMount(() => {
    (o.leaderboards || []).filter((bd) => (bd.rows || []).length).forEach((bd, i) => {
      const c = document.getElementById(`lb-${i}`);
      if (!c) return;
      const draw = () => barChart(c, bd.rows.slice(0, 10).map((r) => ({ label: r.brand, value: r.value })),
        { height: Math.max(160, bd.rows.slice(0, 10).length * 26), fmt: (v) => fmtBoard(bd, v), labelW: 112 });
      draw(); registerRedraw(draw);
    });
  });

  return `
  ${sampleBanner(o.metadata)}
  <h1 style="margin-top:16px">Rankings</h1>
  <p class="muted" style="max-width:64ch">Every ranking states the metric it sorts on and where that metric comes from.
  We do not publish an overall "best broker" — that depends on what you trade.</p>

  ${!(o.leaderboards || []).some((bd) => (bd.rows || []).length)
    ? `<div style="margin-top:16px">${pending('Rankings',
        'Every ranking here sorts on active clients, complaint records or published charges. Those come from NSE and SEBI monthly disclosures, which are being brought in from the primary sources now.')}</div>`
    : ''}
  ${(o.leaderboards || []).filter((bd) => (bd.rows || []).length).map((bd, i) => `
    <div class="card" style="margin-top:16px">
      <div class="card-head">
        <div>
          <h3>${esc(bd.title)}</h3>
          ${bd.note ? `<p class="xs faint" style="margin-top:4px;max-width:70ch">${esc(bd.note)}</p>` : ''}
        </div>
        <span class="badge">${esc(bd.unit || '')}</span>
      </div>
      <div class="grid g-main">
        <div class="chart-box"><canvas id="lb-${i}"></canvas></div>
        <table class="data"><tbody>
          ${bd.rows.slice(0, 10).map((r) => `<tr>
            <td class="rank-cell">${r.rank}</td>
            <td><a href="/broker/${esc(r.id)}" data-link>${esc(r.brand)}</a></td>
            <td class="right num">${fmtBoard(bd, r.value)}</td>
          </tr>`).join('')}
        </tbody></table>
      </div>
    </div>`).join('')}`;
}

/* =========================================================== CALCULATOR */

export async function calculator(params) {
  const o = await loadOverview();
  const priced = (o.brokers || []).filter((b) => b.cost != null);

  // With no verified charges there is nothing to price. Showing an interactive
  // form that returns an empty table is worse than saying so.
  if (!priced.length) {
    return `<h1 style="margin-top:16px">Brokerage cost calculator</h1>
      <p class="muted" style="max-width:70ch">Work out what a month of your actual trading costs at each broker.</p>
      <div style="margin-top:16px">${pending('Broker charges',
        'Charges are published only where they can be traced to the broker\'s own disclosed rate card. Until those are verified, we show nothing rather than an estimate you might act on.')}</div>
      <p class="small muted" style="margin-top:16px">In the meantime, the
      <a href="/brokers" data-link>broker directory</a> and the
      <a href="/registry" data-link>SEBI register</a> carry regulator-sourced facts on every firm.</p>`;
  }

  onMount(() => {
    const form = document.getElementById('calc-form');
    const out = document.getElementById('calc-out');
    if (!form) return;

    const compute = async () => {
      const v = Object.fromEntries(new FormData(form).entries());
      const basket = {
        delivery_buy_value: Number(v.delivery_value) || 0,
        delivery_trades: Number(v.delivery_trades) || 0,
        intraday_turnover: Number(v.intraday_turnover) || 0,
        intraday_trades: Number(v.intraday_trades) || 0,
        fno_premium_turnover: Number(v.fno_turnover) || 0,
        fno_trades: Number(v.fno_trades) || 0,
      };
      const full_ = await Promise.all(priced.map((b) => loadBroker(b.id).catch(() => null)));
      const rows = full_.filter(Boolean).map((b) => {
        const c = b.charges || {};
        const leg = (plan, turnover, trades) => {
          if (!plan || !trades) return 0;
          const per = plan.pct_of_turnover != null ? (turnover / trades) * plan.pct_of_turnover / 100 : 0;
          let v2 = plan.flat_per_order != null
            ? (plan.pct_of_turnover != null ? Math.max(per, plan.flat_per_order) : plan.flat_per_order)
            : per;
          if (plan.cap_per_order != null) v2 = Math.min(v2, plan.cap_per_order);
          return v2 * trades;
        };
        const total = leg(c.delivery, basket.delivery_buy_value, basket.delivery_trades)
          + leg(c.intraday, basket.intraday_turnover, basket.intraday_trades)
          + leg(c.fno, basket.fno_premium_turnover, basket.fno_trades)
          + (c.demat_amc_annual || 0) / 12;
        return { id: b.profile.id, brand: b.profile.brand, total };
      }).sort((a, b) => a.total - b.total);

      out.innerHTML = rows.length ? `
        <div class="table-scroll"><table class="data">
          <thead><tr><th>#</th><th>Broker</th><th class="right">Your monthly cost</th><th class="right">Per year</th><th></th></tr></thead>
          <tbody>${rows.map((r, i) => `<tr>
            <td class="rank-cell">${i + 1}</td>
            <td><div class="bname">${mark(r.id, r.brand, 22)}<a href="/broker/${esc(r.id)}" data-link>${esc(r.brand)}</a></div></td>
            <td class="right num">${inr(r.total, { decimals: 0 })}</td>
            <td class="right num">${inr(r.total * 12, { decimals: 0 })}</td>
            <td class="right"><div class="minibar"><i style="width:${(r.total / rows[rows.length - 1].total * 100).toFixed(0)}%"></i></div></td>
          </tr>`).join('')}</tbody>
        </table></div>
        <p class="xs faint" style="margin-top:10px">Brokerage plus amortised AMC only. Statutory charges are excluded
        because they are identical at every broker for the same trade. Only brokers with verified published pricing
        appear — ${priced.length} of ${o.metadata.broker_count} today.</p>`
        : `<div class="empty">No broker has verified pricing on file yet.</div>`;
      runAfter();
    };

    form.addEventListener('input', compute);
    form.addEventListener('submit', (e) => { e.preventDefault(); compute(); });
    compute();
  });

  return `
  <h1 style="margin-top:16px">What will a broker actually cost you?</h1>
  <p class="muted" style="max-width:64ch">Enter a typical month of your own trading. We price it against every broker
  that has published verified charges, cheapest first.</p>

  <div class="grid g-main" style="margin-top:16px">
    <form class="card" id="calc-form">
      <div class="card-title">Your typical month</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="field"><label for="dv">Delivery buy value (₹)</label><input id="dv" name="delivery_value" type="number" min="0" step="1000" value="50000"></div>
        <div class="field"><label for="dt">Delivery orders</label><input id="dt" name="delivery_trades" type="number" min="0" value="4"></div>
        <div class="field"><label for="it">Intraday turnover (₹)</label><input id="it" name="intraday_turnover" type="number" min="0" step="10000" value="100000"></div>
        <div class="field"><label for="itr">Intraday orders</label><input id="itr" name="intraday_trades" type="number" min="0" value="10"></div>
        <div class="field"><label for="ft">F&amp;O premium turnover (₹)</label><input id="ft" name="fno_turnover" type="number" min="0" step="10000" value="200000"></div>
        <div class="field"><label for="ftr">F&amp;O orders</label><input id="ftr" name="fno_trades" type="number" min="0" value="10"></div>
      </div>
      <button class="btn btn-primary" type="submit" style="margin-top:12px">Recalculate</button>
    </form>
    <div id="calc-out"></div>
  </div>`;
}

/* =========================================================== SEBI REGISTRY */

const regState = { q: '', page: 0, per: 60 };

export async function registry() {
  const r = await loadRegistry();
  const o = await loadOverview();

  onMount(() => {
    const render = () => {
      const q = regState.q.trim().toLowerCase();
      const rows = (r.entities || []).filter((e) =>
        !q || `${e.name} ${e.reg || ''} ${e.city || ''}`.toLowerCase().includes(q));
      const start = regState.page * regState.per;
      const page = rows.slice(start, start + regState.per);
      document.getElementById('reg-body').innerHTML = page.length ? page.map((e) => `<tr>
        <td>${e.slug ? `<a href="/sebi-registry/${esc(e.slug)}/">${esc(e.name)}</a>` : esc(e.name)}${e.trade_name ? `<div class="xs faint">trading as ${esc(e.trade_name)}</div>` : ''}</td>
        <td class="num small">${esc(e.reg || '—')}</td>
        <td class="small">${esc(e.city || '—')}</td>
        <td class="xs muted">${(e.exchanges || []).slice(0, 3).map(esc).join(' · ')}${(e.exchanges || []).length > 3 ? ` +${e.exchanges.length - 3}` : ''}</td>
        <td class="small">${esc(e.validity || '—')}</td>
      </tr>`).join('') : `<tr><td colspan="5" class="empty">Nothing matches “${esc(regState.q)}”.</td></tr>`;
      document.getElementById('reg-meta').textContent =
        `${rows.length.toLocaleString('en-IN')} entities · showing ${rows.length ? start + 1 : 0}–${Math.min(start + regState.per, rows.length)}`;
      document.getElementById('reg-prev').disabled = regState.page === 0;
      document.getElementById('reg-next').disabled = start + regState.per >= rows.length;
    };
    document.getElementById('reg-q').addEventListener('input', (e) => { regState.q = e.target.value; regState.page = 0; render(); });
    document.getElementById('reg-prev').addEventListener('click', () => { regState.page = Math.max(0, regState.page - 1); render(); });
    document.getElementById('reg-next').addEventListener('click', () => { regState.page++; render(); });
    render();
  });

  return `
  <h1 style="margin-top:16px">SEBI-registered intermediaries</h1>
  <p class="muted" style="max-width:70ch">Every registered entity we hold that is not one of the
  ${o.metadata.broker_count} brokers tracked in depth — ${count(r.count)} of them. Straight from SEBI's register:
  legal name, registration number, city, exchange memberships and validity. Nothing here is curated or scored.</p>

  <div class="card" style="margin-top:16px">
    <div class="row-wrap">
      <div class="grow" style="min-width:240px">
        <input type="search" id="reg-q" placeholder="Search by name, registration number or city…">
      </div>
      <span class="small faint" id="reg-meta"></span>
      <button class="btn btn-sm" id="reg-prev">← Prev</button>
      <button class="btn btn-sm" id="reg-next">Next →</button>
    </div>
  </div>

  <div class="table-scroll" style="margin-top:16px">
    <table class="data">
      <thead><tr><th>Legal entity</th><th>Registration</th><th>City</th><th>Exchanges / registers</th><th>Validity</th></tr></thead>
      <tbody id="reg-body"></tbody>
    </table>
  </div>
  <p class="xs faint" style="margin-top:10px">${provDot('sebi_registry')} Source: SEBI recognised-intermediary register,
  pulled ${esc((r.generated_at || '').slice(0, 10))}. <a href="/sources" data-link>Lineage →</a></p>`;
}

/* =========================================================== ALGO PLATFORMS */

const algoState = { q: '', cat: 'all' };

const PRICING_LABEL = {
  free: 'Free', freemium: 'Freemium', subscription: 'Subscription',
  'per-seat licence': 'Per-seat licence', 'enterprise licence': 'Enterprise licence',
};

function algoCard(p) {
  const site = safeUrl(p.website);
  const works = (p.works_with || []).map((b) =>
    `<a class="badge" href="/broker/${esc(b.id)}" data-link title="Executes through ${esc(b.brand)} — view broker profile">${esc(b.brand)}</a>`).join(' ');
  return `<div class="card" style="display:flex;flex-direction:column;gap:8px">
    <div class="row">
      ${mark(p.id, p.name, 30)}
      <div class="grow">
        <div style="font-weight:600">${site ? `<a href="${safeUrl(p.website)}" target="_blank" rel="noopener nofollow">${esc(p.name)}</a>` : esc(p.name)}</div>
        <div class="xs muted">${esc(p.operator || '')}${p.hq ? ` · ${esc(p.hq)}` : ''}</div>
      </div>
      ${p.pricing ? `<span class="badge">${esc(PRICING_LABEL[p.pricing] || p.pricing)}</span>` : ''}
    </div>
    <p class="small" style="margin:0">${esc(p.summary || '')}</p>
    ${works ? `<div class="row-wrap xs"><span class="faint">Executes via:</span> ${works}</div>` : ''}
  </div>`;
}

export async function algo(params) {
  const a = await loadAlgo();
  const cats = a.categories || {};
  const catKeys = Object.keys(cats);
  if (params?.get('cat') && catKeys.includes(params.get('cat'))) algoState.cat = params.get('cat');

  onMount(() => {
    const render = () => {
      const q = algoState.q.trim().toLowerCase();
      const rows = (a.platforms || []).filter((p) =>
        (algoState.cat === 'all' || p.category === algoState.cat)
        && (!q || `${p.name} ${p.operator || ''} ${p.hq || ''} ${p.summary || ''} ${
          (p.works_with || []).map((b) => b.brand).join(' ')}`.toLowerCase().includes(q)));
      const groups = catKeys
        .filter((k) => rows.some((p) => p.category === k))
        .map((k) => `
          <section style="margin-top:20px">
            <h2 style="margin-bottom:2px">${esc(cats[k].label || k)}</h2>
            <p class="small muted" style="max-width:75ch;margin-top:2px">${esc(cats[k].blurb || '')}</p>
            <div class="grid g3" style="margin-top:10px">${rows.filter((p) => p.category === k).map(algoCard).join('')}</div>
          </section>`).join('');
      document.getElementById('algo-list').innerHTML =
        groups || `<div class="empty" style="margin-top:20px"><h2>Nothing matches</h2>
          <p class="muted small">No platform matches “${esc(algoState.q)}” in this category.</p></div>`;
      document.getElementById('algo-meta').textContent = `${rows.length} of ${a.count} platforms`;
      document.querySelectorAll('[data-algo-cat]').forEach((btn) =>
        btn.classList.toggle('btn-primary', btn.dataset.algoCat === algoState.cat));
    };
    document.getElementById('algo-q').addEventListener('input', (e) => { algoState.q = e.target.value; render(); });
    document.querySelectorAll('[data-algo-cat]').forEach((btn) =>
      btn.addEventListener('click', () => { algoState.cat = btn.dataset.algoCat; render(); }));
    render();
  });

  return `
  <h1 style="margin-top:16px">Algo trading platforms in India</h1>
  <p class="muted" style="max-width:75ch">The execution and automation layer around the brokers we track:
  official broker APIs, no-code strategy builders, backtesting tools and the institutional vendors behind
  broker dealing desks. Platform details are curated and verified against each platform's own material —
  not regulator filings — so treat them as a directory, not an endorsement.</p>

  <div class="banner" style="margin-top:14px">
    <span>§</span>
    <div><strong>SEBI's retail algo framework (February 2025).</strong>
    SEBI has brought retail algo trading inside a formal perimeter: brokers remain responsible for every
    algo order, API access requires authentication with static-IP whitelisting, orders above an exchange-set
    rate threshold need an exchange-issued algo ID, and algo providers must be empanelled with the exchanges.
    Strategies split into <em>white-box</em> (logic disclosed) and <em>black-box</em> (undisclosed — the provider
    needs a Research Analyst registration and audit trail). Implementation timelines have moved; check the
    latest SEBI and exchange circulars before relying on any platform's compliance claims.</div>
  </div>

  <div class="card" style="margin-top:14px">
    <div class="row-wrap">
      <div class="grow" style="min-width:220px">
        <input type="search" id="algo-q" placeholder="Search platforms, operators or connected brokers…">
      </div>
      <button class="btn btn-sm" data-algo-cat="all">All</button>
      ${catKeys.map((k) => `<button class="btn btn-sm" data-algo-cat="${esc(k)}">${esc(cats[k].label || k)}</button>`).join('')}
      <span class="small faint" id="algo-meta"></span>
    </div>
  </div>

  <div id="algo-list"></div>

  <p class="xs faint" style="margin-top:10px">${provDot('curated')} Curated directory, last reviewed
  ${esc((a.last_reviewed || a.generated_at || '').slice(0, 10))}. Pricing models are indicative; integrations
  change frequently. Nothing here is investment advice or a recommendation of any platform.</p>`;
}

/* =========================================================== METHODOLOGY */

export async function methodology() {
  return `
  <h1 style="margin-top:16px">Methodology</h1>
  <p class="muted" style="max-width:70ch">Every number here should be checkable. This page states where each figure
  comes from, how derived metrics are calculated, and what we deliberately do not do.</p>

  <div class="section-title"><h2>Where the data comes from</h2></div>
  <div class="grid g2">
    <div class="card"><div class="card-title">Regulator-sourced ${provDot('sebi_registry')}</div>
      <ul class="small" style="padding-left:18px;margin-top:8px">
        <li>Legal entity names and SEBI registration numbers — SEBI recognised-intermediary register</li>
        <li>Exchange memberships and registration validity — same register</li>
        <li>Depository-participant licences — SEBI CDSL and NSDL registers</li>
        <li>Defaulter / expelled status — SEBI defaulter list</li>
        <li>Circulars naming a member — NSE circular feed</li>
      </ul></div>
    <div class="card"><div class="card-title">Market context ${provDot('nse')}</div>
      <ul class="small" style="padding-left:18px;margin-top:8px">
        <li>Index levels and market breadth — NSE</li>
        <li>Institutional flows — NSE FII/DII report</li>
        <li>Cash-market turnover — NSE bhavcopy</li>
        <li>Delivery percentage — BSE scrip-wise gross delivery archive</li>
        <li>Corporate actions — BSE</li>
      </ul></div>
  </div>

  <div class="section-title"><h2>Derived metrics</h2></div>
  <div class="stack">
    <div class="card">
      <h4>Market share</h4>
      <p class="small muted">A broker's active clients divided by the total across all tracked brokers, for the same
      month. It is share of the tracked set, not of every broker in India — smaller firms outside the tracked set are
      not in the denominator.</p>
    </div>
    <div class="card">
      <h4>Complaints per 10,000 clients</h4>
      <p class="small muted">Complaints received over 12 months ÷ active clients × 10,000. Normalising matters: a large
      broker will always show more raw complaints than a small one, which tells you nothing on its own.</p>
    </div>
    <div class="card">
      <h4>Reliability score (0–100)</h4>
      <p class="small muted">A weighted composite, disclosed in full: complaint rate percentile against peers (40%),
      resolution rate (20%), regulatory flags (20%), complaint backlog in months of current inflow (10%), and years
      since founding (10%). Missing components are dropped and remaining weights renormalised, so a broker is not
      penalised for a dataset we have not ingested — instead the profile shows lower confidence. It is arithmetic over
      public disclosures, not an opinion, and it is not a recommendation.</p>
    </div>
    <div class="card">
      <h4>Cost of a standard month</h4>
      <p class="small muted">Brokerage on a fixed basket — ₹50,000 of delivery across 4 orders, ₹1,00,000 of intraday
      turnover across 10 orders, ₹2,00,000 of F&amp;O premium turnover across 10 orders — plus demat AMC divided by
      twelve. Statutory charges (STT, stamp duty, exchange transaction charges, SEBI turnover fees, GST) are excluded
      because they are identical at every broker for an identical trade; including them would compress the differences
      that actually depend on your choice of broker. Use the
      <a href="/calculator" data-link>calculator</a> to price your own pattern instead.</p>
    </div>
  </div>

  <div class="section-title"><h2>What we do not do</h2></div>
  <div class="card">
    <ul class="small" style="padding-left:18px">
      <li>We do not name a single "best broker". It depends entirely on what and how much you trade.</li>
      <li>We do not give investment advice, and we are not a SEBI-registered adviser or research analyst.</li>
      <li>We do not scrape competitor comparison sites. Every figure traces to a primary exchange or regulator source.</li>
      <li>We do not let paid placement move a broker up a factual ranking.</li>
      <li>We do not invent a number to fill a gap. Missing data shows as "—" or "unverified".</li>
    </ul>
  </div>`;
}

/* =========================================================== SOURCES */

export async function sources() {
  const s = await loadSources();
  const groups = {};
  (s.sources || []).forEach((x) => { (groups[x.publisher] = groups[x.publisher] || []).push(x); });

  return `
  <h1 style="margin-top:16px">Sources &amp; data lineage</h1>
  <p class="muted" style="max-width:70ch">Every source the pipeline touches, when it last ran and what came back.
  Published so that anyone can audit a figure back to its origin.</p>

  ${Object.entries(groups).map(([pub, rows]) => `
    <div class="section-title"><h2>${esc(pub)}</h2></div>
    <div class="table-scroll"><table class="data">
      <thead><tr><th>Dataset</th><th>Cadence</th><th>Last run</th><th>Status</th><th>Notes</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td><div style="font-weight:560">${esc(r.title)}</div>
          <div class="xs faint" style="word-break:break-all">${esc(r.url || '')}</div></td>
        <td class="small">${esc(r.cadence || '—')}</td>
        <td class="small nowrap">${esc((r.last_run || '—').slice(0, 16).replace('T', ' '))}</td>
        <td>${statusBadge(r.last_status)}</td>
        <td class="xs muted">${esc(r.notes || '')}</td>
      </tr>`).join('')}</tbody>
    </table></div>`).join('')}

  <div class="section-title"><h2>Licensing position</h2></div>
  <div class="card">
    <dl class="kv">
      ${Object.entries(s.licensing || {}).map(([k, v]) =>
        `<dt>${esc(k.toUpperCase())}</dt><dd class="small muted">${esc(v)}</dd>`).join('')}
    </dl>
  </div>`;
}

function statusBadge(st) {
  if (!st) return '<span class="badge">not run</span>';
  if (st === 'ok') return '<span class="badge badge-up">ok</span>';
  if (st === 'empty') return '<span class="badge badge-warn">empty</span>';
  return `<span class="badge badge-down" title="${esc(st)}">error</span>`;
}

/* =========================================================== 404 */

export function notFound(msg) {
  return `<div class="empty" style="padding-top:80px">
    <h1>Not found</h1>
    <p class="muted">${msg || 'That page does not exist.'}</p>
    <a class="btn btn-primary" href="/" data-link style="margin-top:12px">Back to the market overview</a>
  </div>`;
}
