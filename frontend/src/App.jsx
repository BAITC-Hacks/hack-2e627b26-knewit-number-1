import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  CartApiError,
  confirmCartAction,
  confirmCartText,
  createCartAction,
  getCart,
  getProduct,
} from "./cartApi.js";

const MAX_MESSAGE_LENGTH = 1200;
const DEMO_PRODUCT_ID = 900001;
const TEXT_CONFIRMATIONS = new Set(["да", "подтверждаю", "добавить в корзину"]);
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

function createId(prefix) {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value}`;
}

function normalizeConfirmation(value) {
  return String(value).toLocaleLowerCase("ru-RU").trim().split(/\s+/).join(" ");
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

async function createAssistantResponse(prompt, signal) {
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
    const product = await getProduct(DEMO_PRODUCT_ID, { signal });
    return {
      content: "Нашёл демонстрационную позицию в каталоге. Укажите количество и проверьте резюме перед добавлением:",
      product: { ...product, verified_at: new Date().toISOString() },
    };
  }

  return "Принял запрос. В рабочей версии я найду товар в каталоге, проверю актуальные цену и наличие, а при необходимости покажу объяснимые аналоги. Сейчас это демонстрационный каркас чата.";
}

async function requestDemoAnswer(prompt, signal) {
  await new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(resolve, 650);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timeoutId);
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    }, { once: true });
  });

  return createAssistantResponse(prompt, signal);
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

function displayProductValue(value) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return "Информация не найдена";
  }
  return String(value);
}

function toFiniteNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatProductPrice(value) {
  const price = toFiniteNumber(value);
  if (price === null) {
    return "Информация не найдена";
  }
  return `${new Intl.NumberFormat("ru-RU").format(price)} ₸`;
}

function formatMoney(value, currency = "KZT") {
  const amount = toFiniteNumber(value);
  if (amount === null) return "Информация не найдена";
  try {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency,
      maximumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount);
  } catch {
    return `${new Intl.NumberFormat("ru-RU").format(amount)} ${currency}`;
  }
}

function formatExpiry(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "в течение нескольких минут";
  return `до ${new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(date)}`;
}

function cartErrorCopy(code, payload = {}) {
  const messages = {
    ambiguous_confirmation: "В диалоге несколько предложений. Нажмите кнопку в нужном резюме.",
    no_active_action: "Активного предложения нет. Выберите количество в карточке товара.",
    confirmation_required: "Это сообщение не подтверждает изменение корзины.",
    product_unavailable: "Товар сейчас недоступен для добавления в корзину.",
    cart_integration_unavailable: "Добавление в рабочую корзину пока недоступно. Демо работает только с fixture-каталогом.",
    cart_currency_mismatch: "В корзине уже есть товары в другой валюте.",
    quantity_limit_exceeded: `Можно выбрать не более ${payload?.maximum_quantity ?? "доступного лимита"}.`,
    quantity_rule_violation: "Количество не соответствует правилам продажи товара.",
    catalog_verification_failed: "Не удалось заново проверить цену и остаток. Корзина не изменена.",
    cart_mutation_failed: "Добавление не завершено. Мы проверили актуальное состояние корзины.",
    cart_busy: "Корзина занята другим изменением. Повторите подтверждение.",
    action_in_progress: "Действие ещё обрабатывается. Повторите проверку через несколько секунд.",
    action_expired: "Срок действия резюме истёк. Сформируйте новое.",
    action_stale: "Резюме устарело, а актуального варианта сейчас нет.",
    action_failed: "Это действие уже завершилось ошибкой. Создайте новое резюме.",
    csrf_failed: "Защитная сессия корзины обновлена. Повторите действие.",
    csrf_cookie_missing: "Защитная сессия корзины обновлена. Повторите действие.",
    network_error: "Связь прервалась. Состояние корзины перепроверено; можно безопасно повторить это подтверждение.",
  };
  return messages[code] ?? "Не удалось изменить корзину. Попробуйте сформировать новое резюме.";
}

function formatVerifiedAt(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "Информация не найдена";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDataAge(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "Информация не найдена";
  const ageSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (ageSeconds < 60) return "только что";
  if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)} мин. назад`;
  if (ageSeconds < 86400) return `${Math.floor(ageSeconds / 3600)} ч назад`;
  return `${Math.floor(ageSeconds / 86400)} дн. назад`;
}

