import { describe, expect, it } from "vitest";

import { quickDayOptions } from "../../operator-kit/app/presentation/dates";
import { dayMonth, nextOpenDay, seedPlannedQty, type DayChoice } from "./e2e-live/support/nextOpenDay";

// As jornadas ao vivo J5, J11 e J12 escolhem o dia da encomenda pelos botões que a
// tela desenha (#2976). Aqui a escolha é provada contra o MESMO `quickDayOptions` do
// kit, com o horário da Nelson: abre de segunda a sábado, fecha no domingo.

/** As datas abertas de `from` até `days` adiante, sem domingo (o horário da loja). */
function openDates(from: string, days: number): string[] {
  const out: string[] = [];
  const start = new Date(`${from}T12:00:00Z`);
  for (let step = 0; step <= days; step += 1) {
    const day = new Date(start.getTime() + step * 86_400_000);
    if (day.getUTCDay() !== 0) out.push(day.toISOString().slice(0, 10));
  }
  return out;
}

/** Os botões como a tela os desenha: o motivo apaga o botão. */
function screenOf(today: string, availableDates: readonly string[], max?: string): DayChoice[] {
  const quick = quickDayOptions({ today, min: today, max, availableDates }).map((option) => ({
    key: option.key,
    iso: option.iso,
    disabled: Boolean(option.reason),
  }));
  return [...quick, { key: "other", iso: "", disabled: false }];
}

describe("o próximo dia aberto da encomenda", () => {
  it("sábado, véspera de domingo fechado: escolhe a segunda", () => {
    // 21/11/2026 é sábado; 22/11, domingo, fechado.
    const today = "2026-11-21";
    const options = screenOf(today, openDates(today, 14));
    expect(options.find((option) => option.key === "tomorrow")).toMatchObject({ iso: "2026-11-22", disabled: true });
    const chosen = nextOpenDay(options);
    expect(chosen).toMatchObject({ key: "next", iso: "2026-11-23" });
    expect(dayMonth(chosen!.iso)).toBe("23/11");
  });

  it("sexta, com o sábado aberto: escolhe amanhã", () => {
    const today = "2026-11-20";
    expect(nextOpenDay(screenOf(today, openDates(today, 14)))).toMatchObject({ key: "tomorrow", iso: "2026-11-21" });
  });

  it("feriado na segunda depois do domingo: pula os dois e escolhe a terça", () => {
    const today = "2026-11-21";
    const open = openDates(today, 14).filter((iso) => iso !== "2026-11-23");
    expect(nextOpenDay(screenOf(today, open))).toMatchObject({ key: "next", iso: "2026-11-24" });
  });

  it("nenhum dia aberto nos dias de um toque: nada é escolhido às cegas", () => {
    // A casa só aceita encomenda para hoje (o prazo acaba hoje): amanhã e a próxima
    // data vêm apagados, e a jornada para dizendo por quê, em vez de chutar um dia.
    const today = "2026-11-21";
    const options = screenOf(today, openDates(today, 14), today);
    expect(options.filter((option) => option.key !== "other").every((option) => option.key === "today" || option.disabled)).toBe(true);
    expect(nextOpenDay(options)).toBeNull();
  });

  it("o lote do seed para a data: 22 de segunda a quinta, 28 na sexta e no sábado", () => {
    expect(seedPlannedQty(22, "2026-11-23")).toBe(22); // segunda
    expect(seedPlannedQty(22, "2026-11-26")).toBe(22); // quinta
    expect(seedPlannedQty(22, "2026-11-27")).toBe(28); // sexta: 27,5 vai ao par
    expect(seedPlannedQty(22, "2026-11-28")).toBe(28); // sábado
    // O arredondamento do Python (metade para o par): 42 × 1,25 = 52,5 → 52.
    expect(seedPlannedQty(42, "2026-11-28")).toBe(52);
  });
});
