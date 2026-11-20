import { describe, expect, it } from "vitest";

import {
  railSignalChip,
  sectionDescription,
  sectionRailSignal,
} from "../../operator-kit/app/presentation/suiteChrome";
import { deliveriesWaitingBadge, gestorSections } from "../app/presentation/gestorSections";

// O selo de Entregas (F10, ENT-PERF-14): a contagem que falhou é "?", nunca zero.
// Zero diria "nada aguardando entregador", e isso seria mentira.
function deliveries(waiting: number | null | undefined) {
  return gestorSections({ channelsAttention: "", canManageCustomers: false, deliveriesWaiting: waiting }).find(
    (section) => section.key === "deliveries",
  )!;
}

describe("deliveriesWaitingBadge", () => {
  it("o número que o servidor contou", () => {
    expect(deliveriesWaitingBadge({ waiting: 3 }, false)).toBe(3);
    expect(deliveriesWaitingBadge({ waiting: 0 }, false)).toBe(0);
  });

  it("o servidor não conseguiu contar: desconhecido", () => {
    expect(deliveriesWaitingBadge({ waiting: null }, false)).toBeNull();
  });

  it("a leitura falhou: desconhecido, mesmo com o número de antes", () => {
    expect(deliveriesWaitingBadge(undefined, true)).toBeNull();
    expect(deliveriesWaitingBadge({ waiting: 4 }, true)).toBeNull();
  });

  it("antes da primeira resposta, nenhum selo", () => {
    expect(deliveriesWaitingBadge(undefined, false)).toBeUndefined();
    expect(deliveriesWaitingBadge(null, false)).toBeUndefined();
  });
});

describe("o selo de Entregas no rail", () => {
  it("contagem desconhecida vira o chip com ?, e o nome acessível diz por quê", () => {
    const section = deliveries(null);
    expect(section.badge).toBe("?");
    const signal = sectionRailSignal(section)!;
    expect(signal.unknown).toBe(true);
    expect(railSignalChip(signal).text).toBe("?");
    expect(sectionDescription(section)).toBe("Entregas · contagem indisponível");
  });

  it("zero não é selo, e o número é o chip de sempre", () => {
    expect(deliveries(0).badge).toBeUndefined();
    expect(sectionRailSignal(deliveries(0))).toBeUndefined();
    expect(deliveries(2).badge).toBe("2");
    expect(sectionDescription(deliveries(2))).toBe("Entregas · 2 pendências");
  });

  it("sem resposta ainda, nenhum selo", () => {
    expect(deliveries(undefined).badge).toBeUndefined();
  });
});