const PRODUCT_PROPERTY_FIELDS = [
  ["Серия", ["SERIES", "SERIA", "SERIIA"]],
  ["Полюса", ["KOLICHESTVO_POLYUSOV"]],
  ["Номинальный ток", ["NOMINALNYY_TOK"]],
  ["Отключающая способность", ["NOMINALNAYA_OTKLYUCHAYUSHCHAYA_SPOSOBNOST"]],
  ["Напряжение", ["NOMINALNOE_NAPRYAZHENIE"]],
  ["Бренд", ["TORGOVAYA_MARKA", "BRAND"]],
];

function getProductCharacteristics(product) {
  if (Array.isArray(product?.characteristics) && product.characteristics.length > 0) {
    return product.characteristics.map((item, index) => {
      if (Array.isArray(item)) return [item[0], item[1]];
      return [item?.label ?? item?.name ?? `Характеристика ${index + 1}`, item?.value];
    });
  }

  const properties = product?.properties && typeof product.properties === "object" ? product.properties : {};
  const mapped = PRODUCT_PROPERTY_FIELDS.map(([label, keys]) => {
    const key = keys.find((candidate) => properties[candidate] !== undefined);
    return [label, key ? properties[key] : undefined];
  });
  if (mapped.some(([, value]) => value !== undefined && value !== null && value !== "")) return mapped;
  return [["Характеристики", "Информация не найдена"]];
}

function ProductCard({ cartStatus, messageId, onCreateProposal, product, proposalState }) {
  const [imageFailed, setImageFailed] = useState(false);
  const [selectedQuantity, setSelectedQuantity] = useState("1");
  const productName = displayProductValue(product?.name);
  const article = displayProductValue(product?.article);
  const isCached = [product?.data_status, product?.dataStatus, product?.source, product?.status]
    .some((value) => String(value ?? "").toLowerCase() === "cached" || String(value ?? "").toLowerCase() === "cache");
  const verifiedAt = product?.verified_at ?? product?.verifiedAt;
  const characteristics = getProductCharacteristics(product);
  const sellableQuantity = toFiniteNumber(product?.availability?.sellable_quantity);
  const quantity = sellableQuantity ?? toFiniteNumber(product?.quantity);
  const quantityKnown = quantity !== null;
  const isSellable = product?.availability?.status === "available" && sellableQuantity > 0;
  const availability = product?.availability?.status === "availability_unknown"
    ? "Доступность не подтверждена"
    : quantityKnown
      ? quantity > 0 ? `Доступно: ${quantity} шт.` : "Нет в наличии"
      : "Наличие: информация не найдена";
  const isProposing = proposalState === "proposing";
  const numericQuantity = Number(selectedQuantity);
  const quantityIsValid = Number.isInteger(numericQuantity) && numericQuantity > 0;

  return (
    <article className="product-card" aria-label={`Карточка товара: ${productName}`}>
      <div className="product-card-media">
        {product?.image && !imageFailed ? (
          <img
            alt={`Изображение товара: ${productName}`}
            className="product-card-image"
            onError={() => setImageFailed(true)}
            src={product.image}
          />
        ) : (
          <div className="product-card-image-missing">Изображение: информация не найдена</div>
        )}
      </div>
      <div className="product-card-body">
        <div className="product-card-eyebrow">Товар из каталога EKT.kz</div>
        <h3 className="product-card-title">{productName}</h3>
        <div className="product-card-article">Артикул: {article}</div>
        <div className="product-card-summary">
          <strong className="product-card-price">{formatProductPrice(product?.price)}</strong>
          <span className={`product-card-availability ${isSellable ? "product-card-availability--in" : ""}`}>
            {availability}
          </span>
        </div>
        <div className={`product-card-data ${isCached ? "product-card-data--cached" : "product-card-data--live"}`}>
          <span className="product-card-data-dot" />
          <span>{isCached ? "Данные из кэша" : "Данные live"}</span>
          {isCached && (
            <span className="product-card-data-age">
              verified_at: {formatVerifiedAt(verifiedAt)} · возраст: {formatDataAge(verifiedAt)}
            </span>
          )}
        </div>
        <dl className="product-card-characteristics">
          {characteristics.map(([label, value]) => (
            <div className="product-characteristic" key={label}>
              <dt>{displayProductValue(label)}</dt>
              <dd>{displayProductValue(value)}</dd>
            </div>
          ))}
        </dl>
        {(product?.fit_reason || product?.important_difference) && (
          <div className="product-card-notes">
            {product.fit_reason && <p><strong>Почему подходит:</strong> {product.fit_reason}</p>}
            {product.important_difference && <p><strong>Важно:</strong> {product.important_difference}</p>}
          </div>
        )}
        <form
          className="product-card-cart"
          onSubmit={(event) => {
            event.preventDefault();
            if (quantityIsValid) onCreateProposal(product, messageId, numericQuantity);
          }}
        >
          <label htmlFor={`quantity-${messageId}`}>Количество</label>
          <div className="product-card-cart-controls">
            <input
              aria-describedby={`quantity-help-${messageId}`}
              disabled={!isSellable || isProposing}
              id={`quantity-${messageId}`}
              inputMode="numeric"
              min="1"
              onChange={(event) => setSelectedQuantity(event.target.value)}
              step="1"
              type="number"
              value={selectedQuantity}
            />
            <button disabled={cartStatus === "loading" || !isSellable || !quantityIsValid || isProposing} type="submit">
              <Icon name="cart" size={15} />
              {isProposing ? "Проверяю…" : proposalState === "failed" ? "Повторить" : "Добавить"}
            </button>
          </div>
          <span className="product-card-cart-help" id={`quantity-help-${messageId}`}>
            {cartStatus === "loading"
              ? "Подготавливаем защищённую сессию корзины"
              : cartStatus === "error"
                ? "Соединение восстановится при следующей попытке"
                : "Сначала покажем итоговое резюме"}
          </span>
        </form>
        {product?.url ? (
          <a
            className="product-card-link"
            href={product.url}
            rel="noopener noreferrer"
            target="_blank"
          >
            Открыть официальную карточку <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <span className="product-card-link product-card-link--missing">Официальная карточка: информация не найдена</span>
        )}
      </div>
    </article>
  );
}

