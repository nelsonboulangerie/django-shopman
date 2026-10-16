// Hora da Xepa na grade: o tile risca a etiqueta cheia ao lado do preço que o
// motor cobra agora, e a tela relê a projeção quando a janela abre ou fecha.
import { describe, expect, it } from "vitest";

import {
  PRICE_WINDOW_REFRESH_GRACE_MS,
  priceWindowRefreshDelayMs,
  productStrikePrice,
} from "../app/presentation/catalog";

describe("productStrikePrice", () => {
  it("risca a etiqueta quando o preço de agora é menor", () => {
    expect(productStrikePrice({ price_q: 900, list_price_q: 1200, list_price_display: "R$ 12,00" })).toBe("R$ 12,00");
  });

  it("não risca nada sem desconto (etiqueta ausente, zero ou igual)", () => {
    expect(productStrikePrice({ price_q: 1200 })).toBe("");
    expect(productStrikePrice({ price_q: 1200, list_price_q: 0, list_price_display: "" })).toBe("");
    expect(productStrikePrice({ price_q: 1200, list_price_q: 1200, list_price_display: "R$ 12,00" })).toBe("");
  });
});

describe("priceWindowRefreshDelayMs", () => {
  const now = Date.parse("2026-10-10T17:59:00-03:00");

  it("espera até a virada, com folga para o servidor já estar do outro lado", () => {
    expect(priceWindowRefreshDelayMs("2026-10-10T18:00:00-03:00", now)).toBe(60_000 + PRICE_WINDOW_REFRESH_GRACE_MS);
  });

  it("virada que já passou relê logo (só a folga)", () => {
    expect(priceWindowRefreshDelayMs("2026-10-10T17:30:00-03:00", now)).toBe(PRICE_WINDOW_REFRESH_GRACE_MS);
  });

  it("sem janela ou data ilegível, não arma relógio", () => {
    expect(priceWindowRefreshDelayMs(null, now)).toBeNull();
    expect(priceWindowRefreshDelayMs("", now)).toBeNull();
    expect(priceWindowRefreshDelayMs("amanhã", now)).toBeNull();
  });
});
