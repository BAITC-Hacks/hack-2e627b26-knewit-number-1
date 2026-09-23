import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  CartApiError,
  confirmCartAction,
  createCartAction,
  getCart,
} from "./cartApi.js";

function jsonResponse(payload, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

describe("cart API client", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=csrf-test-token; path=/";
    vi.stubGlobal("fetch", vi.fn());
  });

  it("bootstraps the same-origin cart session", async () => {
    fetch.mockImplementation(() => jsonResponse({ items: [], url: "/demo/cart/" }));

    await expect(getCart()).resolves.toMatchObject({ items: [] });
    expect(fetch).toHaveBeenCalledWith("/api/cart", { credentials: "same-origin" });
  });

  it("sends JSON mutations with the CSRF cookie", async () => {
    fetch.mockImplementation(() => jsonResponse({ action_id: "action-1", status: "proposed" }, 201));
    const payload = {
      dialog_id: "dialog-1",
      message_id: "message-1",
      message_version: 1,
      product_id: 900001,
      offer_id: null,
      quantity: 2,
    };

    await createCartAction(payload);

    expect(fetch).toHaveBeenCalledWith("/api/cart/actions", expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": "csrf-test-token",
      },
      body: JSON.stringify(payload),
    }));
  });

  it("confirms only the action encoded in the URL", async () => {
    fetch.mockImplementation(() => jsonResponse({ action_id: "exact-action", status: "succeeded" }));

    await confirmCartAction("exact-action");

    expect(fetch).toHaveBeenCalledWith(
      "/api/cart/actions/exact-action/confirm",
      expect.objectContaining({ body: "{}", method: "POST" }),
    );
  });

  it("exposes structured backend errors", async () => {
    fetch.mockImplementation(() => jsonResponse({
      error: { code: "insufficient_stock", message: "not enough" },
      maximum_quantity: 3,
    }, 409));

    await expect(createCartAction({})).rejects.toMatchObject({
      name: "CartApiError",
      code: "insufficient_stock",
      status: 409,
      payload: { maximum_quantity: 3 },
    });
  });

  it("fails before mutation when the CSRF cookie is absent", async () => {
    document.cookie = "csrftoken=; Max-Age=0; path=/";

    await expect(confirmCartAction("action-1")).rejects.toBeInstanceOf(CartApiError);
    expect(fetch).not.toHaveBeenCalled();
  });
});