function CartConfirmation({ action, onConfirm, phase = "proposed", result, statusNote }) {
  const product = action?.product ?? {};
  const isPending = phase === "confirming";
  const isInactive = ["expired", "failed", "succeeded"].includes(phase);

  if (phase === "succeeded" && result) {
    return (
      <section className="cart-result cart-result--success" aria-label="Товар добавлен в корзину">
        <div className="cart-result-icon"><Icon name="check" size={18} /></div>
        <div>
          <strong>Добавлено: {result.added_quantity} шт.</strong>
          <span>Корзина обновлена</span>
        </div>
        <a href={result.cart?.url || "/demo/cart/"} rel="noopener noreferrer" target="_blank">
          Открыть корзину <span aria-hidden="true">↗</span>
        </a>
      </section>
    );
  }

  return (
    <section
      className={`cart-confirmation cart-confirmation--${phase}`}
      data-action-id={action?.action_id}
      aria-label="Резюме добавления в корзину"
    >
      <div className="cart-confirmation-head">
        <span><Icon name="cart" size={14} /> Резюме заказа</span>
        <span>{phase === "expired" ? "Устарело" : phase === "failed" ? "Ошибка" : "Нужно подтверждение"}</span>
      </div>
      <div className="cart-confirmation-product">
        <strong>{displayProductValue(product.name)}</strong>
        <span>Артикул {displayProductValue(product.article)}</span>
      </div>
      <dl className="cart-confirmation-lines">
        <div><dt>Количество</dt><dd>{action.quantity} шт.</dd></div>
        <div><dt>Цена за единицу</dt><dd>{formatMoney(action.unit_price, action.currency)}</dd></div>
        <div className="cart-confirmation-total"><dt>Итого</dt><dd>{formatMoney(action.total, action.currency)}</dd></div>
      </dl>
      <p className="cart-confirmation-note">
        Цена и остаток будут проверены ещё раз. Резюме действует {formatExpiry(action.expires_at)}.
      </p>
      {statusNote && <p className="cart-confirmation-status" role="status">{statusNote}</p>}
      <button
        className="cart-confirmation-button"
        disabled={isPending || isInactive}
        onClick={() => onConfirm(action.action_id)}
        type="button"
      >
        {isPending ? "Проверяю цену и остаток…" : isInactive ? "Подтверждение недоступно" : "Подтвердить и добавить"}
      </button>
    </section>
  );
}

