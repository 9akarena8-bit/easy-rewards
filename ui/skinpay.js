/* SkinPay visual checkout inspired by the inventory/cart flow on skin marketplaces.
   This is a LOCAL, NON-PAYABLE PLANNER. It does not retrieve Steam inventories,
   fetch market quotes, send trade offers, initiate payments or grant access. */
(() => {
  "use strict";
  if (typeof paymentHubMarkup !== "function") return;
  const originalMarkup = paymentHubMarkup;
  const items = [];
  const chosen = new Set();
  let nextId = 1, query = "", order = "high", draftTarget = 0, feedback = "";
  const tr = (ru, en, uk) => ({ru, en, uk})[ST?.cfg?.ui_language || "ru"] || ru;
  const rub = value => new Intl.NumberFormat("ru-RU", {style:"currency",currency:"RUB",maximumFractionDigits:2}).format(value / 100);
  const escapeHtml = s => esc(String(s));
  const icons = {dota2:"♜",rust:"⛏",cs2:"⌖",tf2:"⚙",pubg:"◈",dst:"☾",naraka:"✧"};
  const gameItems = () => items.filter(item => item.game === payGame);
  const selectedItems = () => gameItems().filter(item => chosen.has(item.id));
  const moneyFromText = value => {
    const text = String(value || "").replace(/\s/g, "").replace(",", ".");
    if (!/^\d{1,7}(\.\d{1,2})?$/.test(text)) return null;
    const [whole, fraction = ""] = text.split(".");
    const kopeks = Number(whole) * 100 + Number(fraction.padEnd(2,"0"));
    return Number.isSafeInteger(kopeks) && kopeks > 0 && kopeks <= 100000000 ? kopeks : null;
  };
  const labels = () => ({
    title: tr("SKINPAY · ПЛАНИРОВЩИК", "SKINPAY · PLANNER", "SKINPAY · ПЛАНУВАЛЬНИК"),
    subtitle: tr("Инвентарь и расчёт — пока вручную. Реальные трейды будут доступны только после серверной проверки.",
      "Inventory and valuation are manual for now. Live trades need server-side verification.",
      "Інвентар і розрахунок поки вручну. Реальні обміни потребують серверної перевірки."),
    step1: tr("Выбор предметов","Choose items","Вибір предметів"),
    step2: tr("Проверка цены","Verify prices","Перевірка ціни"),
    step3: tr("Steam-обмен","Steam trade","Steam-обмін"),
    step4: tr("Активация","Activation","Активація"),
    inventory: tr("Мой список предметов","My item list","Мій список предметів"),
    noSteam: tr("Steam-инвентарь пока не подключён", "Steam inventory is not connected yet", "Steam-інвентар ще не підключено"),
    trade: tr("Войти через Steam — скоро","Steam sign-in — coming soon","Увійти через Steam — незабаром"),
    search: tr("Поиск по названию","Search by item name","Пошук за назвою"),
    sortHigh: tr("Сначала дорогие","Price: high to low","Спершу дорогі"),
    sortLow: tr("Сначала дешёвые","Price: low to high","Спершу дешеві"),
    name: tr("Название предмета","Item name","Назва предмета"),
    estimate: tr("Моя оценка, ₽","My estimate, RUB","Моя оцінка, ₽"),
    add: tr("Добавить в список","Add to list","Додати до списку"),
    empty: tr("Предметов пока нет. Добавь их вручную для проверки работы корзины.",
      "No items yet. Add items manually to try the cart.", "Предметів ще немає. Додай їх вручну."),
    clear: tr("Очистить выбор","Clear selection","Очистити вибір"),
    selected: tr("Выбрано предметов","Selected items","Обрано предметів"),
    userQuote: tr("Оценка вручную · не рыночная цена","Manual estimates · not market quotes",
      "Оцінка вручну · не ринкова ціна"),
    target: tr("Целевая сумма, ₽ (для примера)","Target RUB amount (planning only)",
      "Цільова сума, ₽ (лише для планування)"),
    auto: tr("Подобрать комбинацию","Find closest combination","Підібрати комбінацію"),
    total: tr("Сумма выбранного","Selected total","Сума обраного"),
    due: tr("Цена тарифа","Real plan price","Ціна тарифу"),
    unknown: tr("Не установлена","Not configured","Не встановлена"),
    over: tr("Сверх выбранной цели","Above draft target","Понад ціль"),
    left: tr("Не хватает до цели","Below draft target","Бракує до цілі"),
    noTarget: tr("Укажи свою условную сумму для проверки подбора предметов.",
      "Enter a planning target to test item matching.",
      "Вкажи умовну суму для перевірки підбору."),
    sampleOnly: tr("Планировщик не проводит оплату и не выдаёт доступ.",
      "This planner cannot take payments or grant access.",
      "Планувальник не приймає оплату та не надає доступ."),
    cs2: tr("CS2: возможна отмена обмена в течение 7 дней — мгновенная выдача доступа не допускается.",
      "CS2: 7-day trade reversal window; instant access cannot be granted.",
      "CS2: обмін можна скасувати протягом 7 днів; миттєвий доступ неможливий."),
    remove: tr("Удалить предмет","Remove item","Видалити предмет"),
    invalid: tr("Укажи название и положительную цену до 1 000 000 ₽ (пример, не котировка).",
      "Enter an item name and estimate of up to RUB 1,000,000.",
      "Вкажи назву та додатну ціну до 1 000 000 ₽."),
    limit: tr("Не более 16 предметов на одну игру в планировщике.",
      "The planner supports up to 16 items per game.",
      "Планувальник підтримує до 16 предметів на гру."),
    picked: tr("Комбинация подобрана только для предварительного расчёта.",
      "Combination found for planning only.",
      "Комбінацію підібрано лише для планування."),
    short: tr("Недостаточно оценённых предметов для этой суммы.",
      "Not enough estimated item value for this target.",
      "Недостатньо оціночної вартості для цілі."),
  });
  function chooseBest(all, goal) {
    if (!Number.isSafeInteger(goal) || goal <= 0 || all.length > 16) return null;
    let best = null;
    for (let mask = 1; mask < (1 << all.length); mask++) {
      let sum = 0, count = 0, ids = [];
      for (let i=0;i<all.length;i++) if (mask & (1 << i)) {
        sum += all[i].estimate_kopeks; count++; ids.push(all[i].id);
      }
      if (sum < goal) continue;
      const key = [sum - goal, count];
      if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1]))
        best = {key, ids, sum};
    }
    return best;
  }
  function checkoutMarkup() {
    const L = labels();
    const game = (ST.payment_hub?.games || []).find(g => g.id === payGame);
    const catalog = gameItems();
    const searched = catalog.filter(i => i.name.toLowerCase().includes(query.toLowerCase()));
    searched.sort((a,b) => order === "high" ? b.estimate_kopeks-a.estimate_kopeks : a.estimate_kopeks-b.estimate_kopeks);
    const picked = selectedItems(), sum = picked.reduce((n,i) => n+i.estimate_kopeks, 0);
    const progress = draftTarget > 0 ? Math.min(100, 100 * sum / draftTarget) : 0;
    const steps = [L.step1,L.step2,L.step3,L.step4];
    const tabs = (ST.payment_hub?.games || []).map(g => '<button type="button" class="skin-game'+(payGame===g.id?' active':'')+
      '" data-skin-action="game" data-skin-id="'+escapeHtml(g.id)+'"><b>'+icons[g.id]+'</b><span>'+escapeHtml(g.name)+
      '</span>'+(g.trade_protected?'<small>7D</small>':'')+'</button>').join("");
    const cards = searched.map(i => {
      const active = chosen.has(i.id);
      return '<article class="skin-item'+(active?' checked':'')+'"><button type="button" class="skin-item-main" '+
        'data-skin-action="select" data-skin-id="'+i.id+'" aria-pressed="'+active+'">'+
        '<span class="skin-item-symbol">'+icons[i.game]+'</span><span class="skin-check">'+(active?'✓':'+')+
        '</span><strong>'+escapeHtml(i.name)+'</strong><small>'+L.userQuote+'</small><b>'+rub(i.estimate_kopeks)+'</b></button>'+
        '<button type="button" class="skin-item-remove" data-skin-action="remove" data-skin-id="'+i.id+'" title="'+
        escapeHtml(L.remove)+'">×</button></article>';
    }).join("");
    return '<div class="skinpay-root">'+
      '<div class="skinpay-header"><div><span class="skinpay-kicker">✦ PIRATE TOKEN</span><h2>'+L.title+
      '</h2><p>'+L.subtitle+'</p></div><span class="skinpay-tag">'+L.sampleOnly+'</span></div>'+
      '<div class="skinpay-steps">'+steps.map((step,i)=>'<span class="'+(i===0?'active':'')+'"><b>'+(i+1)+'</b>'+step+'</span>').join('')+'</div>'+
      '<div class="skin-game-tabs">'+tabs+'</div>'+
      '<div class="skinpay-columns"><section class="skinpay-inventory">'+
      '<div class="skinpay-panel-heading"><h3>'+L.inventory+'</h3><span>'+catalog.length+' · '+escapeHtml(game?.name||'Steam')+'</span></div>'+
      '<div class="skinpay-connect"><span>▣</span><div><strong>'+L.noSteam+'</strong><small>'+L.userQuote+'</small></div>'+
      '<button type="button" disabled title="'+L.noSteam+'">'+L.trade+'</button></div>'+
      '<div class="skinpay-add"><input id="skin-name" type="text" maxlength="100" placeholder="'+L.name+
      '" autocomplete="off"><input id="skin-estimate" type="text" inputmode="decimal" maxlength="12" placeholder="'+
      L.estimate+'"><button type="button" class="skinpay-primary" data-skin-action="add">+ '+L.add+'</button></div>'+
      '<div class="skinpay-toolbar"><input id="skin-search" type="search" placeholder="'+L.search+
      '" value="'+escapeHtml(query)+'"><select id="skin-sort" aria-label="Sort">'+
      '<option value="high"'+(order==='high'?' selected':'')+'>'+L.sortHigh+'</option>'+
      '<option value="low"'+(order==='low'?' selected':'')+'>'+L.sortLow+'</option></select></div>'+
      (cards?'<div class="skin-items">'+cards+'</div>':'<div class="skinpay-empty"><b>◇</b><p>'+L.empty+'</p></div>')+
      '</section><aside class="skinpay-summary"><span class="skinpay-kicker">ВАШ ВЫБОР / CART</span>'+
      '<h3>'+L.selected+': <b>'+picked.length+'</b></h3><div class="skinpay-grand">'+rub(sum)+'</div>'+
      '<small>'+L.userQuote+'</small>'+
      '<div class="skinpay-progress"><span style="width:'+progress+'%"></span></div>'+
      '<label for="skin-target">'+L.target+'</label>'+
      '<input id="skin-target" type="text" inputmode="decimal" value="'+(draftTarget?String(draftTarget/100).replace(".",","):'')+'" placeholder="—">'+
      '<button type="button" class="skinpay-auto" data-skin-action="match">'+L.auto+'</button>'+
      '<div class="skinpay-totalrow"><span>'+L.total+'</span><b>'+rub(sum)+'</b></div>'+
      '<div class="skinpay-totalrow"><span>'+L.due+'</span><b>—</b></div>'+
      (draftTarget>0 ? '<div class="skinpay-totalrow '+(sum>=draftTarget?'over':'short')+'"><span>'+ (sum>=draftTarget?L.over:L.left) +
      '</span><b>'+rub(Math.abs(draftTarget-sum))+'</b></div>' : '<p class="skinpay-note">'+L.noTarget+'</p>')+
      (feedback?'<p class="skinpay-feedback" role="status">'+escapeHtml(feedback)+'</p>':'')+
      (game?.trade_protected?'<p class="skinpay-warning">'+L.cs2+'</p>':'')+
      '<div class="skinpay-actions"><button type="button" class="skinpay-secondary" data-skin-action="clear">'+L.clear+'</button></div>'+
      '<p class="skinpay-warning">'+L.sampleOnly+'</p>'+
      '</aside></div></div>';
  }
  paymentHubMarkup = function () {
    const html = originalMarkup();
    if (payMethod !== "steam_items") return html;
    return html.replace(/<\/section>\s*$/, checkoutMarkup() + '</section>');
  };
  window.skinpayDraftSelection = function () {
    if (payMethod !== "steam_items") return null;
    return {items:selectedItems().map(i => ({name:i.name,estimate_kopeks:i.estimate_kopeks})),
      target_kopeks:draftTarget || null};
  };
  document.addEventListener("click", ev => {
    const el = ev.target?.closest?.("[data-skin-action]");
    if (!el) return;
    const action = el.dataset.skinAction, id = Number(el.dataset.skinId);
    const L = labels();
    if (action === "game") {
      if (!(ST.payment_hub?.games || []).some(g => g.id === el.dataset.skinId)) return;
      payGame = el.dataset.skinId; query = ""; chosen.clear(); feedback = "";
    } else if (action === "add") {
      const name = (document.getElementById("skin-name")?.value || "").trim();
      const amount = moneyFromText(document.getElementById("skin-estimate")?.value);
      if (!name || name.length > 100 || amount == null) {toast(L.invalid); return;}
      if (gameItems().length >= 16) {toast(L.limit); return;}
      const item = {id:nextId++, game:payGame, name, estimate_kopeks:amount};
      items.push(item); chosen.add(item.id); feedback = "";
    } else if (action === "remove") {
      const index = items.findIndex(i => i.id===id && i.game===payGame);
      if (index < 0) return;
      chosen.delete(id); items.splice(index,1); feedback = "";
    } else if (action === "select") {
      const item = gameItems().find(i => i.id === id);
      if (!item) return;
      chosen.has(id) ? chosen.delete(id) : chosen.add(id);
      feedback = "";
    } else if (action === "clear") {
      chosen.clear(); feedback = "";
    } else if (action === "match") {
      const target = moneyFromText(document.getElementById("skin-target")?.value);
      if (target == null) {toast(L.noTarget); return;}
      draftTarget = target;
      const result = chooseBest(gameItems(), target);
      chosen.clear();
      if (result) {result.ids.forEach(i=>chosen.add(i)); feedback=L.picked;}
      else feedback=L.short;
    } else return;
    // Rerender only as the direct result of an action, never per keystroke.
    if (typeof render === "function") render(true);
  });
  document.addEventListener("change", ev => {
    if (ev.target?.id === "skin-sort") {order=ev.target.value==="low"?"low":"high"; render(true);}
    if (ev.target?.id === "skin-target") {draftTarget=moneyFromText(ev.target.value)||0;feedback="";render(true);}
    if (ev.target?.id === "skin-search") {query=String(ev.target.value||"").slice(0,100);render(true);}
  });
  // Pure helpers exposed only for regression tests, never as payment APIs.
  window.skinpayPlanner = Object.freeze({moneyFromText, chooseBest});
})();