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
  const newsItems = () => {
    const items = [];
    // Release notes come from official GitHub Releases, not a manually updated list.
    const published = Array.isArray(ST.release_news) ? ST.release_news : [];
    for (const r of published.slice(0, 7)) {
      items.push({kind:"new", icon:"✦", label:ui("Релиз " + r.version, "Release " + r.version, "Реліз " + r.version),
        title:r.title || `Easy Rewards v${r.version}`,
        body:r.notes || ui("Опубликовано обновление программы.", "An application update is available.", "Доступне оновлення програми.")});
    }
    const u = ST.update || {};
    if (["available", "downloading", "ready"].includes(u.status)) {
      items.push({kind:"new", icon:"↓", label:ui("Доступно обновление", "Update available", "Доступне оновлення"),
        title:ui(`Новая версия ${u.version || ""}`, `New version ${u.version || ""}`, `Нова версія ${u.version || ""}`),
        body:u.notes || ui("Перейди в раздел новостей, чтобы установить обновление.", "Open News to install the update.", "Відкрий Новини, щоб встановити оновлення.")});
    }
    if (!published.some(r => r.version === "1.3.3")) items.push({kind:"repair",icon:"✦",label:ui("Версия 1.3.3", "Version 1.3.3", "Версія 1.3.3"),
      title:ui("Исправления анти-AFK и новый лаунчер", "Anti-AFK fixes and new launcher", "Виправлення анти-AFK та новий лаунчер"),
      body:ui("Диагностика ввода, улучшенная остановка движка и обновлённый золотой интерфейс.",
              "Input diagnostics, more reliable engine stopping and a refreshed gold interface.",
              "Діагностика вводу, покращена зупинка рушія та оновлений золотий інтерфейс.")});
    if (!published.some(r => r.version === "1.3.2")) items.push({kind:"version",icon:"✧",label:ui("Версия 1.3.2", "Version 1.3.2", "Версія 1.3.2"),
      title:ui("Улучшена система обновлений", "Improved update system", "Покращено систему оновлень"),
      body:ui("Проверка GitHub Releases и загрузка установщика с проверкой SHA-256.", "GitHub Releases checks and verified installer download.", "Перевірка GitHub Releases та завантаження перевіреного інсталятора.")});
    if (!published.some(r => r.version === "1.3.0")) items.push({kind:"afk",icon:"↝",label:ui("Версия 1.3.0", "Version 1.3.0", "Версія 1.3.0"),
      title:ui("Расширенные настройки анти-AFK", "Expanded anti-AFK controls", "Розширені налаштування анти-AFK"),
      body:ui("Параметры движений, камеры, пауз и горячих клавиш.", "Movement, camera, pauses and hotkey controls.", "Налаштування рухів, камери, пауз та гарячих клавіш.")});
    items.push({kind:"subs",icon:"♛",label:ui("В разработке", "In development", "У розробці"),
      title:ui("Подписка и оплата картой/СБП", "Subscription and card/SBP payments", "Підписка та оплата карткою/СБП"),
      body:ui("Сейчас доступен только предпросмотр. Покупки и активация отключены.", "Preview only. Purchases and activation are disabled.", "Лише попередній перегляд. Оплата та активація вимкнені.")});
    return items;
  };
  const newsMarkup = (full = false) => {
    const items = newsItems().slice(0, full ? 6 : 3);
    return `<section class="card gold-news ${full ? "gold-news-full" : ""}">
      <div class="gold-section-head"><div><span class="gold-overline">${ui("ЛЕНТА ОБНОВЛЕНИЙ", "UPDATE FEED", "СТРІЧКА ОНОВЛЕНЬ")}</span>
      <h2>${ui("Новости", "News", "Новини")}</h2></div>
      ${full ? "" : `<button class="gold-text-link" data-page="updates">${ui("Все новости", "All news", "Усі новини")} <span>↗</span></button>`}</div>
      <div class="gold-news-list">${items.map(item => `<div class="gold-news-item">
        <div class="gold-news-icon news-${item.kind}" aria-hidden="true">${item.icon}</div><div class="gold-news-copy">
        <span class="gold-mini-tag">${safe(item.label)}</span><h3>${safe(item.title)}</h3>
        <p>${safe(item.body).slice(0, full ? 600 : 160)}</p></div></div>`).join("")}</div></section>`;
  };
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
