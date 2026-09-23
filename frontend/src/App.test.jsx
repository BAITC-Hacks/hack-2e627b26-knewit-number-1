import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

const PRODUCT = {
  id: 900001,
  name: "Автоматический выключатель ВА47-29 1P 6A IEK",
  article: "ДЕМО-01-001",
  price: 917,
  quantity: 10,
  image: "/api/fixtures/product-placeholder.svg",
  url: "/demo/catalog/900001/",
  offers: [],
  properties: { TORGOVAYA_MARKA: "IEK" },
  availability: { status: "available", sellable_quantity: 8 },
  data_source: "fixture",
};

function action(overrides = {}) {
  return {
    action_id: "action-original",
    status: "proposed",
    dialog_id: "dialog-test",
    message_id: "message-test",
    message_version: 1,
    expires_at: "2030-01-01T12:00:00Z",
    product: PRODUCT,
    product_id: PRODUCT.id,
    offer_id: null,
    quantity: 2,
    unit_price: "917.00",
    currency: "KZT",
    total: "1834.00",
    ...overrides,
  };
}

function jsonResponse(payload, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

function installFetch(handler = () => jsonResponse({}), dialogHandler) {
  vi.stubGlobal("fetch", vi.fn((url, options = {}) => {
    if (url === "/api/cart" && (!options.method || options.method === "GET")) {
      return jsonResponse({ version: 0, currency: "KZT", items: [], total: "0.00", url: "/demo/cart/" });
    }
    if (url === "/api/dialog" && (!options.method || options.method === "GET")) {
      return jsonResponse({ dialog_id: "dialog-test", state: "idle", history: [] });
    }
    if (String(url).startsWith("/api/products/detail")) return jsonResponse(PRODUCT);
    if (url === "/api/dialog/messages") {
      const request = JSON.parse(options.body || "{}");
      const dialogPayload = dialogHandler?.(request);
      if (dialogPayload) return jsonResponse(dialogPayload);
      return jsonResponse({
        dialog_id: "dialog-test",
        state: "done",
        message: {
          id: "assistant-from-api",
          role: "assistant",
          state: "done",
          content: request.text === "Хочу купить" ? "Уточните, какой товар вам нужен." : "Нашёл товар в каталоге.",
          products: /автомат|legrand/i.test(request.text || "") ? [PRODUCT] : [],
        },
      });
    }
    return handler(url, options);
  }));
}

function dialogProposalResponse(proposal) {
  return {
    dialog_id: "dialog-test",
    state: "done",
    message: {
      id: "assistant-proposal-from-api",
      role: "assistant",
      state: "done",
      content: "Подготовил предложение добавить 2 шт. выбранного товара. Подтвердите добавление явно.",
      products: [PRODUCT],
      cart_proposal: proposal,
    },
  };
}

async function openProductCard(user) {
  render(<App />);
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/cart", expect.anything()));
  await user.click(screen.getByRole("button", { name: /открыть чат/i }));
  await user.click(screen.getByRole("button", { name: "Автомат Legrand на 160 А" }));
  return screen.findByRole("article", { name: /Автоматический выключатель/ }, { timeout: 2500 });
}

describe("cart confirmation flow", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=csrf-ui-token; path=/";
  });

  it("creates an immutable summary, confirms its action id and updates the cart", async () => {
    const user = userEvent.setup();
    const proposal = action();
    installFetch((url) => {
      if (url === "/api/cart/actions") return jsonResponse(proposal, 201);
      if (url === "/api/cart/actions/action-original/confirm") {
        return jsonResponse({
          action_id: "action-original",
          status: "succeeded",
          added_quantity: 2,
          cart: {
            version: 1,
            currency: "KZT",
            total: "1834.00",
            url: "/demo/cart/",
            items: [{ product_id: PRODUCT.id, quantity: 2, unit_price: "917.00", product: PRODUCT }],
          },
        });
      }
      return jsonResponse({ error: { code: "unexpected" } }, 500);
    });

    const card = await openProductCard(user);
    const quantity = within(card).getByRole("spinbutton", { name: "Количество" });
    await user.clear(quantity);
    await user.type(quantity, "2");
    await user.click(within(card).getByRole("button", { name: /добавить/i }));

    const summary = await screen.findByLabelText("Резюме добавления в корзину");
    expect(fetch.mock.calls.filter(([url]) => url === "/api/cart/actions")).toHaveLength(1);
    expect(within(summary).getByText("ДЕМО-01-001", { exact: false })).toBeInTheDocument();
    expect(within(summary).getByText("2 шт.")).toBeInTheDocument();
    expect(within(summary).getByText(/1\s?834/)).toBeInTheDocument();

    await user.click(within(summary).getByRole("button", { name: "Подтвердить и добавить" }));

    expect(await screen.findByText("Добавлено: 2 шт.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Открыть корзину, товаров: 2/ })).toHaveAttribute("href", "/demo/cart/");
    expect(fetch).toHaveBeenCalledWith(
      "/api/cart/actions/action-original/confirm",
      expect.objectContaining({ method: "POST", body: "{}" }),
    );
  });

  it("renders a server-issued proposal from a text command and confirms its exact action", async () => {
    const user = userEvent.setup();
    const proposal = action({ action_id: "dialog-action" });
    installFetch((url) => {
      if (url === "/api/cart/actions/dialog-action/confirm") {
        return jsonResponse({
          action_id: "dialog-action",
          status: "succeeded",
          added_quantity: 2,
          cart: {
            version: 1,
            currency: "KZT",
            total: "1834.00",
            url: "/demo/cart/",
            items: [{ product_id: PRODUCT.id, quantity: 2, unit_price: "917.00", product: PRODUCT }],
          },
        });
      }
      return jsonResponse({ error: { code: "unexpected" } }, 500);
    }, (request) => request.text === "добавь два" ? dialogProposalResponse(proposal) : null);

    render(<App />);
    await user.click(screen.getByRole("button", { name: /открыть чат/i }));
    const input = screen.getByLabelText("Введите сообщение");
    await user.type(input, "добавь два");
    await user.keyboard("{Enter}");

    const summary = await screen.findByLabelText("Резюме добавления в корзину");
    expect(summary).toHaveAttribute("data-action-id", "dialog-action");
    expect(within(summary).getByText("2 шт.")).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([url]) => url === "/api/cart/actions")).toHaveLength(0);

    await user.click(within(summary).getByRole("button", { name: "Подтвердить и добавить" }));

    expect(await screen.findByText("Добавлено: 2 шт.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Открыть корзину, товаров: 2/ })).toHaveAttribute("href", "/demo/cart/");
    expect(fetch).toHaveBeenCalledWith(
      "/api/cart/actions/dialog-action/confirm",
      expect.objectContaining({ method: "POST", body: "{}" }),
    );
  });

  it("confirms a server-issued proposal when the user explicitly replies yes", async () => {
    const user = userEvent.setup();
    const proposal = action({ action_id: "dialog-text-action" });
    installFetch((url) => {
      if (url === "/api/cart/actions/confirm-text") {
        return jsonResponse({
          action_id: "dialog-text-action",
          status: "succeeded",
          added_quantity: 2,
          cart: {
            version: 1,
            currency: "KZT",
            total: "1834.00",
            url: "/demo/cart/",
            items: [{ product_id: PRODUCT.id, quantity: 2, unit_price: "917.00", product: PRODUCT }],
          },
        });
      }
      return jsonResponse({ error: { code: "unexpected" } }, 500);
    }, (request) => request.text === "добавь два" ? dialogProposalResponse(proposal) : null);

    render(<App />);
    await user.click(screen.getByRole("button", { name: /открыть чат/i }));
    const input = screen.getByLabelText("Введите сообщение");
    await user.type(input, "добавь два");
    await user.keyboard("{Enter}");
    await screen.findByLabelText("Резюме добавления в корзину");

    await user.type(input, "да");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Добавлено: 2 шт.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/cart/actions/confirm-text",
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"text":"да"') }),
    );
  });

  it("renders a separately confirmable replacement when stock is insufficient", async () => {
    const user = userEvent.setup();
    const replacement = action({ action_id: "action-replacement", quantity: 8, total: "7336.00", message_version: 2 });
    installFetch((url) => {
      if (url === "/api/cart/actions") {
        return jsonResponse({
          error: { code: "insufficient_stock", message: "not enough" },
          action_id: "action-expired",
          status: "expired",
          maximum_quantity: 8,
          replacement_action: replacement,
          cart: { items: [], total: "0.00", url: "/demo/cart/" },
        }, 409);
      }
      return jsonResponse({}, 500);
    });

    const card = await openProductCard(user);
    const quantity = within(card).getByRole("spinbutton", { name: "Количество" });
    await user.clear(quantity);
    await user.type(quantity, "9");
    await user.click(within(card).getByRole("button", { name: /добавить/i }));

    expect(await screen.findByText(/новое резюме на 8 шт/i)).toBeInTheDocument();
    const summary = screen.getByLabelText("Резюме добавления в корзину");
    expect(summary).toHaveAttribute("data-action-id", "action-replacement");
    expect(within(summary).getByRole("button", { name: "Подтвердить и добавить" })).toBeEnabled();
  });

  it("recovers from a failed cart bootstrap when the user creates a proposal", async () => {
    const user = userEvent.setup();
    let cartReads = 0;
    vi.stubGlobal("fetch", vi.fn((url) => {
      if (url === "/api/cart") {
        cartReads += 1;
        return cartReads === 1
          ? jsonResponse({ error: { code: "temporary_failure" } }, 503)
          : jsonResponse({ items: [], total: "0.00", url: "/demo/cart/" });
      }
      if (url === "/api/dialog/messages") {
        return jsonResponse({
          dialog_id: "dialog-test",
          state: "done",
          message: {
            id: "assistant-from-api",
            role: "assistant",
            state: "done",
            content: "Нашёл товар в каталоге.",
            products: [PRODUCT],
          },
        });
      }
      if (String(url).startsWith("/api/products/detail")) return jsonResponse(PRODUCT);
      if (url === "/api/cart/actions") return jsonResponse(action({ quantity: 1, total: "917.00" }), 201);
      return jsonResponse({}, 500);
    }));

    const card = await openProductCard(user);
    const addButton = within(card).getByRole("button", { name: /добавить/i });
    expect(addButton).toBeEnabled();
    expect(within(card).getByText(/соединение восстановится/i)).toBeInTheDocument();
    await user.click(addButton);

    expect(await screen.findByLabelText("Резюме добавления в корзину")).toBeInTheDocument();
    expect(cartReads).toBe(2);
  });

  it("refreshes CSRF state and retries the same immutable proposal payload", async () => {
    const user = userEvent.setup();
    const proposalBodies = [];
    installFetch((url, options) => {
      if (url === "/api/cart/actions") {
        proposalBodies.push(options.body);
        return proposalBodies.length === 1
          ? jsonResponse({ error: { code: "csrf_failed", message: "expired" } }, 403)
          : jsonResponse(action({ quantity: 1, total: "917.00" }), 201);
      }
      return jsonResponse({}, 500);
    });

    const card = await openProductCard(user);
    await user.click(within(card).getByRole("button", { name: /добавить/i }));
    const retry = await within(card).findByRole("button", { name: "Повторить" });
    await user.click(retry);

    expect(await screen.findByLabelText("Резюме добавления в корзину")).toBeInTheDocument();
    expect(proposalBodies).toHaveLength(2);
    expect(proposalBodies[1]).toBe(proposalBodies[0]);
  });

  it("expires a stale action and requires confirmation of the replacement action", async () => {
    const user = userEvent.setup();
    const replacement = action({
      action_id: "action-after-price-change",
      message_version: 2,
      unit_price: "1017.00",
      total: "2034.00",
    });
    installFetch((url) => {
      if (url === "/api/cart/actions") return jsonResponse(action(), 201);
      if (url === "/api/cart/actions/action-original/confirm") {
        return jsonResponse({
          error: { code: "action_stale", message: "stale" },
          action_id: "action-original",
          status: "expired",
          replacement_action: replacement,
        }, 409);
      }
      return jsonResponse({}, 500);
    });

    const card = await openProductCard(user);
    const quantity = within(card).getByRole("spinbutton", { name: "Количество" });
    await user.clear(quantity);
    await user.type(quantity, "2");
    await user.click(within(card).getByRole("button", { name: /добавить/i }));
    const original = await screen.findByLabelText("Резюме добавления в корзину");
    await user.click(within(original).getByRole("button", { name: "Подтвердить и добавить" }));

    expect(await screen.findByText(/подтвердите обновлённое резюме/i)).toBeInTheDocument();
    const summaries = screen.getAllByLabelText("Резюме добавления в корзину");
    expect(summaries[0]).toHaveAttribute("data-action-id", "action-original");
    expect(within(summaries[0]).getByRole("button")).toBeDisabled();
    expect(summaries[1]).toHaveAttribute("data-action-id", "action-after-price-change");
    expect(within(summaries[1]).getByRole("button", { name: "Подтвердить и добавить" })).toBeEnabled();
  });

  it("routes exact text confirmation to the backend and explains ambiguity", async () => {
    const user = userEvent.setup();
    installFetch((url) => {
      if (url === "/api/cart/actions/confirm-text") {
        return jsonResponse({
          error: { code: "ambiguous_confirmation", message: "ambiguous" },
        }, 409);
      }
      return jsonResponse({}, 500);
    });
    render(<App />);
    await user.click(screen.getByRole("button", { name: /открыть чат/i }));
    const input = screen.getByLabelText("Введите сообщение");
    await user.type(input, "Подтверждаю");
    await user.keyboard("{Enter}");

    expect(await screen.findByText(/нажмите кнопку в нужном резюме/i)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/cart/actions/confirm-text",
      expect.objectContaining({ body: expect.stringContaining('"text":"Подтверждаю"') }),
    );
  });

  it("shows the confirming state while exact text confirmation is pending", async () => {
    const user = userEvent.setup();
    let resolveTextConfirmation;
    const textConfirmation = new Promise((resolve) => {
      resolveTextConfirmation = resolve;
    });
    installFetch((url) => {
      if (url === "/api/cart/actions") return jsonResponse(action({ quantity: 1, total: "917.00" }), 201);
      if (url === "/api/cart/actions/confirm-text") return textConfirmation;
      return jsonResponse({}, 500);
    });

    const card = await openProductCard(user);
    await user.click(within(card).getByRole("button", { name: /добавить/i }));
    const summary = await screen.findByLabelText("Резюме добавления в корзину");
    const input = screen.getByLabelText("Введите сообщение");
    await user.type(input, "да");
    await user.keyboard("{Enter}");

    expect(within(summary).getByRole("button", { name: /проверяю цену и остаток/i })).toBeDisabled();
    resolveTextConfirmation(new Response(JSON.stringify({
      action_id: "action-original",
      status: "succeeded",
      added_quantity: 1,
      cart: {
        items: [{ product_id: PRODUCT.id, quantity: 1, product: PRODUCT }],
        total: "917.00",
        url: "/demo/cart/",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    expect(await screen.findByText("Добавлено: 1 шт.")).toBeInTheDocument();
  });

  it("does not treat an intent phrase as cart confirmation", async () => {
    const user = userEvent.setup();
    installFetch();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /открыть чат/i }));
    const input = screen.getByLabelText("Введите сообщение");
    await user.type(input, "Хочу купить");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Уточните, какой товар вам нужен.", {}, { timeout: 2500 })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => url === "/api/cart/actions/confirm-text")).toBe(false);
  });

  it("traps keyboard focus in the clear dialog and restores it on Escape", async () => {
    const user = userEvent.setup();
    installFetch();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /открыть чат/i }));
    const clearButton = screen.getByRole("button", { name: "Очистить историю" });
    await user.click(clearButton);

    const cancel = screen.getByRole("button", { name: "Отмена" });
    const confirm = screen.getByRole("button", { name: "Очистить" });
    expect(cancel).toHaveFocus();
    await user.tab();
    expect(confirm).toHaveFocus();
    await user.tab();
    expect(cancel).toHaveFocus();
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    await waitFor(() => expect(clearButton).toHaveFocus());
  });

  it("switches the interface to kk-KZ and safely expires an active cart proposal", async () => {
    const user = userEvent.setup();
    installFetch((url) => {
      if (url === "/api/cart/actions") return jsonResponse(action(), 201);
      if (url === "/api/chat/language") {
        return jsonResponse({
          language: "kk",
          language_changed: true,
          cart_summary: {
            message: "Себеттің белсенді ұсынысы тоқтатылды. Қазақ тілінде жаңа қорытынды жасаңыз.",
            requires_new_proposal: true,
          },
        });
      }
      return jsonResponse({}, 500);
    });

    const card = await openProductCard(user);
    await user.click(within(card).getByRole("button", { name: /добавить/i }));
    const summary = await screen.findByLabelText("Резюме добавления в корзину");
    await user.click(screen.getByRole("button", { name: "Қазақша" }));

    expect((await screen.findAllByText(/Себеттің белсенді ұсынысы тоқтатылды/i)).length).toBeGreaterThanOrEqual(1);
    expect(within(summary).getByRole("button")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Қазақша" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Кеңесші чатын жабу/i })).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([url]) => url === "/api/chat/language").length).toBeGreaterThanOrEqual(1);
  });

  it("uses the site-level language switch before the chat is opened", async () => {
    const user = userEvent.setup();
    installFetch();
    render(<App />);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/cart", expect.anything()));
    await user.click(screen.getByRole("button", { name: "Қазақша" }));
    await user.click(screen.getByRole("button", { name: /Кеңесші чатын ашу/i }));

    expect(await screen.findByText(/Сәлеметсіз бе!/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Қазақша" })).toHaveAttribute("aria-pressed", "true");
  });
});
