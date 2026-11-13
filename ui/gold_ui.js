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
  const activeLanguage = () => ST?.cfg?.ui_language || "ru";
  const extendedUi = {
    fr: {
      "nav.news":"Actualités","nav.account":"Compte","nav.subscriptions":"Abonnement","nav.support":"Assistance","nav.settings":"Paramètres",
      "shell.menu":"Menu principal","shell.notifications":"Notifications","shell.profile":"Profil","shell.myProfile":"Mon profil","shell.noneNew":"Aucune nouvelle notification. Consultez les actualités pour les mises à jour.","shell.openNews":"Ouvrir les actualités","shell.subscriptionActive":"Abonnement actif","shell.subscriptionInactive":"Abonnement inactif","shell.remaining":"Temps restant","shell.manage":"Gérer l’abonnement","shell.version":"Version",
      "news.heading":"Actualités et mises à jour","news.history":"HISTORIQUE DES PATCHS","news.all":"Toutes les actualités","news.latest":"DERNIÈRE MISE À JOUR","news.read":"Lire le patch","news.beta":"Bêta","news.update":"Mise à jour","news.empty":"Aucun patch disponible. Réessayez plus tard.","news.noNotes":"Les notes de mise à jour ne sont pas encore publiées.","news.back":"Retour aux actualités","news.close":"Fermer","news.releaseHistory":"HISTORIQUE DES VERSIONS",
      "home.art":"Coffre pirate avec personnages Fortnite et One Piece","home.controls":"Commandes de lancement","home.start":"Démarrer","home.stop":"Arrêter","home.pause":"Pause","home.resume":"Reprendre","home.focus":"Le jeu a perdu le focus. Revenez à Fortnite et reprenez manuellement.","home.welcome":"Bienvenue sur","home.slogan":"Gagnez des récompenses sans vous épuiser.",
      "support.banner":"Besoin d’aide ?","support.blurb":"Obtenez de l’aide pour utiliser l’application.","support.pending":"Demande en attente de vérification","support.paymentPending":"La demande ne confirme pas le paiement. Attendez la vérification du propriétaire et consultez la page Abonnement.","support.openSubscription":"Ouvrir l’abonnement","support.faq":"Questions fréquentes","support.helpReport":"Aide et rapport","support.contact":"Nous contacter","support.sendReview":"Vérifiez le rapport avant de le partager. Il n’est pas envoyé automatiquement.",
      "settings.appearance":"Apparence","settings.appearanceHint":"Personnalisez l’interface de l’application.","settings.updates":"Mises à jour","settings.application":"Application","settings.applicationHint":"Commandes de lancement et raccourcis","settings.altTab":"Mettre en pause lors d’Alt+Tab","settings.openFortnite":"Ouvrir Fortnite au démarrage","settings.advanced":"Paramètres avancés","settings.updateCheck":"Vérifier et installer les mises à jour","settings.launch":"Démarrer","settings.stop":"Arrêter","settings.pause":"Pause",
      "profile.local":"PROFIL LOCAL","profile.heading":"Profil utilisateur","profile.unavailable":"La connexion au compte n’est pas encore disponible.","profile.open":"Ouvrir l’abonnement","button.notifications":"Notifications","button.settings":"Paramètres","button.profile":"Profil"
    },
    pl: {
      "nav.news":"Aktualności","nav.account":"Konto","nav.subscriptions":"Subskrypcja","nav.support":"Pomoc","nav.settings":"Ustawienia",
      "shell.menu":"Menu główne","shell.notifications":"Powiadomienia","shell.profile":"Profil","shell.myProfile":"Mój profil","shell.noneNew":"Brak nowych powiadomień. Aktualności znajdziesz w sekcji Aktualności.","shell.openNews":"Otwórz aktualności","shell.subscriptionActive":"Subskrypcja aktywna","shell.subscriptionInactive":"Subskrypcja nieaktywna","shell.remaining":"Pozostały czas","shell.manage":"Zarządzaj subskrypcją","shell.version":"Wersja",
      "news.heading":"Aktualności i aktualizacje","news.history":"HISTORIA POPRAWEK","news.all":"Wszystkie aktualności","news.latest":"OSTATNIA AKTUALIZACJA","news.read":"Czytaj opis zmian","news.beta":"Beta","news.update":"Aktualizacja","news.empty":"Brak dostępnych poprawek. Spróbuj ponownie później.","news.noNotes":"Opis aktualizacji nie został jeszcze opublikowany.","news.back":"Wróć do aktualności","news.close":"Zamknij","news.releaseHistory":"HISTORIA WYDAŃ",
      "home.art":"Pirat-ska skrzynia z postaciami Fortnite i One Piece","home.controls":"Sterowanie uruchamianiem","home.start":"Uruchom","home.stop":"Zatrzymaj","home.pause":"Wstrzymaj","home.resume":"Wznów","home.focus":"Gra utraciła fokus. Wróć do Fortnite i wznów ręcznie.","home.welcome":"Witamy w","home.slogan":"Zdobywaj nagrody bez zbędnego wysiłku.",
      "support.banner":"Potrzebujesz pomocy?","support.blurb":"Pomożemy w korzystaniu z aplikacji.","support.pending":"Zgłoszenie oczekuje na weryfikację","support.paymentPending":"Zgłoszenie nie potwierdza płatności. Poczekaj na weryfikację właściciela i sprawdź sekcję Subskrypcja.","support.openSubscription":"Otwórz subskrypcję","support.faq":"Częste pytania","support.helpReport":"Pomoc i raport","support.contact":"Kontakt","support.sendReview":"Sprawdź raport przed udostępnieniem. Nie jest wysyłany automatycznie.",
      "settings.appearance":"Wygląd","settings.appearanceHint":"Dostosuj wygląd interfejsu aplikacji.","settings.updates":"Aktualizacje","settings.application":"Aplikacja","settings.applicationHint":"Sterowanie uruchamianiem i skróty","settings.altTab":"Wstrzymaj po Alt+Tab","settings.openFortnite":"Otwórz Fortnite po uruchomieniu","settings.advanced":"Ustawienia zaawansowane","settings.updateCheck":"Sprawdź i zainstaluj aktualizacje","settings.launch":"Uruchom","settings.stop":"Zatrzymaj","settings.pause":"Wstrzymaj",
      "profile.local":"PROFIL LOKALNY","profile.heading":"Profil użytkownika","profile.unavailable":"Logowanie do konta nie jest jeszcze dostępne.","profile.open":"Otwórz subskrypcję","button.notifications":"Powiadomienia","button.settings":"Ustawienia","button.profile":"Profil"
    },
    ar: {
      "nav.news":"الأخبار","nav.account":"الحساب","nav.subscriptions":"الاشتراك","nav.support":"الدعم","nav.settings":"الإعدادات",
      "shell.menu":"القائمة الرئيسية","shell.notifications":"الإشعارات","shell.profile":"الملف الشخصي","shell.myProfile":"ملفي الشخصي","shell.noneNew":"لا توجد إشعارات جديدة. راجع الأخبار للاطلاع على التحديثات.","shell.openNews":"فتح الأخبار","shell.subscriptionActive":"الاشتراك نشط","shell.subscriptionInactive":"الاشتراك غير نشط","shell.remaining":"الوقت المتبقي","shell.manage":"إدارة الاشتراك","shell.version":"الإصدار",
      "news.heading":"الأخبار والتحديثات","news.history":"سجل التحديثات","news.all":"كل الأخبار","news.latest":"أحدث تحديث","news.read":"قراءة تفاصيل التحديث","news.beta":"تجريبي","news.update":"تحديث","news.empty":"لا تتوفر تحديثات الآن. حاول مرة أخرى لاحقًا.","news.noNotes":"لم يتم نشر ملاحظات التحديث بعد.","news.back":"العودة إلى الأخبار","news.close":"إغلاق","news.releaseHistory":"سجل الإصدارات",
      "home.art":"صندوق كنز القراصنة مع شخصيات Fortnite وOne Piece","home.controls":"عناصر التحكم في التشغيل","home.start":"بدء","home.stop":"إيقاف","home.pause":"إيقاف مؤقت","home.resume":"استئناف","home.focus":"فقدت اللعبة التركيز. عُد إلى Fortnite ثم استأنف يدويًا.","home.welcome":"مرحبًا بك في","home.slogan":"احصل على المكافآت دون عناء.",
      "support.banner":"هل تحتاج إلى مساعدة؟","support.blurb":"نساعدك على استخدام التطبيق.","support.pending":"الطلب بانتظار المراجعة","support.paymentPending":"إرسال الطلب لا يؤكد الدفع. انتظر مراجعة المالك وتحقق من صفحة الاشتراك.","support.openSubscription":"فتح الاشتراك","support.faq":"الأسئلة الشائعة","support.helpReport":"المساعدة والتقرير","support.contact":"اتصل بنا","support.sendReview":"راجع التقرير قبل مشاركته. لا يتم إرساله تلقائيًا.",
      "settings.appearance":"المظهر","settings.appearanceHint":"خصص واجهة التطبيق.","settings.updates":"التحديثات","settings.application":"التطبيق","settings.applicationHint":"عناصر التحكم في التشغيل والاختصارات","settings.altTab":"الإيقاف المؤقت عند Alt+Tab","settings.openFortnite":"فتح Fortnite عند التشغيل","settings.advanced":"إعدادات متقدمة","settings.updateCheck":"التحقق من التحديثات وتثبيتها","settings.launch":"بدء","settings.stop":"إيقاف","settings.pause":"إيقاف مؤقت",
      "profile.local":"ملف محلي","profile.heading":"ملف المستخدم","profile.unavailable":"تسجيل الدخول إلى الحساب غير متاح بعد.","profile.open":"فتح الاشتراك","button.notifications":"الإشعارات","button.settings":"الإعدادات","button.profile":"الملف الشخصي"
    }
  };
  const ui = (ru, en, uk) => {
    const lang = activeLanguage();
    return lang === "fr" || lang === "pl" || lang === "ar"
      ? (S["inline." + en] || extendedUi[lang][ru] || en)
      : ({ru, en, uk})[lang] || en;
  };
  const label = (key, fallback) => S["gold." + key] || extendedUi[activeLanguage()]?.[key] || fallback;
  const localeText = (key, fallback) => {
    if (activeLanguage() === "ru" || activeLanguage() === "en" || activeLanguage() === "uk") return t(key);
    return extendedUi[activeLanguage()]?.[key] || fallback;
  };
  const isRtl = () => activeLanguage() === "ar";
  const safe = value => esc(value == null ? "" : value);
  const updateReady = () => ["available", "downloading", "ready"].includes(ST.update?.status) && hiddenUpdateVersion !== ST.update.version;
  const updateCount = () => updateReady() ? 1 : 0;
  const navTitle = id => {
    if (id === "updates") return localeText("nav.news", "News");
    if (id === "account") return localeText("nav.account", "Account");
    if (id === "subscriptions") return localeText("nav.subscriptions", "Subscription");
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
      ? label("shell.subscriptionActive", "Subscription active")
      : label("shell.subscriptionInactive", "Subscription not active yet");
  };
  // Real published changelog excerpts packaged with the launcher for offline reading.
  const offlinePatches = [
  {
    "version": "1.4.3-beta",
    "title": "Fortnite Pirate Token v1.4.3 — кандидат обновления",
    "published_at": "2026-11-12T00:00:00Z",
    "notes": "## Главное\nПять страниц по согласованным макетам: Главная, Подписка, Новости, Поддержка и Настройки.\n## Добавлено\n- Оформление тарифа с выбором банковского перевода или скинов и инструкциями ручной проверки владельцем. Реальная оплата в приложении не проводится; реквизиты пока не настроены.\n- Импорт подписанной лицензии со сроком и привязкой к установке. Владелец может выдавать бесплатный доступ друзьям.\n- Полный текст патча доступен в приложении без интернета.\n## Исправлено\n- Стоп отменяет запуск во время загрузки и отложенный повторный запуск.\n- При отказе Windows отпустить одну клавишу программа пытается отпустить остальные удерживаемые клавиши и кнопки.\n## Проверка\nКандидат для тестирования. Приём ввода Fortnite и ручная оплата требуют отдельной проверки; автоматическая проверка платежей и рефералов не включена."
  },
  {
    "version": "1.4.2-beta",
    "title": "Fortnite Pirate Token v1.4.2 Beta — объединённые исправления",
    "published_at": "2026-11-12T03:35:44Z",
    "notes": "- **Ветки:** PR #16 + совместимое исправление гонок PR #17. Альтернативное PR #19 не наложено целиком во избежание конфликта, но включены его тесты. Проверки PR #18 стали обязательными.\n- **Anti-AFK:** быстрый Start → Stop → Start не теряет последнюю команду при медленной инициализации; повторная инициализация сериализована, состояние остановки приводится к «Остановлено».\n- **Интерфейс:** поиск окна Fortnite при периодическом обновлении статуса перенесён в фоновый кеш, чтобы медленный Win32-запрос не блокировал pywebview.\n- **Лобби:** сохранены шаблоны «Играть», «Готов», «Подтвердить», HUD; ограничение случайных кликов и действий до подтверждённого входа в матч.\n- **Остальное:** сохранены тёмно-золотой дизайн и F-жетон, Alt+Tab с ручным продолжением, F10/F12, подкат, Epic Launcher, статистика, трекер, обновления, Discord, Telegram Stars, лицензирование-предпросмотр и SkinPay.\n- **Новости/релиз:** отдельная запись v1.4.2 Beta внутри приложения; GitHub Release маркируется предварительным (prerelease) до полноценной проверки.\n- **Проверки:** Python, JS, Windows CI и установщик проверяются в GitHub Actions. Автоматические тесты не доказывают, что защищённый Fortnite принимает ввод, и не заменяют ручную проверку.\n- **Платежи:** реальные карты, СБП, переводы, Steam-трейды и платная выдача остаются выключены."
  },
  {
    "version": "1.4.0-beta",
    "title": "Fortnite Pirate Token v1.4.0 Beta — единая тестовая сборка",
    "published_at": "2026-11-12T02:05:52Z",
    "notes": "Это полный набор изменений 1.2.4–1.3.9 и параллельных PR #11, #12, #13, #14. Ранее опубликованные изменения не выбрасывались и не заменялись старыми архивами.\n\n- **Anti-AFK и надёжность:** основа v1.4.0 из PR #12, защита Alt+Tab (после возврата требуется ручное «Продолжить»), F10 резервная пауза, F12 экстренная остановка, настраиваемые F-клавиши, восстановление после смены окна, безопасное освобождение удержанных клавиш, диагностика и запрос запуска через официальный Epic Games Launcher.\n- **Из дополнительной ветки PR #13:** правильный порядок W → Shift → короткий Ctrl → необязательный Space для подката; остановка освобождает все клавиши. Сам Anti-AFK внутри защищённого Fortnite пока не проверен.\n- **Из PR #11:** проверка типов/диапазонов настроек, безопасная миграция из старых бета-конфигов, атомарная запись и проверка входных данных для локальных заявок оплаты.\n- **Дизайн:** Fortnite Pirate Token, сохранён оригинальный F-жетон, тёмно-сине-золотая главная, море/корабль/сундук, статус, счётчики, горячие клавиши, профиль и обновления, без Minecraft-стиля и надписи Gold Edition.\n- **Сохранены функции v1.2.4–v1.3.9:** статистика, трекер, шаблоны, экран «Играть снова», обновления GitHub, плавная навигация и стабильные кнопки, локальный отчёт поддержки, необязательные Discord-уведомления.\n- **Подписки и SkinPay:** ранее добавленные вкладки Dota 2, Rust, CS2, TF2, PUBG, DST, NARAKA, поиск, подбор предметов, корзина и сохранение локальных черновиков. Это планировщик, не площадка реального обмена.\n- **Из PR #14:** отдельный Telegram Stars-бот и сервер пробных лицензий с SQLite, одноразовой ссылкой на установщик, антидублированием платежных событий, отдельной демо-кассой карт/СБП/QR/переводов и предметов Steam, необязательной проверкой ключа по HTTPS в лаунчере.\n- **Новости:** эта тестовая версия показывает заметку «v1.4.0 Beta» непосредственно в своей ленте; стабильные публичные объявления по-прежнему берутся из GitHub Releases. Лента не обещает работающие платежи.\n- **Ограничения:** продажи, обработка реальных карт/переводов и Steam-обмены выключены. Проверка лицензии пока не ограничивает Anti-AFK. Не обещать безопасность учётной записи Fortnite или совместимость с античитом до реального теста и проверки правил платформ."
  },
  {
    "version": "1.3.9",
    "title": "Fortnite Pirate Token v1.3.9 — каталог оплаты и планировщик SkinPay",
    "published_at": "2026-11-12T00:01:42Z",
    "notes": "- В разделе «Подписка» добавлен выбор: Telegram Stars, банковская карта, СБП, QR СБП, банковский перевод и предметы Steam.\n- Для скинов добавлены Dota 2, Rust, Team Fortress 2, PUBG: BATTLEGROUNDS, Don't Starve Together, NARAKA: BLADEPOINT и Counter-Strike 2. Для CS2 есть отдельное предупреждение о семидневной отмене обмена.\n- В разделе «Подписка» добавлен золотой SkinPay-экран по мотивам UX LIS-SKINS: вкладки игр, ручной список предметов, фильтр, сортировка, выделение карточек, корзина, предварительный расчёт суммы в рублях и подбор комбинации с минимальной переплатой.\n- Появилось сохранение **локального черновика запроса**, включая отмеченные пользователем предметы и условные цены. Черновик не отправляется продавцу, не запускает обмен/денежный перевод и не выдаёт подписку.\n- Подготовлен отдельный модуль подбора комбинации предметов по проверенной рублёвой цене с минимальной переплатой, проверкой доступности предметов и запретом смешивать CS2 с другими предметами в одном трейде. Реальные котировки и Steam API ещё не подключены.\n- Реальные тарифы, платёжный провайдер, Telegram-бот, сервер обработки Steam-обменов и активация доступа пока отсутствуют. Никакой платеж не должен считаться подтверждённым со стороны клиента.\n- Существующий анти-AFK и «Играть снова» не менялись."
  }
];
  const releaseAllowed = version => {
    const parts = String(version).match(/^\d+\.\d+\.\d+/)?.[0].split(".").map(Number);
    const current = String(ST.version || "0.0.0").match(/^\d+\.\d+\.\d+/)?.[0].split(".").map(Number);
    if (!parts || !current) return false;
    for (let i=0; i<3; i++) if (parts[i] !== current[i]) return parts[i] < current[i];
    return true;
  };
  // Display only verified release facts, never marketing placeholders or invented patch notes.
  const newsItems = () => {
    const releases = [...(Array.isArray(ST.release_news) ? ST.release_news : []),
      ...offlinePatches.filter(p => releaseAllowed(p.version))];
    const unique = new Map();
    for (const r of releases) {
      if (!r || typeof r !== "object") continue;
      const version = String(r.version || "");
      if (!/^\d+\.\d+\.\d+(?:-beta)?$/.test(version)) continue;
      const key = version.replace(/-beta$/, "");
      if (unique.has(key)) continue; // the bundled beta has richer offline notes
      const local = offlinePatches.find(p => p.version.replace(/-beta$/, "") === key);
      const notes = String(local?.notes || r.notes || "").trim();
      unique.set(key, {
        version, title: String(r.title || local?.title || ("Fortnite Pirate Token v" + version)),
        notes, date: String(r.published_at || r.date || local?.published_at || ""),
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
  const newsIcon = item => {
    const notes = String(item?.notes || "").toLowerCase();
    if (/добавлено|added|нов|добавлен/.test(notes)) {
      return '<svg viewBox="0 0 48 48" focusable="false"><path d="M10 5h19l9 9v29H10zM29 5v10h9M17 25h14M17 32h14M17 18h5"/><path d="M36 4v9m-4.5-4.5h9"/></svg>';
    }
    if (/исправлено|исправлен|fixed|fixes|bug/.test(notes)) {
      return '<svg viewBox="0 0 48 48" focusable="false"><path d="m29 6 13 13-5 5-13-13zM23 14 9 28a8 8 0 0 0 11 11l14-14M7 7l6 6m-8 8h9m3 22v-9m22 3h-9"/><circle cx="14" cy="34" r="2"/></svg>';
    }
    if (/провер|тест|verify|test|release|beta|бета/.test(notes)) {
      return '<svg viewBox="0 0 48 48" focusable="false"><path d="M8 6h32v36H8zM15 15h18M15 22h18M15 29h8"/><path d="m27 34 4 4 8-9"/></svg>';
    }
    return '<svg viewBox="0 0 48 48" focusable="false"><path d="M20 4h8l1.5 5a17 17 0 0 1 4.1 1.7l4.7-2.1 5.7 5.7-2.1 4.7a17 17 0 0 1 1.7 4.1l5 1.5v8l-5 1.5a17 17 0 0 1-1.7 4.1l2.1 4.7-5.7 5.7-4.7-2.1a17 17 0 0 1-4.1 1.7L28 49h-8l-1.5-5a17 17 0 0 1-4.1-1.7l-4.7 2.1L4 38l2.1-4.7a17 17 0 0 1-1.7-4.1l-5-1.5v-8l5-1.5a17 17 0 0 1 1.7-4.1L4 9.8l5.7-5.7 4.7 2.1A17 17 0 0 1 18.5 4z" transform="translate(3 -.5) scale(.88)"/><circle cx="24" cy="24" r="7"/><path d="m21 24 2 2 4-5"/></svg>';
  };
  const patchExcerpt = value => String(value || "")
    .replace(/^#{1,5}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\[([^\]]+)\]\(https?:\/\/[^\s)]+\)/g, "$1")
    .replace(/[*_`>#]/g, "")
    .replace(/\s+/g, " ").trim();
  const newsMarkup = (full = false) => {
    const all = newsItems();
    const items = full ? all : all.slice(0, 1);
    const headline = label("news.heading", "News and updates");
    const noNews = label("news.empty", "No published patches are available. Check again later.");
    const card = (item, index) => '<button type="button" class="gold-patch-row" data-news-open="' + index + '">' +
      '<span class="gold-patch-thumb" aria-hidden="true">' + newsIcon(item) + '</span>' +
      '<span class="gold-patch-row-text"><span class="gold-mini-tag">' +
      (item.beta ? label("news.beta", "Beta") : label("news.update", "Update")) +
      ' · v' + safe(item.version) + '</span><strong>' + safe(item.title) + '</strong>' +
      '<small>' + safe(patchExcerpt(item.notes)).slice(0, full ? 230 : 125) + '</small></span>' +
      (releaseDate(item.date) ? '<time>' + safe(releaseDate(item.date)) + '</time>' : '') +
      '<span class="gold-patch-arrow" aria-hidden="true">›</span></button>';
    return '<section class="card gold-news ' + (full ? "gold-news-full gold-news-archive" : "") + '">' +
      '<div class="gold-section-head"><div><span class="gold-overline">' +
      label("news.history", "PATCH HISTORY") +
      '</span><h2>' + headline + '</h2></div>' +
      (full ? '' : '<button class="gold-text-link" data-page="updates">' + label("news.all", "All news") + ' →</button>') +
      '</div>' +
      (full && all.length ? '<button type="button" class="gold-patch-feature" data-news-open="0">' +
        '<span class="gold-overline">' + label("news.latest", "LATEST RELEASE") + '</span>' +
        '<strong>' + safe(all[0].title) + '</strong><span>' +
        safe(patchExcerpt(all[0].notes)).slice(0, 240) + '</span><b>' + label("news.read", "Read patch") + ' →</b></button>' : '') +
      (items.length ? '<div class="gold-patch-list">' + items.map(card).join("") + '</div>'
        : '<p class="gold-patch-empty">' + noNews + '</p>') + '</section>';
  };
  // Treat notes as UNTRUSTED plain text/Markdown, never as HTML.
  const patchNotesHtml = value => {
    const text = String(value || "").slice(0, 12000);
    if (!text.trim()) return '<p>' + label("news.noNotes", "Release notes are not available.") + '</p>';
    const inline = value => {
      let out = safe(value);
      out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
      out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      out = out.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>");
      return out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    };
    const lines = text.split(/\r?\n/);
    return lines.map(raw => {
      const line = raw.trim();
      if (!line) return "";
      const h = line.match(/^#{1,5}\s+(.+)$/);
      if (h) return "<h3>" + inline(h[1]) + "</h3>";
      const bullet = line.match(/^(?:[-*+]|\d+[.)])\s+(.+)$/);
      if (bullet) return '<p class="gold-patch-bullet"><span aria-hidden="true">•</span>' + inline(bullet[1]) + "</p>";
      return "<p>" + inline(line) + "</p>";
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
    const back = label("news.back", "Back to news");
    patchOverlay.innerHTML = '<article class="gold-patch-dialog" role="dialog" aria-modal="true" aria-labelledby="gold-patch-title" tabindex="-1">' +
      '<header class="gold-patch-dialog-head"><button type="button" class="gold-patch-back" data-news-close="1">← ' + back +
      '</button><button type="button" class="gold-patch-close" data-news-close="1" aria-label="' +
      label("news.close", "Close") + '">×</button></header>' +
      '<div class="gold-patch-body"><div class="gold-patch-banner"><span class="gold-mini-tag">' +
      label("news.releaseHistory", "RELEASE HISTORY") + '</span>' +
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
  const originalSupport = PAGE.support;
  PAGES.splice(0, PAGES.length,
    ["home", "⌂", "nav.home"], ["afk", "↝", "nav.afk"], ["tracker", "◈", "nav.tracker"],
    ["templates", "▣", "nav.templates"], ["updates", "▤", "nav.updates"],
    ["subscriptions", "♛", "nav.subscriptions"], ["settings", "⚙", "nav.settings"],
    ["support", "⚑", "nav.support"], ["account", "◉", "nav.account"], ["guide", "?", "nav.guide"]);
  const publicPages = ["home", "subscriptions", "updates", "support", "settings"];
  const renderNav = id => {
    const [, icon] = PAGES.find(([route]) => route === id);
    const current = page === id || (id === "settings" && ["afk", "tracker", "templates"].includes(page));
    const title = safe(navTitle(id));
    return `<button class="nav ${current ? "on" : ""}" data-page="${id}" title="${title}"
      aria-label="${title}" ${current ? 'aria-current="page"' : ""}><i aria-hidden="true">${icon}</i><span>${title}</span>
      ${id === "updates" && updateCount() ? '<b class="gold-nav-dot"></b>' : ""}</button>`;
  };
  PAGE.home = function() {
    const e = ST.engine;
    return `<div class="design-home"><div class="design-home-art" role="img" aria-label="${label("home.art", "Pirate chest with Fortnite and One Piece characters")}"></div>
    <section class="design-controls" aria-label="${label("home.controls", "Launch controls")}"><div class="gold-hero-actions">
      <button class="btn pri gold-play" data-act="start" ${e.running || ST.controls?.start_pending ? "disabled" : ""}>▶ ${label("home.start", t("btn.start"))}</button>
      <button class="btn gold-pause" data-act="pause" ${!e.running ? "disabled" : ""}>${e.paused ? "▶" : "Ⅱ"} ${e.paused ? t("btn.resume") : label("home.pause", t("btn.pause"))}</button>
      <button class="btn gold-stop" data-act="stop" ${!e.running && !ST.controls?.start_pending ? "disabled" : ""}>■ ${label("home.stop", t("btn.stop"))}</button></div>
      <div class="design-status"><b data-live="launcher-engine-status">${safe(launcherEngineStatus())}</b><span data-live="launcher-game-status">${safe(launcherGameStatus())}</span></div>
    </section>
    ${e.auto_paused ? `<p class="afk-auto-pause">${label("home.focus", "The game lost focus. Return to Fortnite and resume manually.")}</p>` : ""}
    <div class="gold-dashboard"><div class="gold-dashboard-main">${newsMarkup()}</div><div class="gold-dashboard-side">${subCard()}</div></div>
    <p class="design-hotkeys">${hotkeySummary()}</p></div>`;
  };
  PAGE.updates = function() {
    return newsMarkup(true) + `<details class="design-update-details"><summary>${ui("Проверка и установка обновлений", "Check and install updates", "Перевірка й встановлення оновлень")}</summary><div class="gold-updater">${originalUpdates()}</div></details>`;
  };
  PAGE.settings = function() {
    const c = ST.cfg;
    const field = (label, control) => `<div class="field"><span>${label}</span>${control}</div>`;
    return `<div class="design-settings-art" aria-hidden="true"></div><div class="design-settings">
      <section class="card"><h2>◈ ${label("settings.appearance", "Appearance")}</h2><p class="mute">${label("settings.appearanceHint", "Customize the launcher interface.")}</p>
      ${field(t("set.theme"), `<div class="seg">${["dark","light"].map(l=>`<button class="${c.theme===l?"on":""}" data-theme="${l}">${t("theme."+l)}</button>`).join("")}</div>`)}
      ${field(t("set.ui_language"), `<div class="seg lang-full">${Object.keys(uiLanguageFlags).map(l => languageButton(l, true)).join("")}</div>`)}
      ${field(t("set.game_language"), `<select data-cfg="language">${["ru","en","uk"].map(l=>`<option value="${l}" ${c.language===l?"selected":""}>${safe(t("lang."+l))}</option>`).join("")}</select>`)}
      </section>
      ${PAGE.notifications()}
      <section class="card design-update-settings"><h2>↻ ${label("settings.updates", "Updates")}</h2>${originalUpdates()}</section>
      <section class="card"><h2>☷ ${label("settings.application", "Application")}</h2><p class="mute">${label("settings.applicationHint", "Launch controls and shortcuts")}</p>
      ${field(label("settings.launch", t("btn.start")), hotkeyPicker("afk_start_hotkey",c.afk_start_hotkey))}
      ${field(label("settings.stop", t("btn.stop")), hotkeyPicker("afk_stop_hotkey",c.afk_stop_hotkey))}
      ${field(label("settings.pause", t("btn.pause")), hotkeyPicker("afk_pause_hotkey",c.afk_pause_hotkey))}
      ${field(label("settings.altTab", "Pause on Alt+Tab"),tog("afk_pause_on_alt_tab",c.afk_pause_on_alt_tab))}
      ${field(label("settings.openFortnite", "Open Fortnite on Start"),tog("afk_launch_game",c.afk_launch_game))}
      <p class="mute hotkey-help">${hotkeyHelp()}</p>
      <button class="btn" data-act="mini">${t("mini.open")}</button></section>
      <details class="card design-advanced"><summary>${label("settings.advanced", "Advanced settings")}</summary>${originalSettings().match(/<details class="card launcher-advanced">[\s\S]*?<\/details>/)?.[0] || ""}</details>
      </div>`;
  };
  PAGE.support = function() {
    const box = document.createElement("div"); box.innerHTML = originalSupport();
    const cards = box.querySelectorAll(".grid > .card");
    const faq = cards[2];
    if (faq) faq.insertAdjacentHTML("beforeend", `<details><summary>${label("support.pending", "Order awaiting review")}</summary><p>${label("support.paymentPending", "Submitting an order does not confirm payment. Wait for owner review and check Subscription.")}</p><button class="btn sm" data-page="subscriptions">${label("support.openSubscription", t("nav.subscriptions"))}</button></details>`);
    return `<div class="design-support"><section class="design-help-banner"><div class="design-help-art" aria-hidden="true"></div><h2>${label("support.banner", "Need help?")}</h2><p>${label("support.blurb", "Get help with the launcher.")}</p></section><div class="design-support-main">${faq?.outerHTML || ""}</div><div class="design-support-side">${cards[0]?.outerHTML || ""}${cards[1]?.outerHTML || ""}</div></div>`;
  };
  PAGE.account = function() {
    return `<section class="card gold-account"><div class="gold-account-identity"><img src="pirate_token.png" alt=""><div><span class="gold-overline">${label("profile.local", "LOCAL PROFILE")}</span>
      <h2>${label("profile.heading", "User profile")}</h2><p>${label("profile.unavailable", "Account sign-in is not connected yet.")}</p></div></div>
      <div class="gold-account-facts"><div><span>${localeText("set.app_version", "App version")}</span><b>v${safe(ST.version)}</b></div>
      <div><span>${localeText("nav.subscriptions", "Subscription")}</span><b>${subscriptionNote()}</b></div>
      <div><span>${label("shell.remaining", "Remaining")}</span><b>${remaining()}</b></div></div>
      <button class="btn pri" data-page="subscriptions">${label("profile.open", "Open subscription")}</button></section>`;
  };
  function renderGold(force) {
    const oldSig = sig;
    const savedNavScroll = document.querySelector('#app .gold-nav')?.scrollTop || 0;
    originalRender(force);
    if (MINI || (!force && sig === oldSig)) return;
    const root = document.getElementById("app");
    const rail = root?.querySelector(".rail"), top = root?.querySelector(".top");
    root?.setAttribute("data-design-page",page);
    document.documentElement.setAttribute("dir", isRtl() ? "rtl" : "ltr");
    document.documentElement.setAttribute("lang", activeLanguage());
    if (!rail || !top) return;
    rail.innerHTML = `<div class="brand gold-brand"><img src="pirate_token.png" alt=""><span><b class="launcher-wordmark">FORTNITE<svg class="design-hat" aria-hidden="true" viewBox="0 0 44 28"><path d="M5 19c2-8 9-14 17-14s15 6 17 14c-8 3-26 3-34 0Z" fill="#f7c849" stroke="#fff0a6" stroke-width="1.5"/><path d="M4 19c7 3 29 3 36 0 2 1 2 3 0 4-9 4-27 4-36 0-2-1-2-3 0-4Z" fill="#df9b2d" stroke="#ffe083" stroke-width="1.4"/><path d="M8 20c8 2 20 2 28 0" fill="none" stroke="#b74335" stroke-width="2.5"/></svg></b><em>PIRATE TOKEN</em></span></div>
      <nav class="gold-nav" aria-label="${label("shell.menu", "Main menu")}">${publicPages.map(renderNav).join("")}</nav><div class="design-version" dir="ltr">v${safe(ST.version)}</div>`;
    top.innerHTML = `<div class="gold-top-location"><h1>${safe(navTitle(page))}</h1></div>
      <div class="gold-top-right"><span class="gold-top-version">v${safe(ST.version)}</span>
      <button class="gold-header-btn" data-gold="notifications" title="${label("button.notifications", "Notifications")}" aria-label="${label("button.notifications", "Notifications")}" aria-expanded="${notificationOpen}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></svg>${updateCount()?'<i class="gold-alert-dot"></i>':""}</button>
      <button class="gold-header-btn" data-page="settings" title="${localeText("nav.settings", "Settings")}" aria-label="${localeText("nav.settings", "Settings")}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .3.4 1 1.6-2 2-1.6-1-.4-.3a9 9 0 0 1-2.1.9l-.3 1.8h-2.8l-.3-1.8a9 9 0 0 1-2.1-.9l-1.9 1.3-2-2 1-1.6.3-.4A9 9 0 0 1 5.6 13l-1.8-.3v-2.8l1.8-.3a9 9 0 0 1 .9-2.1L5.2 5.6l2-2 1.9 1.3a9 9 0 0 1 2.1-.9l.3-1.8h2.8l.3 1.8a9 9 0 0 1 2.1.9l1.9-1.3 2 2-1.3 1.9a9 9 0 0 1 .9 2.1l1.8.3v2.8l-1.8.3a9 9 0 0 1-.8 2Z" transform="translate(-.9 0) scale(.98)"/></svg></button>
      <button class="gold-avatar" data-gold="profile" aria-label="${label("button.profile", "Profile")}" aria-expanded="${profileOpen}"><img src="pirate_token.png" alt=""><span>⌄</span></button>
      ${notificationOpen ? `<div class="gold-pop gold-notify"><div class="gold-pop-head"><b>${label("shell.notifications", "Notifications")}</b><span>${updateCount() ? "1" : "0"}</span></div>
        ${updateCount() ? `<p>${localeText("upd.available", "Version available").replace("{v}", safe(ST.update.version))}</p>` : `<p>${label("shell.noneNew", "No new notifications. Read updates in News.")}</p>`}
        <button class="btn sm pri" data-page="updates">${label("shell.openNews", "Open News")} ↗</button></div>` : ""}
      ${profileOpen ? `<div class="gold-pop gold-profile-pop"><div class="gold-pop-head"><b>${label("shell.myProfile", "My profile")}</b></div>
        <p>${subscriptionNote()}</p><div class="gold-pop-remain">${label("shell.remaining", "Subscription remaining")} <b>${remaining()}</b></div>
        <button class="btn sm" data-page="account">${localeText("nav.account", "Account")}</button><button class="btn sm pri" data-page="subscriptions">${localeText("nav.subscriptions", "Subscription")}</button></div>` : ""}
      </div>`;
    const afterNav = root.querySelector('.gold-nav');
    if (afterNav) afterNav.scrollTop = savedNavScroll;
    refreshLiveMetrics();
  }
  render = renderGold;
  if (ST && document.getElementById("running-interface")) renderGold(true);
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
