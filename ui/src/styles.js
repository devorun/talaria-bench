// Scoped styles (every class starts with tb-). Colours come from the host theme: Desktop's --ui-* tokens,
// the dashboard's --color-* tokens, else derived from the inherited text colour, so light and dark
// themes both work. The only fixed hues are the status colours (green/amber/red), each with a theme
// token first.
export const STYLES = `
.tb-root {
  --tb-fg: var(--ui-text-primary, var(--color-foreground, currentColor));
  --tb-fg2: var(--ui-text-secondary, var(--color-muted-foreground, color-mix(in srgb, currentColor 75%, transparent)));
  --tb-fg3: color-mix(in srgb, var(--ui-text-tertiary, var(--color-muted-foreground, color-mix(in srgb, currentColor 55%, transparent))) 68%, var(--tb-fg));
  --tb-line: var(--ui-stroke-secondary, var(--color-border, color-mix(in srgb, currentColor 14%, transparent)));
  --tb-card: color-mix(in srgb, currentColor 3.5%, transparent);
  --tb-card-hi: color-mix(in srgb, currentColor 7%, transparent);
  --tb-accent: var(--ui-accent, var(--color-primary, #7c8cff));
  --tb-green: var(--ui-success, #2fae6f);
  --tb-amber: var(--ui-warning, #e0a12d);
  --tb-red: var(--ui-danger, var(--color-destructive, #e5544b));
  --tb-grey: color-mix(in srgb, currentColor 42%, transparent);
  --tb-green-ink: color-mix(in srgb, var(--tb-green) 46%, var(--tb-fg));
  --tb-amber-ink: color-mix(in srgb, var(--tb-amber) 46%, var(--tb-fg));
  --tb-red-ink: color-mix(in srgb, var(--tb-red) 56%, var(--tb-fg));
  --tb-accent-ink: color-mix(in srgb, var(--tb-accent) 70%, var(--tb-fg));
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
.tb-logo { width: 34px; height: 34px; border-radius: 9px; display: block; flex: none;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--tb-fg) 14%, transparent); }
.tb-title { font-weight: 650; font-size: 15px; letter-spacing: -0.01em; }
.tb-tagline { font-size: 11.5px; color: var(--tb-fg3); }
.tb-tabs { display: flex; gap: 2px; padding: 3px; border-radius: 11px; background: var(--tb-card); border: 1px solid var(--tb-line);
  max-width: 100%; overflow-x: auto; scrollbar-width: none; }
.tb-tabs::-webkit-scrollbar { display: none; }
.tb-tab {
  all: unset; cursor: pointer; padding: 6px 12px; border-radius: 8px; font-size: 12.5px; color: var(--tb-fg2); white-space: nowrap;
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
.tb-chip.tb-tone-green { color: var(--tb-green-ink); background: color-mix(in srgb, var(--tb-green) 13%, transparent); border-color: color-mix(in srgb, var(--tb-green) 30%, transparent); }
.tb-chip.tb-tone-amber { color: var(--tb-amber-ink); background: color-mix(in srgb, var(--tb-amber) 13%, transparent); border-color: color-mix(in srgb, var(--tb-amber) 30%, transparent); }
.tb-chip.tb-tone-red { color: var(--tb-red-ink); background: color-mix(in srgb, var(--tb-red) 13%, transparent); border-color: color-mix(in srgb, var(--tb-red) 30%, transparent); }
.tb-chip.tb-tone-accent { color: var(--tb-accent-ink); background: color-mix(in srgb, var(--tb-accent) 13%, transparent); border-color: color-mix(in srgb, var(--tb-accent) 30%, transparent); }
.tb-chip.tb-tone-grey { color: var(--tb-fg2); }
.tb-meta-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }

.tb-btn {
  display: inline-flex; align-items: center; gap: 7px; padding: 7px 13px; border-radius: 9px; font: inherit;
  font-size: 12.5px; font-weight: 580; cursor: pointer; color: var(--tb-fg); background: var(--tb-card-hi); white-space: nowrap;
  border: 1px solid var(--tb-line); transition: transform .08s, background .15s, border-color .15s;
}
.tb-btn:hover:not(:disabled) { border-color: color-mix(in srgb, currentColor 30%, transparent); }
.tb-btn:active:not(:disabled) { transform: translateY(1px); }
.tb-btn:disabled { opacity: .55; cursor: default; }
.tb-btn-primary { background: var(--tb-accent); border-color: transparent;
  color: var(--ui-accent-foreground, var(--color-primary-foreground, #fff)); }
.tb-btn-primary:hover:not(:disabled) { filter: brightness(1.08); border-color: transparent; }
.tb-icon-btn { all: unset; cursor: pointer; width: 32px; height: 32px; flex: none; display: grid; place-items: center; border-radius: 50%;
  background: var(--tb-accent); color: var(--ui-accent-foreground, var(--color-primary-foreground, #fff)); transition: filter .15s, transform .08s; }
.tb-icon-btn:hover { filter: brightness(1.1); }
.tb-icon-btn:active { transform: scale(.94); }

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
  padding: 3px 8px; border-radius: 6px; color: #fff; background: rgba(18,21,27,.66); border: 1px solid rgba(255,255,255,.22);
  pointer-events: none; backdrop-filter: blur(6px); }
.tb-viewer-tipped { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%); pointer-events: none;
  font-size: 11px; font-weight: 800; letter-spacing: .12em; padding: 4px 10px; border-radius: 7px; color: #fff;
  background: color-mix(in srgb, var(--tb-red) 92%, #000); box-shadow: 0 6px 18px -8px var(--tb-red);
  animation: tb-pop .25s ease-out; }
@keyframes tb-pop { from { transform: translateX(-50%) scale(1.25); opacity: 0; } to { transform: translateX(-50%) scale(1); opacity: 1; } }
.tb-viewer-label { position: absolute; left: 12px; top: 10px; display: flex; flex-direction: column; gap: 1px; pointer-events: none;
  font-size: 12.5px; font-weight: 640; }
.tb-viewer-label small { font-weight: 500; font-size: 11.5px; color: var(--tb-fg3); }
.tb-viewer-label.tb-tone-green small { color: var(--tb-green-ink); }
.tb-viewer-label.tb-tone-red small { color: var(--tb-red-ink); }
.tb-viewer-reset { all: unset; cursor: pointer; position: absolute; right: 10px; bottom: 10px; width: 28px; height: 28px;
  display: grid; place-items: center; border-radius: 7px; color: #fff; background: rgba(18,21,27,.66);
  border: 1px solid rgba(255,255,255,.22); backdrop-filter: blur(6px); }
.tb-viewer-reset:hover { background: rgba(18,21,27,.86); }
.tb-viewer-error { position: absolute; inset: 0; display: grid; place-items: center; color: var(--tb-fg3); }
.tb-viewer-wait { display: grid; place-items: center; color: var(--tb-fg3); background: var(--tb-card); }
.tb-overlay-note { position: absolute; left: 12px; bottom: 56px; font-size: 12px; color: var(--tb-fg2); }
.tb-grid-views { display: grid; gap: 10px; }
.tb-views-1 { grid-template-columns: 1fr; }
.tb-views-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.tb-views-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
@container (max-width: 860px) { .tb-views-2, .tb-views-3 { grid-template-columns: 1fr; } }

.tb-timeline { display: flex; align-items: center; gap: 12px; padding: 14px 14px 10px; flex-wrap: wrap; border-top: 1px solid var(--tb-line); }
.tb-card:not(.tb-card-flush) .tb-timeline { padding: 14px 0 0; border-top: 0; }
.tb-scrub { position: relative; flex: 1; min-width: 150px; height: 28px; display: flex; align-items: center; }
.tb-scrub-track { position: absolute; left: 8px; right: 8px; height: 6px; border-radius: 99px; background: var(--tb-card-hi);
  box-shadow: inset 0 0 0 1px var(--tb-line); overflow: hidden; }
.tb-scrub-fill { height: 100%; background: var(--tb-accent); }
.tb-scrub input { position: relative; width: 100%; height: 28px; margin: 0; padding: 0; background: transparent; cursor: pointer;
  -webkit-appearance: none; appearance: none; }
.tb-scrub input::-webkit-slider-runnable-track { height: 6px; background: transparent; }
.tb-scrub input::-moz-range-track { height: 6px; background: transparent; }
.tb-scrub input::-webkit-slider-thumb { -webkit-appearance: none; width: 16px; height: 16px; margin-top: -5px; border-radius: 50%;
  background: #fff; border: 2px solid var(--tb-accent); box-shadow: 0 1px 4px rgba(0,0,0,.35); }
.tb-scrub input::-moz-range-thumb { width: 12px; height: 12px; border-radius: 50%; background: #fff; border: 2px solid var(--tb-accent);
  box-shadow: 0 1px 4px rgba(0,0,0,.35); }
.tb-mark { position: absolute; top: 5px; bottom: 5px; width: 2px; margin-left: -1px; border-radius: 1px; pointer-events: none;
  background: var(--tb-accent); }
.tb-mark i { position: absolute; bottom: calc(100% + 1px); left: 50%; transform: translateX(-50%); font-style: normal; font-size: 9.5px;
  font-weight: 750; letter-spacing: .06em; text-transform: uppercase; white-space: nowrap; color: var(--tb-accent-ink); }
.tb-mark-red { background: var(--tb-red); }
.tb-mark-red i { color: var(--tb-red-ink); }
.tb-time { font-variant-numeric: tabular-nums; font-size: 12.5px; font-weight: 620; min-width: 96px; text-align: right; }
.tb-time small { font-size: 11.5px; font-weight: 500; color: var(--tb-fg3); }
.tb-rates .tb-seg-btn { padding: 4px 8px; font-size: 11.5px; font-variant-numeric: tabular-nums; }

/* Photo */
.tb-photo { margin: 0; border-radius: var(--tb-radius); overflow: hidden; border: 1px solid var(--tb-line); position: relative; background: var(--tb-card); min-height: 240px; }
.tb-photo img { width: 100%; height: 100%; max-height: 480px; object-fit: cover; display: block; }
.tb-photo figcaption { position: absolute; left: 10px; bottom: 10px; display: flex; gap: 6px; align-items: center; font-size: 11.5px;
  color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,.6); }
.tb-photo-empty { display: grid; place-items: center; }

.tb-photo-col { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.tb-photo-add { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  padding: 20px; border-style: dashed; text-align: center; }
.tb-new-card { align-items: center; justify-content: center; padding: 24px; text-align: center; gap: 8px; min-height: 260px;
  border-style: dashed; }
.tb-new-plus { width: 54px; height: 54px; border-radius: 16px; display: grid; place-items: center; font-size: 30px;
  color: var(--tb-accent); background: color-mix(in srgb, var(--tb-accent) 12%, transparent); }

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
.tb-delta { display: inline-block; font-size: 11px; font-weight: 700; margin-left: 8px; padding: 1px 7px; border-radius: 6px;
  color: var(--tb-fg3); background: var(--tb-card-hi); font-variant-numeric: tabular-nums; }
.tb-delta.tb-up { color: var(--tb-green-ink); background: color-mix(in srgb, var(--tb-green) 14%, transparent); }
.tb-delta.tb-down { color: var(--tb-red-ink); background: color-mix(in srgb, var(--tb-red) 14%, transparent); }
.tb-table tbody th { text-align: left; font-weight: 560; font-size: 12.5px; color: var(--tb-fg); padding: 6px 8px;
  border-bottom: 1px solid var(--tb-line); white-space: nowrap; }
.tb-table tr.tb-clickable:hover th { background: var(--tb-card); }
.tb-table tr.tb-active th { background: color-mix(in srgb, var(--tb-accent) 9%, transparent); }

/* Report tiles */
.tb-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(188px, 1fr)); gap: 10px; }
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
.tb-tile-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.tb-tile-status { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; font-weight: 780; letter-spacing: .08em; white-space: nowrap; }
.tb-tile-status.tb-tone-green { color: var(--tb-green-ink); }
.tb-tile-status.tb-tone-amber { color: var(--tb-amber-ink); }
.tb-tile-status.tb-tone-red { color: var(--tb-red-ink); }
.tb-tile-big small { margin-left: 6px; font-size: 11.5px; font-weight: 600; letter-spacing: 0; color: var(--tb-fg3); }
.tb-tile-title { font-weight: 620; font-size: 12.5px; }
.tb-tile-big { font-size: 30px; font-weight: 740; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; margin-top: 2px; }
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

.tb-seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--tb-card); border: 1px solid var(--tb-line); }
.tb-seg-btn { all: unset; cursor: pointer; padding: 5px 10px; border-radius: 7px; font-size: 12px; color: var(--tb-fg2); }
.tb-seg-btn:hover:not(:disabled) { color: var(--tb-fg); }
.tb-seg-btn.tb-active { background: var(--tb-card-hi); color: var(--tb-fg); font-weight: 620; }
.tb-seg-btn:disabled { opacity: .45; cursor: default; }
.tb-seg-count { font-size: 10.5px; color: var(--tb-fg3); margin-left: 3px; font-variant-numeric: tabular-nums; }
.tb-badge { display: inline-flex; align-items: center; padding: 1px 7px; border-radius: 6px; font-size: 11px; font-weight: 800;
  letter-spacing: .04em; color: #fff; background: var(--tb-badge, var(--tb-accent)); }
.tb-thumb .tb-badge { position: absolute; right: 10px; top: 10px; }


/* Arena */
.tb-tab-feature { color: var(--tb-accent-ink); font-weight: 650; }
.tb-tab-feature::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px;
  background: var(--tb-accent); vertical-align: 1px; }
.tb-arena-robots { display: flex; flex-direction: column; gap: 12px; }
.tb-arena-robot { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--tb-line);
  background: var(--tb-card); }
.tb-arena-variant { align-items: flex-start; border-color: color-mix(in srgb, var(--tb-accent) 40%, var(--tb-line)); }
.tb-arena-variant .tb-field { min-width: 150px; }
.tb-scene-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin: 6px 0 14px; }
.tb-scene { all: unset; box-sizing: border-box; cursor: pointer; display: flex; flex-direction: column; gap: 4px; padding: 12px;
  border-radius: 12px; border: 1px solid var(--tb-line); background: var(--tb-card); color: var(--tb-fg2); }
.tb-scene:hover { background: var(--tb-card-hi); }
.tb-scene:focus-visible { outline: 2px solid var(--tb-accent); outline-offset: 2px; }
.tb-scene.tb-active { border-color: var(--tb-accent); background: color-mix(in srgb, var(--tb-accent) 12%, transparent); color: var(--tb-fg); }
.tb-scene-icon { color: var(--tb-accent-ink); height: 28px; }
.tb-scene-title { font-weight: 650; font-size: 13.5px; color: var(--tb-fg); }
.tb-scene-blurb { font-size: 11.5px; color: var(--tb-fg3); line-height: 1.35; }
.tb-table-arena th, .tb-table-arena td { vertical-align: middle; }
/* Move check */
.tb-verdict { display: grid; grid-template-columns: auto 1fr auto; gap: 30px; align-items: center; padding: 26px 32px;
  border-radius: 18px; color: #fff; position: relative; overflow: hidden; box-shadow: 0 18px 40px -28px #000; }
.tb-verdict::after { content: ""; position: absolute; inset: 0; background: radial-gradient(80% 140% at 100% 0%, rgba(255,255,255,.10), transparent 60%); pointer-events: none; }
.tb-verdict-green { background: linear-gradient(135deg, color-mix(in srgb, var(--tb-green) 58%, #000), color-mix(in srgb, var(--tb-green) 40%, #000)); }
.tb-verdict-red { background: linear-gradient(135deg, color-mix(in srgb, var(--tb-red) 66%, #000), color-mix(in srgb, var(--tb-red) 46%, #000)); }
.tb-verdict-grey { background: linear-gradient(135deg, #59606c, #3f454e); }
.tb-verdict-word { font-size: clamp(44px, 6.6cqi, 92px); font-weight: 850; letter-spacing: .03em; line-height: .95; }
.tb-verdict-title { font-weight: 720; font-size: 17px; margin-bottom: 2px; }
.tb-verdict-body { display: flex; flex-direction: column; gap: 4px; font-size: 13.5px; position: relative; z-index: 1; }
.tb-muted-on { opacity: .85; }
.tb-verdict-stat { text-align: right; font-size: 13px; position: relative; z-index: 1; display: flex; flex-direction: column; gap: 3px; }
.tb-verdict-worlds { font-size: 14.5px; }
.tb-verdict-worlds b { font-weight: 780; }
.tb-big { font-size: clamp(40px, 4.8cqi, 68px); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.tb-big small { margin-left: 8px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.tb-interval { padding: 14px 4px 2px; }
.tb-interval-track { position: relative; height: 16px; border-radius: 99px; background: var(--tb-card-hi); }
.tb-interval-ok { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px 0 0 99px; background: color-mix(in srgb, var(--tb-green) 20%, transparent); }
.tb-interval-range { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: color-mix(in srgb, var(--tb-red) 55%, transparent); min-width: 4px; }
.tb-interval-range.tb-ok { background: color-mix(in srgb, var(--tb-green) 60%, transparent); }
.tb-interval-point { position: absolute; top: -3px; width: 4px; height: 20px; margin-left: -2px; border-radius: 2px; background: var(--tb-fg); }
.tb-interval-limit { position: absolute; top: -10px; bottom: -4px; width: 0; border-left: 2px dashed var(--tb-green); }
.tb-interval-limit span { position: absolute; top: -16px; left: 4px; font-size: 10.5px; font-weight: 650; color: var(--tb-green-ink); white-space: nowrap; }
.tb-interval-scale { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--tb-fg3); margin-top: 4px; }
.tb-suggest ol { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; }
.tb-suggest li::marker { color: var(--tb-accent); font-weight: 700; }

.tb-root code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .92em; padding: 1px 5px; border-radius: 5px;
  color: inherit; background: var(--tb-card-hi); border: 1px solid var(--tb-line); }

/* Layout helpers */
.tb-stack { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.tb-end { align-items: flex-end; }
.tb-card-head > .tb-row { flex-wrap: wrap; }
.tb-summary-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 7px; font-size: 13.5px; line-height: 1.5; }
.tb-summary-list li { position: relative; padding-left: 16px; color: var(--tb-fg2); }
.tb-summary-list li::before { content: ""; position: absolute; left: 2px; top: .62em; width: 5px; height: 5px; border-radius: 50%; background: var(--tb-fg3); }
.tb-summary-list li:first-child { font-size: 14.5px; font-weight: 600; color: var(--tb-fg); }
.tb-summary-list li:first-child::before { background: var(--tb-accent); }

/* Keyboard focus: always visible, also on the controls that reset their own styles. */
.tb-root :is(button, select, input, textarea, a, [role="tab"], [tabindex]):focus-visible {
  outline: 2px solid var(--tb-accent); outline-offset: 2px; }
.tb-root .tb-scrub input:focus-visible { outline-offset: -2px; border-radius: 99px; }
.tb-check:focus-within { outline: 2px solid var(--tb-accent); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  .tb-root *, .tb-root *::before, .tb-root *::after { transition: none !important; }
  .tb-viewer-tipped { animation: none; }
}

/* Phones and narrow panels */
@container (max-width: 560px) {
  .tb-header { padding: 10px 14px; gap: 10px; }
  .tb-main { padding: 14px 14px 32px; }
  .tb-picker { margin-left: 0; width: 100%; }
  .tb-picker .tb-select { width: 100%; }
  .tb-hero h2 { font-size: 19px; }
  .tb-hero-actions { width: 100%; }
  .tb-verdict { padding: 20px; gap: 14px; }
  .tb-verdict-stat { text-align: left; }
  .tb-list-row { flex-direction: column; align-items: flex-start; }
  .tb-time small { display: none; }
  .tb-time { min-width: 0; }
  .tb-barrow { grid-template-columns: 84px 1fr 40px; }
  .tb-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
`
