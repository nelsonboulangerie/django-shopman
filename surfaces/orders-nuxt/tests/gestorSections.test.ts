import { describe, expect, it } from "vitest";

import { activeSectionKey } from "../../operator-kit/app/presentation/appBar";
import {
  quickBarLayout,
  quickBarProblems,
} from "../../operator-kit/app/presentation/suiteChrome";
import {
  gestorSections,
  gestorSettingsSections,
  gestorSwitcherSections,
  SETTINGS_ROUTES,
} from "../app/presentation/gestorSections";

// O rail do Gestor em dois andares (prévia v4, UX-KIT-V2): a operação em cima (Pedidos e
// Saída) e Ajustes no pé. As seções que saíram do rail moram em Ajustes, a um toque.
describe("gestorSections (rail)", () => {
  it("a operação em cima, com o rótulo do grupo; Ajustes no pé", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    expect(sections.map((s) => s.key)).toEqual(["orders", "exit", "settings"]);
    expect(
      sections.filter((s) => s.group === "Operação").map((s) => s.key),
    ).toEqual(["orders", "exit"]);
    expect(sections.find((s) => s.key === "settings")?.foot).toBe(true);
  });

  it("Pedidos abre as três colunas; Saída abre o posto do passe", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
    });
    expect(sections.find((s) => s.key === "orders")?.to).toBe("/?columns=all");
    expect(sections.find((s) => s.key === "exit")?.to).toBe(
      "/?columns=expedition",
    );
  });

  it("quem só expede (SUITE-UX §15) fica só com a operação", () => {
    const keys = gestorSections({
      channelsAttention: "1 desligado",
      canManageCustomers: true,
      expeditesOnly: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["orders", "exit"]);
  });

  it("quem cuida só do catálogo recebe Catálogo e Canais, sem Pedidos ou Clientes", () => {
    const keys = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
      catalogOnly: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["catalog", "feeds"]);
    expect(keys).not.toContain("orders");
    expect(keys).not.toContain("customers");
  });

  it("a atenção de Canais acende o ponto em Ajustes só quando há o que dizer", () => {
    const quiet = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
    }).find((s) => s.key === "settings");
    const loud = gestorSections({
      channelsAttention: "1 desligado",
      canManageCustomers: false,
    }).find((s) => s.key === "settings");
    expect(quiet?.attention).toBeUndefined();
    expect(loud?.attention).toBe("1 desligado");
  });

  it("os selos contam o que o quadro vê; zero não é selo", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
      intakeCount: 2,
      exitCount: 0,
    });
    expect(sections.find((s) => s.key === "orders")).toMatchObject({
      badge: "2",
    });
    expect(sections.find((s) => s.key === "exit")?.badge).toBeUndefined();
  });

  it("barra inferior: as três seções declaradas, sem 'Mais' (o ☰ abre o menu completo)", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    const layout = quickBarLayout(sections);
    expect(layout.items.map((s) => s.key)).toEqual([
      "orders",
      "exit",
      "settings",
    ]);
    expect(layout.more).toBe(false);
    expect(quickBarProblems(sections)).toEqual([]);
    // Quem só expede tem duas seções ao todo: a barra mostra as duas, sem erro.
    const expedite = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
      expeditesOnly: true,
    });
    expect(quickBarLayout(expedite).items.map((s) => s.key)).toEqual([
      "orders",
      "exit",
    ]);
    expect(quickBarProblems(expedite)).toEqual([]);
  });

  it("estar numa seção de Ajustes acende o item Ajustes", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    for (const path of [
      "/catalog",
      "/history",
      "/customers/groups",
      "/customers/merges",
      "/channels/ifood/catalog",
      "/feeds",
      "/workstations",
      "/checklists",
      "/settings",
    ]) {
      expect(activeSectionKey(path, sections)).toBe("settings");
    }
    expect(activeSectionKey("/", sections)).toBe("orders");
    expect(SETTINGS_ROUTES).toContain("/catalog");
  });
});

describe("gestorSettingsSections (andar Ajustes)", () => {
  it("Clientes aparece para quem pode gerir clientes, entre Catálogo e Canais", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["history", "catalog", "customers", "feeds"]);
  });

  it("sem a permissão (ou sem resposta ainda) a linha não existe", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: false,
    }).map((s) => s.key);
    expect(keys).toEqual(["history", "catalog", "feeds"]);
  });

  it("a atenção de Canais também aparece na linha de Canais", () => {
    const loud = gestorSettingsSections({
      channelsAttention: "1 desligado",
      canManageCustomers: false,
    }).find((s) => s.key === "feeds");
    expect(loud?.attention).toBe("1 desligado");
  });

  it("Postos aparece por último, só para quem gere operadores", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: false,
      canManageWorkstations: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["history", "catalog", "feeds", "workstations"]);
    expect(
      gestorSettingsSections({
        channelsAttention: "",
        canManageCustomers: false,
      }).map((s) => s.key),
    ).not.toContain("workstations");
  });

  it("Rotinas aparece só para quem pode executar checklist", () => {
    const visible = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: false,
      canOperateChecklists: true,
    });
    expect(visible.map((s) => s.key)).toEqual([
      "checklists",
      "history",
      "catalog",
      "feeds",
    ]);
    expect(
      gestorSettingsSections({
        channelsAttention: "",
        canManageCustomers: false,
      }).map((s) => s.key),
    ).not.toContain("checklists");
  });
});

// O trocador e a barra de baixo do celular (modelo de navegação; dono, 03/11/2026: "seção
// vai para baixo", aba no topo é só subdivisão). As seções do chão vão para o polegar.
describe("gestorSwitcherSections (trocador e barra de baixo)", () => {
  const input = {
    channelsAttention: "",
    canManageCustomers: true,
    canOperateChecklists: true,
  };
  const all = () => gestorSwitcherSections(gestorSections(input), gestorSettingsSections(input));

  it("lista tudo na ordem do app, sem o item Ajustes, cada seção com a sua forma", () => {
    expect(all().map((s) => `${s.key}:${s.form}`)).toEqual([
      "orders:floor",
      "exit:floor",
      "checklists:floor",
      "history:office",
      "catalog:office",
      "customers:office",
      "feeds:office",
    ]);
  });

  it("a barra de baixo do chão: Pedidos, Saída e Rotinas, sem 'Mais' (o selo abre o resto)", () => {
    const floor = all().filter((s) => s.form === "floor");
    const layout = quickBarLayout(floor);
    expect(layout.items.map((s) => s.label)).toEqual(["Pedidos", "Saída", "Rotinas"]);
    expect(layout.more).toBe(false);
    expect(quickBarProblems(floor)).toEqual([]);
    expect(all().filter((s) => s.quick).map((s) => s.key)).toEqual(["orders", "exit", "checklists"]);
  });

  it("sem a permissão de Rotinas, o chão fica com Pedidos e Saída", () => {
    const sections = gestorSwitcherSections(
      gestorSections({ ...input, canOperateChecklists: false }),
      gestorSettingsSections({ ...input, canOperateChecklists: false }),
    );
    expect(sections.filter((s) => s.form === "floor").map((s) => s.key)).toEqual(["orders", "exit"]);
  });

  it("antes de montar (Ajustes ainda sem resposta) o chão já tem Pedidos e Saída", () => {
    expect(
      gestorSwitcherSections(gestorSections(input), []).map((s) => s.key),
    ).toEqual(["orders", "exit"]);
  });
});
