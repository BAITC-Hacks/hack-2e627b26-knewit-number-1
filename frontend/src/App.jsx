import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  CartApiError,
  confirmCartAction,
  confirmCartText,
  createCartAction,
  getCart,
  getProduct,
  setChatLanguage,
} from "./cartApi.js";
import {
  DEFAULT_LANGUAGE,
  LOCALES,
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatTime,
  getLocale,
  getMessages,
  normalizeLanguage,
} from "./i18n.js";

const MAX_MESSAGE_LENGTH = 1200;
const DEMO_PRODUCT_ID = 900001;
const TEXT_CONFIRMATIONS = new Set([
  "да", "подтверждаю", "добавить в корзину", "иә", "растаймын", "себетке қосу", "себетке қосыңыз",
]);

function safeErrorMessage(language = DEFAULT_LANGUAGE) {
  return getMessages(language).chat.responseError;
}

const DEMO_PRODUCT = {
  id: 515291,
  name: "027228 АВ DRX250 MT 3ф 160А 18ka Legrand (1)",
  article: "200300285_",
  price: 64920,
  quantity: 23,
  image: "https://ekt.kz/upload/iblock/1ca/8mdfx6517jvalt5da1n9865q2fzpj6jp/027228_av_drx250_mt_3f_160a_18ka_legrand_1.jpg",
  url: "https://ekt.kz/catalog/nizkovoltnaya_apparatura/silovye_avtomaticheskie_vyklyuchateli/drx250_mt_10_250_a_legrand/027228_av_drx250_mt_3f_160a_18ka_legrand_1/",
  data_status: "live",
  verified_at: new Date().toISOString(),
  characteristics: [
    ["Серия", "DRX250 MT"],
    ["Полюса", "3"],
    ["Номинальный ток", "160 А"],
    ["Отключающая способность", "18 кА"],
    ["Напряжение", "400 В AC"],
    ["Бренд", "Legrand"],
  ],
  fit_reason: "Подходит для промышленной и коммерческой сети, если нужны 3 полюса и ток до 160 А.",
  important_difference: "Перед заказом проверьте ток уставки: в свойствах каталога также указано номинальное значение 250 А.",
};

const DEMO_ANALOG_COMPARISON = {
  is_demo: true,
  source_product: {
    id: 900003,
    name: "Автоматический выключатель ВА47-29 3P 10A IEK",
    article: "ДЕМО-01-003",
  },
  analog: {
    id: 900006,
    name: "Автоматический выключатель ВА47-29 3P 16A IEK",
    article: "ДЕМО-01-006",
    price: { amount: 1625, currency: "KZT" },
    availability: { status: "available", sellable_quantity: 1, unit: "шт." },
    data_status: "live",
    verified_at: new Date().toISOString(),
  },
  why_fits: "Та же серия, бренд и трёхполюсное исполнение. Аналог есть в продаваемом остатке.",
  matching_parameters: [
    ["Категория", "Автоматический выключатель"],
    ["Серия", "ВА47-29"],
    ["Количество полюсов", "3P"],
    ["Бренд", "IEK"],
  ],
  differences: [
    {
      label: "Номинальный ток",
      source: "10 A",
      analog: "16 A",
      note: "Существенное отличие: подтвердите допустимый ток до замены.",
    },
    {
      label: "Цена",
      source: "1 167 ₸",
      analog: "1 625 ₸",
      note: "Аналог дороже на 458 ₸ по данным demo-fixture.",
    },
    {
      label: "Продаваемый остаток",
      source: "0 шт.",
      analog: "1 шт.",
      note: "Аналог доступен, исходная позиция недоступна.",
    },
  ],
};

function createWelcomeMessage(language = DEFAULT_LANGUAGE) {
  const messages = getMessages(language);
  return {
    id: "welcome",
    role: "assistant",
    content: messages.welcome,
    suggestions: messages.suggestions,
  };
}