function MessageBubble({
  cartStatus,
  cartRequest,
  message,
  onConfirmAction,
  onCreateProposal,
  onRetry,
  onSuggestion,
}) {
  const isUser = message.role === "user";
  const paragraphs = sanitizeAssistantText(message.content).split(/\n{2,}/);
  const isRich = Boolean(message.product || message.cartAction);

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      <div
        className={`message-bubble ${isUser ? "message-bubble--user" : "message-bubble--assistant"}${message.error ? " message-bubble--error" : ""}${isRich ? " message-bubble--rich" : ""}`}
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
        {message.product && (
          <ProductCard
            cartStatus={cartStatus}
            messageId={message.id}
            onCreateProposal={onCreateProposal}
            product={message.product}
            proposalState={cartRequest?.kind === "proposal" && cartRequest.key === message.id ? "proposing" : message.proposalState}
          />
        )}
        {message.cartAction && (
          <CartConfirmation
            action={message.cartAction}
            onConfirm={onConfirmAction}
            phase={message.cartPhase}
            result={message.cartResult}
            statusNote={message.cartStatusNote}
          />
        )}
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
        {message.error && message.retryPrompt && (
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
  const confirmRef = useRef(null);

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
          if (event.key === "Tab") {
            if (event.shiftKey && document.activeElement === cancelRef.current) {
              event.preventDefault();
              confirmRef.current?.focus();
            } else if (!event.shiftKey && document.activeElement === confirmRef.current) {
              event.preventDefault();
              cancelRef.current?.focus();
            }
          }
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
          <button className="button button--danger" onClick={onConfirm} ref={confirmRef} type="button">
            Очистить
          </button>
        </div>
      </section>
    </div>
  );
}

function ChatWidget({ cartStatus, isOpen, onCartChange, onEnsureCart, onOpenChange }) {
  const [messages, setMessages] = useState(() => [createWelcomeMessage()]);
  const [inputValue, setInputValue] = useState("");
  const [phase, setPhase] = useState("idle");
  const [cartRequest, setCartRequest] = useState(null);
  const [isClearDialogOpen, setIsClearDialogOpen] = useState(false);
  const inputRef = useRef(null);
  const launcherRef = useRef(null);
  const clearButtonRef = useRef(null);
  const bodyRef = useRef(null);
  const openFocusTimerRef = useRef(null);
  const pendingRef = useRef(null);
  const cartLockRef = useRef(false);
  const dialogIdRef = useRef(createId("dialog"));
  const messageVersionRef = useRef(0);
  const proposalRetryRef = useRef(new Map());

  const closeClearDialog = useCallback(() => {
    setIsClearDialogOpen(false);
    requestAnimationFrame(() => clearButtonRef.current?.focus());
  }, []);

  const scrollToLatest = useCallback(() => {
    requestAnimationFrame(() => {
      if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    });
  }, []);

  useEffect(() => {
    if (isOpen) {
      openFocusTimerRef.current = window.setTimeout(() => {
        openFocusTimerRef.current = null;
        inputRef.current?.focus();
      }, 120);
    }

    return () => {
      if (openFocusTimerRef.current) window.clearTimeout(openFocusTimerRef.current);
      openFocusTimerRef.current = null;
    };
  }, [isOpen]);

  useEffect(() => {
    if (isClearDialogOpen && openFocusTimerRef.current) {
      window.clearTimeout(openFocusTimerRef.current);
      openFocusTimerRef.current = null;
    }
  }, [isClearDialogOpen]);

  useEffect(() => {
    scrollToLatest();
  }, [messages, phase, scrollToLatest]);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key !== "Escape") return;
      if (isClearDialogOpen) {
        closeClearDialog();
      } else if (isOpen) {
        onOpenChange(false);
        launcherRef.current?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeClearDialog, isClearDialogOpen, isOpen, onOpenChange]);

  useEffect(() => () => {
    pendingRef.current?.controller.abort();
    if (pendingRef.current?.statusTimer) window.clearTimeout(pendingRef.current.statusTimer);
  }, []);

  const updateCartFromPayload = useCallback((payload) => {
    if (payload?.cart) onCartChange(payload.cart);
  }, [onCartChange]);

  const expireActiveSummaries = useCallback((current, exceptActionId = "") => current.map((message) => {
    if (
      message.cartAction
      && message.cartPhase === "proposed"
      && message.cartAction.action_id !== exceptActionId
    ) {
      return {
        ...message,
        cartPhase: "expired",
        cartStatusNote: "Это резюме заменено более новым.",
      };
    }
    return message;
  }), []);

  const appendReplacement = useCallback((payload, sourceActionId, content) => {
    const replacement = payload?.replacement_action;
    if (replacement?.message_version) {
      messageVersionRef.current = Math.max(messageVersionRef.current, replacement.message_version);
    }
    updateCartFromPayload(payload);
    setMessages((current) => {
      const updated = expireActiveSummaries(current).map((message) => (
        message.cartAction?.action_id === sourceActionId
          ? { ...message, cartPhase: "expired", cartStatusNote: "Данные изменились; используйте новое резюме ниже." }
          : message
      ));
      if (!replacement) {
        return [
          ...updated,
          {
            id: createId("cart-unavailable"),
            role: "assistant",
            content,
            time: getTimeLabel(),
          },
        ];
      }
      return [
        ...updated,
        {
          id: createId("cart-replacement"),
          role: "assistant",
          content,
          cartAction: replacement,
          cartPhase: "proposed",
          time: getTimeLabel(),
        },
      ];
    });
  }, [expireActiveSummaries, updateCartFromPayload]);

  const applyCartSuccess = useCallback((result) => {
    onCartChange(result.cart);
    setMessages((current) => current.map((message) => (
      message.cartAction?.action_id === result.action_id
        ? {
          ...message,
          cartPhase: "succeeded",
          cartResult: result,
          cartStatusNote: "",
        }
        : message
    )));
  }, [onCartChange]);

  const createProposal = useCallback(async (product, messageId, quantity) => {
    if (cartLockRef.current) return;
    cartLockRef.current = true;
    setCartRequest({ kind: "proposal", key: messageId });
    setMessages((current) => current.map((message) => (
      message.id === messageId ? { ...message, proposalState: "proposing" } : message
    )));

    const retryPayload = proposalRetryRef.current.get(messageId);
    const payload = retryPayload?.quantity === quantity
      ? retryPayload
      : {
        dialog_id: dialogIdRef.current,
        message_id: messageId,
        message_version: ++messageVersionRef.current,
        product_id: product.id,
        offer_id: null,
        quantity,
      };

    try {
      if (cartStatus !== "ready") await onEnsureCart();
      const action = await createCartAction(payload);
      proposalRetryRef.current.delete(messageId);
      setMessages((current) => [
        ...expireActiveSummaries(current).map((message) => (
          message.id === messageId ? { ...message, proposalState: "idle" } : message
        )),
        {
          id: createId("cart-summary"),
          role: "assistant",
          content: "Проверьте состав действия. Корзина изменится только после подтверждения.",
          cartAction: action,
          cartPhase: "proposed",
          time: getTimeLabel(),
        },
      ]);
    } catch (error) {
      const apiError = error instanceof CartApiError ? error : new CartApiError(String(error));
      const response = apiError.payload;
      updateCartFromPayload(response);
      if (response?.replacement_action || apiError.code === "insufficient_stock") {
        proposalRetryRef.current.delete(messageId);
        setMessages((current) => current.map((message) => (
          message.id === messageId ? { ...message, proposalState: "idle" } : message
        )));
        appendReplacement(
          response,
          response?.action_id,
          response?.replacement_action
            ? `Запрошенного количества нет. Подготовил новое резюме на ${response.maximum_quantity} шт.`
            : "Доступный остаток закончился. Товар не добавлен.",
        );
      } else {
        if (["network_error", "csrf_cookie_missing", "csrf_failed"].includes(apiError.code)) {
          proposalRetryRef.current.set(messageId, payload);
          if (["csrf_cookie_missing", "csrf_failed"].includes(apiError.code)) {
            try {
              await onEnsureCart();
            } catch {
              // The same immutable proposal payload remains available for retry.
            }
          }
        } else {
          proposalRetryRef.current.delete(messageId);
        }
        setMessages((current) => [
          ...current.map((message) => (
            message.id === messageId ? { ...message, proposalState: "failed" } : message
          )),
          {
            id: createId("cart-error"),
            role: "assistant",
            content: cartErrorCopy(apiError.code, response),
            error: true,
            time: getTimeLabel(),
          },
        ]);
      }
    } finally {
      cartLockRef.current = false;
      setCartRequest(null);
    }
  }, [appendReplacement, cartStatus, expireActiveSummaries, onEnsureCart, updateCartFromPayload]);

  const confirmAction = useCallback(async (actionId) => {
    if (cartLockRef.current) return;
    cartLockRef.current = true;
    setCartRequest({ kind: "confirmation", key: actionId });
    setMessages((current) => current.map((message) => (
      message.cartAction?.action_id === actionId
        ? { ...message, cartPhase: "confirming", cartStatusNote: "" }
        : message
    )));

    try {
      const result = await confirmCartAction(actionId);
      applyCartSuccess(result);
    } catch (error) {
      const apiError = error instanceof CartApiError ? error : new CartApiError(String(error));
      const response = apiError.payload;
      updateCartFromPayload(response);
      if (response?.replacement_action) {
        appendReplacement(
          response,
          actionId,
          apiError.code === "insufficient_stock"
            ? `Остаток уменьшился. Подготовил новое резюме на ${response.replacement_action.quantity} шт.`
            : "Цена, остаток или версия корзины изменились. Подтвердите обновлённое резюме.",
        );
      } else if (["network_error", "csrf_cookie_missing", "csrf_failed", "cart_busy", "action_in_progress"].includes(apiError.code)) {
        try {
          await onEnsureCart();
        } catch {
          // The original action remains the only safe retry target.
        }
        setMessages((current) => current.map((message) => (
          message.cartAction?.action_id === actionId
            ? { ...message, cartPhase: "proposed", cartStatusNote: cartErrorCopy(apiError.code) }
            : message
        )));
      } else {
        const nextPhase = ["action_expired", "action_stale"].includes(apiError.code) ? "expired" : "failed";
        setMessages((current) => current.map((message) => (
          message.cartAction?.action_id === actionId
            ? { ...message, cartPhase: nextPhase, cartStatusNote: cartErrorCopy(apiError.code, response) }
            : message
        )));
      }
    } finally {
      cartLockRef.current = false;
      setCartRequest(null);
    }
  }, [appendReplacement, applyCartSuccess, onEnsureCart, updateCartFromPayload]);

  const confirmByText = useCallback(async (text) => {
    if (cartLockRef.current) return;
    cartLockRef.current = true;
    setCartRequest({ kind: "text-confirmation", key: dialogIdRef.current });
    setMessages((current) => current.map((message) => (
      message.cartAction && message.cartPhase === "proposed"
        ? { ...message, cartPhase: "confirming", cartStatusNote: "" }
        : message
    )));
    try {
      const result = await confirmCartText(dialogIdRef.current, text);
      applyCartSuccess(result);
    } catch (error) {
      const apiError = error instanceof CartApiError ? error : new CartApiError(String(error));
      const response = apiError.payload;
      updateCartFromPayload(response);
      if (response?.replacement_action) {
        appendReplacement(
          response,
          response.action_id,
          "Предложение изменилось. Проверьте и подтвердите новое резюме.",
        );
      } else {
        if (["network_error", "csrf_cookie_missing", "csrf_failed"].includes(apiError.code)) {
          try {
            await onEnsureCart();
          } catch {
            // A refreshed cart is best-effort; no new mutation is created.
          }
        }
        setMessages((current) => [
          ...current.map((message) => (
            message.cartPhase === "confirming"
              ? { ...message, cartPhase: "proposed", cartStatusNote: "" }
              : message
          )),
          {
            id: createId("cart-text-error"),
            role: "assistant",
            content: cartErrorCopy(apiError.code, response),
            error: !["ambiguous_confirmation", "no_active_action", "confirmation_required"].includes(apiError.code),
            time: getTimeLabel(),
          },
        ]);
      }
    } finally {
      cartLockRef.current = false;
      setCartRequest(null);
    }
  }, [appendReplacement, applyCartSuccess, onEnsureCart, updateCartFromPayload]);

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
    if (!prompt || pendingRef.current || cartLockRef.current) return;

    setInputValue("");
    setMessages((current) => {
      const withoutError = isRetry ? current.filter((message) => message.id !== errorId) : current;
      return [
        ...withoutError,
        {
          id: createId("user"),
          role: "user",
          content: prompt,
          time: getTimeLabel(),
        },
      ];
    });

    if (TEXT_CONFIRMATIONS.has(normalizeConfirmation(prompt))) {
      void confirmByText(prompt);
      return;
    }

    const controller = new AbortController();
    const statusTimer = window.setTimeout(() => setPhase("processing"), 280);
    pendingRef.current = { controller, statusTimer };
    setPhase("submitting");
    requestDemoAnswer(prompt, controller.signal)
      .then((answer) => {
        if (controller.signal.aborted) return;
        const response = typeof answer === "string" ? { content: answer } : answer;
        pendingRef.current = null;
        window.clearTimeout(statusTimer);
        setPhase("idle");
        setMessages((current) => [
          ...current,
          {
            id: createId("assistant"),
            role: "assistant",
            content: sanitizeAssistantText(response?.content),
            product: response?.product,
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
            id: createId("error"),
            role: "assistant",
            content: SAFE_ERROR_MESSAGE,
            error: true,
            retryPrompt: prompt,
            time: getTimeLabel(),
          },
        ]);
      });
  }, [confirmByText]);

  const clearHistory = useCallback(() => {
    if (pendingRef.current) cancelGeneration();
    setMessages([createWelcomeMessage()]);
    setInputValue("");
    setPhase("idle");
    setCartRequest(null);
    cartLockRef.current = false;
    dialogIdRef.current = createId("dialog");
    messageVersionRef.current = 0;
    proposalRetryRef.current.clear();
    setIsClearDialogOpen(false);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [cancelGeneration]);

  const handleSubmit = (event) => {
    event.preventDefault();
    sendPrompt(inputValue);
  };

  const statusLabel = cartRequest
    ? "Проверяет корзину"
    : phase === "processing" || phase === "submitting"
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
                disabled={Boolean(cartRequest)}
                onClick={() => setIsClearDialogOpen(true)}
                ref={clearButtonRef}
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
            aria-busy={Boolean(cartRequest) || phase === "submitting" || phase === "processing"}
            className="chat-body"
            ref={bodyRef}
            role="log"
            aria-live="polite"
          >
            <div className="chat-date"><span /> Сегодня <span /></div>
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                cartStatus={cartStatus}
                cartRequest={cartRequest}
                message={message}
                onConfirmAction={confirmAction}
                onCreateProposal={createProposal}
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
                disabled={Boolean(pendingRef.current) || Boolean(cartRequest)}
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
                  disabled={Boolean(pendingRef.current) || Boolean(cartRequest) || !inputValue.trim()}
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
        <ConfirmClearDialog onCancel={closeClearDialog} onConfirm={clearHistory} />
      )}
    </>
  );
}

