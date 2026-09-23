import { describe, expect, it } from "vitest";
import { formatCurrency, formatDateTime, formatNumber, getLocale, getMessages } from "./i18n.js";

describe("interface localization", () => {
  it("exposes Kazakhstan locales and keeps product values out of translations", () => {
    expect(getLocale("ru")).toBe("ru-KZ");
    expect(getLocale("kk")).toBe("kk-KZ");
    expect(getMessages("kk").suggestions[0].prompt).toContain("Legrand");
  });

  it("formats numbers, currency and date/time with the selected locale", () => {
    expect(formatNumber(1234567.5, "kk")).toBe(new Intl.NumberFormat("kk-KZ").format(1234567.5));
    expect(formatNumber(1234567.5, "ru")).toBe(new Intl.NumberFormat("ru-KZ").format(1234567.5));
    expect(formatCurrency(64920, "KZT", "kk")).toMatch(/₸|KZT/);
    expect(formatDateTime("2030-01-01T12:00:00Z", "kk", { year: "numeric" })).toContain("2030");
  });
});
