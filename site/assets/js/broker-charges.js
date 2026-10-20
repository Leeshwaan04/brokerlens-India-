/* Per-broker charges calculator (/broker/<id>/charges/).
 *
 * CSP here is script-src 'self' with no unsafe-inline, so the page ships no inline
 * script: every rate this file uses is read from data-attributes on the
 * [data-broker-charges] element, which the build writes from the same fee schedule
 * and statutory constants as the worked-example tables.
 *
 * compute() mirrors pipeline/broker_charges_engine.py compute_charges() step for
 * step (same rounding to paise per component, same brokerage rule). Keep the two in
 * sync; tests/qa_extra_brokerpages.py runs both and compares them.
 */
(function () {
  'use strict';

  var ROWS = [
    ['brokerage', 'Brokerage (buy and sell orders)'],
    ['stt', 'Securities transaction tax (STT)'],
    ['exchange_charges', 'Exchange transaction charges (NSE)'],
    ['sebi_charges', 'SEBI turnover fee'],
    ['stamp_duty', 'Stamp duty (buy side)'],
    ['gst', 'GST on brokerage, exchange and SEBI charges'],
    ['dp_charge', 'Depository participant (DP) charge']
  ];

  // Round to paise like Python's round(x, 2): correctly rounded on the exact value of
  // the double, ties to even. toFixed rounds exact ties up, and an exact tie only
  // happens when x is an odd multiple of 1/8 (0.125, 0.375, ...), so handle those.
  function r2(x) {
    var eighths = x * 8;
    if (eighths === Math.floor(eighths) && eighths % 2 !== 0) {
      var floor = Math.floor(x * 100);
      return (floor % 2 === 0 ? floor : floor + 1) / 100;
    }
    return parseFloat(x.toFixed(2));
  }

  function legBrokerage(value, flat, pct) {
    if (!(value > 0)) return 0;
    if (flat === 0 && pct === 0) return 0;
    var pctCost = value * pct;
    return pctCost > 0 ? Math.min(flat, pctCost) : flat;
  }

  function compute(cfg, buy, sell, segment) {
    var delivery = segment === 'delivery';
    var flat = delivery ? cfg.deliveryFlat : cfg.intradayFlat;
    var pct = delivery ? cfg.deliveryPct : cfg.intradayPct;
    var turnover = buy + sell;
    var brokerage = r2(legBrokerage(buy, flat, pct) + legBrokerage(sell, flat, pct));
    var stt = delivery ? r2(turnover * cfg.sttDelivery) : r2(sell * cfg.sttIntradaySell);
    var exchange = r2(turnover * cfg.nse);
    var sebi = r2(turnover * cfg.sebi);
    if (turnover > 0 && sebi < 0.01) sebi = 0.01;
    var stamp = r2(buy * (delivery ? cfg.stampDelivery : cfg.stampIntraday));
    var gst = r2((brokerage + exchange + sebi) * cfg.gst);
    var dp = delivery && sell > 0 ? cfg.dpCharge : 0;
    var total = r2(brokerage + stt + exchange + sebi + stamp + gst + dp);
    return {
      brokerage: brokerage, stt: stt, exchange_charges: exchange, sebi_charges: sebi,
      stamp_duty: stamp, gst: gst, dp_charge: dp, total: total
    };
  }

  function readConfig(el) {
    function n(name) { return parseFloat(el.getAttribute('data-' + name)); }
    var cfg = {
      deliveryFlat: n('delivery-flat'), deliveryPct: n('delivery-pct'),
      intradayFlat: n('intraday-flat'), intradayPct: n('intraday-pct'),
      dpCharge: n('dp-charge'), sttDelivery: n('stt-delivery'), sttIntradaySell: n('stt-intraday-sell'),
      nse: n('nse'), sebi: n('sebi'), gst: n('gst'),
      stampDelivery: n('stamp-delivery'), stampIntraday: n('stamp-intraday')
    };
    for (var k in cfg) { if (!isFinite(cfg[k])) return null; }
    return cfg;
  }

  function fmt(x) {
    return x.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function render(res, segment) {
    var rows = '';
    for (var i = 0; i < ROWS.length; i++) {
      var key = ROWS[i][0];
      if (key === 'dp_charge' && segment !== 'delivery') continue;
      rows += '<tr><th scope="row">' + ROWS[i][1] + '</th><td class="right num">Rs ' + fmt(res[key]) + '</td></tr>';
    }
    rows += '<tr class="total"><th scope="row">Total charges</th><td class="right num"><strong>Rs ' +
      fmt(res.total) + '</strong></td></tr>';
    return '<div class="table-scroll"><table class="data"><thead><tr><th>Charge</th>' +
      '<th class="right">Amount</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function init() {
    var el = document.querySelector('[data-broker-charges]');
    if (!el) return;
    var cfg = readConfig(el);
    if (!cfg) return;
    var seg = document.getElementById('bc-segment');
    var buy = document.getElementById('bc-buy');
    var sell = document.getElementById('bc-sell');
    var out = document.getElementById('bc-out');
    var btn = document.getElementById('bc-run');
    var note = el.querySelector('p.xs');
    if (!seg || !buy || !sell || !out) return;

    function run() {
      var b = parseFloat(buy.value);
      var s = parseFloat(sell.value);
      if (!isFinite(b) || b < 0) b = 0;
      if (!isFinite(s) || s < 0) s = 0;
      var segment = seg.value === 'intraday' ? 'intraday' : 'delivery';
      out.innerHTML = render(compute(cfg, b, s, segment), segment);
      if (note) {
        note.textContent = 'Shown for a Rs ' + b.toLocaleString('en-IN') + ' buy and a Rs ' +
          s.toLocaleString('en-IN') + ' sell as equity ' + segment + '. Change the values and press Calculate; ' +
          'the sums run in your browser.';
      }
    }

    if (btn) btn.addEventListener('click', run);
    seg.addEventListener('change', run);
    buy.addEventListener('input', run);
    sell.addEventListener('input', run);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { compute: compute, r2: r2 };
  }
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})();
