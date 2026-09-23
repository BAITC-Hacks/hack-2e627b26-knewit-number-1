export class CartApiError extends Error {
  constructor(message, { status = 0, payload = null } = {}) {
    super(message);
    this.name = "CartApiError";
    this.status = status;
    this.payload = payload;
    this.code = payload?.error?.code ?? (status === 0 ? "network_error" : "unknown_error");
  }
}

function getCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));

  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

const RETRYABLE_GET_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

async function requestJson(path, options = {}) {
  const isGet = !options.method || options.method.toUpperCase() === "GET";
  const maxAttempts = isGet ? 3 : 1;
  let lastError;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, 180 * (2 ** (attempt - 1))));

    try {
      return await requestJsonOnce(path, options);
    } catch (error) {
      lastError = error;
      const retryable = error?.code === "network_error" || RETRYABLE_GET_STATUSES.has(error?.status);
      if (!retryable || attempt === maxAttempts - 1) throw error;
    }
  }

  throw lastError;
}

async function requestJsonOnce(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...options,
    });
  } catch (error) {
    throw new CartApiError("Не удалось связаться с сервером корзины.", {
      payload: { error: { code: "network_error", message: String(error?.message ?? error) } },
    });
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new CartApiError(
      payload?.error?.message || `Сервер корзины вернул ошибку ${response.status}.`,
      { status: response.status, payload },
    );
  }

  return payload;
}

async function postJson(path, body) {
  const csrfToken = getCookie("csrftoken");
  if (!csrfToken) {
    throw new CartApiError("Не удалось подготовить защищённый запрос корзины.", {
      payload: { error: { code: "csrf_cookie_missing" } },
    });
  }

  return requestJson(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify(body),
  });
}

export function getCart(options = {}) {
  return requestJson("/api/cart", options);
}

export function getProducts(page = 1, options = {}) {
  return requestJson(`/api/products?page=${encodeURIComponent(page)}`, options);
}

function normalizeProductPayload(payload) {
  const normalized = payload?.normalized;
  if (!normalized || typeof normalized !== "object") return payload;

  const normalizedPrice = normalized.price;
  const normalizedAvailability = normalized.availability;

  return {
    ...payload,
    ...normalized,
    // ProductCard expects the legacy flat fields while the backend's
    // canonical contract keeps price nested under normalized.price.
    price: normalizedPrice?.amount ?? payload.price,
    currency: normalizedPrice?.currency ?? payload.currency,
    verified_at: normalizedPrice?.verified_at ?? normalizedAvailability?.verified_at ?? payload.verified_at,
    availability: normalizedAvailability ?? payload.availability,
    quantity: payload.quantity ?? normalizedAvailability?.sellable_quantity,
    image: normalized.image_url ?? payload.image,
    url: normalized.product_url ?? payload.url,
    properties: normalized.properties_raw ?? payload.properties,
  };
}

export function getProduct(productId, options = {}) {
  return requestJson(`/api/products/detail?id=${encodeURIComponent(productId)}`, options)
    .then(normalizeProductPayload);
}

export function createCartAction(payload) {
  return postJson("/api/cart/actions", payload);
}

export function confirmCartAction(actionId) {
  return postJson(`/api/cart/actions/${encodeURIComponent(actionId)}/confirm`, {});
}

export function confirmCartText(dialogId, confirmationText) {
  return postJson("/api/cart/actions/confirm-text", {
    dialog_id: dialogId,
    text: confirmationText,
  });
}

export function setChatLanguage(dialogId, language) {
  return postJson("/api/chat/language", {
    dialog_id: dialogId,
    language,
  });
}
