// Leitura pura da caixa pessoal — sem Vue, sem rede.
import { describe, expect, it } from "vitest";

import {
  anomalyLabels,
  badgeCount,
  isHighlighted,
  isSignIn,
  signInSummary,
  unreadOf,
} from "../app/presentation/notifications";

describe("badgeCount", () => {
  it("some quando não há nada por ler", () => {
    expect(badgeCount(0)).toBe("");
    expect(badgeCount(-3)).toBe("");
  });

  it("mostra o número até nove", () => {
    expect(badgeCount(1)).toBe("1");
    expect(badgeCount(9)).toBe("9");
  });

  it("acima de nove vira 9+ — o número exato não muda decisão nenhuma", () => {
    expect(badgeCount(10)).toBe("9+");
    expect(badgeCount(240)).toBe("9+");
  });
});

describe("isHighlighted", () => {
  it("realça o que o backend marcou", () => {
    expect(isHighlighted({ action_data: { highlight: true } })).toBe(true);
  });

  it("o acesso de rotina não se destaca — senão nada se destaca", () => {
    expect(isHighlighted({ action_data: { highlight: false } })).toBe(false);
    expect(isHighlighted({ action_data: {} })).toBe(false);
  });
});

describe("anomalyLabels", () => {
  it("lê os códigos que o backend mandou", () => {
    expect(anomalyLabels({ action_data: { anomalies: ["badge", "burst"] } })).toEqual([
      "badge",
      "burst",
    ]);
  });

  it("payload torto não quebra a lista", () => {
    expect(anomalyLabels({ action_data: { anomalies: "badge" } })).toEqual([]);
    expect(anomalyLabels({ action_data: {} })).toEqual([]);
  });
});

describe("isSignIn", () => {
  it("separa o aviso de acesso dos demais", () => {
    expect(isSignIn({ category: "sign_in" })).toBe(true);
    expect(isSignIn({ category: "campaign" })).toBe(false);
  });
});

describe("signInSummary", () => {
  const base = {
    pk: 1,
    method: "badge",
    method_display: "crachá",
    outcome: "success",
    outcome_display: "entrou",
    station_ref: "pdv-main",
    station_display: "pdv-main",
    ip_address: "",
    created_at: "",
    created_at_display: "29/08 às 06:12",
    anomalies: [],
    anomaly_labels: [],
    highlight: false,
  };

  it("diz por qual porta e de onde", () => {
    expect(signInSummary(base)).toBe("crachá · pdv-main");
  });

  it("a recusa vem primeiro — é o que muda a leitura da linha", () => {
    expect(
      signInSummary({ ...base, outcome: "failed", outcome_display: "recusado" }),
    ).toBe("recusado · crachá · pdv-main");
  });

  it("sem estação, diz de onde foi em vez de deixar vazio", () => {
    expect(
      signInSummary({ ...base, station_ref: "", station_display: "fora da loja" }),
    ).toBe("crachá · fora da loja");
  });
});

describe("unreadOf", () => {
  it("resposta truncada não vira contador negativo nem NaN", () => {
    expect(unreadOf(null)).toBe(0);
    expect(unreadOf({})).toBe(0);
    expect(unreadOf({ unread_count: -2 })).toBe(0);
    expect(unreadOf({ unread_count: 4 })).toBe(4);
  });
});
