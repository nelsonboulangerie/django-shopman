// Leitura pura da caixa pessoal — sem Vue, sem rede.
import { describe, expect, it } from "vitest";

import {
  badgeCount,
  canReportNotMe,
  inboxLayout,
  isHighlighted,
  isSignIn,
  routineSignInsLabel,
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

// Beta 05/11 (CEN-01): 28 "Sua conta foi usada" antes dos 2 lotes da Qualidade.
describe("inboxLayout", () => {
  const access = (pk: number, highlight = false) =>
    ({ pk, category: "sign_in", action_data: { highlight }, is_actionable: true }) as never;
  const lote = { pk: 99, category: "production", action_data: {}, is_actionable: false } as never;

  it("a operação vem antes dos acessos", () => {
    const layout = inboxLayout([access(1), access(2), lote]);
    expect(layout.operation.map((n: { pk: number }) => n.pk)).toEqual([99]);
    expect(layout.signIns.map((n: { pk: number }) => n.pk)).toEqual([1, 2]);
    expect(layout.routine).toEqual([]);
  });

  it("acessos de rotina em quantidade viram uma linha; o suspeito continua inteiro", () => {
    const layout = inboxLayout([access(1), access(2, true), access(3), access(4), lote]);
    expect(layout.signIns.map((n: { pk: number }) => n.pk)).toEqual([2]);
    expect(layout.routine.map((n: { pk: number }) => n.pk)).toEqual([1, 3, 4]);
    expect(routineSignInsLabel(3)).toBe("3 acessos seus sem nada fora do comum");
    expect(routineSignInsLabel(1)).toBe("1 acesso seu sem nada fora do comum");
  });

  it("'Não fui eu' só sobre acesso que aconteceu", () => {
    expect(canReportNotMe({ category: "sign_in", is_actionable: true })).toBe(true);
    expect(canReportNotMe({ category: "sign_in", is_actionable: false })).toBe(false);
    expect(canReportNotMe({ category: "production", is_actionable: true })).toBe(false);
  });
});
