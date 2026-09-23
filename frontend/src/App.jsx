import { useCallback, useEffect, useRef, useState } from "react";

const MAX_MESSAGE_LENGTH = 1200;
const SAFE_ERROR_MESSAGE =
  "Не удалось получить ответ. Проверьте соединение и попробуйте ещё раз.";

const SUGGESTIONS = [
  {
    label: "Автомат Legrand на 160 А",
    prompt: "Нужен автомат Legrand на 160 А, 3 полюса",
  },
  {
    label: "Кабель для квартиры",
    prompt: "Подберите кабель ВВГнг для прокладки в квартире",
  },
  {
    label: "Условия доставки",
    prompt: "Есть ли доставка в Алматы и от какой суммы она бесплатная?",
  },
];

function createWelcomeMessage() {
  return {
    id: "welcome",
    role: "assistant",
    content:
      "Здравствуйте! Я помогу найти электротехнический товар, проверить наличие и подобрать подходящий вариант.\n\nЧто вы ищете?",
    suggestions: SUGGESTIONS,
  };
}

function getTimeLabel() {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function sanitizeAssistantText(value) {
  const text = String(value ?? "").replace(/[<>]/g, "");
  const withoutSecrets = text
    .replace(
      /(?:api[_ -]?key|api[_ -]?password|authorization|bearer|basic\s+auth|token|secret)\s*[:=]\s*[^\s,;]+/gi,
      "[секрет скрыт]",
    )
    .replace(
      /(?:stack trace|traceback|internal server error|at\s+[\w./-]+\([^\n]*\))/gi,
      "[внутренняя ошибка скрыта]",
    );

  return withoutSecrets.length > 2000
    ? `${withoutSecrets.slice(0, 1997)}…`
    : withoutSecrets;
}

function createAssistantResponse(prompt) {
  const normalized = prompt.toLowerCase();

  if (normalized.includes("ошибка")) {
    throw new Error("demo_failure");
  }

  if (normalized.includes("достав")) {
    return "Подскажу условия доставки после уточнения города и суммы заказа. Для Алматы точный порог бесплатной доставки сейчас нужно подтвердить по актуальному условию — я не буду называть неподтверждённую сумму.";
  }

  if (normalized.includes("кабел")) {
    return "Помогу подобрать кабель по сечению, материалу жил, напряжению и способу прокладки. Уточните длину и где он будет использоваться — так я отберу релевантные позиции из каталога.";
  }

  if (normalized.includes("автомат") || normalized.includes("legrand")) {
    return "Нашёл подходящее направление: автоматические выключатели Legrand. Уточните номинальный ток, количество полюсов и отключающую способность — после этого покажу конкретные позиции, цену и наличие.";
  }

  return "Принял запрос. В рабочей версии я найду товар в каталоге, проверю актуальные цену и наличие, а при необходимости покажу объяснимые аналоги. Сейчас это демонстрационный каркас чата.";
}

function requestDemoAnswer(prompt, signal) {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      try {
        resolve(createAssistantResponse(prompt));
      } catch (error) {
        reject(error);
      }
    }, 1150);

    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeoutId);
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      },
      { once: true },
    );
  });
}

function Icon({ name, size = 18 }) {
  const paths = {
    arrow: <><path d="m5 12 14-8-4.5 16-3.2-6.2L5 12Z" /><path d="m11.2 13.8 7.8-9.8" /></>,
    bot: <><rect x="4" y="6" width="16" height="13" rx="4" /><path d="M12 3v3M8.5 12h.01M15.5 12h.01M8 16h8" /></>,
    cart: <><path d="M4 5h2l1.4 9.1a2 2 0 0 0 2 1.7h7.7a2 2 0 0 0 1.9-1.4L20 8H7" /><circle cx="10" cy="19" r="1.2" /><circle cx="17" cy="19" r="1.2" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    trash: <><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
    refresh: <><path d="M20 11a8 8 0 0 0-14.7-4L4 9" /><path d="M4 4v5h5M4 13a8 8 0 0 0 14.7 4L20 15" /><path d="M20 20v-5h-5" /></>,
    sparkle: <><path d="m12 3 1.2 4.8L18 9l-4.8 1.2L12 15l-1.2-4.8L6 9l4.8-1.2L12 3ZM19 15l.6 2.4L22 18l-2.4.6L19 21l-.6-2.4L16 18l2.4-.6L19 15Z" /></>,
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    alert: <><path d="M12 4 3.3 19h17.4L12 4Z" /><path d="M12 9v4M12 16h.01" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      width={size}
    >
      {paths[name]}
    </svg>
  );
}

