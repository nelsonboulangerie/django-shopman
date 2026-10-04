import { describe, expect, it } from "vitest";

import { activeSectionKey } from "../../operator-kit/app/presentation/appBar";
import { gestorSections, gestorSettingsSections, SETTINGS_ROUTES } from "../app/presentation/gestorSections";

// O rail do Gestor em dois andares (prévia v4, UX-KIT-V2): a operação em cima (Pedidos e
// Saída) e Ajustes no pé. As seções que saíram do rail moram em Ajustes, a um toque.
describe("gestorSections (rail)", () => {
  it("a operação em cima, com o rótulo do grupo; Ajustes no pé", () => {
    const sections = gestorSections({ channelsAttention: "", canManageCustomers: true });
    expect(sections.map((s) => s.key)).toEqual(["orders", "exit", "settings"]);
    expect(sections.filter((s) => s.group === "Operação").map((s) => s.key)).toEqual(["orders", "exit"]);
    expect(sections.find((s) => s.key === "settings")?.foot).toBe(true);
  });

  it("Pedidos abre as três colunas; Saída abre o posto do passe", () => {
    const sections = gestorSections({ channelsAttention: "", canManageCustomers: false });
    expect(sections.find((s) => s.key === "orders")?.to).toBe("/?columns=all");
    expect(sections.find((s) => s.key === "exit")?.to).toBe("/?columns=expedition");
  });

  it("quem só expede (SUITE-UX §15) fica só com a operação", () => {
    const keys = gestorSections({ channelsAttention: "1 desligado", canManageCustomers: true, expeditesOnly: true }).map((s) => s.key);
    expect(keys).toEqual(["orders", "exit"]);
  });

  it("a atenção de Canais acende o ponto em Ajustes só quando há o que dizer", () => {
    const quiet = gestorSections({ channelsAttention: "", canManageCustomers: false }).find((s) => s.key === "settings");
    const loud = gestorSections({ channelsAttention: "1 desligado", canManageCustomers: false }).find((s) => s.key === "settings");
    expect(quiet?.attention).toBeUndefined();
    expect(loud?.attention).toBe("1 desligado");
  });

  it("os selos contam o que o quadro vê; zero não é selo", () => {
    const sections = gestorSections({ channelsAttention: "", canManageCustomers: false, intakeCount: 2, exitCount: 0 });
    expect(sections.find((s) => s.key === "orders")).toMatchObject({ badge: "2", badgeLabel: "2 pedidos novos" });
    expect(sections.find((s) => s.key === "exit")?.badge).toBeUndefined();
  });

  it("estar numa seção de Ajustes acende o item Ajustes", () => {
    const sections = gestorSections({ channelsAttention: "", canManageCustomers: true });
    for (const path of ["/catalog", "/history", "/customers/merges", "/channels/ifood/catalog", "/feeds", "/workstations", "/settings"]) {
      expect(activeSectionKey(path, sections)).toBe("settings");
    }
    expect(activeSectionKey("/", sections)).toBe("orders");
    expect(SETTINGS_ROUTES).toContain("/catalog");
  });
});

describe("gestorSettingsSections (andar Ajustes)", () => {
  it("Clientes aparece para quem pode gerir clientes, entre Catálogo e Canais", () => {
    const keys = gestorSettingsSections({ channelsAttention: "", canManageCustomers: true }).map((s) => s.key);
    expect(keys).toEqual(["history", "catalog", "customers", "feeds"]);
  });

  it("sem a permissão (ou sem resposta ainda) a linha não existe", () => {
    const keys = gestorSettingsSections({ channelsAttention: "", canManageCustomers: false }).map((s) => s.key);
    expect(keys).toEqual(["history", "catalog", "feeds"]);
  });

  it("a atenção de Canais também aparece na linha de Canais", () => {
    const loud = gestorSettingsSections({ channelsAttention: "1 desligado", canManageCustomers: false }).find((s) => s.key === "feeds");
    expect(loud?.attention).toBe("1 desligado");
  });

  it("Postos aparece por último, só para quem gere operadores", () => {
    const keys = gestorSettingsSections({ channelsAttention: "", canManageCustomers: false, canManageWorkstations: true }).map((s) => s.key);
    expect(keys).toEqual(["history", "catalog", "feeds", "workstations"]);
    expect(gestorSettingsSections({ channelsAttention: "", canManageCustomers: false }).map((s) => s.key)).not.toContain("workstations");
  });
});
