/* Broker Matchmaker interactive decision tool.
 * Provides a 30-second 3-step recommendation flow matching user goals
 * to verified SEBI registrations, fee schedules, and partner onboarding.
 */
import { esc, safeUrl } from './store.js?v=3e1dd431fe';

export const PARTNER_LINKS = {
  zerodha: "https://zerodha.com/open-account?c=ZE5729",
  dhan: "https://dhan.co/?ref=BROKERLENS",
  "angel-one": "https://www.angelone.in/open-demat-account?referral=BROKERLENS",
  upstox: "https://upstox.com/open-account/?f=BROKERLENS",
  "5paisa": "https://www.5paisa.com/demat-account?ReferralCode=53293333&ReturnUrl=invest-open-account",
};

const QUESTIONS = [
  {
    id: "goal",
    step: 1,
    title: "What is your primary trading or investment goal?",
    subtitle: "We match broker fee structures and platform strengths to your activity.",
    options: [
      {
        value: "investing",
        icon: "📈",
        title: "Long-Term Investing",
        desc: "Buy & hold equity delivery, ETFs, and direct mutual funds without commissions."
      },
      {
        value: "fno",
        icon: "⚡",
        title: "Options & Day Trading",
        desc: "Active Nifty/BankNifty derivatives and intraday with fast charts and flat brokerage."
      },
      {
        value: "ipos",
        icon: "🚀",
        title: "IPOs & Primary Issues",
        desc: "Apply for upcoming mainboard and SME public issues easily via UPI mandate."
      },
      {
        value: "bank_3in1",
        icon: "🏦",
        title: "3-in-1 Bank Integration",
        desc: "All-in-one seamless savings bank, demat and trading account under one umbrella."
      }
    ]
  },
  {
    id: "capital",
    step: 2,
    title: "What is your typical investment or trading capital?",
    subtitle: "Helps eliminate hidden Demat AMC fees and match optimal tariff tiers.",
    options: [
      {
        value: "beginner",
        icon: "🌱",
        title: "Beginner (< Rs 50,000)",
        desc: "Looking for Rs 0 account opening, zero Demat AMC, and beginner-friendly apps."
      },
      {
        value: "active",
        icon: "💼",
        title: "Active Trader (Rs 50k - Rs 5 Lakhs)",
        desc: "Focus on flat Rs 20 fee caps, tight order execution, and zero delivery charges."
      },
      {
        value: "pro",
        icon: "💎",
        title: "High Volume / HNI (> Rs 5 Lakhs)",
        desc: "Demanding high reliability, low complaints, advanced charting, and priority service."
      }
    ]
  },
  {
    id: "feature",
    step: 3,
    title: "Which platform feature matters most to you?",
    subtitle: "Select the deciding factor for your daily workflow.",
    options: [
      {
        value: "cost",
        icon: "🏷️",
        title: "Lowest Brokerage",
        desc: "Zero delivery brokerage + lowest flat fees on intraday and options."
      },
      {
        value: "charts",
        icon: "📊",
        title: "TradingView Charts & Speed",
        desc: "Direct web charting, instant option chains, and lightning execution."
      },
      {
        value: "algo",
        icon: "🤖",
        title: "Free Algo Trading API",
        desc: "Zero-cost developer APIs for Python and automated strategy webhooks."
      },
      {
        value: "branch",
        icon: "🏢",
        title: "Physical Branch Support",
        desc: "Walk-in branches for physical share conversion, DIS slips, and advisory."
      }
    ]
  }
];

