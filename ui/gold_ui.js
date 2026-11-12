/* Fortnite Pirate Token / Gold UI enhancement layer.
   No backend, engine, purchase, licence or update behavior is changed.
   This file enhances the existing EasyRewards frontend.
   Core anti-AFK functionality remains in app.js, core.py, backend.py and winio.py. */
(() => {
  "use strict";
  if (typeof PAGE === "undefined" || typeof render !== "function" || typeof PAGES === "undefined") {
    window.easyRewardsBootError?.("Не найден основной интерфейс EasyRewards.");
    return;
  }
  let notificationOpen = false;
  let profileOpen = false;
  const ui = (ru, en, uk) => ({ru, en, uk})[ST?.cfg?.ui_language || "ru"] || ru;
  const safe = value => esc(value == null ? "" : value);
  const statusBadge = () => `<span class="gold-status"><i class="gold-led ${ST.engine.running && !ST.engine.paused ? "active" : ""}"></i>${safe(t("state." + ST.engine.state))}</span>`;
  const updateReady = () => ["available", "downloading", "ready"].includes(ST.update?.status) && hiddenUpdateVersion !== ST.update.version;
  const updateCount = () => updateReady() ? 1 : 0;
  const navTitle = id => {
    if (id === "updates") return ui("Новости", "News", "Новини");
    if (id === "account") return ui("Аккаунт", "Account", "Акаунт");
    if (id === "subscriptions") return ui("Подписка", "Subscription", "Підписка");
    return t("nav." + id);
  };
  const remaining = () => {
    const sub = ST.subscription || {};
    const secs = sub.remaining_seconds;
    if (sub.enabled && typeof secs === "number" && Number.isFinite(secs) && secs >= 0) {
      const days = Math.floor(secs / 86400);
      const hours = Math.floor((secs % 86400) / 3600);
      const minutes = Math.floor((secs % 3600) / 60);
      return ui(`${days} д ${hours} ч ${minutes} мин`, `${days}d ${hours}h ${minutes}m`, `${days} д ${hours} г ${minutes} хв`);
    }
    return "—";
  };
  const subscriptionNote = () => {
    const sub = ST.subscription || {};
    return sub.enabled && typeof sub.remaining_seconds === "number"
      ? ui("Подписка активна", "Subscription active", "Підписка активна")
      : ui("Подписка ещё не активна", "Subscription not active yet", "Підписка ще не активна");
  };
  // Display only release facts, never marketing placeholders or invented patch notes.
  const newsItems = () => {
    const releases = Array.isArray(ST.release_news) ? ST.release_news : [];
    const unique = new Map();
    for (const r of releases) {
      if (!r || typeof r !== "object") continue;
      const version = String(r.version || "");
      if (!/^\d+\.\d+\.\d+(?:-beta)?$/.test(version)) continue;
      const key = version.replace(/-beta$/, "");
      if (unique.has(key)) continue; // the bundled beta has richer offline notes
      const notes = String(r.notes || "").trim();
      unique.set(key, {
        version, title: String(r.title || ("Fortnite Pirate Token v" + version)),
        notes, date: String(r.published_at || r.date || ""),
        beta: version.endsWith("-beta")
      });
    }
    return [...unique.values()].sort((a, b) => {
      const left = a.version.match(/\d+/g).slice(0, 3).map(Number);
      const right = b.version.match(/\d+/g).slice(0, 3).map(Number);
      for (let i = 0; i < 3; ++i) if (left[i] !== right[i]) return right[i] - left[i];
      return 0;
    });
  };
  const releaseDate = value => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const lang = ({en:"en-GB",uk:"uk-UA"})[ST?.cfg?.ui_language] || "ru-RU";
    return new Intl.DateTimeFormat(lang, {day:"numeric",month:"long",year:"numeric"}).format(date);
  };
  const newsIcon = index => ["⚙", "🔧", "⌘", "🛠", "</>", "⚙"][index % 6];
  const newsMarkup = (full = false) => {
    const all = newsItems();
    const items = full ? all : all.slice(0, 3);
    const headline = ui("Новости и обновления", "News and updates", "Новини й оновлення");
    const noNews = ui("Пока нет доступных патчей. Попробуй проверить обновления позже.",
      "No published patches are available. Check again later.",
      "Опублікованих оновлень поки немає. Перевірте пізніше.");
    const card = (item, index) => '<button type="button" class="gold-patch-row" data-news-open="' + index + '">' +
      '<span class="gold-patch-thumb" aria-hidden="true">' + safe(newsIcon(index)) + '</span>' +
      '<span class="gold-patch-row-text"><span class="gold-mini-tag">' +
      (item.beta ? ui("Бета", "Beta", "Бета") : ui("Обновление", "Update", "Оновлення")) +
      ' · v' + safe(item.version) + '</span><strong>' + safe(item.title) + '</strong>' +
      '<small>' + safe(item.notes).slice(0, full ? 230 : 125) + '</small></span>' +
      (releaseDate(item.date) ? '<time>' + safe(releaseDate(item.date)) + '</time>' : '') +
      '<span class="gold-patch-arrow" aria-hidden="true">›</span></button>';
    return '<section class="card gold-news ' + (full ? "gold-news-full gold-news-archive" : "") + '">' +
      '<div class="gold-section-head"><div><span class="gold-overline">' +
      ui("ИСТОРИЯ ПАТЧЕЙ", "PATCH HISTORY", "ІСТОРІЯ ОНОВЛЕНЬ") +
      '</span><h2>' + headline + '</h2></div>' +
      (full ? '' : '<button class="gold-text-link" data-page="updates">' + ui("Все новости", "All news", "Усі новини") + ' →</button>') +
      '</div>' +
      (full && all.length ? '<button type="button" class="gold-patch-feature" data-news-open="0">' +
        '<span class="gold-overline">' + ui("ПОСЛЕДНЕЕ ОБНОВЛЕНИЕ", "LATEST RELEASE", "ОСТАННЄ ОНОВЛЕННЯ") + '</span>' +
        '<strong>' + safe(all[0].title) + '</strong><span>' +
        safe(all[0].notes).slice(0, 240) + '</span><b>' + ui("Читать патч", "Read patch", "Читати зміни") + ' →</b></button>' : '') +
      (items.length ? '<div class="gold-patch-list">' + items.map(card).join("") + '</div>'
        : '<p class="gold-patch-empty">' + noNews + '</p>') + '</section>';
  };
  // Treat notes as UNTRUSTED plain text/Markdown, never as HTML.
  const patchNotesHtml = value => {
    const text = String(value || "").slice(0, 12000);
    if (!text.trim()) return '<p>' + ui("Описание обновления пока не опубликовано.",
      "Release notes are not available.", "Опис оновлення поки не опубліковано.") + '</p>';
    const lines = text.split(/\r?\n/);
    return lines.map(raw => {
      const line = raw.trim().replace(/\*\*/g, "");
      if (!line) return "";
      const h = line.match(/^#{1,5}\s+(.+)$/);
      if (h) return "<h3>" + safe(h[1]) + "</h3>";
      const bullet = line.match(/^(?:[-*+]|\d+[.)])\s+(.+)$/);
      if (bullet) return '<p class="gold-patch-bullet"><span aria-hidden="true">•</span>' + safe(bullet[1]) + "</p>";
      return "<p>" + safe(line) + "</p>";
    }).join("");
  };
  let patchOverlay = null, patchOpener = null;
  function closePatch() {
    if (!patchOverlay) return;
    patchOverlay.remove();
    patchOverlay = null;
    document.documentElement.classList.remove("gold-patch-is-open");
    if (patchOpener?.isConnected) patchOpener.focus();
    patchOpener = null;
  }
  function openPatch(index, opener) {
    const item = newsItems()[index];
    if (!item || MINI) return;
    closePatch();
    patchOpener = opener;
    patchOverlay = document.createElement("div");
    patchOverlay.className = "gold-patch-overlay";
    const back = ui("К новостям", "Back to news", "До новин");
    patchOverlay.innerHTML = '<article class="gold-patch-dialog" role="dialog" aria-modal="true" aria-labelledby="gold-patch-title" tabindex="-1">' +
      '<header class="gold-patch-dialog-head"><button type="button" class="gold-patch-back" data-news-close="1">← ' + back +
      '</button><button type="button" class="gold-patch-close" data-news-close="1" aria-label="' +
      ui("Закрыть", "Close", "Закрити") + '">×</button></header>' +
      '<div class="gold-patch-body"><div class="gold-patch-banner"><span class="gold-mini-tag">' +
      ui("ИСТОРИЯ ОБНОВЛЕНИЙ", "RELEASE HISTORY", "ІСТОРІЯ ОНОВЛЕНЬ") + '</span>' +
      '<h2 id="gold-patch-title">' + safe(item.title) + '</h2><p>v' + safe(item.version) +
      (releaseDate(item.date) ? ' · ' + safe(releaseDate(item.date)) : '') + '</p></div>' +
      '<div class="gold-patch-copy">' + patchNotesHtml(item.notes) + '</div></div></article>';
    document.body.appendChild(patchOverlay);
    document.documentElement.classList.add("gold-patch-is-open");
    patchOverlay.querySelector(".gold-patch-dialog").focus();
  }
  document.addEventListener("click", ev => {
    if (patchOverlay) {
      if (ev.target === patchOverlay || ev.target.closest("[data-news-close]")) {
        ev.preventDefault(); ev.stopImmediatePropagation(); closePatch(); return;
      }
      if (patchOverlay.contains(ev.target)) {
        ev.stopImmediatePropagation(); return;
      }
    }
    const open = ev.target.closest("[data-news-open]");
    if (open) {
      ev.preventDefault(); ev.stopImmediatePropagation();
      openPatch(Number(open.dataset.newsOpen), open);
    }
  }, true);
  document.addEventListener("keydown", ev => {
    if (!patchOverlay) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopImmediatePropagation(); closePatch(); return; }
    if (ev.key !== "Tab") return;
    const controls = Array.from(patchOverlay.querySelectorAll("button:not([disabled])"));
    const first = controls[0], last = controls[controls.length - 1];
    if (!first || !last) return;
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  }, true);
  const subCard = () => `<button type="button" class="card gold-sub-card" data-page="subscriptions">
      <span class="gold-overline">${ui("ТВОЙ ДОСТУП", "YOUR ACCESS", "ТВІЙ ДОСТУП")}</span>
      <span class="gold-crown">♛</span><strong>${ui("Подписка", "Subscription", "Підписка")}</strong>
      <span class="gold-sub-note">${subscriptionNote()}</span>
      <span class="gold-remain-label">${ui("Осталось времени", "Time remaining", "Залишилось часу")}</span>
      <span class="gold-remain">${remaining()}</span>
      <span class="gold-sub-footer">${ui("Управление подпиской", "Manage subscription", "Керування підпискою")} <span>↗</span></span>
    </button>`;
  const originalRender = render;
  const originalUpdates = PAGE.updates;
  const originalSettings = PAGE.settings;
  PAGES.splice(0, PAGES.length,
    ["home", "⌂", "nav.home"], ["afk", "↝", "nav.afk"], ["tracker", "◈", "nav.tracker"],
    ["templates", "▣", "nav.templates"], ["updates", "▤", "nav.updates"],
    ["subscriptions", "♛", "nav.subscriptions"], ["settings", "⚙", "nav.settings"],
    ["support", "⚑", "nav.support"], ["account", "◉", "nav.account"], ["guide", "?", "nav.guide"]);
  PAGE.home = function() {
    const e = ST.engine, hist = Array.isArray(e.history) ? e.history : [], max = Math.max(1, ...hist.map(x => x.games + x.cycles));
    const guide = ST.guide || {}, todo = !guide.dismissed && !(guide.c1 && guide.c2 && guide.c3);
    const stats = [
      [ui("Матчи", "Matches", "Матчі"),e.games],
      [ui("Циклы", "Cycles", "Цикли"),e.cycles],
      [ui("Время", "Time", "Час"),fmtT(e.runtime)],
      [ui("Награды", "Rewards", "Нагороди"),num(e.rewards || 0)]];
    return `<section class="gold-hero"><div class="gold-hero-copy">
      <div class="gold-hero-kicker"><span>✦</span> ${ui("ТВОЙ ПОМОЩНИК В FORTNITE", "YOUR FORTNITE COMPANION", "ТВІЙ ПОМІЧНИК У FORTNITE")}</div>
      <h2>${ui("Добро пожаловать в", "Welcome to", "Ласкаво просимо до")}<br><span>Fortnite Pirate Token</span></h2>
      <p class="gold-slogan">${ui("Получай награды — не трать силы и нервы.", "Earn rewards — save your time and energy.", "Отримуй нагороди — бережи час і сили.")}</p>
      <div class="gold-hero-actions"><button class="btn pri gold-play" data-act="start" ${e.running ? "disabled" : ""}><span>▶</span> ${t("btn.start")}</button>
       <button class="btn gold-stop" data-act="stop" ${!e.running && !ST.controls?.start_pending ? "disabled" : ""}>■ ${t("btn.stop")}</button>
       <button class="btn gold-pause" data-act="pause" ${!e.running ? "disabled" : ""}>${e.paused ? "▶" : "Ⅱ"} ${e.paused ? t("btn.resume") : t("btn.pause")}</button></div>
      <div class="gold-hero-meta">${statusBadge()}<span class="gold-version">${ui("Версия", "Version", "Версія")} ${safe(ST.version)}</span></div>
    </div><div class="gold-hero-visual" aria-hidden="true">
      <div class="gold-hero-halo"></div><img class="gold-chest" src="hero_chest.svg" alt="">
      <img class="gold-token token-a" src="pirate_token.png" alt=""><img class="gold-token token-b" src="pirate_token.png" alt=""><img class="gold-token token-c" src="pirate_token.png" alt="">
      <span class="gold-spark spark-a">✦</span><span class="gold-spark spark-b">✦</span></div></section>
    <div class="gold-dashboard"><div class="gold-dashboard-main">${newsMarkup()}
      <div class="gold-summary-grid"><section class="card gold-metrics"><div class="gold-section-head"><div><span class="gold-overline">${ui("ТВОЙ ПРОГРЕСС", "YOUR PROGRESS", "ТВІЙ ПРОГРЕС")}</span><h2>${ui("Статистика", "Statistics", "Статистика")}</h2></div></div>
       <div class="gold-stat-grid">${stats.map(([name,value],index)=>`<div class="gold-stat"><b data-live="${["games","cycles","runtime","rewards"][index]}">${safe(value)}</b><span>${safe(name)}</span></div>`).join("")}</div>
       <div class="gold-chart-label">${t("home.last_hour")}</div><div class="gold-bars">${hist.map(h=>`<i style="height:${Math.max(4,(h.games+h.cycles)/max*100)}%"></i>`).join("")}</div></section>
      <section class="card gold-metrics gold-diagnostics"><div class="gold-section-head"><div><span class="gold-overline">${ui("ДИАГНОСТИКА", "DIAGNOSTICS", "ДІАГНОСТИКА")}</span><h2>${t("diag.heading")}</h2></div></div>
        <div class="focus-line"><span>${t("diag.game")}</span><b class="${ST.diagnostics?.game_active ? "good" : "muted"}">${ST.diagnostics?.game_active ? t("diag.active") : t("diag.inactive")}</b></div>
        <div class="focus-line"><span>${t("diag.foreground")}</span><b data-live="foreground-title">${safe(ST.diagnostics?.foreground_title || t("diag.none"))}</b></div>
        <div class="focus-line"><span>${t("afk.last_control")}</span><b data-live="last-control">${safe(ST.controls?.last || "—")} ${safe(ST.controls?.time || "")} (${Number(ST.controls?.sequence || 0)})</b></div>
        <div class="focus-line"><span>${t("diag.inputs")}</span><b>${safe(e.input_count || 0)}${e.last_input ? " · "+safe(e.last_input) : ""}</b></div>
        ${e.input_error ? `<p class="focus-warn">${safe(e.input_error)}</p>` : ""}
        ${e.running && !ST.diagnostics?.game_active && ST.cfg.require_foreground ? `<p class="focus-warn">${t("diag.focus_hint")}</p>` : ""}
      </section></div>
      <div class="card gold-activity"><div class="gold-section-head"><div><span class="gold-overline">${ui("ЖУРНАЛ", "ACTIVITY", "ЖУРНАЛ")}</span><h2>${t("log.title")}</h2></div></div>
        <div class="log">${ST.log.slice(-6).reverse().map(r=>`${safe(r.t)}  ${safe(t(r.key, r.kw))}`).join("<br>") || "—"}</div></div>
    </div><div class="gold-dashboard-side">${subCard()}
      <div class="card gold-quick"><span class="gold-overline">${ui("БЫСТРЫЕ ДЕЙСТВИЯ", "QUICK ACTIONS", "ШВИДКІ ДІЇ")}</span>
       <h2>${ui("Под контролем", "In control", "Під контролем")}</h2>
       <div class="gold-quick-row"><span>${t("home.session")}</span><strong>${num(e.rewards || 0)} ✦</strong></div>
       <div class="gold-quick-row"><span>${t("home.all_time")}</span><strong>${num(ST.reward?.total || 0)} ✦</strong></div>
       <div class="gold-quick-row"><span>${t("stat.time")}</span><strong><span data-live="runtime">${fmtT(e.runtime)}</span></strong></div>
       <div class="gold-quick-actions"><button class="btn sm" data-page="afk">${ui("Настройки анти-AFK", "Anti-AFK settings", "Налаштування анти-AFK")} ↗</button>
       <button class="btn sm" data-act="ptest" data-target="fortnite">${ui("Тест ввода (F6)", "Input test (F6)", "Тест вводу (F6)")}</button>
       <button class="btn sm" data-act="reset">${t("btn.reset")}</button></div>
       <small>${hotkeySummary()}</small></div>
      ${todo ? `<div class="card gold-tip"><span class="gold-overline">${ui("ПЕРВЫЙ ЗАПУСК", "GET STARTED", "ПЕРШИЙ ЗАПУСК")}</span><p>${t("guide.card")}</p>
       <button class="btn pri sm" data-page="guide">${t("guide.open")}</button><button class="btn sm" data-act="dismiss">${t("guide.dismiss")}</button></div>` : ""}
    </div></div>`;
  };
  PAGE.updates = function() {
    return newsMarkup(true) + `<div class="gold-updater">${originalUpdates()}</div>`;
  };
  PAGE.settings = function() {
    return `<div class="card gold-settings-shortcut"><div><span class="gold-overline">FORTNITE PIRATE TOKEN</span><h2>${ui("Настройки анти-AFK", "Anti-AFK settings", "Налаштування анти-AFK")}</h2>
       <p>${ui("Движение, камера, задержки и дополнительные действия находятся в отдельном разделе.", "Movement, camera, delays and extra actions are available in a dedicated section.", "Рухи, камера, затримки та додаткові дії розміщені в окремому розділі.")}</p></div>
       <button class="btn pri" data-page="afk">${ui("Открыть анти-AFK", "Open anti-AFK", "Відкрити анти-AFK")} ↗</button></div>` + originalSettings();
  };
  PAGE.account = function() {
    return `<section class="card gold-account"><div class="gold-account-identity"><img src="pirate_token.png" alt=""><div><span class="gold-overline">${ui("ЛОКАЛЬНЫЙ ПРОФИЛЬ", "LOCAL PROFILE", "ЛОКАЛЬНИЙ ПРОФІЛЬ")}</span>
      <h2>${ui("Профиль пользователя", "User profile", "Профіль користувача")}</h2><p>${ui("Авторизация аккаунта ещё не подключена.", "Account sign-in is not connected yet.", "Вхід в акаунт ще не підключено.")}</p></div></div>
      <div class="gold-account-facts"><div><span>${ui("Версия приложения", "App version", "Версія застосунку")}</span><b>v${safe(ST.version)}</b></div>
      <div><span>${ui("Подписка", "Subscription", "Підписка")}</span><b>${subscriptionNote()}</b></div>
      <div><span>${ui("Осталось", "Remaining", "Залишилось")}</span><b>${remaining()}</b></div></div>
      <button class="btn pri" data-page="subscriptions">${ui("Открыть подписку", "Open subscription", "Відкрити підписку")}</button></section>`;
  };
  function renderGold(force) {
    const oldSig = sig;
    const savedNavScroll = document.querySelector('#app .gold-nav')?.scrollTop || 0;
    originalRender(force);
    if (MINI || (!force && sig === oldSig)) return;
    const root = document.getElementById("app");
    const rail = root?.querySelector(".rail"), top = root?.querySelector(".top");
    if (!rail || !top) return;
    rail.innerHTML = `<div class="brand gold-brand"><img src="pirate_token.png" alt=""><span><b>FORTNITE</b><em>PIRATE TOKEN</em><small>LAUNCHER</small></span></div>
      <div class="gold-nav-label">${ui("МЕНЮ", "MENU", "МЕНЮ")}</div>
      <nav class="gold-nav">${PAGES.map(p=>`<button class="nav ${page === p[0] ? "on" : ""}" data-page="${p[0]}"><i>${p[1]}</i><span>${safe(navTitle(p[0]))}</span>${p[0] === "updates" && updateCount() ? '<b class="gold-nav-dot"></b>' : ""}</button>`).join("")}</nav>
      <div class="gold-rail-bottom"><button class="gold-rail-profile" data-page="account"><img src="pirate_token.png" alt=""><span><strong>${ui("Мой профиль", "My profile", "Мій профіль")}</strong><small>${subscriptionNote()}</small></span><b>↗</b></button>
        <div class="gold-rail-foot">${ui("Версия", "Version", "Версія")} ${safe(ST.version)}</div></div>`;
    top.innerHTML = `<div class="gold-top-location"><span>${ui("FORTNITE / ЛАУНЧЕР", "FORTNITE / LAUNCHER", "FORTNITE / ЛАУНЧЕР")}</span><h1>${safe(navTitle(page))}</h1></div>
      <div class="gold-top-right"><span class="gold-top-version">v${safe(ST.version)}</span>
      <button class="gold-header-btn" data-gold="notifications" title="${ui("Уведомления", "Notifications", "Сповіщення")}" aria-label="${ui("Уведомления", "Notifications", "Сповіщення")}" aria-expanded="${notificationOpen}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></svg>${updateCount()?'<i class="gold-alert-dot"></i>':""}</button>
      <button class="gold-header-btn" data-page="settings" title="${ui("Настройки", "Settings", "Налаштування")}" aria-label="${ui("Настройки", "Settings", "Налаштування")}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .3.4 1 1.6-2 2-1.6-1-.4-.3a9 9 0 0 1-2.1.9l-.3 1.8h-2.8l-.3-1.8a9 9 0 0 1-2.1-.9l-1.9 1.3-2-2 1-1.6.3-.4A9 9 0 0 1 5.6 13l-1.8-.3v-2.8l1.8-.3a9 9 0 0 1 .9-2.1L5.2 5.6l2-2 1.9 1.3a9 9 0 0 1 2.1-.9l.3-1.8h2.8l.3 1.8a9 9 0 0 1 2.1.9l1.9-1.3 2 2-1.3 1.9a9 9 0 0 1 .9 2.1l1.8.3v2.8l-1.8.3a9 9 0 0 1-.8 2Z" transform="translate(-.9 0) scale(.98)"/></svg></button>
      <button class="gold-avatar" data-gold="profile" aria-label="${ui("Профиль", "Profile", "Профіль")}" aria-expanded="${profileOpen}"><img src="pirate_token.png" alt=""><span>⌄</span></button>
      ${notificationOpen ? `<div class="gold-pop gold-notify"><div class="gold-pop-head"><b>${ui("Уведомления", "Notifications", "Сповіщення")}</b><span>${updateCount() ? ui("1 новое", "1 new", "1 нове") : ui("Нет новых", "No new", "Немає нових")}</span></div>
        ${updateCount() ? `<p>${ui("Доступна версия", "Version available", "Доступна версія")} ${safe(ST.update.version)}</p>` : `<p>${ui("Новых уведомлений пока нет. Новости об обновлениях доступны в разделе «Новости».", "No new notifications. Read recent updates in News.", "Нових сповіщень поки немає. Новини оновлень — у розділі «Новини».")}</p>`}
        <button class="btn sm pri" data-page="updates">${ui("Открыть новости", "Open News", "Відкрити новини")} ↗</button></div>` : ""}
      ${profileOpen ? `<div class="gold-pop gold-profile-pop"><div class="gold-pop-head"><b>${ui("Мой профиль", "My profile", "Мій профіль")}</b></div>
        <p>${subscriptionNote()}</p><div class="gold-pop-remain">${ui("До конца подписки", "Subscription remaining", "До завершення підписки")} <b>${remaining()}</b></div>
        <button class="btn sm" data-page="account">${ui("Аккаунт", "Account", "Акаунт")}</button><button class="btn sm pri" data-page="subscriptions">${ui("Подписка", "Subscription", "Підписка")}</button></div>` : ""}
      </div>`;
    const afterNav = root.querySelector('.gold-nav');
    if (afterNav) afterNav.scrollTop = savedNavScroll;
    refreshLiveMetrics();
  }
  render = renderGold;
  document.addEventListener("click", ev => {
    const gold = ev.target.closest("[data-gold]");
    if (gold) {
      if (gold.dataset.gold === "notifications") { notificationOpen = !notificationOpen; profileOpen = false; }
      if (gold.dataset.gold === "profile") { profileOpen = !profileOpen; notificationOpen = false; }
      renderGold(true);
      ev.stopImmediatePropagation();
      ev.preventDefault();
      return;
    }
    if (ev.target.closest("[data-page]")) { notificationOpen = false; profileOpen = false; return; }
    if (!ev.target.closest(".gold-pop")) {
      if (notificationOpen || profileOpen) {
        notificationOpen = false; profileOpen = false;
        // The listener runs during capture, BEFORE app.js's click handler.
        // Rebuilding here removes the clicked element and loses control clicks.
        setTimeout(() => renderGold(true), 0);
      }
    }
  }, true);
})();
