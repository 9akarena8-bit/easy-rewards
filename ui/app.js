"use strict";
const api = new Proxy({}, {get: (_, n) => (...a) => window.pywebview.api[n](...a)});
const $ = (s, r = document) => r.querySelector(s);
const MINI = new URLSearchParams(location.search).has("mini");
let pointerIsDown = false, pollingInProgress = false;
let tplRole = "start", tplName = "", S = {}, ST = null, page = "home", sig = "", flt = "all", tplList = [], shot = null, testRes = null, toastT, hiddenUpdateVersion = "";
const PAGES = [["home", "◉", "nav.home"], ["afk", "↝", "nav.afk"], ["tracker", "✦", "nav.tracker"], ["templates", "▣", "nav.templates"],
  ["settings", "⚙", "nav.settings"], ["updates", "⟳", "nav.updates"], ["subscriptions", "◇", "nav.subscriptions"], ["guide", "?", "nav.guide"]];
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const t = (k, kw = {}) => (S[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => kw[n] ?? "");
const fmtT = seconds => { const s = Math.floor(Math.max(0, Number(seconds) || 0)); return [s / 3600 | 0, (s / 60 | 0) % 60, s % 60].map(n => String(n).padStart(2, "0")).join(":"); };
const num = n => Number(n).toLocaleString();
const tog = (k, on) => `<div class="tog ${on ? "on" : ""}" data-tog="${k}"></div>`;
function toast(m) { clearTimeout(toastT); document.querySelectorAll(".toast").forEach(e => e.remove());
  const d = document.createElement("div"); d.className = "toast"; d.textContent = m; document.body.append(d); toastT = setTimeout(() => d.remove(), 2200); }
const cname = c => c.name || t(c.key);
const languageButton = l => `<button class="${ST.cfg.ui_language === l ? "on" : ""}" data-ui="${l}" title="${esc(t("lang." + l))}">${({ru:"🇷🇺",en:"🇬🇧",uk:"🇺🇦"})[l]} <span>${esc(t("lang.short_" + l))}</span></button>`;

async function init() {
  document.body.classList.toggle("mini", MINI);
  ST = await api.state(); await loadStrings(); await tick(); setInterval(tick, 400);
}
async function loadStrings() { S = await api.strings(ST.cfg.ui_language); document.documentElement.lang = ST.cfg.ui_language; }
async function tick() {
  if (pollingInProgress) return;
  pollingInProgress = true;
  try { return await refreshFromBackend(); } finally { pollingInProgress = false; }
}
async function refreshFromBackend() {
  const prevLang = ST && ST.cfg.ui_language;
  try { ST = await api.state(); } catch (e) { return; }
  if (ST.cfg.ui_language !== prevLang) await loadStrings();
  document.documentElement.dataset.theme = ST.cfg.theme;
  render();
}
function refreshLiveMetrics() {
  if (!ST || !ST.engine) return;
  document.querySelectorAll('[data-live="runtime"]').forEach(node => {
    const value = fmtT(ST.engine.runtime || 0);
    if (node.textContent !== value) node.textContent = value;
  });
}
// Mouse down -> click must target the same DOM node. Rebuilding it mid-click
// makes Stop/Pause intermittently unclickable on slower WebView2 machines.
document.addEventListener("pointerdown", () => { pointerIsDown = true; }, true);
document.addEventListener("pointerup", () => { pointerIsDown = false; setTimeout(() => render(), 0); }, true);
document.addEventListener("pointercancel", () => { pointerIsDown = false; }, true);
function render(force) {
  if (!force && pointerIsDown) return;
  const a = document.activeElement, editing = a && a.matches && a.matches("input,select") && !MINI;
  const s = JSON.stringify([page, flt, ST.cfg.ui_language, ST.cfg.theme, ST.cfg, {...ST.engine, runtime: undefined}, ST.diagnostics, ST.tracker.rev, ST.week, ST.guide, ST.tpl_counts,
    ST.update, ST.release_news, ST.subscription, ST.log.length && ST.log.at(-1).n, tplList.length, !!shot, testRes, ST.cfg.guide_dismissed]);
  if (!force && (s === sig || (editing && !shot))) { refreshLiveMetrics(); return; }
  const previousPage = document.querySelector('#app .page');
  const oldScroll = previousPage ? previousPage.scrollTop : 0;
  const oldRail = document.querySelector('#app .gold-nav');
  const oldRailScroll = oldRail ? oldRail.scrollTop : 0;
  const samePage = document.querySelector('#app [data-current-page]')?.dataset.currentPage === page;
  sig = s;
  if (MINI) { renderMini(); if (!document.getElementById("running-interface")) { const mark = document.createElement("span"); mark.id = "running-interface"; mark.hidden = true; document.body.append(mark); } return; }
  const tit = PAGES.find(p => p[0] === page)[2];
  const wk = ST.week ? `<span class="badge">${t("wk.label", {n: ST.week.n})} · ${t("wk.left", {d: ST.week.d, h: ST.week.h})}</span>` : "";
  $("#app").innerHTML = `
  <aside class="rail"><div class="brand"><img src="pirate_token.png" alt=""><span><b>Easy</b><em>Rewards</em></span></div>
    ${PAGES.map(p => `<button class="nav ${page === p[0] ? "on" : ""}" data-page="${p[0]}"><i>${p[1]}</i><span>${t(p[2])}</span></button>`).join("")}
    <div class="ver">v${esc(ST.version)}</div></aside>
  <section class="main"><header class="top"><div class="top-label">EASY REWARDS</div><h1>${t(tit.replace("nav.", "") === "home" ? "home.title" : tit)}</h1>${wk}
    <div class="seg">${["ru", "en", "uk"].map(languageButton).join("")}</div>
    <button class="icon" data-act="theme" title="${t("set.theme")}">${ST.cfg.theme === "dark" ? "☀" : "☾"}</button>
    <button class="icon" data-act="mini" title="${t("mini.open")}">⧉</button></header>
    ${["available", "downloading", "ready"].includes(ST.update.status) && hiddenUpdateVersion !== ST.update.version ? `<div class="update-banner">
      <div><b>${t("upd.banner_title", {v: esc(ST.update.version)})}</b><span>${ST.update.status === "ready" ? t("upd.ready") : ST.update.status === "downloading" ? t("upd.downloading") : t("upd.banner_subtitle")}</span></div>
      <button class="btn pri sm" data-act="uinst" ${ST.update.status === "downloading" ? "disabled" : ""}>${t("upd.exit_install")}</button>
      <button class="btn sm" data-act="ulater">${t("upd.later")}</button></div>` : ""}
    <div class="page" data-current-page="${page}">${PAGE[page]()}</div></section>${shot ? overlay() : ""}`;
  if (samePage) {
    const newScroll = document.querySelector('#app .page');
    if (newScroll) newScroll.scrollTop = oldScroll;
    const newRail = document.querySelector('#app .gold-nav');
    if (newRail) newRail.scrollTop = oldRailScroll;
  }
  refreshLiveMetrics();
  if (shot) bindShot();
  if (!document.getElementById("running-interface")) { const mark = document.createElement("span"); mark.id = "running-interface"; mark.hidden = true; document.body.append(mark); }
}

// ---------------------------------------------------------------- pages
const PAGE = {
  home() {
    const e = ST.engine, g = ST.guide, h = e.history, mx = Math.max(1, ...h.map(x => x.games + x.cycles));
    const done = [g.c1, g.c2, g.c3], quick = !g.dismissed && !done.every(Boolean);
    const status = `<span class="pill"><span class="dot ${e.running && !e.paused ? "on" : ""}"></span>${t("state." + e.state)}</span>`;
    return `<div class="home-topline"><div><div class="eyebrow">✧ ${t("home.overview")}</div><div class="intro-head">${t("home.title")}<span class="intro-line"></span></div></div>
      <div class="home-top-panels"><div class="session-head"><span>${t("home.status")}</span>${status}</div>
      <button class="btn sm" data-page="guide">${t("guide.open")}</button></div></div>
    <div class="grid g2 home-grid">
    <div class="card compact-controller"><h3>${t("home.status")}</h3>
      <div class="control-buttons">
        <button class="start-square" data-act="start" ${e.running ? "disabled" : ""}><span>▶</span><strong>${t("btn.start")}</strong></button>
        <button class="btn control-stop" data-act="stop" ${!e.running ? "disabled" : ""}>■ &nbsp;${t("btn.stop")}</button>
        <button class="btn control-pause" data-act="main" ${!e.running ? "disabled" : ""}>${e.paused ? "▶" : "Ⅱ"} &nbsp;${e.paused ? t("btn.resume") : t("btn.pause")}</button>
      </div>
      <div class="control-footer"><button class="btn sm" data-act="reset">${t("btn.reset")}</button><small>${t("hotkeys")}</small></div></div>
    <div class="card stats-card"><h3>${t("home.session_stats")}</h3><div class="grid g4"><div class="stat"><b>${e.games}</b><span>${t("stat.games")}</span></div>
      <div class="stat"><b>${e.cycles}</b><span>${t("stat.cycles")}</span></div><div class="stat"><b><span data-live="runtime">${fmtT(e.runtime)}</span></b><span>${t("stat.time")}</span></div>
      <div class="stat"><b>${(e.score * 100 | 0)}%</b><span>${t("stat.match")}</span></div></div>
      <div class="history-title"><h3>${t("home.last_hour")}</h3><small>${t("home.chart_hint")}</small></div>
      <div class="bars">${h.map((x,i) => `<div title="${t("home.chart_bucket", {n:i+1, c:x.games+x.cycles})}" style="height:${Math.max(4, (x.games + x.cycles) / mx * 100)}%"></div>`).join("")}</div></div>
    <div class="card focus-card"><h3>${t("diag.heading")}</h3>
      <div class="focus-line"><span>${t("diag.game")}</span><b class="${ST.diagnostics?.game_active ? "good" : "muted"}">${ST.diagnostics?.game_active ? t("diag.active") : t("diag.inactive")}</b></div>
      <div class="focus-line"><span>${t("diag.foreground")}</span><b>${esc(ST.diagnostics?.foreground_title || t("diag.none"))}</b></div>
      <div class="focus-line"><span>${t("diag.inputs")}</span><b>${e.input_count || 0}${e.last_input ? " · " + esc(e.last_input) : ""}</b></div>
      ${e.input_error ? `<p class="focus-warn">${esc(e.input_error)}</p>` : ""}
      ${e.running && !ST.diagnostics?.game_active && ST.cfg.require_foreground ? `<p class="focus-warn">${t("diag.focus_hint")}</p>` : ""}
      ${e.running && !ST.diagnostics?.template_count ? `<p class="mute">${t("diag.afk_only")}</p>` : ""}
    </div>
    <div class="card reward-card"><div class="reward-art"><img src="pirate_token.png" alt=""></div><div class="eyebrow">${t("home.reward_heading")}</div>
      <div class="reward-numbers"><div><span>${t("home.session")}</span><strong>${num(e.rewards || 0)}</strong></div>
      <div><span>${t("home.all_time")}</span><strong>${num(ST.reward?.total || 0)}</strong></div></div>
      <p class="mute">${t("home.reward_note")}</p><button class="btn sm" data-page="templates">${t("nav.templates")}</button></div>
    ${quick ? `<div class="card"><h3>${t("guide.card")}</h3>${[1, 2, 3].map(i => `<div class="todo"><div class="chk ${done[i - 1] ? "on" : ""}">${done[i - 1] ? "✓" : ""}</div>${t("guide.c" + i)}</div>`).join("")}
      <div class="row" style="margin-top:8px"><button class="btn sm pri" data-page="guide">${t("guide.open")}</button><button class="btn sm" data-act="dismiss">${t("guide.dismiss")}</button></div></div>` : ""}
    <div class="card" style="${quick ? "" : "grid-column:1/-1"}"><h3>${t("log.title")}</h3><div class="log">${ST.log.slice().reverse().map(r => `${r.t}  ${esc(t(r.key, r.kw))}`).join("<br>") || "—"}</div></div></div>`;
  },
  afk() {
    const c = ST.cfg, e = ST.engine;
    const f = (label, inner) => `<div class="field"><span>${label}</span>${inner}</div>`;
    const sl = (key, min, max, step) => `<div class="row"><input type="range" data-cfg="${key}" min="${min}" max="${max}" step="${step}" value="${c[key]}"><b data-out="${key}">${c[key]}</b></div>`;
    const status = `<span class="pill"><span class="dot ${e.running && !e.paused ? "on" : ""}"></span>${t("state." + e.state)}</span>`;
    return `<div class="home-topline"><div><div class="eyebrow">✧ ${t("afk.subtitle_small")}</div><div class="intro-head">${t("afk.title")}<span class="intro-line"></span></div></div>${status}</div>
    <p class="mute">${t("afk.v13desc")}</p>
    <div class="row" style="margin-bottom:14px;flex-wrap:wrap">
      <button class="btn pri" data-act="start" ${e.running ? "disabled" : ""}>▶ ${t("btn.start")}</button>
      <button class="btn" data-act="stop" ${!e.running ? "disabled" : ""}>■ ${t("btn.stop")}</button>
      <button class="btn" data-act="main" ${!e.running ? "disabled" : ""}>${e.paused ? t("btn.resume") : t("btn.pause")}</button>
      <span class="badge">${t("afk.total")}: ${e.input_count}</span>
      <span class="badge">${t("afk.last")}: ${esc(e.last_input || "—")}</span>
    </div>
    ${e.input_error ? `<div class="warnbox">${esc(e.input_error)}</div>` : ""}
    <div class="card afk-diag" style="margin-bottom:16px">
      <h3>${t("diag.heading")}</h3>
      <p class="mute">${t("afk.diag_status")}: <b>${ST.diagnostics?.game_active ? t("diag.active") : (ST.diagnostics?.game_found ? t("afk.diag_background") : t("afk.diag_missing"))}</b></p>
      <p class="mute">${t("diag.foreground")}: <b>${esc(ST.diagnostics?.foreground_title || t("diag.none"))}</b>
        (${esc(ST.diagnostics?.foreground_process || "—")})</p>
      ${e.wait_reason ? `<p class="focus-warn">${esc(t("afk.reason_" + e.wait_reason))}</p>` : ""}
      <div class="row" style="flex-wrap:wrap;gap:10px">
        <button class="btn sm pri" data-act="ptest" data-target="fortnite" ${e.running || e.probe_status === "scheduled" ? "disabled" : ""}>${t("afk.probe_button")}</button>
        <button class="btn sm" data-act="ptest" data-target="notepad" ${e.running || e.probe_status === "scheduled" ? "disabled" : ""}>${t("afk.probe_notepad")}</button>
        <span class="mute">${t("afk.probe_help")}</span>
      </div>
      ${e.probe_status !== "idle" ? `<p class="mute">${t("afk.probe_status")}: ${esc(e.probe_target === "notepad" ? t("afk.probe_notepad_name") : "Fortnite")} — ${esc(t("afk.probe_" + e.probe_status))}
        ${e.probe_status === "error" ? "— " + esc(e.probe_detail || "") : ""} ${e.probe_at ? " (" + esc(e.probe_at) + ")" : ""}</p>` : ""}
      <p class="mute">${t("afk.probe_note")}</p>
    </div>
    <div class="grid g2" style="align-items:start">
    <div class="card"><h3>${t("afk.mode")}</h3>
      ${f(t("afk.enabled"), tog("afk_enabled", c.afk_enabled))}
      ${f(t("afk.sequence"), tog("afk_sequence_enabled", c.afk_sequence_enabled))}
      ${f(t("afk.minpause"), sl("afk_pause_min", .2, 5, .1))}
      ${f(t("afk.maxpause"), sl("afk_pause_max", .2, 5, .1))}
      ${f(t("afk.hold"), sl("afk_hold", .3, 4, .1))}
      ${f(t("afk.keys"), `<input class="in" type="text" data-cfg="afk_keys" maxlength="4" value="${esc(c.afk_keys)}">`)}
      <h3 style="margin-top:14px">${t("afk.motion")}</h3>
      ${f(t("afk.jump"), tog("afk_jump_enabled", c.afk_jump_enabled))}
      ${f(t("afk.sprint"), tog("afk_sprint_enabled", c.afk_sprint_enabled))}
      ${f(t("afk.slide"), tog("afk_slide_enabled", c.afk_slide_enabled))}
      ${f(t("afk.slots"), tog("afk_slot_enabled", c.afk_slot_enabled))}
      </div>
    <div class="card"><h3>${t("afk.camera")}</h3>
      ${f(t("afk.camera_on"), tog("afk_camera_enabled", c.afk_camera_enabled))}
      ${f(t("afk.calibration"), sl("afk_camera_pixels_360", 200, 4000, 50))}
      <p class="mute">${t("afk.calibration_help")}</p>
      <h3 style="margin-top:14px">${t("afk.extras")}</h3>
      ${f(t("afk.pickaxe"), tog("afk_pickaxe_enabled", c.afk_pickaxe_enabled))}
      ${f(t("afk.grenade"), tog("afk_grenade_enabled", c.afk_grenade_enabled))}
      ${f(t("afk.weapon"), tog("afk_weapon_enabled", c.afk_weapon_enabled))}
      <p class="mute">${t("afk.weapon_note")}</p>
      <div class="warnbox">${t("afk.safety")}</div>
      <h3 style="margin-top:14px">${t("afk.replay_heading")}</h3>
      ${f(t("afk.auto_yellow"), tog("afk_replay_auto_detect", c.afk_replay_auto_detect))}
      <p class="mute">${t("afk.replay_help")}</p>
      <div class="row"><span class="badge">${t("afk.replay_clicks")}: ${e.replay_count || 0}</span><span class="badge">${t("afk.replay_count")}: ${ST.tpl_counts.replay || 0}</span></div>
      <div class="row"><span class="badge">${t("afk.replay_state")}: ${t("replay." + (e.replay_status || "idle"))}</span></div>
      ${e.wait_reason === "replay_unresponsive" ? `<div class="warnbox">${t("afk.replay_unresponsive")}</div>` : ""}
      <button class="btn sm" data-act="replay_capture">${t("afk.capture_replay")}</button>
    </div></div>`;
  },
  tracker() {
    const T = ST.tracker, L = ST.luck, pr = T.prizes.filter(p => flt === "all" || (flt === "found") === p.found), found = T.prizes.filter(p => p.found).length;
    return `<p class="mute" style="margin:0 0 14px">${t("trk.subtitle")}</p><div class="grid g3">
    ${T.counters.map(c => { const nx = c.goals.find(g => g > c.value), pv = c.goals.filter(g => g <= c.value).pop() || 0;
      return `<div class="card cnt"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(cname(c))}</h3>
        <button class="btn sm warn" data-cdel="${c.id}">✕</button></div><div class="val">${num(c.value)}</div>
        <div class="prog"><i style="width:${nx ? (c.value - pv) / (nx - pv) * 100 : 100}%"></i></div>
        <div class="mute">${nx ? t("trk.next", {n: nx}) : t("trk.done")}</div>
        <div class="row"><button class="btn pri" data-cadd="${c.id}" data-d="1">+1</button><button class="btn" data-cadd="${c.id}" data-d="10">+10</button><button class="btn" data-cadd="${c.id}" data-d="-1">−</button></div></div>`; }).join("")}
    <div class="card"><h3>${t("trk.new_counter")}</h3><input class="in" id="nc" placeholder="${t("trk.counter_name")}"><input class="in" id="ng" placeholder="${t("trk.goals")}" style="margin-top:8px">
      <button class="btn" data-act="newc" style="margin-top:10px">${t("trk.prize_add")}</button></div></div>
    <div class="grid g2" style="margin-top:16px">
    <div class="card cnt"><h3 style="margin:0">${t("trk.tokens")}</h3><div class="val">${num(T.tokens)}</div><div class="mute">${t("trk.tokens_hint")}</div>
      <div class="row"><button class="btn pri" data-act="tok">${t("trk.found_one")}</button><button class="btn" data-act="tokm">−</button></div>
      <hr style="border:0;border-top:1px solid var(--line);width:100%"><h3 style="margin:0">${t("trk.luck")}</h3>
      <div class="luck-inputs">
        <label>${t("trk.luck_boost")} <span class="luck-factor">× <input class="in" id="boost" type="number" min="0.1" max="100" step="0.1" value="${T.boost}" inputmode="decimal"></span></label>
        <label>${t("trk.luck_odds")} <input class="in" id="odds" type="number" min="1" max="100000000" step="1" value="${T.odds}"></label>
        <button class="btn sm pri" data-act="lucksave">${t("btn.save")}</button></div>
      <div>${t("trk.luck_per", {n: num(L.one_in)})}</div><div>${t("trk.luck_so_far", {c: num(L.chests), p: (L.chance * 100).toFixed(1)})}</div>
      <div class="mute">${t("trk.luck_50", {n: num(L.n50)})} · ${t("trk.luck_90", {n: num(L.n90)})}</div><div class="mute">${t("trk.luck_note")}</div></div>
    <div class="card"><h3>${t("trk.prizes")} · ${t("trk.prizes_found", {a: found, b: T.prizes.length})}</h3>
      <div class="row" style="margin-bottom:8px"><div class="seg">${[["all", "trk.f_all"], ["found", "trk.f_found"], ["out", "trk.f_out"]].map(f => `<button class="${flt === f[0] ? "on" : ""}" data-flt="${f[0]}">${t(f[1])}</button>`).join("")}</div></div>
      <div class="row" style="margin-bottom:6px"><input class="in" id="pn" placeholder="${t("trk.prize_ph")}" style="flex:1;width:auto"><button class="btn pri" data-act="addp">${t("trk.prize_add")}</button></div>
      ${pr.map(p => `<div class="prize ${p.found ? "found" : ""}"><div class="chk ${p.found ? "on" : ""}" data-ptog="${p.id}">${p.found ? "✓" : ""}</div><span>${esc(p.name)}</span><button class="btn sm warn" data-pdel="${p.id}">✕</button></div>`).join("") || `<p class="mute">${t("trk.prizes_empty")}</p>`}
      <h3 style="margin-top:16px">${t("trk.backup")}</h3><div class="row"><button class="btn sm" data-act="exp">${t("trk.download")}</button><button class="btn sm" data-act="imp">${t("trk.bring_back")}</button><button class="btn sm warn" data-act="rst">${t("trk.start_over")}</button></div></div></div>`;
  },
  templates() {
    return `<p class="mute" style="margin:0 0 14px">${t("tpl.subtitle")}</p><div class="card">
    <div class="row" style="margin-bottom:10px"><select class="in" id="role" style="width:auto">${["start", "result", "wait", "reward", "replay", "death"].map(r => `<option value="${r}" ${tplRole === r ? "selected" : ""}>${t("tpl.role_" + r)}</option>`).join("")}</select>
      <input class="in" id="tname" value="${esc(tplName)}" placeholder="${t("tpl.name")}" style="width:160px"><button class="btn pri" data-act="cap">${t("tpl.capture")}</button><button class="btn" data-act="test">${t("tpl.test")}</button></div>
    <div class="mute" style="margin-bottom:6px">${t("tpl.legend")}</div>
    ${tplList.map(x => `<div class="tpl"><img src="${x.thumb}" alt=""><div style="flex:1"><b>${esc(x.name)}</b><div class="mute">${x.w}×${x.h}px</div></div>
      ${testRes && testRes.scores.find(s => s.name === x.name) ? `<span class="badge">${testRes.scores.find(s => s.name === x.name).score}</span>` : ""}
      <span class="role">${t("tpl.role_" + x.role)}</span><button class="btn sm warn" data-tdel="${esc(x.name)}">${t("tpl.delete")}</button></div>`).join("") || `<p class="mute">${t("tpl.empty")}</p>`}</div>`;
  },
  settings() {
    const c = ST.cfg, f = (l, inner) => `<div class="field"><span>${l}</span>${inner}</div>`;
    const sl = (k, lo, hi, st, v) => `<div class="row"><input type="range" data-cfg="${k}" min="${lo}" max="${hi}" step="${st}" value="${v}"><b data-out="${k}">${v}</b></div>`;
    return `<div class="grid g2"><div class="card"><h3>${t("set.general")}</h3>
      ${f(t("set.ui_language"), `<div class="seg lang-full">${["ru", "en", "uk"].map(l => `<button class="${c.ui_language === l ? "on" : ""}" data-ui="${l}">${({ru:"🇷🇺",en:"🇬🇧",uk:"🇺🇦"})[l]} ${esc(t("lang." + l))}</button>`).join("")}</div>`)}
      ${f(t("set.theme"), `<div class="seg">${["light", "dark"].map(l => `<button class="${c.theme === l ? "on" : ""}" data-theme="${l}">${t("theme." + l)}</button>`).join("")}</div>`)}
      ${f(t("set.game_language"), `<select data-cfg="language">${["ru", "en", "uk"].map(l => `<option value="${l}" ${c.language === l ? "selected" : ""}>${esc(t("lang." + l))}</option>`).join("")}</select>`)}
      <h3 style="margin-top:18px">${t("set.season")}</h3>${f(t("set.week_start"), `<input type="datetime-local" id="wk" value="${ST.tracker.week_start}">`)}<div class="mute">${t("set.week_hint")}</div>
      <h3 style="margin-top:18px">${t("set.hotkeys")}</h3><div class="mute">${t("set.hotkeys_text")}</div></div>
    <div class="card"><h3>${t("set.recognition")}</h3>
      ${f(t("set.threshold"), sl("threshold", .3, .99, .01, c.threshold))}${f(t("set.scan"), sl("scan_interval", .1, 3, .1, c.scan_interval))}${f(t("set.delay"), sl("click_delay", 0, 10, .5, c.click_delay))}
      ${f(t("set.foreground"), tog("require_foreground", c.require_foreground))}${f(t("set.focus"), tog("auto_focus", c.auto_focus))}${f(t("set.treasure_auto_boost"), tog("treasure_auto_boost", c.treasure_auto_boost))}
       <h3 style="margin-top:18px">${t("set.movement")}</h3>
       <button class="btn sm" data-page="afk">${t("afk.open_settings")}</button></div></div>`;
  },
  updates() {
    const u = ST.update, msg = {idle: "", need_url: t("upd.need_url"), checking: t("upd.checking"), downloading: t("upd.downloading"), installer_started:t("upd.installer_started"), ready:t("upd.ready"), latest: t("upd.latest", {v: u.version}),
      available: t("upd.available", {v: u.version}), installed: t("upd.done_running", {v: u.version}), error: t("upd.failed", {err: u.error})}[u.status] || "";
    return `<div class="card" style="max-width:640px"><p class="mute" style="margin-top:0">${t("upd.subtitle")}</p><p>${t("upd.version", {v: ST.version})}</p>
      ${ST.release_mode ? `<p class="update-channel">GitHub Releases · 9akarena8-bit/easy-rewards</p>` : `<input class="in" id="uurl" type="url" placeholder="https://…/version.json" value="${esc(ST.cfg.update_url)}">`}
      <div class="field"><span>${t("upd.auto")}</span>${tog("auto_update", ST.cfg.auto_update)}</div>
      <div class="row"><button class="btn pri" data-act="ucheck" ${u.status === "downloading" ? "disabled" : ""}>${t("upd.check")}</button>${["available", "ready"].includes(u.status) ? `<button class="btn" data-act="uinst">${t("upd.exit_install")}</button>` : ""}</div>
      <p>${esc(msg)}</p><div class="warnbox">${t("upd.warn")}</div></div>`;
  },
  subscriptions() {
    const sub = ST.subscription || {plans:[], payment_methods:[], enabled:false};
    const labels = {demo:"subs.demo", day:"subs.day", three_days:"subs.three_days", week:"subs.week"};
    return `<p class="mute" style="margin:0 0 14px">${t("subs.intro")}</p>
    <div class="card" style="margin-bottom:16px"><div class="row" style="justify-content:space-between;align-items:center">
      <h3 style="margin:0">${t("subs.status_title")}</h3><span class="badge">${t("subs.not_active")}</span></div>
      <div class="sub-remaining">—</div><p class="mute">${t("subs.remain_text")}</p>
      <p class="mute">${t("subs.notice_text")}</p></div>
    <h3>${t("subs.plans_title")}</h3>
    <div class="grid g2 subs-grid">${(sub.plans || []).map(p => `<div class="card">
      <div class="eyebrow">◇ EASY REWARDS</div><h3>${t(labels[p.id] || "subs.demo")}</h3>
      <p class="mute">${p.id === "demo" ? t("subs.demo_note") : t("subs.access_note")}</p>
      <div class="row" style="justify-content:space-between"><b>${t("subs.price_unset")}</b>
      <button type="button" class="btn sm" disabled>${t("subs.unavailable")}</button></div></div>`).join("")}</div>
    <div class="card" style="margin-top:16px"><h3>${t("subs.payments")}</h3>
      <p class="mute">${t("subs.payments_disabled")}</p><div class="row">
      <button type="button" class="btn" disabled>${t("subs.card")}</button>
      <button type="button" class="btn" disabled>${t("subs.sbp")}</button></div></div>`;
  },
  guide() {
    const g = ST.guide, go = {1: ["templates", "guide.go"], 2: ["templates", "guide.go"], 3: ["templates", "guide.go"], 4: ["home", "guide.go"], 5: ["tracker", "guide.go"], 6: ["updates", "guide.go"]};
    const done = {2: g.c1 && g.c2, 4: g.c3};
    return `<p class="mute" style="margin:0 0 14px">${t("guide.subtitle")}</p><div class="grid g2" style="align-items:start"><div class="card grid" style="gap:18px">
      ${[1, 2, 3, 4, 5, 6].map(i => `<div class="step"><div class="n">${done[i] ? "✓" : i}</div><div><h4>${t("guide.s" + i + "_t")}</h4><p>${t("guide.s" + i + "_d")}</p>
        ${i > 1 ? `<button class="btn sm" data-page="${go[i][0]}">${t("guide.go")}</button>` : ""}</div></div>`).join("")}</div>
      <div class="grid"><div class="warnbox">${t("guide.warn")}</div></div></div>`;
  },
};
function renderMini() {
  const e = ST.engine, T = ST.tracker;
  $("#app").innerHTML = `<div class="minibox"><div class="minirow"><span class="pill"><span class="dot ${e.running ? "on" : ""}"></span>${t("state." + e.state)}</span>
    <span class="mute">${fmtT(e.runtime)}</span></div>
    <div class="minirow"><button class="btn pri sm" data-act="main">${!e.running ? t("btn.start") : e.paused ? t("btn.resume") : t("btn.pause")}</button><button class="btn sm" data-act="stop">${t("btn.stop")}</button>
      <span class="mute">${e.games}/${e.cycles} · ✧${e.rewards || 0}</span></div>
    ${T.counters.slice(0, 3).map(c => `<div class="minirow"><span>${esc(cname(c))}</span><b>${num(c.value)}</b><button class="btn sm" data-cadd="${c.id}" data-d="1">+1</button></div>`).join("")}
    <div class="minirow"><span>${t("trk.tokens")}</span><b>${T.tokens}</b><button class="btn sm" data-act="tok">+1</button></div></div>`;
}
function overlay() {
  return `<div class="overlay"><div class="shot" id="shot"><img src="${shot.image}" draggable="false"><div class="sel" id="sel" hidden></div></div>
    <div style="color:#fff">${t("tpl.pick")}</div><div class="row"><button class="btn pri" data-act="saveshot">${t("tpl.save")}</button><button class="btn" data-act="cancelshot">${t("btn.cancel")}</button></div></div>`;
}
let box = null;
function bindShot() {
  const el = $("#shot"), sel = $("#sel"); let p0 = null;
  const pos = ev => { const r = el.getBoundingClientRect(); return [Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height))]; };
  const draw = (a, b) => { const x = Math.min(a[0], b[0]), y = Math.min(a[1], b[1]), w = Math.abs(a[0] - b[0]), h = Math.abs(a[1] - b[1]);
    box = {fx: x, fy: y, fw: w, fh: h}; Object.assign(sel.style, {left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%"}); sel.hidden = false; };
  el.onpointerdown = ev => { p0 = pos(ev); el.setPointerCapture(ev.pointerId); draw(p0, p0); };
  el.onpointermove = ev => { if (p0) draw(p0, pos(ev)); };
  el.onpointerup = () => { p0 = null; };
  if (box) { draw([box.fx, box.fy], [box.fx + box.fw, box.fy + box.fh]); }
}

// ---------------------------------------------------------------- events
async function patch(p) { await api.set_config(p); await tick(); }
document.addEventListener("click", async ev => {
  const windowButton = ev.target.closest("[data-window]");
  if (windowButton) {
    if (!window.pywebview || !window.pywebview.api) return;
    try { await window.pywebview.api["window_" + windowButton.dataset.window](); }
    catch (err) { toast("Не удалось управлять окном: " + String(err)); }
    return;
  }
  const el = ev.target.closest("[data-page],[data-act],[data-ui],[data-theme],[data-tog],[data-cadd],[data-cdel],[data-ptog],[data-pdel],[data-flt],[data-tdel]");
  if (!el) return; const d = el.dataset;
  if (d.page) { page = d.page; if (page === "templates") tplList = await api.templates(); return render(true); }
  if (d.ui) return patch({ui_language: d.ui});
  if (d.theme) return patch({theme: d.theme});
  if (d.tog) return patch({[d.tog]: !ST.cfg[d.tog]});
  if (d.cadd) { await api.counter_add(d.cadd, +d.d); return tick(); }
  if (d.cdel) { if (confirm(t("trk.delete_counter"))) { await api.counter_delete(d.cdel); tick(); } return; }
  if (d.ptog) { await api.prize_toggle(d.ptog); return tick(); }
  if (d.pdel) { await api.prize_delete(d.pdel); return tick(); }
  if (d.flt) { flt = d.flt; return render(true); }
  if (d.tdel) { await api.delete_template(d.tdel); tplList = await api.templates(); return tick(); }
  const a = d.act, v = id => ($("#" + id) || {}).value || "";
  if (a === "theme") return patch({theme: ST.cfg.theme === "dark" ? "light" : "dark"});
  if (a === "start") { await api.start(); return tick(); }
  if (a === "ptest") { const r = await api.input_probe_delayed(d.target || "fortnite");
    toast(r.ok ? t("afk.probe_started") : t("afk.probe_stop_first")); return tick(); }
  if (a === "main") { const e = ST.engine; await (e.running ? api.pause() : api.start()); return tick(); }
  if (a === "stop") { await api.stop(); return tick(); }
  if (a === "reset") { await api.reset_stats(); return tick(); }
  if (a === "mini") return api.open_mini();
  if (a === "dismiss") return patch({guide_dismissed: true});
  if (a === "tok") { await api.tokens_add(1); return tick(); }
  if (a === "tokm") { await api.tokens_add(-1); return tick(); }
  if (a === "lucksave") { const b = Number(v("boost").replace(",", ".")), odds = Number(v("odds"));
    if (!Number.isFinite(b) || b < .1 || b > 100 || !Number.isInteger(odds) || odds < 1 || odds > 100000000) {
      toast(t("trk.luck_invalid")); return;
    }
    await api.tracker_set({boost:b, odds});
    await api.set_config({treasure_auto_boost:false});
    toast(t("trk.luck_saved")); return tick();
  }
  if (a === "newc") { if (v("nc").trim()) { await api.counter_new(v("nc"), v("ng")); tick(); } return; }
  if (a === "addp") { if (v("pn").trim()) { await api.prize_add(v("pn")); tick(); } return; }
  if (a === "exp") { const r = await api.tracker_export(); if (r.ok) toast(t("trk.exported", {path: r.path})); return; }
  if (a === "imp") { const r = await api.tracker_import(); if (r.ok) toast(t("trk.imported")); else if (r.error !== "cancelled") toast(t("trk.import_failed")); return tick(); }
  if (a === "rst") { if (confirm(t("trk.confirm_reset"))) { await api.tracker_reset(); tick(); } return; }
  if (a === "replay_capture") { tplRole = "replay"; tplName = "play_again"; page = "templates"; tplList = await api.templates(); render(true); return; }
  if (a === "cap") { box = null; toast(t("tpl.capture_wait", {s: 5})); const r = await api.capture_screenshot(5); if (r.ok) { shot = r; render(true); } return; }
  if (a === "cancelshot") { shot = null; box = null; return render(true); }
  if (a === "saveshot") { if (!box) return; const r = await api.save_template(tplRole, tplName || "button", box.fx, box.fy, box.fw, box.fh);
    shot = null; box = null; tplList = await api.templates(); toast(r.ok ? t("toast.saved") : r.error); return tick(); }
  if (a === "test") { testRes = await api.test_templates(); return render(true); }
  if (a === "ucheck") { await api.update_check(ST.release_mode ? null : v("uurl")); return tick(); }
  if (a === "uinst") { toast(t("upd.downloading")); const r = await api.update_install();
    if (r.status === "installer_started") { toast(t("upd.installer_started")); await api.window_close(); return; }
    if (r.status === "error") toast(t("upd.failed", {err:r.error})); return tick();
  }
  if (a === "ulater") { hiddenUpdateVersion = ST.update.version; return render(true); }
});
document.addEventListener("input", ev => { const e = ev.target; if (e.id === "tname") tplName = e.value; if (e.dataset.cfg && e.type === "range") { const o = $(`[data-out="${e.dataset.cfg}"]`); if (o) o.textContent = e.value; } });
document.addEventListener("change", async ev => { const e = ev.target; if (e.id === "role") tplRole = e.value;
  if (e.dataset.cfg) { await patch({[e.dataset.cfg]: e.value}); toast(t("toast.saved")); }
  else if (e.id === "wk") { await api.tracker_set({week_start: e.value}); tick(); }
  else if (e.id === "boost" || e.id === "odds") { /* Save explicitly with the button. */ } });
// The pywebviewready event is dispatched on WINDOW, not document.
// A polling fallback also covers a lost event (before this script was loaded).
// Visible boot/error UI prevents an apparently frozen black window.
let bootStarted = false;
let bootChecks = 0;
let bridgeWatch = null;
function connectBridge() {
  if (bootStarted || !(window.pywebview && window.pywebview.api)) return false;
  if (typeof window.pywebview.api.state !== "function") return false;
  bootStarted = true;
  if (bridgeWatch) clearInterval(bridgeWatch);
  init().catch(err => window.easyRewardsBootError("Python API: " + String(err)));
  return true;
}
window.addEventListener("pywebviewready", connectBridge);
document.addEventListener("pywebviewready", connectBridge); // compatibility with older wrappers
if (!connectBridge()) {
  bridgeWatch = setInterval(() => {
    if (connectBridge()) return;
    if (++bootChecks > 100) {
      clearInterval(bridgeWatch);
      window.easyRewardsBootError("Нет соединения с pywebview (20 секунд). Проверь установку Microsoft Edge WebView2 Runtime.");
    }
  }, 200);
}