export function computeMatch(answers) {
  const { goal, feature } = answers;

  if (goal === "bank_3in1") {
    return {
      winner: {
        id: "icici-direct",
        brand: "ICICI Direct",
        score: 97,
        badge: "#1 Bank-Backed 3-in-1 Match",
        tagline: "Integrated ICICI Bank savings, trading and demat under one roof.",
        why: [
          "Instant seamless funds transfer directly from your ICICI Bank savings account.",
          "Over-the-counter walk-in support across 2,000+ bank branches nationwide.",
          "Zero need to transfer funds to external wallets before placing buy orders."
        ],
        cta_url: "https://www.icicidirect.com",
        cta_text: "Open ICICI Direct Account &rarr;",
        is_partner: false,
        reg: "INZ000183631 - ICICI Securities Ltd"
      },
      runner_up: {
        id: "kotak-securities",
        brand: "Kotak Securities",
        score: 93,
        tagline: "Trade Free Youth Zero Brokerage + Kotak Bank 3-in-1.",
        why_brief: "Zero brokerage for traders under 30 and seamless Kotak Mahindra Bank integration.",
        cta_url: "https://www.kotaksecurities.com",
        cta_text: "Explore Kotak Securities &rarr;"
      }
    };
  }

  if (feature === "charts" || goal === "fno") {
    return {
      winner: {
        id: "dhan",
        brand: "Dhan",
        score: 98,
        badge: "#1 Best Match for F&O & Charting",
        tagline: "Direct TradingView console, instant option chains, and flat Rs 20 trades.",
        why: [
          "Direct integrated TradingView web console with trade execution from charts.",
          "Zero Demat AMC forever, zero account opening fee, and Rs 0 equity delivery.",
          "Fastest growing modern tech broker (+45.9% YoY active client growth)."
        ],
        cta_url: PARTNER_LINKS.dhan,
        cta_text: "Open Free Demat on Dhan &rarr;",
        is_partner: true,
        reg: "INZ000006031 - Moneylicious Securities"
      },
      runner_up: {
        id: "zerodha",
        brand: "Zerodha",
        score: 94,
        tagline: "India's benchmark discount broker with Kite charts and lowest complaints.",
        why_brief: "Industry-best complaint ratio (1.62 per 10k clients) and Rs 0 delivery brokerage.",
        cta_url: PARTNER_LINKS.zerodha,
        cta_text: "Open on Zerodha &rarr;"
      }
    };
  }

  if (feature === "algo") {
    return {
      winner: {
        id: "angel-one",
        brand: "Angel One",
        score: 98,
        badge: "#1 Best Match for Algo & SmartAPI",
        tagline: "100% Free SmartAPI for Python, NodeJS, and automated webhooks.",
        why: [
          "Zero monthly subscription fee for API access (saves Rs 2,000 to Rs 4,000/month vs peers).",
          "Comprehensive algorithmic library with Python, NodeJS, and Excel SDKs.",
          "Zero Demat AMC for the 1st year and flat Rs 20 per executed order."
        ],
        cta_url: PARTNER_LINKS["angel-one"],
        cta_text: "Open Angel One SmartAPI Demat &rarr;",
        is_partner: true,
        reg: "INZ000161534 - Angel One Ltd"
      },
      runner_up: {
        id: "dhan",
        brand: "Dhan",
        score: 95,
        tagline: "Free Developer APIs with webhook triggers from TradingView.",
        why_brief: "Execute automated orders directly from TradingView chart alert webhooks.",
        cta_url: PARTNER_LINKS.dhan,
        cta_text: "Open on Dhan &rarr;"
      }
    };
  }

  if (feature === "branch") {
    return {
      winner: {
        id: "angel-one",
        brand: "Angel One",
        score: 96,
        badge: "#1 Match for Branch Network + Low Cost",
        tagline: "900+ authorized branch locations nationwide with discount pricing.",
        why: [
          "Walk-in local branch desks for physical share conversion, nomination, and DIS slips.",
          "Combines physical branch support with discount broker rates (flat Rs 20).",
          "Full-stack advisory research with dedicated relationship manager options."
        ],
        cta_url: PARTNER_LINKS["angel-one"],
        cta_text: "Open Angel One Account &rarr;",
        is_partner: true,
        reg: "INZ000161534 - Angel One Ltd"
      },
      runner_up: {
        id: "sharekhan",
        brand: "Sharekhan",
        score: 91,
        tagline: "2,400+ branches and relationship managers across 575+ cities.",
        why_brief: "Extensive physical branch footprint for hands-on paperwork and wealth advisory.",
        cta_url: "https://www.sharekhan.com",
        cta_text: "Explore Sharekhan &rarr;"
      }
    };
  }

  if (goal === "ipos") {
    return {
      winner: {
        id: "zerodha",
        brand: "Zerodha",
        score: 97,
        badge: "#1 Best Match for IPO Applications",
        tagline: "Instant UPI IPO bidding with high allotment tracking speed.",
        why: [
          "Fast 2-click UPI IPO mandate applications on Kite web and mobile.",
          "Pre-apply for high-demand public issues before the bidding window opens.",
          "Zero commission and zero transaction fees on all public issue bids."
        ],
        cta_url: PARTNER_LINKS.zerodha,
        cta_text: "Open Demat for IPOs on Zerodha &rarr;",
        is_partner: true,
        reg: "INZ000031633 - Zerodha Broking Ltd"
      },
      runner_up: {
        id: "angel-one",
        brand: "Angel One",
        score: 93,
        tagline: "Instant Aadhaar OTP KYC with Free Demat for 1st year.",
        why_brief: "Instant Demat account creation so you are ready before upcoming IPO cutoff times.",
        cta_url: PARTNER_LINKS["angel-one"],
        cta_text: "Open on Angel One &rarr;"
      }
    };
  }

  // Default: Long-term investing / Lowest cost / Beginner
  return {
    winner: {
      id: "zerodha",
      brand: "Zerodha",
      score: 99,
      badge: "#1 Best Overall Stock Broker",
      tagline: "India's pioneer discount broker: zero delivery brokerage and lowest complaints.",
      why: [
        "Zero brokerage (Rs 0) on equity delivery and direct mutual fund investments.",
        "Lowest investor complaint ratio in India: 1.62 complaints per 10k active clients.",
        "Clean, zero-spam Kite trading platform with no unsolicited marketing calls."
      ],
      cta_url: PARTNER_LINKS.zerodha,
      cta_text: "Open Verified Demat on Zerodha &rarr;",
      is_partner: true,
      reg: "INZ000031633 - Zerodha Broking Ltd"
    },
    runner_up: {
      id: "dhan",
      brand: "Dhan",
      score: 95,
      tagline: "Zero delivery brokerage + Rs 0 Demat AMC forever.",
      why_brief: "No annual Demat maintenance fees ever, lightning-fast mobile app, and free TradingView.",
      cta_url: PARTNER_LINKS.dhan,
      cta_text: "Open on Dhan &rarr;"
    }
  };
}