function MessageBubble({ message, onSuggestion, onRetry }) {
  const isUser = message.role === "user";
  const paragraphs = sanitizeAssistantText(message.content).split(/\n{2,}/);

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      <div
        className={`message-bubble ${isUser ? "message-bubble--user" : "message-bubble--assistant"}${message.error ? " message-bubble--error" : ""}`}
      >
        {message.error && (
          <div className="message-kicker message-kicker--error">
            <Icon name="alert" size={14} />
            Не удалось выполнить запрос
          </div>
        )}
        {paragraphs.map((paragraph, index) => (
          <p key={`${message.id}-paragraph-${index}`}>{paragraph}</p>
        ))}
        {message.suggestions && (
          <div className="suggestion-list" aria-label="Примеры запросов">
            {message.suggestions.map((suggestion) => (
              <button
                className="suggestion-chip"
                key={suggestion.label}
                onClick={() => onSuggestion(suggestion.prompt)}
                type="button"
              >
                {suggestion.label}
              </button>
            ))}
          </div>
        )}
        {message.error && (
          <button
            className="retry-button"
            onClick={() => onRetry(message.retryPrompt, message.id)}
            type="button"
          >
            <Icon name="refresh" size={14} />
            Повторить
          </button>
        )}
        <div className="message-time">{message.time ?? "Только что"}</div>
      </div>
    </div>
  );
}

function TypingMessage({ onCancel }) {
  return (
    <div className="processing-row" role="status">
      <div className="typing-bubble" aria-label="Ассистент формирует ответ">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
      <div className="processing-copy">
        <span>Формирую ответ</span>
        <button className="cancel-button" onClick={onCancel} type="button">
          Отменить
        </button>
      </div>
    </div>
  );
}

function ConfirmClearDialog({ onCancel, onConfirm }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  return (
    <div className="dialog-backdrop" role="presentation">
      <section
        aria-describedby="clear-dialog-description"
        aria-labelledby="clear-dialog-title"
        aria-modal="true"
        className="confirm-dialog"
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
        }}
        role="alertdialog"
      >
        <div className="dialog-icon"><Icon name="trash" size={18} /></div>
        <p className="dialog-eyebrow">Текущий диалог</p>
        <h2 id="clear-dialog-title">Очистить историю?</h2>
        <p id="clear-dialog-description">Сообщения будут удалены только из этого окна. Новая консультация начнётся с приветствия.</p>
        <div className="dialog-actions">
          <button className="button button--secondary" onClick={onCancel} ref={cancelRef} type="button">
            Отмена
          </button>
          <button className="button button--danger" onClick={onConfirm} type="button">
            Очистить
          </button>
        </div>
      </section>
    </div>
  );
}