function createId(prefix) {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value}`;
}

function normalizeConfirmation(value, language = DEFAULT_LANGUAGE) {
  return String(value).toLocaleLowerCase(getLocale(language)).trim().split(/\s+/).join(" ");
}

function getTimeLabel(language = DEFAULT_LANGUAGE) {
  return formatTime(new Date(), language);
}

function sanitizeAssistantText(value, language = DEFAULT_LANGUAGE) {
  const copy = getMessages(language).chat;
  const text = String(value ?? "").replace(/[<>]/g, "");
  const withoutSecrets = text
    .replace(
      /(?:api[_ -]?key|api[_ -]?password|authorization|bearer|basic\s+auth|token|secret)\s*[:=]\s*[^\s,;]+/gi,
      copy.secretHidden,
    )
    .replace(
      /(?:stack trace|traceback|internal server error|at\s+[\w./-]+\([^\n]*\))/gi,
      copy.internalErrorHidden,
    );

  return withoutSecrets.length > 2000
    ? `${withoutSecrets.slice(0, 1997)}…`
    : withoutSecrets;
}

async function createAssistantResponse(prompt, signal, language = DEFAULT_LANGUAGE) {
  const demo = getMessages(language).demo;
  const normalized = prompt.toLowerCase();

  if (normalized.includes("ошибка")) {
    throw new Error("demo_failure");
  }

  if (normalized.includes("достав")) {
    return demo.delivery;
  }

  if (normalized.includes("кабел")) {
    return demo.cable;
  }

  if (normalized.includes("аналог")) {
    return {
      content: demo.analog,
      analogComparison: {
        ...DEMO_ANALOG_COMPARISON,
        analog: {
          ...DEMO_ANALOG_COMPARISON.analog,
          verified_at: new Date().toISOString(),
        },
      },
    };
  }

  if (normalized.includes("автомат") || normalized.includes("legrand")) {
    const product = await getProduct(DEMO_PRODUCT_ID, { signal });
    return {
      content: demo.product,
      product: { ...product, verified_at: new Date().toISOString() },
    };
  }

  return demo.fallback;
}

async function requestDemoAnswer(prompt, signal, language = DEFAULT_LANGUAGE) {
  await new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(resolve, 650);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timeoutId);
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    }, { once: true });
  });

  return createAssistantResponse(prompt, signal, language);
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

function displayProductValue(value, language = DEFAULT_LANGUAGE) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return getMessages(language).analog.infoMissing;
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

function formatProductPrice(value, language = DEFAULT_LANGUAGE) {
  const price = toFiniteNumber(value);
  if (price === null) return getMessages(language).product.priceMissing;
  return formatCurrency(price, "KZT", language);
}

function formatMoney(value, currency = "KZT", language = DEFAULT_LANGUAGE) {
  const amount = toFiniteNumber(value);
  if (amount === null) return getMessages(language).analog.infoMissing;
  try {
    return new Intl.NumberFormat(getLocale(language), {
      style: "currency", currency, maximumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount);
  } catch {
    return `${formatNumber(amount, language)} ${currency}`;
  }
}

function formatExpiry(value, language = DEFAULT_LANGUAGE) {
  const copy = getMessages(language).cart;
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return copy.expiryFallback;
  return copy.expiryUntil(formatDateTime(value, language, { hour: "2-digit", minute: "2-digit" }));
}

function cartErrorCopy(code, payload = {}, language = DEFAULT_LANGUAGE) {
  const messages = getMessages(language).errors;
  if (code === "quantity_limit_exceeded" || code === "insufficient_stock") return messages.insufficient_stock(payload?.maximum_quantity ?? "доступного лимита");
  return messages[code] ?? messages.generic;
}

function formatVerifiedAt(value, language = DEFAULT_LANGUAGE) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return getMessages(language).analog.infoMissing;
  return formatDateTime(date, language, { dateStyle: "medium", timeStyle: "short" });
}

function formatDataAge(value, language = DEFAULT_LANGUAGE) {
  const copy = getMessages(language).product;
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return getMessages(language).analog.infoMissing;
  const ageSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (ageSeconds < 60) return copy.dataAgeNow;
  if (ageSeconds < 3600) return copy.dataAgeMinutes(Math.floor(ageSeconds / 60));
  if (ageSeconds < 86400) return copy.dataAgeHours(Math.floor(ageSeconds / 3600));
  return copy.dataAgeDays(Math.floor(ageSeconds / 86400));
}

const PRODUCT_PROPERTY_FIELDS = [
  ["SERIES", "SERIA", "SERIIA"],
  ["KOLICHESTVO_POLYUSOV"],
  ["NOMINALNYY_TOK"],
  ["NOMINALNAYA_OTKLYUCHAYUSHCHAYA_SPOSOBNOST"],
  ["NOMINALNOE_NAPRYAZHENIE"],
  ["TORGOVAYA_MARKA", "BRAND"],
];

function getProductCharacteristics(product, language = DEFAULT_LANGUAGE) {
  const labels = getMessages(language).product.characteristics;
  if (Array.isArray(product?.characteristics) && product.characteristics.length > 0) {
    return product.characteristics.map((item, index) => {
      if (Array.isArray(item)) return [item[0], item[1]];
      return [item?.label ?? item?.name ?? `Характеристика ${index + 1}`, item?.value];
    });
  }

  const properties = product?.properties && typeof product.properties === "object" ? product.properties : {};
  const mapped = PRODUCT_PROPERTY_FIELDS.map((keys, index) => {
    const key = keys.find((candidate) => properties[candidate] !== undefined);
    return [labels[index], key ? properties[key] : undefined];
  });
  if (mapped.some(([, value]) => value !== undefined && value !== null && value !== "")) return mapped;
  return [[getMessages(language).product.characteristicsTitle, getMessages(language).analog.infoMissing]];
}

function ProductCard({ cartStatus, language, messageId, onCreateProposal, product, proposalState }) {
  const messages = getMessages(language);
  const productCopy = messages.product;
  const [imageFailed, setImageFailed] = useState(false);
  const [selectedQuantity, setSelectedQuantity] = useState("1");
  const productName = displayProductValue(product?.name, language);
  const article = displayProductValue(product?.article, language);
  const isCached = [product?.data_status, product?.dataStatus, product?.source, product?.status]
    .some((value) => String(value ?? "").toLowerCase() === "cached" || String(value ?? "").toLowerCase() === "cache");
  const verifiedAt = product?.verified_at ?? product?.verifiedAt;
  const characteristics = getProductCharacteristics(product, language);
  const sellableQuantity = toFiniteNumber(product?.availability?.sellable_quantity);
  const quantity = sellableQuantity ?? toFiniteNumber(product?.quantity);
  const quantityKnown = quantity !== null;
  const isSellable = product?.availability?.status === "available" && sellableQuantity > 0;
  const availability = product?.availability?.status === "availability_unknown"
    ? productCopy.availabilityUnknown
    : quantityKnown
      ? quantity > 0 ? productCopy.available(quantity) : productCopy.unavailable
      : productCopy.availabilityMissing;
  const isProposing = proposalState === "proposing";
  const numericQuantity = Number(selectedQuantity);
  const quantityIsValid = Number.isInteger(numericQuantity) && numericQuantity > 0;

  return (
    <article className="product-card" aria-label={`${productCopy.card}: ${productName}`}>
      <div className="product-card-media">
        {product?.image && !imageFailed ? (
          <img
            alt={`${productCopy.image}: ${productName}`}
            className="product-card-image"
            onError={() => setImageFailed(true)}
            src={product.image}
          />
        ) : (
          <div className="product-card-image-missing">{productCopy.missingImage}</div>
        )}
      </div>
      <div className="product-card-body">
        <div className="product-card-eyebrow">{productCopy.eyebrow}</div>
        <h3 className="product-card-title">{productName}</h3>
        <div className="product-card-article">{productCopy.article}: {article}</div>
        <div className="product-card-summary">
          <strong className="product-card-price">{formatProductPrice(product?.price, language)}</strong>
          <span className={`product-card-availability ${isSellable ? "product-card-availability--in" : ""}`}>
            {availability}
          </span>
        </div>
        <div className={`product-card-data ${isCached ? "product-card-data--cached" : "product-card-data--live"}`}>
          <span className="product-card-data-dot" />
          <span>{isCached ? productCopy.cache : productCopy.live}</span>
          {isCached && (
            <span className="product-card-data-age">
              {productCopy.verified}: {formatVerifiedAt(verifiedAt, language)} · {productCopy.age}: {formatDataAge(verifiedAt, language)}
            </span>
          )}
        </div>
        <dl className="product-card-characteristics">
          {characteristics.map(([label, value]) => (
            <div className="product-characteristic" key={label}>
              <dt>{displayProductValue(label, language)}</dt>
              <dd>{displayProductValue(value, language)}</dd>
            </div>
          ))}
        </dl>
        {(product?.fit_reason || product?.important_difference) && (
          <div className="product-card-notes">
            {product.fit_reason && <p><strong>{productCopy.fit}</strong> {product.fit_reason}</p>}
            {product.important_difference && <p><strong>{productCopy.important}</strong> {product.important_difference}</p>}
          </div>
        )}
        <form
          className="product-card-cart"
          onSubmit={(event) => {
            event.preventDefault();
            if (quantityIsValid) onCreateProposal(product, messageId, numericQuantity);
          }}
        >
          <label htmlFor={`quantity-${messageId}`}>{productCopy.quantity}</label>
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
              {isProposing ? productCopy.checking : proposalState === "failed" ? productCopy.retry : productCopy.add}
            </button>
          </div>
          <span className="product-card-cart-help" id={`quantity-help-${messageId}`}>
            {cartStatus === "loading"
              ? productCopy.preparing
              : cartStatus === "error"
                ? productCopy.reconnect
                : productCopy.summaryHint}
          </span>
        </form>
        {product?.url ? (
          <a
            className="product-card-link"
            href={product.url}
            rel="noopener noreferrer"
            target="_blank"
          >
            {productCopy.official} <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <span className="product-card-link product-card-link--missing">{productCopy.officialMissing}</span>
        )}
      </div>
    </article>
  );
}

function formatAnalogMoney(amount, currency, language = DEFAULT_LANGUAGE) {
  const value = toFiniteNumber(amount);
  if (value === null) return getMessages(language).analog.infoMissing;
  return currency === "KZT" ? formatCurrency(value, currency, language) : `${formatNumber(value, language)} ${displayProductValue(currency, language)}`;
}

function AnalogComparisonCard({ comparison, language }) {
  const copy = getMessages(language).analog;
  const sourceProductRaw = comparison?.source_product ?? comparison?.original_product ?? {};
  const sourceProduct = sourceProductRaw?.normalized ?? sourceProductRaw;
  const analogRaw = comparison?.analog ?? {};
  const analog = analogRaw?.normalized ?? analogRaw;
  const analogPrice = analog?.price && typeof analog.price === "object" ? analog.price : {};
  const analogAvailability = analog?.availability && typeof analog.availability === "object"
    ? analog.availability
    : {};
  const sellableQuantity = toFiniteNumber(analogAvailability.sellable_quantity);
  const isAvailable = analogAvailability.status === "available" && sellableQuantity !== null && sellableQuantity > 0;
  const isLive = String(analogRaw.data_status ?? analogRaw.status ?? analog.data_status ?? "").toLowerCase() === "live";
  const verifiedAt = analogAvailability.verified_at ?? analogPrice.verified_at ?? analogRaw.verified_at;
  const matches = Array.isArray(comparison?.matching_parameters) ? comparison.matching_parameters : [];
  const differences = Array.isArray(comparison?.differences) ? comparison.differences : [];

  return (
    <article className="analog-card" aria-label={`${copy.comparison}: ${displayProductValue(analog.name, language)}`}>
      <div className="analog-card-topline">
        <span className="analog-card-label">{copy.label}</span>
        {comparison?.is_demo && <span className="analog-demo-badge">DEMO fixture</span>}
      </div>
      <div className="analog-source">
        <span>{copy.instead}</span>
        <strong>{displayProductValue(sourceProduct.name, language)}</strong>
        <small>{copy.article}: {displayProductValue(sourceProduct.article, language)}</small>
      </div>
      <div className="analog-arrow" aria-hidden="true">↓</div>
      <div className="analog-product">
        <h3>{displayProductValue(analog.name, language)}</h3>
        <span>{copy.article}: {displayProductValue(analog.article, language)}</span>
        <div className="analog-commerce">
            <strong>{formatAnalogMoney(analogPrice.amount ?? analog.price, analogPrice.currency ?? analog.currency, language)}</strong>
          <span className={isAvailable ? "analog-stock analog-stock--available" : "analog-stock"}>
            {isAvailable
              ? copy.inStock(sellableQuantity, displayProductValue(analogAvailability.unit ?? (normalizeLanguage(language) === "kk" ? "дана" : "шт."), language))
              : analogAvailability.status === "unavailable"
                ? copy.unavailable
                : copy.missing}
          </span>
        </div>
        <div className={`analog-verification ${isLive ? "analog-verification--live" : "analog-verification--cached"}`}>
          <span className="analog-verification-dot" />
          <strong>{isLive ? copy.live : copy.notLive}</strong>
          <span>{copy.checked}: {formatVerifiedAt(verifiedAt, language)}</span>
        </div>
      </div>

      <section className="analog-reason" aria-label={copy.why}>
        <span>{copy.why}</span>
        <p>{displayProductValue(comparison?.why_fits, language)}</p>
      </section>

      <section className="analog-section" aria-label={copy.matching}>
        <h4>{copy.matching}</h4>
        {matches.length > 0 ? (
          <ul className="analog-match-list">
            {matches.map((item, index) => {
              const label = Array.isArray(item) ? item[0] : item?.label;
              const value = Array.isArray(item) ? item[1] : item?.value;
              return (
                <li key={`${label ?? "match"}-${index}`}>
                  <Icon name="check" size={13} />
                  <span>{displayProductValue(label, language)}</span>
                  <strong>{displayProductValue(value, language)}</strong>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="analog-missing">{copy.infoMissing}</p>
        )}
      </section>

      <section className="analog-section" aria-label={copy.differences}>
        <h4>{copy.differences}</h4>
        {differences.length > 0 ? (
          <div className="analog-difference-list">
            {differences.map((difference, index) => (
              <div className="analog-difference" key={`${difference?.label ?? "difference"}-${index}`}>
                <strong>{displayProductValue(difference?.label, language)}</strong>
                <dl>
                  <div><dt>{copy.original}</dt><dd>{displayProductValue(difference?.source, language)}</dd></div>
                  <div><dt>{copy.analog}</dt><dd>{displayProductValue(difference?.analog, language)}</dd></div>
                </dl>
                <p>{displayProductValue(difference?.note, language)}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="analog-missing">{copy.infoMissing}</p>
        )}
      </section>
    </article>
  );
}

function CartConfirmation({ action, language, onConfirm, phase = "proposed", result, statusNote }) {
  const copy = getMessages(language).cart;
  const product = action?.product ?? {};
  const isPending = phase === "confirming";
  const isInactive = ["expired", "failed", "succeeded"].includes(phase);

  if (phase === "succeeded" && result) {
    return (
      <section className="cart-result cart-result--success" aria-label={copy.result}>
        <div className="cart-result-icon"><Icon name="check" size={18} /></div>
        <div>
          <strong>{copy.added(result.added_quantity)}</strong>
          <span>{copy.updated}</span>
        </div>
        <a href={result.cart?.url || "/demo/cart/"} rel="noopener noreferrer" target="_blank">
          {copy.open} <span aria-hidden="true">↗</span>
        </a>
      </section>
    );
  }

  return (
    <section
      className={`cart-confirmation cart-confirmation--${phase}`}
      data-action-id={action?.action_id}
      aria-label={copy.summary}
    >
      <div className="cart-confirmation-head">
        <span><Icon name="cart" size={14} /> {copy.orderSummary}</span>
        <span>{phase === "expired" ? copy.expired : phase === "failed" ? copy.error : copy.confirmationNeeded}</span>
      </div>
      <div className="cart-confirmation-product">
        <strong>{displayProductValue(product.name, language)}</strong>
        <span>{copy.article} {displayProductValue(product.article, language)}</span>
      </div>
      <dl className="cart-confirmation-lines">
        <div><dt>{copy.quantity}</dt><dd>{action.quantity} {normalizeLanguage(language) === "kk" ? "дана" : "шт."}</dd></div>
        <div><dt>{copy.unitPrice}</dt><dd>{formatMoney(action.unit_price, action.currency, language)}</dd></div>
        <div className="cart-confirmation-total"><dt>{copy.total}</dt><dd>{formatMoney(action.total, action.currency, language)}</dd></div>
      </dl>
      <p className="cart-confirmation-note">
        {copy.note(formatExpiry(action.expires_at, language))}
      </p>
      {statusNote && <p className="cart-confirmation-status" role="status">{statusNote}</p>}
      <button
        className="cart-confirmation-button"
        disabled={isPending || isInactive}
        onClick={() => onConfirm(action.action_id)}
        type="button"
      >
        {isPending ? copy.checking : isInactive ? copy.unavailable : copy.confirm}
      </button>
    </section>
  );
}

function LanguageCartSummary({ language, summary }) {
  const copy = getMessages(language).cart;
  const items = Array.isArray(summary?.items) ? summary.items : [];
  return (
    <section className="cart-confirmation cart-confirmation--expired language-cart-summary" aria-label={`${copy.orderSummary} · ${copy.expired}`}>
      <div className="cart-confirmation-head">
        <span><Icon name="cart" size={14} /> {copy.orderSummary}</span>
        <span>{copy.expired}</span>
      </div>
      <p className="cart-confirmation-note">{summary?.message}</p>
      {items.length > 0 && (
        <ul className="language-cart-summary-items">
          {items.map((item, index) => {
            const product = item?.product ?? {};
            return (
              <li key={`${product.id ?? product.article ?? "item"}-${index}`}>
                <strong>{displayProductValue(product.name, language)}</strong>
                <span>{copy.article}: {displayProductValue(product.article, language)} · {copy.quantity}: {item.quantity}</span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="cart-confirmation-status" role="status">{copy.newProposal}</p>
    </section>
  );
}

function MessageBubble({
  cartStatus,
  cartRequest,
  language,
  message,
  onConfirmAction,
  onCreateProposal,
  onRetry,
  onSuggestion,
}) {
  const copy = getMessages(language).chat;
  const isUser = message.role === "user";
  const paragraphs = sanitizeAssistantText(message.content, language).split(/\n{2,}/);
  const isRich = Boolean(message.product || message.cartAction || message.languageSummary);

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      <div
        className={`message-bubble ${isUser ? "message-bubble--user" : "message-bubble--assistant"}${message.error ? " message-bubble--error" : ""}${isRich ? " message-bubble--rich" : ""}`}
      >
        {message.error && (
          <div className="message-kicker message-kicker--error">
            <Icon name="alert" size={14} />
            {copy.error}
          </div>
        )}
        {paragraphs.map((paragraph, index) => (
          <p key={`${message.id}-paragraph-${index}`}>{paragraph}</p>
        ))}
        {message.product && (
          <ProductCard
            cartStatus={cartStatus}
            language={language}
            messageId={message.id}
            onCreateProposal={onCreateProposal}
            product={message.product}
            proposalState={cartRequest?.kind === "proposal" && cartRequest.key === message.id ? "proposing" : message.proposalState}
          />
        )}
        {message.analogComparison && <AnalogComparisonCard comparison={message.analogComparison} language={language} />}
        {message.languageSummary && <LanguageCartSummary language={language} summary={message.languageSummary} />}
        {message.cartAction && (
          <CartConfirmation
            action={message.cartAction}
            language={language}
            onConfirm={onConfirmAction}
            phase={message.cartPhase}
            result={message.cartResult}
            statusNote={message.cartStatusNote}
          />
        )}
        {message.suggestions && (
          <div className="suggestion-list" aria-label={copy.examples}>
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
            {copy.retry}
          </button>
        )}
        <div className="message-time">{message.time ?? copy.justNow}</div>
      </div>
    </div>
  );
}

function TypingMessage({ language, onCancel }) {
  const copy = getMessages(language).chat;
  return (
    <div className="processing-row" role="status">
      <div className="typing-bubble" aria-label={copy.typing}>
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
      <div className="processing-copy">
        <span>{copy.forming}</span>
        <button className="cancel-button" onClick={onCancel} type="button">
          {copy.cancel}
        </button>
      </div>
    </div>
  );
}

function ConfirmClearDialog({ language, onCancel, onConfirm }) {
  const copy = getMessages(language).clearDialog;
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
        <p className="dialog-eyebrow">{copy.eyebrow}</p>
        <h2 id="clear-dialog-title">{copy.title}</h2>
        <p id="clear-dialog-description">{copy.description}</p>
        <div className="dialog-actions">
          <button className="button button--secondary" onClick={onCancel} ref={cancelRef} type="button">
            {copy.cancel}
          </button>
          <button className="button button--danger" onClick={onConfirm} ref={confirmRef} type="button">
            {copy.confirm}
          </button>
        </div>
      </section>
    </div>
  );
}

function ChatWidget({ cartStatus, isOpen, language, languageChangeRequest, onCartChange, onEnsureCart, onLanguageChange, onOpenChange }) {
  const copy = getMessages(language);
  const [messages, setMessages] = useState(() => [createWelcomeMessage(language)]);
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
  const languageInitializedRef = useRef(false);

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
        cartStatusNote: copy.chat.proposalChanged,
      };
    }
    return message;
  }), [copy.chat.proposalChanged]);

  const changeLanguage = useCallback(async (nextLanguage) => {
    const normalized = normalizeLanguage(nextLanguage);
    if (normalized === language) return;
    setMessages((current) => {
      const active = current.filter((message) => message.cartAction && message.cartPhase === "proposed");
      const updated = expireActiveSummaries(current);
      if (!active.length) {
        return current.length === 1 && current[0]?.id === "welcome"
          ? [createWelcomeMessage(normalized)]
          : updated;
      }
      return [
        ...updated,
        {
          id: createId("language-summary"),
          role: "assistant",
          content: getMessages(normalized).chat.languageSummary,
          languageSummary: { message: getMessages(normalized).chat.languageSummary, items: [] },
          time: getTimeLabel(normalized),
        },
      ];
    });
    onLanguageChange(normalized);
    try {
      if (!languageInitializedRef.current) {
        try {
          await setChatLanguage(dialogIdRef.current, language);
        } catch {
          // A missing CSRF cookie should not block the local safe state transition.
        }
        languageInitializedRef.current = true;
      }
      const response = await setChatLanguage(dialogIdRef.current, normalized);
      if (response?.cart_summary?.message) {
        setMessages((current) => current.map((message) => (
          message.id.startsWith("language-summary-")
            ? { ...message, content: response.cart_summary.message, languageSummary: response.cart_summary }
            : message
        )));
      }
    } catch {
      // Local invalidation remains active even if the optional language endpoint is unavailable.
    }
  }, [expireActiveSummaries, language, onLanguageChange]);

  useEffect(() => {
    if (languageChangeRequest && languageChangeRequest !== language) {
      void changeLanguage(languageChangeRequest);
    }
  }, [changeLanguage, language, languageChangeRequest]);

  const appendReplacement = useCallback((payload, sourceActionId, content) => {
    const replacement = payload?.replacement_action;
    if (replacement?.message_version) {
      messageVersionRef.current = Math.max(messageVersionRef.current, replacement.message_version);
    }
    updateCartFromPayload(payload);
    setMessages((current) => {
      const updated = expireActiveSummaries(current).map((message) => (
        message.cartAction?.action_id === sourceActionId
          ? { ...message, cartPhase: "expired", cartStatusNote: copy.chat.sourceChanged }
          : message
      ));
      if (!replacement) {
        return [
          ...updated,
          {
            id: createId("cart-unavailable"),
            role: "assistant",
            content,
            time: getTimeLabel(language),
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
          time: getTimeLabel(language),
        },
      ];
    });
  }, [copy.chat.sourceChanged, expireActiveSummaries, language, updateCartFromPayload]);

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
          content: copy.chat.summaryNotice,
          cartAction: action,
          cartPhase: "proposed",
          time: getTimeLabel(language),
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
            ? copy.chat.maxSummary(response.maximum_quantity)
            : copy.chat.noStock,
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
            content: cartErrorCopy(apiError.code, response, language),
            error: true,
            time: getTimeLabel(language),
          },
        ]);
      }
    } finally {
      cartLockRef.current = false;
      setCartRequest(null);
    }
  }, [appendReplacement, cartStatus, copy.chat.maxSummary, copy.chat.noStock, copy.chat.summaryNotice, expireActiveSummaries, language, onEnsureCart, updateCartFromPayload]);

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
            ? copy.chat.insufficientSummary(response.replacement_action.quantity)
            : copy.chat.refreshedSummary,
        );
      } else if (["network_error", "csrf_cookie_missing", "csrf_failed", "cart_busy", "action_in_progress"].includes(apiError.code)) {
        try {
          await onEnsureCart();
        } catch {
          // The original action remains the only safe retry target.
        }
        setMessages((current) => current.map((message) => (
          message.cartAction?.action_id === actionId
            ? { ...message, cartPhase: "proposed", cartStatusNote: cartErrorCopy(apiError.code, {}, language) }
            : message
        )));
      } else {
        const nextPhase = ["action_expired", "action_stale"].includes(apiError.code) ? "expired" : "failed";
        setMessages((current) => current.map((message) => (
          message.cartAction?.action_id === actionId
            ? { ...message, cartPhase: nextPhase, cartStatusNote: cartErrorCopy(apiError.code, response, language) }
            : message
        )));
      }
    } finally {
      cartLockRef.current = false;
      setCartRequest(null);
    }
  }, [appendReplacement, applyCartSuccess, copy.chat.insufficientSummary, copy.chat.refreshedSummary, language, onEnsureCart, updateCartFromPayload]);

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
          copy.chat.replacementChanged,
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
            content: cartErrorCopy(apiError.code, response, language),
            error: !["ambiguous_confirmation", "no_active_action", "confirmation_required"].includes(apiError.code),
            time: getTimeLabel(language),
          },
        ]);
      }
    } finally {
      cartLockRef.current = false;
      setCartRequest(null);
    }
  }, [appendReplacement, applyCartSuccess, copy.chat.replacementChanged, language, onEnsureCart, updateCartFromPayload]);

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
        content: copy.chat.stopped,
        time: getTimeLabel(language),
      },
    ]);
  }, [copy.chat.stopped, language]);

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
        time: getTimeLabel(language),
        },
      ];
    });

    if (TEXT_CONFIRMATIONS.has(normalizeConfirmation(prompt, language))) {
      void confirmByText(prompt);
      return;
    }

    const controller = new AbortController();
    const statusTimer = window.setTimeout(() => setPhase("processing"), 280);
    pendingRef.current = { controller, statusTimer };
    setPhase("submitting");
    requestDemoAnswer(prompt, controller.signal, language)
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
            content: sanitizeAssistantText(response?.content, language),
            product: response?.product,
            analogComparison: response?.analogComparison,
            time: getTimeLabel(language),
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
            content: safeErrorMessage(language),
            error: true,
            retryPrompt: prompt,
            time: getTimeLabel(language),
          },
        ]);
      });
  }, [confirmByText, language]);

  const clearHistory = useCallback(() => {
    if (pendingRef.current) cancelGeneration();
    setMessages([createWelcomeMessage(language)]);
    setInputValue("");
    setPhase("idle");
    setCartRequest(null);
    cartLockRef.current = false;
    dialogIdRef.current = createId("dialog");
    messageVersionRef.current = 0;
    proposalRetryRef.current.clear();
    setIsClearDialogOpen(false);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [cancelGeneration, language]);

  const handleSubmit = (event) => {
    event.preventDefault();
    sendPrompt(inputValue);
  };

  const statusLabel = cartRequest
    ? copy.chat.status.cart
    : phase === "processing" || phase === "submitting"
    ? copy.chat.status.forming
    : phase === "error"
      ? copy.chat.status.retry
      : copy.chat.status.online;

  return (
    <>
      <button
        aria-expanded={isOpen}
        aria-label={isOpen ? copy.chat.close : copy.chat.open}
        className="chat-launcher"
        onClick={() => onOpenChange(!isOpen)}
        ref={launcherRef}
        type="button"
      >
        <span className="launcher-icon"><Icon name="bot" size={18} /></span>
        <span className="launcher-copy">
          <strong>{copy.chat.launcher}</strong>
          <small>{copy.chat.ai}</small>
        </span>
        <span className="launcher-pulse" />
      </button>

      {isOpen && (
        <aside
          aria-label={copy.chat.dialog}
          aria-modal="false"
          className="chat-widget"
          role="dialog"
        >
          <header className="chat-header">
            <div className="assistant-identity">
              <div className="assistant-avatar"><Icon name="bot" size={19} /></div>
              <div className="assistant-title-wrap">
                <strong>{copy.chat.title}</strong>
                <span className={`assistant-status ${phase === "error" ? "assistant-status--error" : ""}`}>
                  <span className="status-dot" />
                  {statusLabel}
                </span>
              </div>
            </div>
            <div className="chat-header-actions">
              <button
                aria-label={copy.chat.clear}
                className="icon-button"
                disabled={Boolean(cartRequest)}
                onClick={() => setIsClearDialogOpen(true)}
                ref={clearButtonRef}
                title={copy.chat.clear}
                type="button"
              >
                <Icon name="trash" size={17} />
              </button>
              <button
                aria-label={copy.chat.closeShort}
                className="icon-button"
                onClick={() => {
                  onOpenChange(false);
                  launcherRef.current?.focus();
                }}
                title={copy.chat.closeShort}
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
            <div className="chat-date"><span /> {copy.chat.today} <span /></div>
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                cartStatus={cartStatus}
                cartRequest={cartRequest}
                language={language}
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
            {(phase === "submitting" || phase === "processing") && <TypingMessage language={language} onCancel={cancelGeneration} />}
          </div>

          <div className="chat-composer-wrap">
            <p className="composer-hint" role="status">
              <Icon name="sparkle" size={13} />
              {copy.chat.catalogBasis}
            </p>
            <form className="chat-composer" onSubmit={handleSubmit}>
              <label className="sr-only" htmlFor="message-input">{copy.chat.inputLabel}</label>
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
                placeholder={copy.chat.placeholder}
                ref={inputRef}
                rows={1}
                value={inputValue}
              />
              <div className="composer-actions">
                <span className="composer-counter">{inputValue.length}/{MAX_MESSAGE_LENGTH}</span>
                <button
                  aria-label={copy.chat.send}
                  className="send-button"
                  disabled={Boolean(pendingRef.current) || Boolean(cartRequest) || !inputValue.trim()}
                  type="submit"
                >
                  <Icon name="arrow" size={17} />
                </button>
              </div>
            </form>
            <p className="composer-disclaimer" id="composer-disclaimer">
              {copy.chat.disclaimer}
            </p>
          </div>
        </aside>
      )}

      {isClearDialogOpen && (
        <ConfirmClearDialog language={language} onCancel={closeClearDialog} onConfirm={clearHistory} />
      )}
    </>
  );
}

function SitePreview({ cart, language, onLanguageRequest, onOpenChat }) {
  const copy = getMessages(language).site;
  const categories = copy.categories.map(([title, description], index) => [title, description, ["#d9f3e9", "#e3edff", "#fff0cc", "#f1e5ff"][index]]);
  const cartCount = Array.isArray(cart?.items)
    ? cart.items.reduce((total, item) => total + (toFiniteNumber(item?.quantity) ?? 0), 0)
    : 0;

  return (
    <main className="site-preview">
      <nav className="site-nav">
        <a className="brand" href="#top" aria-label={copy.brand}>
          <span className="brand-mark">E</span>
          <span>EKT<span className="brand-dot">.</span>kz</span>
        </a>
        <div className="site-nav-links" aria-label={copy.nav}>
          <a href="#catalog">{copy.catalog}</a>
          <a href="#delivery">{copy.delivery}</a>
          <a href="#contacts">{copy.contacts}</a>
        </div>
        <div className="site-nav-actions">
          <div className="site-language-switcher" aria-label={copy.languageSwitcher}>
            {Object.entries(LOCALES).map(([key, locale]) => (
              <button
                aria-label={locale.label}
                aria-pressed={language === key}
                className={`site-language-button${language === key ? " site-language-button--active" : ""}`}
                key={key}
                onClick={() => onLanguageRequest(key)}
                type="button"
              >
                {locale.short}
              </button>
            ))}
          </div>
          <a
            aria-label={copy.cartAria(cartCount)}
            className="cart-button"
            href={cart?.url || "/demo/cart/"}
            rel="noopener noreferrer"
            target="_blank"
          >
            <Icon name="cart" size={16} />
            {copy.cart} <span className="cart-count">{cartCount}</span>
          </a>
        </div>
      </nav>

      <section className="hero-preview" id="top">
        <div className="hero-copy">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.hero}</h1>
          <p className="hero-description">{copy.description}</p>
          <div className="hero-actions">
            <a className="primary-button" href="#catalog">{copy.openCatalog}</a>
            <button className="text-button" onClick={onOpenChat} type="button">{copy.ask} <span>↗</span></button>
          </div>
        </div>
        <div className="hero-card" aria-label={copy.stats}>
          <div className="hero-card-top"><span className="hero-card-live"><span /> DEMO PREVIEW</span><span>2026</span></div>
          <div className="hero-card-label">{copy.catalogNearby}</div>
          <div className="hero-card-value">14<span>k</span></div>
          <div className="hero-card-caption">{copy.pages}</div>
          <div className="hero-card-chart"><i /><i /><i /><i /><i /><i /><i /></div>
        </div>
      </section>

      <section className="category-section" id="catalog">
        <div className="section-heading"><div><span className="section-overline">{copy.overline}</span><h2>{copy.find}</h2></div><span className="section-note">{copy.directions}</span></div>
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

      <section className="site-footer-strip" id="delivery"><span>{copy.footer}</span><span>·</span><span id="contacts">{copy.cities}</span></section>
    </main>
  );
}

function CookieBanner({ language, onClose }) {
  const copy = getMessages(language).cookie;
  return (
    <aside className="cookie-banner" aria-label={copy.aria}>
      <div className="cookie-copy"><strong>{copy.title}</strong><p>{copy.text}</p></div>
      <button className="cookie-close" onClick={onClose} type="button">{copy.close}</button>
    </aside>
  );
}

export default function App() {
  const [showCookie, setShowCookie] = useState(true);
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
  const [languageChangeRequest, setLanguageChangeRequest] = useState(null);
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
      <SitePreview
        cart={cart}
        language={language}
        onLanguageRequest={setLanguageChangeRequest}
        onOpenChat={() => setIsChatOpen(true)}
      />
      {showCookie && <CookieBanner language={language} onClose={() => setShowCookie(false)} />}
      <ChatWidget
        cartStatus={cartStatus}
        isOpen={isChatOpen}
        language={language}
        languageChangeRequest={languageChangeRequest}
        onCartChange={(snapshot) => {
          setCart(snapshot);
          setCartStatus("ready");
        }}
        onEnsureCart={refreshCart}
        onLanguageChange={setLanguage}
        onOpenChange={setIsChatOpen}
      />
    </>
  );
}
