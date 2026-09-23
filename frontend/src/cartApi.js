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

async function requestJson(path, options = {}) {
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

export function getProduct(productId, options = {}) {
  return requestJson(`/api/products/detail?id=${encodeURIComponent(productId)}`, options);
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