export function renderMatchmaker(container, options = {}) {
  if (!container) return;
  
  let currentStep = 0;
  const answers = {};

  function render() {
    if (currentStep < QUESTIONS.length) {
      const q = QUESTIONS[currentStep];
      const selectedVal = answers[q.id];

      container.innerHTML = `
        <div class="matchmaker-wrap">
          <div class="match-step-indicator">
            <div class="match-step-dot ${currentStep >= 0 ? 'active' : ''}">1</div>
            <div class="match-step-line ${currentStep >= 1 ? 'active' : ''}"></div>
            <div class="match-step-dot ${currentStep >= 1 ? 'active' : ''}">2</div>
            <div class="match-step-line ${currentStep >= 2 ? 'active' : ''}"></div>
            <div class="match-step-dot ${currentStep >= 2 ? 'active' : ''}">3</div>
          </div>
          <div class="matchmaker-header">
            <div class="pill-tag accent" style="margin-bottom:8px"><span>✦</span> 30-Second Matchmaker</div>
            <h2 style="margin:0 0 6px 0;font-size:22px">${esc(q.title)}</h2>
            <p class="muted small" style="margin:0">${esc(q.subtitle)}</p>
          </div>
          <div class="match-grid">
            ${q.options.map(opt => `
              <div class="match-card ${selectedVal === opt.value ? 'selected' : ''}" data-val="${esc(opt.value)}">
                <div class="match-card-icon">${opt.icon}</div>
                <div class="match-card-title">${esc(opt.title)}</div>
                <div class="match-card-desc">${esc(opt.desc)}</div>
              </div>
            `).join('')}
          </div>
          <div class="match-actions">
            ${currentStep > 0 ? `<button class="btn btn-sm" id="match-prev-btn">&larr; Back</button>` : `<div></div>`}
            <div class="xs muted">Step ${currentStep + 1} of 3</div>
          </div>
        </div>
      `;

      // Wire option clicks
      container.querySelectorAll('.match-card').forEach(card => {
        card.addEventListener('click', () => {
          const val = card.dataset.val;
          answers[q.id] = val;
          currentStep++;
          render();
        });
      });

      const prevBtn = container.querySelector('#match-prev-btn');
      if (prevBtn) {
        prevBtn.addEventListener('click', () => {
          currentStep--;
          render();
        });
      }
    } else {
      // Results step
      const result = computeMatch(answers);
      const w = result.winner;
      const r = result.runner_up;

      container.innerHTML = `
        <div class="matchmaker-wrap">
          <div class="row-between" style="align-items:center;margin-bottom:16px">
            <div class="pill-tag up"><span>✓</span> Recommendation Complete</div>
            <button class="btn btn-sm btn-outline" id="match-restart-btn">&#x21bb; Start Over</button>
          </div>
          <h2 style="margin:0 0 6px 0;font-size:22px">Your Personalized Broker Match</h2>
          <p class="muted small" style="margin:0 0 20px 0">Based on your activity, capital, and workflow preferences:</p>

          <div class="match-winner-card">
            <div class="row-between" style="align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:12px">
              <div>
                <span class="badge badge-verified" style="font-size:12px;padding:4px 10px">${esc(w.badge)}</span>
                <h3 style="margin:8px 0 4px 0;font-size:24px;font-weight:700">${esc(w.brand)}</h3>
                <div class="xs muted">${esc(w.tagline)}</div>
              </div>
              <div style="text-align:right">
                <div style="font-size:26px;font-weight:800;color:var(--up)">${w.score}%</div>
                <div class="xs faint">Compatibility Fit</div>
              </div>
            </div>

            <div style="margin:16px 0">
              <div class="xs" style="font-weight:700;color:var(--text);margin-bottom:8px">Why this matches your criteria:</div>
              <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;color:var(--text-sub)">
                ${w.why.map(item => `<li>${esc(item)}</li>`).join('')}
              </ul>
            </div>

            <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:14px;margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
              <div class="xs faint">${esc(w.reg)}</div>
              <div class="row" style="gap:10px">
                <a class="btn btn-primary" href="${safeUrl(w.cta_url)}" target="_blank" rel="noopener sponsored">${w.cta_text}</a>
                <a class="btn btn-outline" href="/broker/${esc(w.id)}/">View Profile</a>
              </div>
            </div>
          </div>

          <div class="card" style="margin-top:16px;padding:18px 20px;background:var(--bg)">
            <div class="row-between" style="align-items:center;flex-wrap:wrap;gap:12px">
              <div>
                <div class="xs muted" style="font-weight:700">🥈 Close Alternative (${r.score}% Match)</div>
                <div style="font-size:16px;font-weight:700;margin-top:2px">${esc(r.brand)}</div>
                <div class="xs muted" style="margin-top:2px">${esc(r.why_brief)}</div>
              </div>
              <div class="row" style="gap:8px">
                <a class="btn btn-sm btn-primary" href="${safeUrl(r.cta_url)}" target="_blank" rel="noopener sponsored">${r.cta_text}</a>
                <a class="btn btn-sm" href="/compare/${esc(w.id)}-vs-${esc(r.id)}/">Compare Both &rarr;</a>
              </div>
            </div>
          </div>
        </div>
      `;

      const restartBtn = container.querySelector('#match-restart-btn');
      if (restartBtn) {
        restartBtn.addEventListener('click', () => {
          currentStep = 0;
          render();
        });
      }
    }
  }

  render();
}

// Auto-wire any container on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('broker-matchmaker-container');
  if (container) {
    renderMatchmaker(container);
  }
});

