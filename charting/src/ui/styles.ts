// Scoped styles for the studio. Colours come from the host page's CSS variables
// (the same names exist on brokerlens.in and paper.brokerlens.in), with fallbacks.
const CSS = `
.blc{--blc-bg:var(--bg-raised,#fff);--blc-text:var(--text,#111827);--blc-muted:var(--text-muted,#6b7280);--blc-border:var(--border,#e5e7eb);--blc-accent:var(--accent,#2f4a8f);color:var(--blc-text);font-size:13px}
.blc *{box-sizing:border-box}
.blc-note{margin:0;padding:24px 8px;color:var(--blc-muted);text-align:center}
.blc-hud{display:flex;flex-wrap:wrap;gap:4px 14px;min-height:20px;margin:0 0 8px;color:var(--blc-muted);font-variant-numeric:tabular-nums}
.blc-hud strong{color:var(--blc-text);font-weight:600}
.blc-bars{display:flex;flex-direction:column;gap:6px;margin-bottom:8px}
.blc-row{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.blc-chips{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.blc-chip{white-space:nowrap;appearance:none;font:inherit;font-size:12px;line-height:1;padding:6px 9px;min-height:28px;border:1px solid var(--blc-border);border-radius:6px;background:transparent;color:var(--blc-muted);cursor:pointer}
.blc-chip:hover:not(:disabled){color:var(--blc-text);border-color:var(--blc-muted)}
.blc-chip[aria-pressed="true"]{background:var(--accent-soft,#eaeefa);border-color:var(--blc-accent);color:var(--accent-text,var(--blc-accent));font-weight:600}
.blc-chip:disabled{opacity:.4;cursor:not-allowed}
.blc-chip:focus-visible,.blc-input:focus-visible{outline:2px solid var(--blc-accent);outline-offset:2px}
.blc-target{display:inline-flex;gap:4px;align-items:center}
.blc-input{font:inherit;font-size:12px;width:104px;min-height:28px;padding:4px 8px;border:1px solid var(--blc-border);border-radius:6px;background:transparent;color:var(--blc-text)}
.blc-canvas{position:relative;width:100%;min-height:200px}
.blc-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.blc-table{margin-top:8px;color:var(--blc-muted);max-width:100%;overflow-x:auto}
.blc-table summary{cursor:pointer}
.blc-table table{width:100%;min-width:420px;white-space:nowrap;border-collapse:collapse;margin-top:6px;font-variant-numeric:tabular-nums}
.blc-table th,.blc-table td{padding:4px 6px;text-align:right;border-bottom:1px solid var(--blc-border)}
.blc-table th:first-child,.blc-table td:first-child{text-align:left}
.blc-expanded{position:fixed;inset:0;z-index:1000;padding:16px;overflow:auto;background:var(--blc-bg)}
@media (max-width:560px){.blc-chip{padding:7px 9px;min-height:32px}.blc-input{width:88px}}
`;

export function injectStyles(): void {
  if (document.getElementById("blc-styles")) return;
  const s = document.createElement("style");
  s.id = "blc-styles";
  s.textContent = CSS;
  document.head.append(s);
}