function SitePreview({ cart, onOpenChat }) {
  const categories = [
    ["Кабель / провод", "Кабель, провод и аксессуары", "#d9f3e9"],
    ["Светильники", "LED, лампы и управление светом", "#e3edff"],
    ["Низковольтная аппаратура", "Автоматика и защита сетей", "#fff0cc"],
    ["Монтаж и инструмент", "Всё для надёжного монтажа", "#f1e5ff"],
  ];
  const cartCount = Array.isArray(cart?.items)
    ? cart.items.reduce((total, item) => total + (toFiniteNumber(item?.quantity) ?? 0), 0)
    : 0;

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
        <a
          aria-label={`Открыть корзину, товаров: ${cartCount}`}
          className="cart-button"
          href={cart?.url || "/demo/cart/"}
          rel="noopener noreferrer"
          target="_blank"
        >
          <Icon name="cart" size={16} />
          Корзина <span className="cart-count">{cartCount}</span>
        </a>
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
  const [cart, setCart] = useState({ items: [], total: "0.00", url: "/demo/cart/" });
  const [cartStatus, setCartStatus] = useState("loading");

  const refreshCart = useCallback(async () => {
    setCartStatus("loading");
    try {
      const snapshot = await getCart();
      setCart(snapshot);
      setCartStatus("ready");
      return snapshot;
    } catch (error) {
      setCartStatus("error");
      throw error;
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    const controller = new AbortController();
    getCart({ signal: controller.signal })
      .then((snapshot) => {
        if (ignore) return;
        setCart(snapshot);
        setCartStatus("ready");
      })
      .catch(() => {
        if (!ignore) setCartStatus("error");
      });
    return () => {
      ignore = true;
      controller.abort();
    };
  }, []);

  return (
    <>
      <SitePreview cart={cart} onOpenChat={() => setIsChatOpen(true)} />
      {showCookie && <CookieBanner onClose={() => setShowCookie(false)} />}
      <ChatWidget
        cartStatus={cartStatus}
        isOpen={isChatOpen}
        onCartChange={(snapshot) => {
          setCart(snapshot);
          setCartStatus("ready");
        }}
        onEnsureCart={refreshCart}
        onOpenChange={setIsChatOpen}
      />
    </>
  );
}
