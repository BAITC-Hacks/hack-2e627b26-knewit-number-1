export const LOCALES = {
  ru: { id: "ru-KZ", label: "Русский", short: "RU" },
  kk: { id: "kk-KZ", label: "Қазақша", short: "KZ" },
};

export const DEFAULT_LANGUAGE = "ru";

const resources = {
  ru: {
    languageName: "Русский",
    languageChanged: "Язык интерфейса изменён на русский.",
    languageSummary: "Активное предложение корзины погашено. Сформируйте новое резюме на русском языке.",
    welcome: "Здравствуйте! Я помогу найти электротехнический товар, проверить наличие и подобрать подходящий вариант.\n\nЧто вы ищете?",
    suggestions: [
      { label: "Автомат Legrand на 160 А", prompt: "Нужен автомат Legrand на 160 А, 3 полюса" },
      { label: "Кабель для квартиры", prompt: "Подберите кабель ВВГнг для прокладки в квартире" },
      { label: "Условия доставки", prompt: "Есть ли доставка в Алматы и от какой суммы она бесплатная?" },
      { label: "Аналог отсутствующего товара", prompt: "Подберите аналог отсутствующего автомата 3P" },
    ],
    demo: { delivery: "Подскажу условия доставки после уточнения города и суммы заказа. Для Алматы точный порог бесплатной доставки сейчас нужно подтвердить по актуальному условию — я не буду называть неподтверждённую сумму.", cable: "Помогу подобрать кабель по сечению, материалу жил, напряжению и способу прокладки. Уточните длину и где он будет использоваться — так я отберу релевантные позиции из каталога.", analog: "Нашёл доступный аналог и сравнил критичные параметры:", product: "Нашёл демонстрационную позицию в каталоге. Укажите количество и проверьте резюме перед добавлением:", fallback: "Принял запрос. В рабочей версии я найду товар в каталоге, проверю актуальные цену и наличие, а при необходимости покажу объяснимые аналоги. Сейчас это демонстрационный каркас чата." },
    chat: {
      open: "Открыть чат с консультантом", close: "Закрыть чат с консультантом", launcher: "Помощь с выбором", ai: "AI-консультант",
      dialog: "Чат-консультант EKT.kz", title: "EKT Консультант", clear: "Очистить историю", closeShort: "Закрыть чат", languageSwitcher: "Язык интерфейса",
      status: { cart: "Проверяет корзину", forming: "Формирует ответ", retry: "Нужна повторная попытка", online: "Онлайн · отвечает за несколько секунд" },
      today: "Сегодня", examples: "Примеры запросов", catalogBasis: "Ответы основаны на данных каталога EKT.kz",
      inputLabel: "Введите сообщение", placeholder: "Например: нужен кабель 3×2,5 мм²", send: "Отправить сообщение",
      disclaimer: "Не вводите платёжные данные и пароли", error: "Не удалось выполнить запрос", retry: "Повторить",
      attachmentAdd: "Прикрепить файл", attachmentRemove: "Удалить вложение", attachmentUploading: "Загружаем файл…", attachmentReady: "Файл готов", attachmentTypeError: "Поддерживаются только PDF, DOCX, XLSX и JPEG.", attachmentSizeError: "Размер файла не должен превышать 10 МБ.", attachmentUploadError: "Файл не удалось загрузить. Попробуйте ещё раз.", attachmentHelp: "PDF, DOCX, XLSX или JPEG · до 10 МБ", attachmentPrompt: "Проверьте прикреплённый файл.",
      typing: "Ассистент формирует ответ", forming: "Формирую ответ", cancel: "Отменить",
      stopped: "Формирование ответа остановлено. Чем ещё помочь?", justNow: "Только что", responseError: "Не удалось получить ответ. Проверьте соединение и попробуйте ещё раз.", secretHidden: "[секрет скрыт]", internalErrorHidden: "[внутренняя ошибка скрыта]",
      proposalChanged: "Это резюме заменено более новым.",
      summaryNotice: "Проверьте состав действия. Корзина изменится только после подтверждения.",
      sourceChanged: "Данные изменились; используйте новое резюме ниже.",
      insufficientSummary: (n) => `Остаток уменьшился. Подготовил новое резюме на ${n} шт.`,
      refreshedSummary: "Цена, остаток или версия корзины изменились. Подтвердите обновлённое резюме.",
      replacementChanged: "Предложение изменилось. Проверьте и подтвердите новое резюме.",
      noStock: "Доступный остаток закончился. Товар не добавлен.",
      maxSummary: (n) => `Запрошенного количества нет. Подготовил новое резюме на ${n} шт.`,
      languageSummary: "Активное предложение корзины погашено. Сформируйте новое резюме на русском языке.",
    },
    clearDialog: { eyebrow: "Текущий диалог", title: "Очистить историю?", description: "Сообщения будут удалены только из этого окна. Новая консультация начнётся с приветствия.", cancel: "Отмена", confirm: "Очистить" },
    product: {
      card: "Карточка товара", image: "Изображение товара", missingImage: "Изображение: информация не найдена", eyebrow: "Товар из каталога EKT.kz", characteristics: ["Серия", "Полюса", "Номинальный ток", "Отключающая способность", "Напряжение", "Бренд"], propertyLabels: { POWER: "Мощность", RATED_CURRENT: "Номинальный ток", VOLTAGE: "Напряжение", IP_RATING: "Степень защиты", COLOR_TEMPERATURE: "Цветовая температура", LUMINOUS_FLUX: "Световой поток" }, characteristicsTitle: "Характеристики",
      article: "Артикул", priceMissing: "Цена: информация не найдена", availabilityUnknown: "Доступность не подтверждена", available: (n, unit = "шт.") => `Доступно: ${n} ${unit}`,
      unavailable: "Нет в наличии", availabilityMissing: "Наличие: информация не найдена", cache: "Данные из кэша", live: "Данные live", verified: "verified_at", age: "возраст", dataAgeNow: "только что", dataAgeMinutes: (n) => `${n} мин. назад`, dataAgeHours: (n) => `${n} ч назад`, dataAgeDays: (n) => `${n} дн. назад`,
      fit: "Почему подходит:", important: "Важно:", documents: "Документы и сертификаты", certificate: "Сертификат", document: "Документ", instruction: "Инструкция", quantity: "Количество", checking: "Проверяю…", retry: "Повторить", add: "Добавить", preparing: "Подготавливаем защищённую сессию корзины", reconnect: "Соединение восстановится при следующей попытке", summaryHint: "Сначала покажем итоговое резюме", official: "Открыть официальную карточку", officialMissing: "Официальная карточка: информация не найдена",
    },
    analog: { comparison: "Сравнение аналога", label: "Рекомендуемый аналог", instead: "Вместо", article: "Артикул", inStock: (n, unit = "шт.") => `В наличии: ${n} ${unit}`, unavailable: "Нет в наличии", missing: "Наличие: информация не найдена", live: "Цена и наличие проверены live", notLive: "Цена и наличие не подтверждены live", checked: "Проверено", why: "Почему подходит", matching: "Совпадающие параметры", differences: "Существенные отличия", original: "Исходный", analog: "Аналог", infoMissing: "Информация не найдена", differenceKinds: { higher_protection: "У аналога выше степень защиты." }, parameters: { purpose: "Назначение", mounting: "Монтаж", power: "Мощность", voltage: "Напряжение", color_temperature: "Цветовая температура", luminous_flux: "Световой поток", ip_rating: "Степень защиты", dimensions: "Габариты" } },
    cart: { added: (n) => `Добавлено: ${n} шт.`, updated: "Корзина обновлена", open: "Открыть корзину", result: "Товар добавлен в корзину", summary: "Резюме добавления в корзину", orderSummary: "Резюме заказа", expired: "Устарело", error: "Ошибка", confirmationNeeded: "Нужно подтверждение", newProposal: "Для добавления сформируйте новое резюме и подтвердите его.", article: "Артикул", quantity: "Количество", unitPrice: "Цена за единицу", total: "Итого", note: (expiry) => `Цена и остаток будут проверены ещё раз. Резюме действует ${expiry}.`, checking: "Проверяю цену и остаток…", unavailable: "Подтверждение недоступно", confirm: "Подтвердить и добавить", replaced: "Данные изменились; используйте новое резюме ниже.", expiryFallback: "в течение нескольких минут", expiryUntil: (time) => `до ${time}` },
    errors: { network_error: "Связь прервалась. Состояние корзины перепроверено; можно безопасно повторить это подтверждение.", csrf_cookie_missing: "Защитная сессия корзины обновлена. Повторите действие.", csrf_failed: "Защитная сессия корзины обновлена. Повторите действие.", cart_busy: "Корзина занята другим изменением. Повторите подтверждение.", action_in_progress: "Действие ещё обрабатывается. Повторите проверку через несколько секунд.", insufficient_stock: (n) => `Недостаточно остатка. Максимально доступно: ${n} шт.`, action_expired: "Срок действия резюме истёк. Сформируйте новое.", action_stale: "Резюме устарело, а актуального варианта сейчас нет.", action_failed: "Это действие уже завершилось ошибкой. Создайте новое резюме.", product_unavailable: "Товар сейчас недоступен для добавления в корзину.", cart_integration_unavailable: "Добавление в рабочую корзину пока недоступно. Демо работает только с fixture-каталогом.", cart_currency_mismatch: "В корзине уже есть товары в другой валюте.", quantity_rule_violation: "Количество не соответствует правилам продажи товара.", catalog_verification_failed: "Не удалось заново проверить цену и остаток. Корзина не изменена.", cart_mutation_failed: "Добавление не завершено. Мы проверили актуальное состояние корзины.", confirmation_required: "Это сообщение не подтверждает изменение корзины.", ambiguous_confirmation: "В диалоге несколько предложений. Нажмите кнопку в нужном резюме.", no_active_action: "Активного предложения нет. Выберите количество в карточке товара.", generic: "Не удалось изменить корзину. Попробуйте сформировать новое резюме." },
    site: { brand: "EKT.kz, на главную", nav: "Основная навигация", languageSwitcher: "Язык интерфейса", catalog: "Каталог", delivery: "Доставка", contacts: "Контакты", cart: "Корзина", cartAria: (n) => `Открыть корзину, товаров: ${n}`, eyebrow: "Электротехника для дома и бизнеса", hero: "Подберём решение под вашу задачу", description: "Кабель, освещение, низковольтная аппаратура и комплектующие — с понятной консультацией в чате.", openCatalog: "Открыть каталог", ask: "Задать вопрос", stats: "Демо-статистика каталога", catalogNearby: "Каталог рядом", pages: "страниц категорий и товаров", overline: "КАТАЛОГ EKT", find: "Найдите нужное с первого запроса", directions: "12 направлений", footer: "Проверенная консультация", cities: "Алматы · Астана · Шымкент · и ещё 6 городов", categories: [["Кабель / провод", "Кабель, провод и аксессуары"], ["Светильники", "LED, лампы и управление светом"], ["Низковольтная аппаратура", "Автоматика и защита сетей"], ["Монтаж и инструмент", "Всё для надёжного монтажа"]] },
    cookie: { aria: "Уведомление о cookie", title: "Мы используем cookie", text: "Они помогают сделать сайт удобнее.", close: "Понятно" },
  },
  kk: {
    languageName: "Қазақша",
    languageChanged: "Интерфейс тілі қазақшаға өзгертілді.",
    languageSummary: "Себеттің белсенді ұсынысы тоқтатылды. Қазақ тілінде жаңа қорытынды жасаңыз.",
    welcome: "Сәлеметсіз бе! Электротехникалық тауарды табуға, бар-жоғын тексеруге және қолайлы нұсқаны таңдауға көмектесемін.\n\nНе іздеп жүрсіз?",
    suggestions: [
      { label: "160 А Legrand автоматы", prompt: "3 полюсті 160 А Legrand автоматы керек" },
      { label: "Пәтерге арналған кабель", prompt: "Пәтерге төсеуге ВВГнг кабелін таңдаңыз" },
      { label: "Жеткізу шарттары", prompt: "Алматыға жеткізу бар ма және қай сомадан тегін?" },
      { label: "Жоқ тауардың аналогы", prompt: "Жоқ 3P автоматқа аналог таңдаңыз" },
    ],
    demo: { delivery: "Қала мен тапсырыс сомасын нақтыласаңыз, жеткізу шарттарын айтамын. Алматы үшін тегін жеткізудің нақты шегін қолданыстағы шартпен растау керек — расталмаған соманы атамаймын.", cable: "Кабельді қимасы, өзек материалы, кернеуі және төсеу тәсілі бойынша таңдауға көмектесемін. Ұзындығын және қолданылатын орнын нақтылаңыз — каталогтан тиісті позицияларды табамын.", analog: "Қолжетімді аналогты тауып, маңызды параметрлерді салыстырдым:", product: "Каталогтан демо-позиция таптым. Санды көрсетіп, қоспас бұрын қорытындыны тексеріңіз:", fallback: "Сұрауыңызды қабылдадым. Жұмыс нұсқасында каталогтан тауарды тауып, баға мен қалдықты тексеріп, қажет болса түсіндірмесі бар аналогтарды көрсетемін. Қазір бұл чаттың демонстрациялық қаңқасы." },
    chat: {
      open: "Кеңесші чатын ашу", close: "Кеңесші чатын жабу", launcher: "Таңдауға көмек", ai: "AI-кеңесші",
      dialog: "EKT.kz кеңесші чаты", title: "EKT кеңесшісі", clear: "Тарихты тазарту", closeShort: "Чатты жабу", languageSwitcher: "Интерфейс тілі",
      status: { cart: "Себетті тексеруде", forming: "Жауап дайындалуда", retry: "Қайталап көру қажет", online: "Онлайн · бірнеше секундта жауап береді" },
      today: "Бүгін", examples: "Сұрау мысалдары", catalogBasis: "Жауаптар EKT.kz каталогы деректеріне негізделген",
      inputLabel: "Хабарлама енгізіңіз", placeholder: "Мысалы: 3×2,5 мм² кабель керек", send: "Хабарлама жіберу",
      disclaimer: "Төлем деректері мен құпиясөздерді енгізбеңіз", error: "Сұрауды орындау мүмкін болмады", retry: "Қайталау",
      attachmentAdd: "Файл тіркеу", attachmentRemove: "Тіркелген файлды жою", attachmentUploading: "Файл жүктелуде…", attachmentReady: "Файл дайын", attachmentTypeError: "Тек PDF, DOCX, XLSX және JPEG қолдау көрсетіледі.", attachmentSizeError: "Файл өлшемі 10 МБ-тан аспауы керек.", attachmentUploadError: "Файлды жүктеу мүмкін болмады. Қайталап көріңіз.", attachmentHelp: "PDF, DOCX, XLSX немесе JPEG · 10 МБ-қа дейін", attachmentPrompt: "Тіркелген файлды тексеріңіз.",
      typing: "Ассистент жауап дайындауда", forming: "Жауап дайындауда", cancel: "Бас тарту",
      stopped: "Жауап дайындау тоқтатылды. Тағы немен көмектесейін?", justNow: "Жаңа ғана", responseError: "Жауап алу мүмкін болмады. Байланысты тексеріп, қайталап көріңіз.", secretHidden: "[құпия жасырылды]", internalErrorHidden: "[ішкі қате жасырылды]",
      proposalChanged: "Бұл қорытынды жаңа қорытындымен ауыстырылды.", summaryNotice: "Әрекет құрамын тексеріңіз. Себет тек растаудан кейін өзгереді.", sourceChanged: "Деректер өзгерді; төмендегі жаңа қорытындыны пайдаланыңыз.", insufficientSummary: (n) => `Қалдық азайды. ${n} данаға жаңа қорытынды дайындалды.`, refreshedSummary: "Баға, қалдық немесе себет нұсқасы өзгерді. Жаңартылған қорытындыны растаңыз.", replacementChanged: "Ұсыныс өзгерді. Жаңа қорытындыны тексеріп, растаңыз.", noStock: "Қолжетімді қалдық бітіп қалды. Тауар қосылмады.", maxSummary: (n) => `Сұралған сан жоқ. ${n} данаға жаңа қорытынды дайындалды.`, languageSummary: "Себеттің белсенді ұсынысы тоқтатылды. Қазақ тілінде жаңа қорытынды жасаңыз.",
    },
    clearDialog: { eyebrow: "Ағымдағы диалог", title: "Тарих тазартылсын ба?", description: "Хабарламалар тек осы терезеден өшеді. Жаңа кеңес сәлемдесуден басталады.", cancel: "Бас тарту", confirm: "Тазарту" },
    product: { card: "Тауар карточкасы", image: "Тауар суреті", missingImage: "Сурет: ақпарат табылмады", eyebrow: "EKT.kz каталогындағы тауар", characteristics: ["Серия", "Полюстер", "Номиналды ток", "Ажырату қабілеті", "Кернеу", "Бренд"], propertyLabels: { POWER: "Қуат", RATED_CURRENT: "Номиналды ток", VOLTAGE: "Кернеу", IP_RATING: "Қорғаныс дәрежесі", COLOR_TEMPERATURE: "Түс температурасы", LUMINOUS_FLUX: "Жарық ағыны" }, characteristicsTitle: "Сипаттамалар", article: "Артикул", priceMissing: "Баға: ақпарат табылмады", availabilityUnknown: "Қолжетімділігі расталмады", available: (n, unit = "дана") => `Қолжетімді: ${n} ${unit}`, unavailable: "Қоймада жоқ", availabilityMissing: "Қалдық: ақпарат табылмады", cache: "Кэш деректері", live: "Live деректері", verified: "verified_at", age: "жасы", dataAgeNow: "жаңа ғана", dataAgeMinutes: (n) => `${n} мин бұрын`, dataAgeHours: (n) => `${n} сағ бұрын`, dataAgeDays: (n) => `${n} күн бұрын`, fit: "Неге сәйкес:", important: "Маңызды:", documents: "Құжаттар мен сертификаттар", certificate: "Сертификат", document: "Құжат", instruction: "Нұсқаулық", quantity: "Саны", checking: "Тексерілуде…", retry: "Қайталау", add: "Қосу", preparing: "Қорғалған себет сессиясы дайындалуда", reconnect: "Келесі әрекетте байланыс қалпына келеді", summaryHint: "Алдымен қорытындыны көрсетеміз", official: "Ресми тауар карточкасын ашу", officialMissing: "Ресми карточка: ақпарат табылмады" },
    analog: { comparison: "Аналогты салыстыру", label: "Ұсынылған аналог", instead: "Оның орнына", article: "Артикул", inStock: (n, unit = "дана") => `Қоймада бар: ${n} ${unit}`, unavailable: "Қоймада жоқ", missing: "Қалдық: ақпарат табылмады", live: "Баға мен қалдық live тексерілді", notLive: "Баға мен қалдық live расталмады", checked: "Тексерілді", why: "Неге сәйкес", matching: "Сәйкес параметрлер", differences: "Маңызды айырмашылықтар", original: "Бастапқы", analog: "Аналог", infoMissing: "Ақпарат табылмады", differenceKinds: { higher_protection: "Аналогтың қорғаныс дәрежесі жоғары." }, parameters: { purpose: "Мақсаты", mounting: "Монтаж", power: "Қуат", voltage: "Кернеу", color_temperature: "Түс температурасы", luminous_flux: "Жарық ағыны", ip_rating: "Қорғаныс дәрежесі", dimensions: "Өлшемдер" } },
    cart: { added: (n) => `Қосылды: ${n} дана`, updated: "Себет жаңартылды", open: "Себетті ашу", result: "Тауар себетке қосылды", summary: "Себетке қосу қорытындысы", orderSummary: "Тапсырыс қорытындысы", expired: "Ескірген", error: "Қате", confirmationNeeded: "Растау қажет", newProposal: "Қосу үшін жаңа қорытынды жасап, оны растаңыз.", article: "Артикул", quantity: "Саны", unitPrice: "Бірлік бағасы", total: "Барлығы", note: (expiry) => `Баға мен қалдық қайта тексеріледі. Қорытындының мерзімі ${expiry}.`, checking: "Баға мен қалдық тексерілуде…", unavailable: "Растау қолжетімсіз", confirm: "Растау және қосу", replaced: "Деректер өзгерді; төмендегі жаңа қорытындыны пайдаланыңыз.", expiryFallback: "бірнеше минут ішінде", expiryUntil: (time) => `${time} дейін` },
    errors: { network_error: "Байланыс үзілді. Себет күйі қайта тексерілді; бұл растауды қауіпсіз қайталауға болады.", csrf_cookie_missing: "Себеттің қорғалған сессиясы жаңартылды. Әрекетті қайталаңыз.", csrf_failed: "Себеттің қорғалған сессиясы жаңартылды. Әрекетті қайталаңыз.", cart_busy: "Себетте басқа өзгеріс орындалуда. Растауды қайталаңыз.", action_in_progress: "Әрекет өңделуде. Бірнеше секундтан соң тексеріңіз.", insufficient_stock: (n) => `Қалдық жеткіліксіз. Ең көбі: ${n} дана.`, action_expired: "Қорытынды мерзімі аяқталды. Жаңасын жасаңыз.", action_stale: "Қорытынды ескірді, қазір өзекті нұсқа жоқ.", action_failed: "Бұл әрекет қате аяқталды. Жаңа қорытынды жасаңыз.", product_unavailable: "Тауарды қазір себетке қосу мүмкін емес.", cart_integration_unavailable: "Жұмыс себетіне қосу әзірге қолжетімсіз. Демо тек fixture-каталогымен жұмыс істейді.", cart_currency_mismatch: "Себетте басқа валютадағы тауарлар бар.", quantity_rule_violation: "Саны тауарды сату ережелеріне сәйкес емес.", catalog_verification_failed: "Баға мен қалдықты қайта тексеру мүмкін болмады. Себет өзгертілмеді.", cart_mutation_failed: "Қосу аяқталмады. Себеттің өзекті күйін тексердік.", confirmation_required: "Бұл хабарлама себет өзгерісін растамайды.", ambiguous_confirmation: "Диалогта бірнеше ұсыныс бар. Қажетті қорытындыдағы батырманы басыңыз.", no_active_action: "Белсенді ұсыныс жоқ. Тауар карточкасынан санды таңдаңыз.", generic: "Себетті өзгерту мүмкін болмады. Жаңа қорытынды жасап көріңіз." },
    site: { brand: "EKT.kz, басты бетке", nav: "Негізгі навигация", languageSwitcher: "Интерфейс тілі", catalog: "Каталог", delivery: "Жеткізу", contacts: "Байланыс", cart: "Себет", cartAria: (n) => `Себетті ашу, тауар саны: ${n}`, eyebrow: "Үй мен бизнеске арналған электротехника", hero: "Міндетіңізге сай шешім таңдаймыз", description: "Кабель, жарықтандыру, төмен вольтты аппаратура және керек-жарақ — чаттағы түсінікті кеңеспен.", openCatalog: "Каталогты ашу", ask: "Сұрақ қою", stats: "Каталогтың демо-статистикасы", catalogNearby: "Каталог жақын жерде", pages: "санаттар мен тауар беті", overline: "EKT КАТАЛОГЫ", find: "Қажеттісін бірінші сұраудан табыңыз", directions: "12 бағыт", footer: "Тексерілген кеңес", cities: "Алматы · Астана · Шымкент · тағы 6 қала", categories: [["Кабель / сым", "Кабель, сым және керек-жарақ"], ["Шамдар", "LED, шамдар және жарықты басқару"], ["Төмен вольтты аппаратура", "Желілерді автоматтандыру және қорғау"], ["Монтаж және құрал", "Сапалы монтажға қажетті заттар"]] },
    cookie: { aria: "Cookie туралы хабарлама", title: "Біз cookie қолданамыз", text: "Олар сайтты ыңғайлы етуге көмектеседі.", close: "Түсінікті" },
  },
};

export function normalizeLanguage(language) {
  return language === "kk" || language === "kk-KZ" ? "kk" : DEFAULT_LANGUAGE;
}

export function getMessages(language = DEFAULT_LANGUAGE) {
  return resources[normalizeLanguage(language)];
}

export function getLocale(language = DEFAULT_LANGUAGE) {
  return LOCALES[normalizeLanguage(language)].id;
}

export function formatNumber(value, language = DEFAULT_LANGUAGE, options = {}) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat(getLocale(language), options).format(number);
}

export function formatCurrency(value, currency = "KZT", language = DEFAULT_LANGUAGE) {
  const number = Number(value);
  if (!Number.isFinite(number)) return getMessages(language).product.priceMissing;
  return new Intl.NumberFormat(getLocale(language), { style: "currency", currency, maximumFractionDigits: 2 }).format(number);
}

export function formatDateTime(value, language = DEFAULT_LANGUAGE, options = {}) {
  if (!value) return getMessages(language).analog.infoMissing;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return getMessages(language).analog.infoMissing;
  return new Intl.DateTimeFormat(getLocale(language), options).format(date);
}

export function formatTime(value = new Date(), language = DEFAULT_LANGUAGE) {
  return new Intl.DateTimeFormat(getLocale(language), { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
