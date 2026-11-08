// Scoped styles (every class starts with tb-). Colours come from the host theme: Desktop's --ui-* tokens,
// the dashboard's --color-* tokens, else derived from the inherited text colour, so light and dark
// themes both work. The only fixed hues are the status colours (green/amber/red), each with a theme
// token first.
export const STYLES = `
.tb-root {
  --tb-fg: var(--ui-text-primary, var(--color-foreground, currentColor));
  --tb-fg2: var(--ui-text-secondary, var(--color-muted-foreground, color-mix(in srgb, currentColor 75%, transparent)));
  --tb-fg3: var(--ui-text-tertiary, var(--color-muted-foreground, color-mix(in srgb, currentColor 55%, transparent)));
  --tb-line: var(--ui-stroke-secondary, var(--color-border, color-mix(in srgb, currentColor 14%, transparent)));
  --tb-card: color-mix(in srgb, currentColor 3.5%, transparent);
  --tb-card-hi: color-mix(in srgb, currentColor 7%, transparent);
  --tb-accent: var(--ui-accent, var(--color-primary, #7c8cff));
  --tb-green: var(--ui-success, #2fae6f);
  --tb-amber: var(--ui-warning, #e0a12d);
  --tb-red: var(--ui-danger, var(--color-destructive, #e5544b));
  --tb-grey: color-mix(in srgb, currentColor 42%, transparent);
  --tb-radius: 14px;
  color: var(--tb-fg);
  font-size: 13.5px;
  line-height: 1.45;
  height: 100%;
  overflow: auto;
  container-type: inline-size;
}
.tb-root * { box-sizing: border-box; }
.tb-surface-dashboard { height: auto; overflow: visible; }

.tb-header {
  position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 14px 22px; border-bottom: 1px solid var(--tb-line);
  background: color-mix(in srgb, var(--background, var(--color-background, transparent)) 90%, transparent);
  backdrop-filter: blur(10px);
}
.tb-surface-dashboard .tb-header { position: static; background: transparent; padding: 4px 0 14px; }
.tb-brand { display: flex; align-items: center; gap: 10px; margin-right: 6px; }
.tb-logo {
  width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; color: var(--tb-accent);
  background: color-mix(in srgb, var(--tb-accent) 16%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tb-accent) 30%, transparent);
}
.tb-title { font-weight: 650; font-size: 15px; letter-spacing: -0.01em; }
.tb-tagline { font-size: 11.5px; color: var(--tb-fg3); }
.tb-tabs { display: flex; gap: 2px; padding: 3px; border-radius: 11px; background: var(--tb-card); border: 1px solid var(--tb-line); }
.tb-tab {
  all: unset; cursor: pointer; padding: 6px 12px; border-radius: 8px; font-size: 12.5px; color: var(--tb-fg2);
  transition: background .15s, color .15s;
}
.tb-tab:hover { color: var(--tb-fg); background: var(--tb-card); }
.tb-tab.tb-active { color: var(--tb-fg); background: var(--tb-card-hi); box-shadow: 0 1px 0 color-mix(in srgb, currentColor 8%, transparent); font-weight: 600; }
.tb-picker { margin-left: auto; }

.tb-main { padding: 20px 22px 40px; }
.tb-surface-dashboard .tb-main { padding: 6px 0 30px; }
.tb-page { display: flex; flex-direction: column; gap: 16px; max-width: 1380px; margin: 0 auto; }
.tb-hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; flex-wrap: wrap; }
.tb-hero h2 { margin: 0 0 4px; font-size: 22px; font-weight: 680; letter-spacing: -0.02em; }
.tb-hero p { margin: 0; color: var(--tb-fg2); max-width: 760px; }
.tb-hero-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.tb-section-title { margin: 8px 0 0; font-size: 14px; color: var(--tb-fg2); font-weight: 600; }

.tb-card {
  background: var(--tb-card); border: 1px solid var(--tb-line); border-radius: var(--tb-radius); padding: 16px;
  display: flex; flex-direction: column; gap: 10px; min-width: 0; position: relative;
}
.tb-card-flush { padding: 0; overflow: hidden; gap: 0; }
.tb-card-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.tb-card h3 { margin: 0; font-size: 14px; font-weight: 640; }
.tb-card h4 { margin: 8px 0 2px; font-size: 13px; font-weight: 620; display: flex; gap: 8px; align-items: center; }
.tb-muted { color: var(--tb-fg3); font-size: 12px; }
.tb-small { font-size: 12px; }
.tb-lead { margin: 0; font-size: 14.5px; line-height: 1.55; }
.tb-hint { margin: -4px 0 0; color: var(--tb-fg3); font-size: 12px; text-align: center; }
.tb-row { display: flex; align-items: center; }
.tb-wrap { flex-wrap: wrap; }
.tb-gap { gap: 10px; }
.tb-gap-sm { gap: 6px; }
.tb-two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.tb-two-tight { gap: 10px; }
.tb-split { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: 16px; }
.tb-split-single { grid-template-columns: minmax(0, 1fr); }
@container (max-width: 860px) {
  .tb-two, .tb-split { grid-template-columns: minmax(0, 1fr); }
  .tb-verdict { grid-template-columns: 1fr !important; }
}

.tb-chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-size: 11px;
  font-weight: 560; white-space: nowrap; background: var(--tb-card-hi); color: var(--tb-fg2);
  border: 1px solid var(--tb-line);
}
.tb-chip.tb-tone-green { color: var(--tb-green); background: color-mix(in srgb, var(--tb-green) 13%, transparent); border-color: color-mix(in srgb, var(--tb-green) 30%, transparent); }
.tb-chip.tb-tone-amber { color: var(--tb-amber); background: color-mix(in srgb, var(--tb-amber) 13%, transparent); border-color: color-mix(in srgb, var(--tb-amber) 30%, transparent); }
.tb-chip.tb-tone-red { color: var(--tb-red); background: color-mix(in srgb, var(--tb-red) 13%, transparent); border-color: color-mix(in srgb, var(--tb-red) 30%, transparent); }
.tb-chip.tb-tone-accent { color: var(--tb-accent); background: color-mix(in srgb, var(--tb-accent) 13%, transparent); border-color: color-mix(in srgb, var(--tb-accent) 30%, transparent); }
.tb-chip.tb-tone-grey { color: var(--tb-fg2); }
.tb-meta-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }

.tb-btn {
  display: inline-flex; align-items: center; gap: 7px; padding: 7px 13px; border-radius: 9px; font: inherit;
  font-size: 12.5px; font-weight: 580; cursor: pointer; color: var(--tb-fg); background: var(--tb-card-hi);
  border: 1px solid var(--tb-line); transition: transform .08s, background .15s, border-color .15s;
}
.tb-btn:hover:not(:disabled) { border-color: color-mix(in srgb, currentColor 30%, transparent); }
.tb-btn:active:not(:disabled) { transform: translateY(1px); }
.tb-btn:disabled { opacity: .55; cursor: default; }
.tb-btn-primary { background: var(--tb-accent); border-color: transparent;
  color: var(--ui-accent-foreground, var(--color-primary-foreground, #fff)); }
.tb-btn-primary:hover:not(:disabled) { filter: brightness(1.08); border-color: transparent; }
.tb-icon-btn { all: unset; cursor: pointer; width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; background: var(--tb-card-hi); font-size: 11px; }

.tb-input, .tb-select {
  font: inherit; font-size: 12.5px; color: var(--tb-fg); background: var(--tb-card); border: 1px solid var(--tb-line);
  border-radius: 8px; padding: 6px 9px; min-width: 0;
}
.tb-select option { color: initial; }
.tb-input:focus, .tb-select:focus { outline: 2px solid color-mix(in srgb, var(--tb-accent) 55%, transparent); outline-offset: 1px; }
.tb-input-sm { width: 140px; }
.tb-input-xs { width: 76px; }
.tb-select-sm { padding: 4px 6px; font-size: 12px; }
.tb-textarea { width: 100%; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.tb-field { display: flex; flex-direction: column; gap: 4px; font-size: 11.5px; color: var(--tb-fg3); }
.tb-toggle { display: inline-flex; gap: 6px; align-items: center; font-size: 12.5px; color: var(--tb-fg2); }

.tb-spinner {
  display: inline-block; width: 12px; height: 12px; border-radius: 50%; vertical-align: -2px;
  border: 2px solid color-mix(in srgb, currentColor 25%, transparent); border-top-color: currentColor;
  animation: tb-spin .8s linear infinite;
}
@keyframes tb-spin { to { transform: rotate(360deg); } }
.tb-empty { padding: 40px; text-align: center; color: var(--tb-fg3); }

/* Gallery */
.tb-grid-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }
.tb-robot-card { all: unset; cursor: pointer; padding: 0; overflow: hidden; gap: 0; transition: transform .15s, border-color .15s, box-shadow .15s; }
.tb-robot-card { background: var(--tb-card); border: 1px solid var(--tb-line); border-radius: var(--tb-radius); display: flex; flex-direction: column; }
.tb-robot-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--tb-accent) 45%, transparent);
  box-shadow: 0 10px 30px -18px color-mix(in srgb, var(--tb-accent) 60%, transparent); }
.tb-thumb { position: relative; aspect-ratio: 4 / 3; background: linear-gradient(160deg, #f4f5f7, #e3e6ea); overflow: hidden; }
.tb-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tb-thumb-ph { position: absolute; inset: 0; display: grid; place-items: center; font-size: 42px; font-weight: 700; color: #9aa3ad; }
.tb-thumb-tag { position: absolute; left: 10px; top: 10px; font-size: 10px; font-weight: 700; letter-spacing: .08em;
  padding: 2px 7px; border-radius: 6px; color: #384152; background: rgba(255,255,255,.82); }
.tb-robot-card-body { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 6px; }
.tb-robot-card-title { display: flex; justify-content: space-between; align-items: center; font-weight: 640; font-size: 14.5px; }
.tb-robot-card-role { margin: 2px 0 0; color: var(--tb-fg2); font-size: 12.5px; }
.tb-robot-card-headline { margin: 0; font-size: 12px; color: var(--tb-fg3); border-top: 1px dashed var(--tb-line); padding-top: 7px; }

/* 3D viewer */
.tb-viewer { position: relative; width: 100%; border-radius: var(--tb-radius); overflow: hidden;
  background: radial-gradient(120% 90% at 50% 15%, color-mix(in srgb, currentColor 6%, transparent), transparent 70%); }
.tb-card-flush .tb-viewer { border-radius: 0; }
.tb-viewer-canvas { position: absolute; inset: 0; }
.tb-viewer-canvas canvas { width: 100% !important; height: 100% !important; display: block; outline: none; }
.tb-viewer-tag { position: absolute; top: 10px; right: 10px; font-size: 10px; font-weight: 750; letter-spacing: .12em;
  padding: 3px 8px; border-radius: 6px; color: var(--tb-fg2); background: var(--tb-card-hi); border: 1px solid var(--tb-line);
  pointer-events: none; backdrop-filter: blur(6px); }
.tb-viewer-label { position: absolute; left: 12px; top: 10px; display: flex; flex-direction: column; gap: 1px; pointer-events: none;
  font-size: 12.5px; font-weight: 640; }
.tb-viewer-label small { font-weight: 500; font-size: 11.5px; color: var(--tb-fg3); }
.tb-viewer-label.tb-tone-green small { color: var(--tb-green); }
.tb-viewer-label.tb-tone-red small { color: var(--tb-red); }
.tb-viewer-reset { all: unset; cursor: pointer; position: absolute; right: 10px; bottom: 10px; width: 26px; height: 26px;
  display: grid; place-items: center; border-radius: 7px; background: var(--tb-card-hi); border: 1px solid var(--tb-line); color: var(--tb-fg2); }
.tb-viewer-error { position: absolute; inset: 0; display: grid; place-items: center; color: var(--tb-fg3); }
.tb-viewer-wait { display: grid; place-items: center; color: var(--tb-fg3); background: var(--tb-card); }
.tb-overlay-note { position: absolute; left: 12px; bottom: 56px; font-size: 12px; color: var(--tb-fg2); }
.tb-grid-views { display: grid; gap: 10px; }
.tb-views-1 { grid-template-columns: 1fr; }
.tb-views-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.tb-views-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
@container (max-width: 860px) { .tb-views-2, .tb-views-3 { grid-template-columns: 1fr; } }

.tb-timeline { display: flex; align-items: center; gap: 10px; padding: 10px 12px; }
.tb-card:not(.tb-card-flush) .tb-timeline { padding: 4px 0 0; }
.tb-scrub { position: relative; flex: 1; display: flex; align-items: center; }
.tb-scrub input { width: 100%; accent-color: var(--tb-accent); }
.tb-mark { position: absolute; top: -4px; width: 2px; height: 8px; background: var(--tb-red); border-radius: 1px; pointer-events: none; }
.tb-time { font-variant-numeric: tabular-nums; font-size: 11.5px; color: var(--tb-fg3); min-width: 92px; text-align: right; }

/* Photo */
.tb-photo { margin: 0; border-radius: var(--tb-radius); overflow: hidden; border: 1px solid var(--tb-line); position: relative; background: var(--tb-card); min-height: 240px; }
.tb-photo img { width: 100%; height: 100%; max-height: 480px; object-fit: cover; display: block; }
.tb-photo figcaption { position: absolute; left: 10px; bottom: 10px; display: flex; gap: 6px; align-items: center; font-size: 11.5px;
  color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,.6); }
.tb-photo-empty { display: grid; place-items: center; }

/* Lists and tables */
.tb-list { display: flex; flex-direction: column; }
.tb-list-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 9px 4px; border-top: 1px solid var(--tb-line); }
.tb-list-row:first-child { border-top: 0; }
.tb-list-row.tb-active { background: color-mix(in srgb, var(--tb-accent) 8%, transparent); border-radius: 8px; }
.tb-list-title { font-weight: 600; display: flex; gap: 6px; align-items: center; }
.tb-table-wrap { overflow-x: auto; }
.tb-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tb-table th { text-align: left; font-weight: 600; color: var(--tb-fg3); font-size: 11.5px; padding: 6px 8px; border-bottom: 1px solid var(--tb-line); white-space: nowrap; }
.tb-table td { padding: 6px 8px; border-bottom: 1px solid var(--tb-line); white-space: nowrap; }
.tb-table tr.tb-clickable { cursor: pointer; }
.tb-table tr.tb-clickable:hover td { background: var(--tb-card); }
.tb-table tr.tb-active td { background: color-mix(in srgb, var(--tb-accent) 9%, transparent); }
.tb-swatch { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 7px; vertical-align: -1px; box-shadow: inset 0 0 0 1px rgba(0,0,0,.15); }
.tb-delta { font-size: 11px; font-weight: 650; margin-left: 4px; color: var(--tb-fg3); }
.tb-delta.tb-up { color: var(--tb-green); }
.tb-delta.tb-down { color: var(--tb-red); }

/* Report tiles */
.tb-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(178px, 1fr)); gap: 10px; }
.tb-tile { all: unset; cursor: pointer; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 3px;
  border: 1px solid var(--tb-line); background: var(--tb-card); position: relative; overflow: hidden; transition: transform .12s, box-shadow .15s; }
.tb-tile::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--tb-grey); }
.tb-tile-green::before { background: var(--tb-green); }
.tb-tile-amber::before { background: var(--tb-amber); }
.tb-tile-red::before { background: var(--tb-red); }
.tb-tile-green { background: color-mix(in srgb, var(--tb-green) 7%, var(--tb-card)); }
.tb-tile-amber { background: color-mix(in srgb, var(--tb-amber) 8%, var(--tb-card)); }
.tb-tile-red { background: color-mix(in srgb, var(--tb-red) 8%, var(--tb-card)); }
.tb-tile:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 22px -16px currentColor; }
.tb-tile.tb-active { box-shadow: 0 0 0 2px var(--tb-accent); }
.tb-tile:disabled { cursor: default; }
.tb-tile-grey, .tb-tile-muted { color: var(--tb-fg2); }
.tb-tile-top { display: flex; justify-content: space-between; align-items: center; }
.tb-tile-title { font-weight: 620; font-size: 12.5px; }
.tb-tile-big { font-size: 26px; font-weight: 720; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; margin-top: 2px; }
.tb-tile-sub, .tb-tile-worst, .tb-tile-note { font-size: 11.5px; color: var(--tb-fg3); }
.tb-tile-metric { font-size: 12px; color: var(--tb-fg2); }
.tb-tile-scope { font-size: 11.5px; font-weight: 700; letter-spacing: .06em; margin-top: 10px; color: var(--tb-fg2); }
.tb-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.tb-fill-green { background: var(--tb-green); }
.tb-fill-amber { background: var(--tb-amber); }
.tb-fill-red { background: var(--tb-red); }
.tb-fill-grey, .tb-fill-muted { background: var(--tb-grey); }
.tb-fill-accent { background: var(--tb-accent); }

/* Bars */
.tb-barrow { display: grid; grid-template-columns: 110px 1fr 44px; align-items: center; gap: 8px; font-size: 12px; }
.tb-barrow-label { color: var(--tb-fg2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tb-barrow-right { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
.tb-barrow-note { grid-column: 2 / 4; margin-top: -6px; font-size: 10.5px; color: var(--tb-fg3); }
.tb-bar { position: relative; height: 8px; border-radius: 99px; background: var(--tb-card-hi); overflow: visible; }
.tb-bar-fill { height: 100%; border-radius: 99px; transition: width .4s ease; }
.tb-bar-mark { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--tb-fg3); border-radius: 1px; }

.tb-progress { display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border-radius: 12px; background: var(--tb-card); border: 1px solid var(--tb-line); }
.tb-progress-head { display: flex; justify-content: space-between; font-size: 12px; color: var(--tb-fg2); }

.tb-callout { border-radius: 10px; padding: 10px 12px; font-size: 12.5px; border: 1px solid var(--tb-line); background: var(--tb-card); }
.tb-callout p { margin: 4px 0 0; }
.tb-callout ul { margin: 6px 0 0; padding-left: 18px; }
.tb-callout pre { white-space: pre-wrap; font-size: 11px; max-height: 160px; overflow: auto; }
.tb-callout.tb-tone-red { border-color: color-mix(in srgb, var(--tb-red) 40%, transparent); background: color-mix(in srgb, var(--tb-red) 8%, transparent); }
.tb-callout.tb-tone-green { border-color: color-mix(in srgb, var(--tb-green) 40%, transparent); background: color-mix(in srgb, var(--tb-green) 8%, transparent); }
.tb-callout.tb-tone-amber { border-color: color-mix(in srgb, var(--tb-amber) 40%, transparent); background: color-mix(in srgb, var(--tb-amber) 8%, transparent); }

/* Compare */
.tb-checks { display: flex; flex-wrap: wrap; gap: 8px; }
.tb-check { display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--tb-line); cursor: pointer; min-width: 180px; position: relative; }
.tb-check input { position: absolute; right: 10px; top: 10px; accent-color: var(--tb-accent); }
.tb-check span { font-weight: 620; padding-right: 22px; }
.tb-check small { color: var(--tb-fg3); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10.5px; }
.tb-check.tb-active { border-color: color-mix(in srgb, var(--tb-accent) 55%, transparent); background: color-mix(in srgb, var(--tb-accent) 7%, transparent); }

/* Move check */
.tb-verdict { display: grid; grid-template-columns: auto 1fr auto; gap: 22px; align-items: center; padding: 20px 24px;
  border-radius: 18px; color: #fff; position: relative; overflow: hidden; }
.tb-verdict::after { content: ""; position: absolute; inset: 0; background: radial-gradient(80% 140% at 100% 0%, rgba(255,255,255,.18), transparent 60%); pointer-events: none; }
.tb-verdict-green { background: linear-gradient(135deg, color-mix(in srgb, var(--tb-green) 92%, #000), color-mix(in srgb, var(--tb-green) 70%, #000)); }
.tb-verdict-red { background: linear-gradient(135deg, color-mix(in srgb, var(--tb-red) 92%, #000), color-mix(in srgb, var(--tb-red) 68%, #000)); }
.tb-verdict-grey { background: linear-gradient(135deg, #5d6470, #444a54); }
.tb-verdict-word { font-size: 40px; font-weight: 800; letter-spacing: .04em; line-height: 1; }
.tb-verdict-title { font-weight: 700; font-size: 15px; margin-bottom: 2px; }
.tb-verdict-body { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.tb-muted-on { opacity: .78; }
.tb-verdict-stat { text-align: right; font-size: 12.5px; }
.tb-big { font-size: 34px; font-weight: 780; line-height: 1; font-variant-numeric: tabular-nums; }
.tb-interval { padding: 14px 4px 2px; }
.tb-interval-track { position: relative; height: 14px; border-radius: 99px; background: var(--tb-card-hi); }
.tb-interval-range { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: color-mix(in srgb, var(--tb-red) 45%, transparent); min-width: 4px; }
.tb-interval-point { position: absolute; top: -3px; width: 4px; height: 20px; margin-left: -2px; border-radius: 2px; background: var(--tb-fg); }
.tb-interval-limit { position: absolute; top: -10px; bottom: -4px; width: 0; border-left: 2px dashed var(--tb-green); }
.tb-interval-limit span { position: absolute; top: -16px; left: 4px; font-size: 10.5px; color: var(--tb-green); white-space: nowrap; }
.tb-interval-scale { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--tb-fg3); margin-top: 4px; }
.tb-suggest ol { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; }
.tb-suggest li::marker { color: var(--tb-accent); font-weight: 700; }
`
