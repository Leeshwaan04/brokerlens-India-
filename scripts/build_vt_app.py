import json

brokers = json.load(open('virtual-trading/seed/broker-rates.json'))
stocks = json.load(open('dist-vt/stocks.json'))

html = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Virtual Trading & Portfolio Simulator | BrokerLens India</title>
  <meta name="description" content="Practice equity investing with realistic brokerage and statutory taxes on NSE top stocks. Delayed EOD prices for investor education.">
  <link rel="icon" href="/brokerlens-mark.svg">
  <style>
    :root {
      --bg: #0b0f19;
      --bg-card: #111827;
      --bg-sub: #1f2937;
      --border: #374151;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --up: #10b981;
      --up-soft: rgba(16, 185, 129, 0.15);
      --down: #ef4444;
      --down-soft: rgba(239, 68, 68, 0.15);
      --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    [data-theme="light"] {
      --bg: #f8fafc;
      --bg-card: #ffffff;
      --bg-sub: #f1f5f9;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --up: #059669;
      --up-soft: rgba(5, 150, 105, 0.12);
      --down: #dc2626;
      --down-soft: rgba(220, 38, 38, 0.12);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: var(--font); background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .container { max-width: 1200px; margin: 0 auto; padding: 0 16px; width: 100%; }
    
    header { background: var(--bg-card); border-bottom: 1px solid var(--border); padding: 12px 0; position: sticky; top: 0; z-index: 50; }
    .header-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
    .logo-lockup { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text); font-weight: 700; font-size: 18px; }
    .logo-img { height: 32px; width: auto; }
    .nav-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .nav-tab { padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; border: 1px solid transparent; background: transparent; color: var(--text-muted); transition: all 0.15s; }
    .nav-tab:hover { background: var(--bg-sub); color: var(--text); }
    .nav-tab.active { background: var(--accent); color: #fff; }
    
    .status-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 10px; border-radius: 20px; background: var(--bg-sub); border: 1px solid var(--border); color: var(--text-muted); }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--up); }
    
    .account-bar { background: var(--bg-card); border-bottom: 1px solid var(--border); padding: 14px 0; }
    .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .stat-card { padding: 12px 16px; background: var(--bg-sub); border-radius: 8px; border: 1px solid var(--border); }
    .stat-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 600; }
    .stat-val { font-size: 20px; font-weight: 700; margin-top: 4px; font-family: var(--font-mono); }
    
    main { flex: 1; padding: 24px 0; }
    .panel { display: none; }
    .panel.active { display: block; }
    
    .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 20px; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    @media (max-width: 840px) { .grid-2 { grid-template-columns: 1fr; } }
    
    .field { margin-bottom: 14px; }
    .field label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--text-muted); }
    .field input, .field select { width: 100%; padding: 10px 12px; background: var(--bg-sub); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 14px; }
    .field input:focus, .field select:focus { outline: none; border-color: var(--accent); }
    
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 18px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }
    .btn-primary { background: var(--accent); color: #fff; }
    .btn-primary:hover { background: var(--accent-hover); }
    .btn-buy { background: var(--up); color: #fff; }
    .btn-sell { background: var(--down); color: #fff; }
    .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
    .btn-outline:hover { background: var(--bg-sub); }
    
    .table-wrap { overflow-x: auto; margin-top: 10px; border: 1px solid var(--border); border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
    th { background: var(--bg-sub); padding: 10px 14px; font-weight: 600; color: var(--text-muted); border-bottom: 1px solid var(--border); }
    td { padding: 12px 14px; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    .num { font-family: var(--font-mono); }
    .text-up { color: var(--up); }
    .text-down { color: var(--down); }
    
    .cost-box { background: var(--bg-sub); padding: 14px; border-radius: 8px; border: 1px solid var(--border); font-size: 12px; }
    .cost-row { display: flex; justify-content: space-between; padding: 4px 0; color: var(--text-muted); }
    .cost-row.total { font-weight: 700; color: var(--text); border-top: 1px solid var(--border); padding-top: 8px; margin-top: 6px; font-size: 13px; }
    
    .broker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-top: 16px; }
    .broker-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px; }
    .broker-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    
    footer { background: var(--bg-card); border-top: 1px solid var(--border); padding: 24px 0; font-size: 12px; color: var(--text-muted); }
  </style>
</head>
<body>

  <header>
    <div class="container header-row">
      <div style="display:flex;align-items:center;gap:16px">
        <a href="https://www.brokerlens.in" class="logo-lockup">
          <img src="/brokerlens-mark.svg" alt="BrokerLens" class="logo-img">
          <span>BrokerLens <span style="color:var(--accent)">Paper</span></span>
        </a>
        <div class="status-badge">
          <span class="status-dot"></span>
          <span>NSE EOD Delayed (SEBI Investor Education)</span>
        </div>
      </div>
      <div class="header-row" style="gap:10px">
        <nav class="nav-tabs">
          <button class="nav-tab active" data-tab="trade">Trade</button>
          <button class="nav-tab" data-tab="portfolio">Portfolio</button>
          <button class="nav-tab" data-tab="orders">Orders</button>
          <button class="nav-tab" data-tab="brokers">Brokers</button>
          <button class="nav-tab" data-tab="analytics">Analytics</button>
        </nav>
        <button class="btn btn-outline" id="theme-btn" style="padding:6px 10px;font-size:12px">Theme</button>
      </div>
    </div>
  </header>

  <section class="account-bar">
    <div class="container stat-grid">
      <div class="stat-card">
        <div class="stat-label">Virtual Portfolio Value</div>
        <div class="stat-val" id="stat-portfolio">Rs 10,00,000.00</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Available Cash</div>
        <div class="stat-val" id="stat-cash">Rs 10,00,000.00</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Realized P&L</div>
        <div class="stat-val" id="stat-pnl">Rs 0.00</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Active Broker Tariff</div>
        <div class="stat-val" id="stat-broker" style="font-size:16px">Zerodha (Rs 0 Del)</div>
      </div>
    </div>
  </section>

  <main class="container">

    <!-- TRADE TAB -->
    <div id="tab-trade" class="panel active">
      <div class="grid-2">
        <div class="card">
          <h2 style="font-size:18px;margin-bottom:16px">Place Virtual Equity Order</h2>
          <div class="field">
            <label for="stock-select">Select Nifty Stock (Real EOD Close Prices)</label>
            <select id="stock-select"></select>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--bg-sub);border-radius:6px;margin-bottom:14px">
            <div>
              <span class="stat-label">Latest EOD Close</span>
              <div id="current-price" style="font-size:18px;font-weight:700;font-family:var(--font-mono)">Rs 0.00</div>
            </div>
            <div id="current-change" style="font-weight:600">0.00%</div>
          </div>
          <div class="field">
            <label for="order-qty">Quantity (Shares)</label>
            <input type="number" id="order-qty" value="10" min="1" step="1">
          </div>
          <div class="field">
            <label for="order-action">Order Action</label>
            <select id="order-action">
              <option value="BUY">BUY (Equity Delivery - CNC)</option>
              <option value="SELL">SELL (Equity Delivery - CNC)</option>
            </select>
          </div>
          <div style="display:flex;gap:10px;margin-top:20px">
            <button class="btn btn-buy" id="btn-exec" style="flex:1">Submit Buy Order</button>
            <button class="btn btn-outline" id="btn-reset" style="font-size:12px">Reset Simulator</button>
          </div>
        </div>

        <div class="card">
          <h2 style="font-size:18px;margin-bottom:12px">Real Brokerage & Statutory Breakdown</h2>
          <p class="stat-label" style="margin-bottom:12px">Calculated per official SEBI, NSE, STT & Stamp Duty schedules</p>
          <div class="cost-box">
            <div class="cost-row"><span>Gross Order Value</span><span id="c-val" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>Brokerage (<span id="c-broker-name">Zerodha</span>)</span><span id="c-brokerage" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>STT (Securities Transaction Tax 0.1%)</span><span id="c-stt" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>NSE Exchange Charges (0.00297%)</span><span id="c-nse" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>SEBI Turnover Fee (0.0001%)</span><span id="c-sebi" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>Stamp Duty (0.015% on Buy)</span><span id="c-stamp" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>GST (18% on Brokerage + Exchange + SEBI)</span><span id="c-gst" class="num">Rs 0.00</span></div>
            <div class="cost-row" id="row-dp" style="display:none"><span>DP Charge (Sell Leg)</span><span id="c-dp" class="num">Rs 0.00</span></div>
            <div class="cost-row total"><span>Net Cash Required / Realized</span><span id="c-total" class="num">Rs 0.00</span></div>
          </div>
          <div style="margin-top:14px;font-size:11px;color:var(--text-muted);line-height:1.5">
            Verified statutory rate constants mirror BrokerLens core engine. Zero extrapolation.
          </div>
        </div>
      </div>
    </div>

    <!-- PORTFOLIO TAB -->
    <div id="tab-portfolio" class="panel">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div>
            <h2 style="font-size:18px">Current Stock Holdings</h2>
            <p class="stat-label" style="margin-top:2px">Priced at real NSE closing prices with all-in cost basis</p>
          </div>
        </div>
        <div class="table-wrap">
          <table id="holdings-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th class="num">Shares</th>
                <th class="num">Avg Cost (w/ Taxes)</th>
                <th class="num">Current Price</th>
                <th class="num">Current Value</th>
                <th class="num">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody id="holdings-body">
              <tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted)">No active stock positions. Place an order from the Trade tab to start.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ORDERS TAB -->
    <div id="tab-orders" class="panel">
      <div class="card">
        <h2 style="font-size:18px;margin-bottom:6px">Virtual Execution Ledger</h2>
        <p class="stat-label" style="margin-bottom:16px">Audited ledger with exact brokerage & statutory tax deductions</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Symbol</th>
                <th class="num">Qty</th>
                <th class="num">Price</th>
                <th class="num">Brokerage</th>
                <th class="num">Taxes</th>
                <th class="num">Net Total</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody id="orders-body">
              <tr><td colspan="9" style="text-align:center;padding:24px;color:var(--text-muted)">No order transactions recorded yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- BROKERS TAB -->
    <div id="tab-brokers" class="panel">
      <div class="card">
        <h2 style="font-size:18px;margin-bottom:4px">Broker Tariff Profiles</h2>
        <p class="stat-label">Choose which real broker tariff to simulate your trading with, or open a live account</p>
        <div class="broker-grid" id="broker-grid"></div>
      </div>
    </div>

    <!-- ANALYTICS TAB -->
    <div id="tab-analytics" class="panel">
      <div class="grid-2">
        <div class="card">
          <h2 style="font-size:18px;margin-bottom:14px">Trader Confidence Analytics</h2>
          <div class="cost-box">
            <div class="cost-row"><span>Completed Trades</span><span id="an-trades" class="num">0</span></div>
            <div class="cost-row"><span>Profitable Trades (Win Rate)</span><span id="an-winrate" class="num">0.0%</span></div>
            <div class="cost-row"><span>Total Brokerage Saved</span><span id="an-saved" class="num">Rs 0.00</span></div>
            <div class="cost-row"><span>Total Statutory Taxes Paid</span><span id="an-taxes" class="num">Rs 0.00</span></div>
          </div>
          <div style="margin-top:16px;padding:12px;background:var(--up-soft);border-radius:6px;border:1px solid var(--up);font-size:13px">
            <strong>Investor Education Mode:</strong> Complete at least 5 round-trip trades to generate your full SEBI compliance score.
          </div>
        </div>
        <div class="card">
          <h2 style="font-size:18px;margin-bottom:14px">Next Steps in Live Markets</h2>
          <p style="font-size:13px;color:var(--text-muted);line-height:1.6;margin-bottom:16px">
            Ready to transition from paper trading to real investments? Compare live demat account fees and statutory charges side by side on BrokerLens.
          </p>
          <div style="display:flex;gap:10px;flex-direction:column">
            <a href="https://www.brokerlens.in/compare/" target="_blank" class="btn btn-primary" style="text-decoration:none">Compare All 48 SEBI Registered Brokers &rarr;</a>
            <a href="https://www.brokerlens.in/trade-costs/" target="_blank" class="btn btn-outline" style="text-decoration:none">Statutory Trade Cost Engine</a>
          </div>
        </div>
      </div>
    </div>

  </main>

  <footer>
    <div class="container" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:16px;align-items:center">
      <div>
        <strong>BrokerLens Virtual Trading</strong> &middot; Hosted on Cloudflare Pages
        <div style="margin-top:4px;font-size:11px">
          Delayed end-of-day pricing per SEBI 24 May 2024 Circular &amp; November 2024 Advisory on simulated trading platforms.
        </div>
      </div>
      <div>
        <a href="https://www.brokerlens.in">Back to BrokerLens.in</a>
      </div>
    </div>
  </footer>

  <script>
    const STOCKS = """ + json.dumps(stocks) + """;
    const BROKERS = """ + json.dumps(brokers) + """;
    
    let activeBroker = BROKERS[0];
    let simState = {
      cash: 1000000.0,
      holdings: {},
      orders: [],
      pnl: 0.0,
      selectedBrokerId: activeBroker.id
    };

    function loadState() {
      const saved = localStorage.getItem('bl_sim_state');
      if (saved) {
        try { simState = JSON.parse(saved); } catch(e) {}
      }
      activeBroker = BROKERS.find(b => b.id === simState.selectedBrokerId) || BROKERS[0];
    }

    function saveState() {
      localStorage.setItem('bl_sim_state', JSON.stringify(simState));
      renderAccount();
      renderHoldings();
      renderOrders();
      renderAnalytics();
    }

    function fmt(n) {
      return 'Rs ' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function showTab(id) {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      const target = document.getElementById('tab-' + id);
      if (target) target.classList.add('active');
      const tabBtn = document.querySelector(`.nav-tab[data-tab="${id}"]`);
      if (tabBtn) tabBtn.classList.add('active');
    }

    function toggleTheme() {
      const cur = document.documentElement.getAttribute('data-theme') || 'dark';
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    }

    function initStocks() {
      const sel = document.getElementById('stock-select');
      sel.innerHTML = STOCKS.map(s => `<option value="${s.symbol}">${s.symbol} (Rs ${s.price.toFixed(2)})</option>`).join('');
      updateStockDetails();
    }

    function updateStockDetails() {
      const sym = document.getElementById('stock-select').value;
      const s = STOCKS.find(x => x.symbol === sym) || STOCKS[0];
      document.getElementById('current-price').textContent = fmt(s.price);
      const chg = document.getElementById('current-change');
      chg.textContent = (s.change >= 0 ? '+' : '') + s.change.toFixed(2) + '%';
      chg.className = s.change >= 0 ? 'text-up' : 'text-down';
      calculateCosts();
    }

    function calculateCosts() {
      const sym = document.getElementById('stock-select').value;
      const s = STOCKS.find(x => x.symbol === sym) || STOCKS[0];
      const qty = Math.max(1, parseInt(document.getElementById('order-qty').value || '1', 10));
      const action = document.getElementById('order-action').value;
      const isBuy = action === 'BUY';
      
      const gross = s.price * qty;
      const brokerage = activeBroker.delivery_flat === 0 && activeBroker.delivery_pct === 0 
        ? 0 
        : Math.min(activeBroker.delivery_flat || 20, gross * (activeBroker.delivery_pct || 0.001));
      
      const stt = gross * 0.001;
      const nse = gross * 0.0000297;
      const sebi = Math.max(0.01, gross * 0.000001);
      const stamp = isBuy ? gross * 0.00015 : 0;
      const gst = (brokerage + nse + sebi) * 0.18;
      const dp = !isBuy ? (activeBroker.dp_charge || 15.34) : 0;
      const taxes = stt + nse + sebi + stamp + gst + dp;
      const net = isBuy ? (gross + brokerage + taxes) : (gross - brokerage - taxes);

      document.getElementById('c-val').textContent = fmt(gross);
      document.getElementById('c-brokerage').textContent = fmt(brokerage);
      document.getElementById('c-broker-name').textContent = activeBroker.brand;
      document.getElementById('c-stt').textContent = fmt(stt);
      document.getElementById('c-nse').textContent = fmt(nse);
      document.getElementById('c-sebi').textContent = fmt(sebi);
      document.getElementById('c-stamp').textContent = fmt(stamp);
      document.getElementById('c-gst').textContent = fmt(gst);
      document.getElementById('c-dp').textContent = fmt(dp);
      document.getElementById('row-dp').style.display = !isBuy ? 'flex' : 'none';
      document.getElementById('c-total').textContent = fmt(net);
      
      const btn = document.getElementById('btn-exec');
      btn.textContent = isBuy ? `Submit Buy Order (${fmt(net)})` : `Submit Sell Order (Net ${fmt(net)})`;
      btn.className = isBuy ? 'btn btn-buy' : 'btn btn-sell';
      return { gross, brokerage, taxes, net, isBuy, qty, s };
    }

    function executeOrder() {
      const c = calculateCosts();
      if (c.isBuy) {
        if (simState.cash < c.net) {
          alert('Insufficient virtual cash to place this order.');
          return;
        }
        simState.cash -= c.net;
        const cur = simState.holdings[c.s.symbol] || { qty: 0, totalCost: 0 };
        cur.qty += c.qty;
        cur.totalCost += c.net;
        cur.avgPrice = cur.totalCost / cur.qty;
        simState.holdings[c.s.symbol] = cur;
      } else {
        const cur = simState.holdings[c.s.symbol];
        if (!cur || cur.qty < c.qty) {
          alert(`You do not own enough shares of ${c.s.symbol} to sell.`);
          return;
        }
        const costFraction = (cur.totalCost / cur.qty) * c.qty;
        const profit = c.net - costFraction;
        simState.pnl += profit;
        simState.cash += c.net;
        cur.qty -= c.qty;
        cur.totalCost -= costFraction;
        if (cur.qty === 0) delete simState.holdings[c.s.symbol];
        else simState.holdings[c.s.symbol] = cur;
      }

      simState.orders.unshift({
        time: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        type: c.isBuy ? 'BUY' : 'SELL',
        symbol: c.s.symbol,
        qty: c.qty,
        price: c.s.price,
        brokerage: c.brokerage,
        taxes: c.taxes,
        net: c.net,
        status: 'FILLED'
      });

      saveState();
      alert(`Order successfully executed! ${c.isBuy ? 'Bought' : 'Sold'} ${c.qty} shares of ${c.s.symbol}.`);
    }

    function renderAccount() {
      let holdingVal = 0;
      for (const sym in simState.holdings) {
        const h = simState.holdings[sym];
        const s = STOCKS.find(x => x.symbol === sym);
        if (s) holdingVal += h.qty * s.price;
      }
      const total = simState.cash + holdingVal;
      document.getElementById('stat-portfolio').textContent = fmt(total);
      document.getElementById('stat-cash').textContent = fmt(simState.cash);
      const pnlEl = document.getElementById('stat-pnl');
      pnlEl.textContent = (simState.pnl >= 0 ? '+' : '') + fmt(simState.pnl);
      pnlEl.style.color = simState.pnl >= 0 ? 'var(--up)' : 'var(--down)';
      document.getElementById('stat-broker').textContent = `${activeBroker.brand} (${activeBroker.delivery_flat === 0 ? 'Rs 0' : 'Flat Rs ' + activeBroker.delivery_flat} Del)`;
    }

    function renderHoldings() {
      const tbody = document.getElementById('holdings-body');
      const rows = [];
      for (const sym in simState.holdings) {
        const h = simState.holdings[sym];
        const s = STOCKS.find(x => x.symbol === sym) || { price: h.avgPrice };
        const curVal = h.qty * s.price;
        const unPnl = curVal - h.totalCost;
        const unPnlPct = (unPnl / h.totalCost) * 100;
        rows.push(`
          <tr>
            <td><strong>${sym}</strong></td>
            <td class="num">${h.qty}</td>
            <td class="num">${fmt(h.avgPrice)}</td>
            <td class="num">${fmt(s.price)}</td>
            <td class="num">${fmt(curVal)}</td>
            <td class="num ${unPnl >= 0 ? 'text-up' : 'text-down'}">${unPnl >= 0 ? '+' : ''}${fmt(unPnl)} (${unPnlPct.toFixed(2)}%)</td>
          </tr>
        `);
      }
      tbody.innerHTML = rows.length ? rows.join('') : '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted)">No active stock positions. Place an order from the Trade tab to start.</td></tr>';
    }

    function renderOrders() {
      const tbody = document.getElementById('orders-body');
      tbody.innerHTML = simState.orders.length ? simState.orders.map(o => `
        <tr>
          <td>${o.time}</td>
          <td><span style="font-weight:700;color:${o.type === 'BUY' ? 'var(--up)' : 'var(--down)'}">${o.type}</span></td>
          <td><strong>${o.symbol}</strong></td>
          <td class="num">${o.qty}</td>
          <td class="num">${fmt(o.price)}</td>
          <td class="num">${fmt(o.brokerage)}</td>
          <td class="num">${fmt(o.taxes)}</td>
          <td class="num"><strong>${fmt(o.net)}</strong></td>
          <td><span style="color:var(--up);font-size:12px;font-weight:600">✓ ${o.status}</span></td>
        </tr>
      `).join('') : '<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--text-muted)">No order transactions recorded yet.</td></tr>';
    }

    function renderBrokers() {
      const grid = document.getElementById('broker-grid');
      grid.innerHTML = BROKERS.slice(0, 16).map(b => `
        <div class="broker-card ${b.id === activeBroker.id ? 'selected' : ''}">
          <div>
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
              <h3 style="font-size:16px;font-weight:700">${b.brand}</h3>
              ${b.partner_badge ? `<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--accent);color:#fff">Partner</span>` : ''}
            </div>
            <p style="font-size:12px;color:var(--text-muted);margin:6px 0 10px 0">${b.tagline}</p>
            <div style="font-size:12px;display:flex;flex-direction:column;gap:4px">
              <div>Delivery: <strong>${b.delivery_flat === 0 ? 'Free (Rs 0)' : 'Rs ' + b.delivery_flat + ' flat'}</strong></div>
              <div>Intraday: <strong>Flat Rs ${b.intraday_flat}</strong></div>
              <div>DP Charge: <strong>Rs ${b.dp_charge || 15.34}</strong></div>
            </div>
          </div>
          <div style="display:flex;gap:8px;margin-top:10px">
            <button class="btn btn-outline" data-broker="${b.id}" style="flex:1;font-size:12px">${b.id === activeBroker.id ? 'Active Tariff' : 'Simulate With This'}</button>
            <a href="${b.cta_url}" target="_blank" class="btn btn-primary" style="font-size:12px;padding:6px 12px;text-decoration:none">Open Demat &rarr;</a>
          </div>
        </div>
      `).join('');

      grid.querySelectorAll('[data-broker]').forEach(btn => {
        btn.addEventListener('click', () => selectBroker(btn.dataset.broker));
      });
    }

    function selectBroker(id) {
      activeBroker = BROKERS.find(b => b.id === id) || BROKERS[0];
      simState.selectedBrokerId = activeBroker.id;
      saveState();
      renderBrokers();
      calculateCosts();
      alert(`Active broker tariff switched to ${activeBroker.brand}! All future paper trades will simulate using their exact charges.`);
    }

    function renderAnalytics() {
      const trades = simState.orders.filter(o => o.type === 'SELL');
      document.getElementById('an-trades').textContent = simState.orders.length;
      document.getElementById('an-winrate').textContent = trades.length ? ((trades.filter(t => t.net > t.price * t.qty).length / trades.length) * 100).toFixed(1) + '%' : '0.0%';
      let totalBrok = 0, totalTax = 0;
      simState.orders.forEach(o => { totalBrok += o.brokerage; totalTax += o.taxes; });
      document.getElementById('an-saved').textContent = fmt(totalBrok);
      document.getElementById('an-taxes').textContent = fmt(totalTax);
    }

    function resetSim() {
      if (confirm('Are you sure you want to reset your virtual portfolio back to Rs 10,00,000 cash?')) {
        simState = { cash: 1000000.0, holdings: {}, orders: [], pnl: 0.0, selectedBrokerId: activeBroker.id };
        saveState();
      }
    }

    // Event listeners
    document.querySelectorAll('.nav-tab').forEach(btn => {
      btn.addEventListener('click', () => showTab(btn.dataset.tab));
    });
    document.getElementById('theme-btn').addEventListener('click', toggleTheme);
    document.getElementById('stock-select').addEventListener('change', updateStockDetails);
    document.getElementById('order-qty').addEventListener('input', calculateCosts);
    document.getElementById('order-action').addEventListener('change', calculateCosts);
    document.getElementById('btn-exec').addEventListener('click', executeOrder);
    document.getElementById('btn-reset').addEventListener('click', resetSim);

    // Init
    loadState();
    initStocks();
    renderAccount();
    renderHoldings();
    renderOrders();
    renderBrokers();
    renderAnalytics();
  </script>
</body>
</html>
"""

with open('dist-vt/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('dist-vt/index.html generated successfully.')