function ChatWidget({ isOpen, onOpenChange }) {
  const [messages, setMessages] = useState(() => [createWelcomeMessage()]);
  const [inputValue, setInputValue] = useState("");
  const [phase, setPhase] = useState("idle");
  const [isClearDialogOpen, setIsClearDialogOpen] = useState(false);
  const inputRef = useRef(null);
  const launcherRef = useRef(null);
  const bodyRef = useRef(null);
  const pendingRef = useRef(null);

  const scrollToLatest = useCallback(() => {
    requestAnimationFrame(() => {
      if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    });
  }, []);

  useEffect(() => {
    if (isOpen) {
      window.setTimeout(() => inputRef.current?.focus(), 120);
    }
  }, [isOpen]);

  useEffect(() => {
    scrollToLatest();
  }, [messages, phase, scrollToLatest]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key !== "Escape") return;
      if (isClearDialogOpen) {
        setIsClearDialogOpen(false);
      } else if (isOpen) {
        onOpenChange(false);
        launcherRef.current?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isClearDialogOpen, isOpen]);

  useEffect(() => () => {
    pendingRef.current?.controller.abort();
    if (pendingRef.current?.statusTimer) window.clearTimeout(pendingRef.current.statusTimer);
  }, []);

  const cancelGeneration = useCallback(() => {
    const pending = pendingRef.current;
    if (!pending) return;

    pendingRef.current = null;
    pending.controller.abort();
    window.clearTimeout(pending.statusTimer);
    setPhase("idle");
    setMessages((current) => [
      ...current,
      {
        id: `cancelled-${Date.now()}`,
        role: "assistant",
        content: "Формирование ответа остановлено. Чем ещё помочь?",
        time: getTimeLabel(),
      },
    ]);
  }, []);

  const sendPrompt = useCallback((rawPrompt, { isRetry = false, errorId = "" } = {}) => {
    const prompt = String(rawPrompt).trim().slice(0, MAX_MESSAGE_LENGTH);
    if (!prompt || pendingRef.current) return;

    const controller = new AbortController();
    const statusTimer = window.setTimeout(() => setPhase("processing"), 280);
    pendingRef.current = { controller, statusTimer };
    setPhase("submitting");
    setInputValue("");
    setMessages((current) => {
      const withoutError = isRetry ? current.filter((message) => message.id !== errorId) : current;
      return [
        ...withoutError,
        {
          id: `user-${Date.now()}`,
          role: "user",
          content: prompt,
          time: getTimeLabel(),
        },
      ];
    });

    requestDemoAnswer(prompt, controller.signal)
      .then((answer) => {
        if (controller.signal.aborted) return;
        pendingRef.current = null;
        window.clearTimeout(statusTimer);
        setPhase("idle");
        setMessages((current) => [
          ...current,
          {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content: sanitizeAssistantText(answer),
            time: getTimeLabel(),
          },
        ]);
      })
      .catch((error) => {
        if (error?.name === "AbortError") return;
        pendingRef.current = null;
        window.clearTimeout(statusTimer);
        setPhase("error");
        setMessages((current) => [
          ...current,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: SAFE_ERROR_MESSAGE,
            error: true,
            retryPrompt: prompt,
            time: getTimeLabel(),
          },
        ]);
      });
  }, []);

  const clearHistory = useCallback(() => {
    if (pendingRef.current) cancelGeneration();
    setMessages([createWelcomeMessage()]);
    setInputValue("");
    setPhase("idle");
    setIsClearDialogOpen(false);
  }, [cancelGeneration]);

  const handleSubmit = (event) => {
    event.preventDefault();
    sendPrompt(inputValue);
  };

  const statusLabel = phase === "processing" || phase === "submitting"
    ? "Формирует ответ"
    : phase === "error"
      ? "Нужна повторная попытка"
      : "Онлайн · отвечает за несколько секунд";

  return (
    <>
      <button
        aria-expanded={isOpen}
        aria-label={isOpen ? "Закрыть чат с консультантом" : "Открыть чат с консультантом"}
        className="chat-launcher"
        onClick={() => onOpenChange(!isOpen)}
        ref={launcherRef}
        type="button"
      >
        <span className="launcher-icon"><Icon name="bot" size={18} /></span>
        <span className="launcher-copy">
          <strong>Помощь с выбором</strong>
          <small>AI-консультант</small>
        </span>
        <span className="launcher-pulse" />
      </button>

      {isOpen && (
        <aside
          aria-label="Чат-консультант EKT.kz"
          aria-modal="false"
          className="chat-widget"
          role="dialog"
        >
          <header className="chat-header">
            <div className="assistant-identity">
              <div className="assistant-avatar"><Icon name="bot" size={19} /></div>
              <div className="assistant-title-wrap">
                <strong>EKT Консультант</strong>
                <span className={`assistant-status ${phase === "error" ? "assistant-status--error" : ""}`}>
                  <span className="status-dot" />
                  {statusLabel}
                </span>
              </div>
            </div>
            <div className="chat-header-actions">
              <button
                aria-label="Очистить историю"
                className="icon-button"
                onClick={() => setIsClearDialogOpen(true)}
                title="Очистить историю"
                type="button"
              >
                <Icon name="trash" size={17} />
              </button>
              <button
                aria-label="Закрыть чат"
                className="icon-button"
                onClick={() => {
                  onOpenChange(false);
                  launcherRef.current?.focus();
                }}
                title="Закрыть чат"
                type="button"
              >
                <Icon name="close" size={18} />
              </button>
            </div>
          </header>

          <div
            aria-busy={phase === "submitting" || phase === "processing"}
            className="chat-body"
            ref={bodyRef}
            role="log"
            aria-live="polite"
          >
            <div className="chat-date"><span /> Сегодня <span /></div>
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onRetry={(prompt, errorId) => {
                  setPhase("idle");
                  sendPrompt(prompt, { errorId, isRetry: true });
                }}
                onSuggestion={sendPrompt}
              />
            ))}
            {(phase === "submitting" || phase === "processing") && <TypingMessage onCancel={cancelGeneration} />}
          </div>

          <div className="chat-composer-wrap">
            <p className="composer-hint" role="status">
              <Icon name="sparkle" size={13} />
              Ответы основаны на данных каталога EKT.kz
            </p>
            <form className="chat-composer" onSubmit={handleSubmit}>
              <label className="sr-only" htmlFor="message-input">Введите сообщение</label>
              <textarea
                aria-describedby="composer-disclaimer"
                autoComplete="off"
                disabled={Boolean(pendingRef.current)}
                id="message-input"
                maxLength={MAX_MESSAGE_LENGTH}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendPrompt(inputValue);
                  }
                }}
                placeholder="Например: нужен кабель 3×2,5 мм²"
                ref={inputRef}
                rows={1}
                value={inputValue}
              />
              <div className="composer-actions">
                <span className="composer-counter">{inputValue.length}/{MAX_MESSAGE_LENGTH}</span>
                <button
                  aria-label="Отправить сообщение"
                  className="send-button"
                  disabled={Boolean(pendingRef.current) || !inputValue.trim()}
                  type="submit"
                >
                  <Icon name="arrow" size={17} />
                </button>
              </div>
            </form>
            <p className="composer-disclaimer" id="composer-disclaimer">
              Не вводите платёжные данные и пароли
            </p>
          </div>
        </aside>
      )}

      {isClearDialogOpen && (
        <ConfirmClearDialog onCancel={() => setIsClearDialogOpen(false)} onConfirm={clearHistory} />
      )}
    </>
  );
}

