"use strict";
const api = new Proxy({}, {get: (_, n) => (...a) => window.pywebview.api[n](...a)});
const $ = (s, r = document) => r.querySelector(s);
const MINI = new URLSearchParams(location.search).has("mini");
let tplRole = "start", tplName = "", S = {}, ST = null, page = "home", sig = "", flt = "all", tplList = [], shot = null, testRes = null, toastT;
const PAGES = [["home", "◉", "nav.home"], ["tracker", "✦", "nav.tracker"], ["templates", "▣", "nav.templates"],
  ["settings", "⚙", "nav.settings"], ["updates", "⟳", "nav.updates"], ["guide", "?", "nav.guide"]];
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const t = (k, kw = {}) => (S[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => kw[n] ?? "");
const fmtT = s => [s / 3600 | 0, (s / 60 | 0) % 60, s % 60].map(n => String(n).padStart(2, "0")).join(":");
const num = n => Number(n).toLocaleString();
const tog = (k, on) => `<div class="tog ${on ? "on" : ""}" data-tog="${k}"></div>`;
function toast(m) { clearTimeout(toastT); document.querySelectorAll(".toast").forEach(e => e.remove());
  const d = document.createElement("div"); d.className = "toast"; d.textContent = m; document.body.append(d); toastT = setTimeout(() => d.remove(), 2200); }
const cname = c => c.name || t(c.key);

async function init() {
  document.body.classList.toggle("mini", MINI);
  ST = await api.state(); await loadStrings(); tick(); setInterval(tick, 400);
}
async function loadStrings() { S = await api.strings(ST.cfg.ui_language); document.documentElement.lang = ST.cfg.ui_language; }
async function tick() {
  const prevLang = ST && ST.cfg.ui_language;
  try { ST = await api.state(); } catch (e) { return; }
  if (ST.cfg.ui_language !== prevLang) await loadStrings();
  document.documentElement.dataset.theme = ST.cfg.theme;
  render();
}
function render(force) {
  const a = document.activeElement, editing = a && a.matches && a.matches("input,select") && !MINI;
  const s = JSON.stringify([page, flt, ST.cfg.ui_language, ST.cfg.theme, ST.engine, ST.tracker.rev, ST.week, ST.guide, ST.tpl_counts,
    ST.update, ST.log.length && ST.log.at(-1).n, tplList.length, !!shot, testRes, ST.cfg.guide_dismissed]);
  if (!force && (s === sig || (editing && !shot))) return;
  sig = s;
  if (MINI) return renderMini();
  const tit = PAGES.find(p => p[0] === page)[2];
  const wk = ST.week ? `<span class="badge">${t("wk.label", {n: ST.week.n})} · ${t("wk.left", {d: ST.week.d, h: ST.week.h})}</span>` : "";
  $("#app").innerHTML = `
  <aside class="rail"><div class="brand"><img src="logo.png" alt=""><span>Easy Rewards</span></div>
    ${PAGES.map(p => `<button class="nav ${page === p[0] ? "on" : ""}" data-page="${p[0]}"><i>${p[1]}</i><span>${t(p[2])}</span></button>`).join("")}
    <div class="ver">v${esc(ST.version)}</div></aside>
  <section class="main"><header class="top"><h1>${t(tit.replace("nav.", "") === "home" ? "home.title" : tit)}</h1>${wk}
    <div class="seg">${["ru", "en", "uk"].map(l => `<button class="${ST.cfg.ui_language === l ? "on" : ""}" data-ui="${l}">${l.toUpperCase()}</button>`).join("")}</div>
    <button class="icon" data-act="theme" title="${t("set.theme")}">${ST.cfg.theme === "dark" ? "☀" : "☾"}</button>
    <button class="icon" data-act="mini" title="${t("mini.open")}">⧉</button></header>
    <div class="page">${PAGE[page]()}</div></section>${shot ? overlay() : ""}`;
  if (shot) bindShot();
}

// ---------------------------------------------------------------- pages
const PAGE = {
  home() {
    const e = ST.engine, g = ST.guide, h = e.history, mx = Math.max(1, ...h.map(x => x.games + x.cycles));
    const label = !e.running ? t("btn.start") : e.paused ? t("btn.resume") : t("btn.pause");
    const done = [g.c1, g.c2, g.c3], quick = !g.dismissed && !(done.every(Boolean));
    return `<div class="grid g2">
    <div class="card hero"><div class="ring ${e.running && !e.paused ? "run" : ""}"><button data-act="main">${label}</button></div>
      <div style="flex:1"><div class="pill"><span class="dot ${e.running ? "on" : ""}"></span>${t("state." + e.state)}</div>
        <p class="mute" style="margin:10px 0">${t("hotkeys")}</p>
        <div class="row"><button class="btn" data-act="stop">${t("btn.stop")}</button><button class="btn" data-act="reset">${t("btn.reset")}</button></div></div></div>
    <div class="card"><div class="grid g4"><div class="stat"><b>${e.games}</b><span>${t("stat.games")}</span></div>
      <div class="stat"><b>${e.cycles}</b><span>${t("stat.cycles")}</span></div><div class="stat"><b>${fmtT(e.runtime)}</b><span>${t("stat.time")}</span></div>
      <div class="stat"><b>${(e.score * 100 | 0)}%</b><span>${t("stat.match")}</span></div></div>
      <h3 style="margin-top:16px">${t("home.last_hour")}</h3><div class="bars">${h.map(x => `<div style="height:${Math.max(4, (x.games + x.cycles) / mx * 100)}%"></div>`).join("")}</div></div>
    ${quick ? `<div class="card"><h3>${t("guide.card")}</h3>${[1, 2, 3].map(i => `<div class="todo"><div class="chk ${done[i - 1] ? "on" : ""}">${done[i - 1] ? "✓" : ""}</div>${t("guide.c" + i)}</div>`).join("")}
      <div class="row" style="margin-top:8px"><button class="btn sm pri" data-page="guide">${t("guide.open")}</button><button class="btn sm" data-act="dismiss">${t("guide.dismiss")}</button></div></div>` : ""}
    <div class="card" style="${quick ? "" : "grid-column:1/-1"}"><h3>${t("log.title")}</h3><div class="log">${ST.log.slice().reverse().map(r => `${r.t}  ${esc(t(r.key, r.kw))}`).join("<br>") || "—"}</div></div></div>`;
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
      <div class="row"><select class="in" id="boost" style="width:auto">${[1, 1.5, 2].map(b => `<option ${T.boost == b ? "selected" : ""} value="${b}">×${b}</option>`).join("")}</select>
        <input class="in" id="odds" type="number" value="${T.odds}" style="width:120px" title="${t("trk.luck_odds")}"></div>
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
    <div class="row" style="margin-bottom:10px"><select class="in" id="role" style="width:auto">${["start", "result", "wait"].map(r => `<option value="${r}" ${tplRole === r ? "selected" : ""}>${t("tpl.role_" + r)}</option>`).join("")}</select>
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
      ${f(t("set.ui_language"), `<div class="seg">${["ru", "en", "uk"].map(l => `<button class="${c.ui_language === l ? "on" : ""}" data-ui="${l}">${l.toUpperCase()}</button>`).join("")}</div>`)}
      ${f(t("set.theme"), `<div class="seg">${["light", "dark"].map(l => `<button class="${c.theme === l ? "on" : ""}" data-theme="${l}">${t("theme." + l)}</button>`).join("")}</div>`)}
      ${f(t("set.game_language"), `<select data-cfg="language">${["ru", "en", "uk"].map(l => `<option ${c.language === l ? "selected" : ""}>${l}</option>`).join("")}</select>`)}
      <h3 style="margin-top:18px">${t("set.season")}</h3>${f(t("set.week_start"), `<input type="datetime-local" id="wk" value="${ST.tracker.week_start}">`)}<div class="mute">${t("set.week_hint")}</div>
      <h3 style="margin-top:18px">${t("set.hotkeys")}</h3><div class="mute">${t("set.hotkeys_text")}</div></div>
    <div class="card"><h3>${t("set.recognition")}</h3>
      ${f(t("set.threshold"), sl("threshold", .3, .99, .01, c.threshold))}${f(t("set.scan"), sl("scan_interval", .1, 3, .1, c.scan_interval))}${f(t("set.delay"), sl("click_delay", 0, 10, .5, c.click_delay))}
      ${f(t("set.foreground"), tog("require_foreground", c.require_foreground))}${f(t("set.focus"), tog("auto_focus", c.auto_focus))}
      <h3 style="margin-top:18px">${t("set.movement")}</h3>${f(t("afk.enabled"), tog("afk_enabled", c.afk_enabled))}
      ${f(t("afk.interval"), sl("afk_interval", 2, 30, 1, c.afk_interval))}${f(t("afk.hold"), sl("afk_hold", .5, 6, .5, c.afk_hold))}${f(t("afk.keys"), `<input type="text" data-cfg="afk_keys" value="${esc(c.afk_keys)}" maxlength="4">`)}</div></div>`;
  },
  updates() {
    const u = ST.update, msg = {idle: "", need_url: t("upd.need_url"), checking: t("upd.checking"), latest: t("upd.latest", {v: u.version}),
      available: t("upd.available", {v: u.version}), installed: t("upd.done_running", {v: u.version}), error: t("upd.failed", {err: u.error})}[u.status] || "";
    return `<div class="card" style="max-width:640px"><p class="mute" style="margin-top:0">${t("upd.subtitle")}</p><p>${t("upd.version", {v: ST.version})}</p>
      <input class="in" id="uurl" type="url" placeholder="https://…/version.json" value="${esc(ST.cfg.update_url)}">
      <div class="field"><span>${t("upd.auto")}</span>${tog("auto_update", ST.cfg.auto_update)}</div>
      <div class="row"><button class="btn pri" data-act="ucheck">${t("upd.check")}</button>${u.status === "available" ? `<button class="btn" data-act="uinst">${t("upd.install")}</button>` : ""}</div>
      <p>${esc(msg)}</p><div class="warnbox">${t("upd.warn")}</div></div>`;
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
      <span class="mute">${e.games}/${e.cycles}</span></div>
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
  if (a === "main") { const e = ST.engine; await (e.running ? api.pause() : api.start()); return tick(); }
  if (a === "stop") { await api.stop(); return tick(); }
  if (a === "reset") { await api.reset_stats(); return tick(); }
  if (a === "mini") return api.open_mini();
  if (a === "dismiss") return patch({guide_dismissed: true});
  if (a === "tok") { await api.tokens_add(1); return tick(); }
  if (a === "tokm") { await api.tokens_add(-1); return tick(); }
  if (a === "newc") { if (v("nc").trim()) { await api.counter_new(v("nc"), v("ng")); tick(); } return; }
  if (a === "addp") { if (v("pn").trim()) { await api.prize_add(v("pn")); tick(); } return; }
  if (a === "exp") { const r = await api.tracker_export(); if (r.ok) toast(t("trk.exported", {path: r.path})); return; }
  if (a === "imp") { const r = await api.tracker_import(); if (r.ok) toast(t("trk.imported")); else if (r.error !== "cancelled") toast(t("trk.import_failed")); return tick(); }
  if (a === "rst") { if (confirm(t("trk.confirm_reset"))) { await api.tracker_reset(); tick(); } return; }
  if (a === "cap") { box = null; toast(t("tpl.capture_wait", {s: 5})); const r = await api.capture_screenshot(5); if (r.ok) { shot = r; render(true); } return; }
  if (a === "cancelshot") { shot = null; box = null; return render(true); }
  if (a === "saveshot") { if (!box) return; const r = await api.save_template(tplRole, tplName || "button", box.fx, box.fy, box.fw, box.fh);
    shot = null; box = null; tplList = await api.templates(); toast(r.ok ? t("toast.saved") : r.error); return tick(); }
  if (a === "test") { testRes = await api.test_templates(); return render(true); }
  if (a === "ucheck") { await api.update_check(v("uurl")); return tick(); }
  if (a === "uinst") { await api.update_install(); return tick(); }
});
document.addEventListener("input", ev => { const e = ev.target; if (e.id === "tname") tplName = e.value; if (e.dataset.cfg && e.type === "range") { const o = $(`[data-out="${e.dataset.cfg}"]`); if (o) o.textContent = e.value; } });
document.addEventListener("change", async ev => { const e = ev.target; if (e.id === "role") tplRole = e.value;
  if (e.dataset.cfg) { await patch({[e.dataset.cfg]: e.value}); toast(t("toast.saved")); }
  else if (e.id === "wk") { await api.tracker_set({week_start: e.value}); tick(); }
  else if (e.id === "boost" || e.id === "odds") { await api.tracker_set({boost: $("#boost").value, odds: $("#odds").value}); tick(); } });
init();