function SitePreview({ onOpenChat }) {
  const categories = [
    ["Кабель / провод", "Кабель, провод и аксессуары", "#d9f3e9"],
    ["Светильники", "LED, лампы и управление светом", "#e3edff"],
    ["Низковольтная аппаратура", "Автоматика и защита сетей", "#fff0cc"],
    ["Монтаж и инструмент", "Всё для надёжного монтажа", "#f1e5ff"],
  ];

  return (
    <main className="site-preview">
      <nav className="site-nav">
        <a className="brand" href="#top" aria-label="EKT.kz, на главную">
          <span className="brand-mark">E</span>
          <span>EKT<span className="brand-dot">.</span>kz</span>
        </a>
        <div className="site-nav-links" aria-label="Основная навигация">
          <a href="#catalog">Каталог</a>
          <a href="#delivery">Доставка</a>
          <a href="#contacts">Контакты</a>
        </div>
        <button className="cart-button" type="button">
          <Icon name="cart" size={16} />
          Корзина <span className="cart-count">0</span>
        </button>
      </nav>

      <section className="hero-preview" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Электротехника для дома и бизнеса</p>
          <h1>Подберём решение под вашу задачу</h1>
          <p className="hero-description">
            Кабель, освещение, низковольтная аппаратура и комплектующие — с понятной консультацией в чате.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#catalog">Открыть каталог</a>
            <button className="text-button" onClick={onOpenChat} type="button">Задать вопрос <span>↗</span></button>
          </div>
        </div>
        <div className="hero-card" aria-label="Демо-статистика каталога">
          <div className="hero-card-top"><span className="hero-card-live"><span /> DEMO PREVIEW</span><span>2026</span></div>
          <div className="hero-card-label">Каталог рядом</div>
          <div className="hero-card-value">14<span>k</span></div>
          <div className="hero-card-caption">страниц категорий и товаров</div>
          <div className="hero-card-chart"><i /><i /><i /><i /><i /><i /><i /></div>
        </div>
      </section>

      <section className="category-section" id="catalog">
        <div className="section-heading"><div><span className="section-overline">КАТАЛОГ EKT</span><h2>Найдите нужное с первого запроса</h2></div><span className="section-note">12 направлений</span></div>
        <div className="category-grid">
          {categories.map(([title, description, color], index) => (
            <a className="category-card" href="#catalog" key={title}>
              <span className="category-number">0{index + 1}</span>
              <span className="category-icon" style={{ backgroundColor: color }}>{["⌁", "◉", "▣", "⌗"][index]}</span>
              <strong>{title}</strong>
              <span>{description}</span>
              <span className="category-arrow">↗</span>
            </a>
          ))}
        </div>
      </section>

      <section className="site-footer-strip" id="delivery"><span>Проверенная консультация</span><span>·</span><span id="contacts">Алматы · Астана · Шымкент · и ещё 6 городов</span></section>
    </main>
  );
}

function CookieBanner({ onClose }) {
  return (
    <aside className="cookie-banner" aria-label="Уведомление о cookie">
      <div className="cookie-copy"><strong>Мы используем cookie</strong><p>Они помогают сделать сайт удобнее.</p></div>
      <button className="cookie-close" onClick={onClose} type="button">Понятно</button>
    </aside>
  );
}

export default function App() {
  const [showCookie, setShowCookie] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(false);

  return (
    <>
      <SitePreview onOpenChat={() => setIsChatOpen(true)} />
      {showCookie && <CookieBanner onClose={() => setShowCookie(false)} />}
      <ChatWidget isOpen={isChatOpen} onOpenChange={setIsChatOpen} />
    </>
  );
}
