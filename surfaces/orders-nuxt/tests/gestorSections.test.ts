import { describe, expect, it } from "vitest";

import { activeSectionKey } from "../../operator-kit/app/presentation/appBar";
import {
  quickBarLayout,
  quickBarProblems,
} from "../../operator-kit/app/presentation/suiteChrome";
import {
  gestorRoutePermission,
  gestorSections,
  gestorSettingsSections,
  deniedSettingsSection,
  gestorSwitcherSections,
  SETTINGS_ROUTES,
} from "../app/presentation/gestorSections";

// O rail do Gestor em dois andares (D, 13/11/2026): a operação em cima (Pedidos e, para
// quem cuida do catálogo, Canais) e Ajustes no pé. As seções que saíram do rail moram em Ajustes, a um toque.
describe("gestorSections (rail)", () => {
  it("a operação em cima, com o rótulo do grupo; Ajustes no pé", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    expect(sections.map((s) => s.key)).toEqual(["orders", "history", "settings"]);
    expect(
      sections.filter((s) => s.group === "Operação").map((s) => s.key),
    ).toEqual(["orders", "history"]);
    expect(sections.find((s) => s.key === "settings")?.foot).toBe(true);
  });

  it("Pedidos abre o quadro como o posto deixou; não há seção Saída", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
    });
    expect(sections.find((s) => s.key === "orders")?.to).toBe("/");
    expect(sections.find((s) => s.key === "exit")).toBeUndefined();
  });

  it("Catálogo e Canais sobem para a operação de quem cuida do catálogo, com o ponto em Canais", () => {
    const sections = gestorSections({
      channelsAttention: "1 desligado",
      canManageCustomers: false,
      canManageCatalog: true,
    });
    expect(
      sections.filter((s) => s.group === "Operação").map((s) => s.key),
    ).toEqual(["orders", "history", "catalog", "feeds"]);
    expect(sections.find((s) => s.key === "feeds")?.attention).toBe("1 desligado");
    expect(activeSectionKey("/catalog", sections)).toBe("catalog");
    expect(activeSectionKey("/history", sections)).toBe("history");
    // O ponto não se repete em Ajustes, e Canais acende Canais, não Ajustes.
    expect(sections.find((s) => s.key === "settings")?.attention).toBeUndefined();
    expect(activeSectionKey("/feeds", sections)).toBe("feeds");
    expect(activeSectionKey("/channels/ifood/catalog", sections)).toBe("feeds");
  });

  it("quem só expede (SUITE-UX §15) fica só com a operação", () => {
    const keys = gestorSections({
      channelsAttention: "1 desligado",
      canManageCustomers: true,
      expeditesOnly: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["orders"]);
  });

  it("quem só expede entra direto no balcão de saída", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
      expeditesOnly: true,
    });
    expect(sections.find((s) => s.key === "orders")?.to).toBe("/?columns=expedition");
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
      intakeCount: 0,
    });
    expect(sections.find((s) => s.key === "orders")?.badge).toBeUndefined();
    expect(
      gestorSections({ channelsAttention: "", canManageCustomers: false, intakeCount: 2 })
        .find((s) => s.key === "orders"),
    ).toMatchObject({ badge: "2" });
  });

  it("barra inferior: as seções declaradas, sem erro de regra", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    expect(quickBarLayout(sections).items.map((s) => s.key)).toEqual([
      "orders",
      "settings",
    ]);
    expect(quickBarProblems(sections)).toEqual([]);
  });

  it("estar numa seção de Ajustes acende o item Ajustes", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    for (const path of [
      "/customers/groups",
      "/customers/merges",
      "/workstations",
      "/settings",
    ]) {
      expect(activeSectionKey(path, sections)).toBe("settings");
    }
    expect(activeSectionKey("/", sections)).toBe("orders");
    expect(SETTINGS_ROUTES).toContain("/customers");
  });
});

describe("gestorSettingsSections (andar Ajustes)", () => {
  it("Clientes aparece para quem pode gerir clientes (Histórico, Catálogo e Canais moram no rail)", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: true,
      canManageCatalog: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["customers"]);
  });

  it("sem a permissão (ou sem resposta ainda) a linha não existe", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: false,
      canManageCatalog: true,
    }).map((s) => s.key);
    expect(keys).toEqual([]);
  });

  it("Canais não se repete em Ajustes: mora no rail", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "1 desligado",
      canManageCustomers: false,
      canManageCatalog: true,
    }).map((s) => s.key);
    expect(keys).not.toContain("feeds");
  });

  it("Postos aparece por último, só para quem gere operadores", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: false,
      canManageCatalog: true,
      canManageWorkstations: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["workstations"]);
    expect(
      gestorSettingsSections({
        channelsAttention: "",
        canManageCustomers: false,
      }).map((s) => s.key),
    ).not.toContain("workstations");
  });

  it("Rotinas não mora mais no Gestor: foram para o PDV", () => {
    expect(
      gestorSettingsSections({ channelsAttention: "", canManageCustomers: true }).map((s) => s.key),
    ).not.toContain("checklists");
    expect(SETTINGS_ROUTES).not.toContain("/checklists");
  });
});

// O trocador e a barra de baixo do celular (modelo de navegação; dono, 03/11/2026: "seção
// vai para baixo", aba no topo é só subdivisão). As seções do chão vão para o polegar.
describe("gestorSwitcherSections (trocador e barra de baixo)", () => {
  const input = {
    channelsAttention: "",
    canManageCustomers: true,
    canManageCatalog: true,
  };
  const all = () => gestorSwitcherSections(gestorSections(input), gestorSettingsSections(input));

  it("lista tudo na ordem do app, sem o item Ajustes, cada seção com a sua forma", () => {
    expect(all().map((s) => `${s.key}:${s.form}`)).toEqual([
      "orders:floor",
      "history:floor",
      "catalog:floor",
      "feeds:floor",
      "customers:office",
    ]);
  });

  it("a barra de baixo do chão: a operação inteira", () => {
    const floor = all().filter((s) => s.form === "floor");
    expect(quickBarLayout(floor).items.map((s) => s.label)).toEqual(["Pedidos", "Histórico", "Catálogo", "Canais"]);
    expect(quickBarProblems(floor)).toEqual([]);
    expect(all().filter((s) => s.quick).map((s) => s.key)).toEqual(["orders", "history", "catalog", "feeds"]);
  });

  it("sem Catálogo, o chão fica com Pedidos e Histórico", () => {
    const sections = gestorSwitcherSections(
      gestorSections({ ...input, canManageCatalog: false }),
      gestorSettingsSections({ ...input, canManageCatalog: false }),
    );
    expect(sections.filter((s) => s.form === "floor").map((s) => s.key)).toEqual(["orders", "history"]);
  });

  it("antes de montar (Ajustes ainda sem resposta) o trocador já tem a operação inteira", () => {
    expect(
      gestorSwitcherSections(gestorSections(input), []).map((s) => s.key),
    ).toEqual(["orders", "history", "catalog", "feeds"]);
  });
});

// Beta 05/11 (CEN-05, GES-17): a Caixa via Catálogo e Canais em Ajustes e, ao abrir,
// "Sem conexão" com "Tentar de novo"; o servidor respondia 403 a cada minuto.
describe("Ajustes só lista o que a conta abre", () => {
  it("sem shop.manage_catalog, Catálogo e Canais saem de Ajustes", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: true,
      canManageCatalog: false,
    }).map((s) => s.key);
    expect(keys).not.toContain("catalog");
    expect(keys).not.toContain("feeds");
    expect(keys).toContain("customers");
  });

  it("cada tela de Ajustes diz a permissão dela e o nome para a recusa", () => {
    expect(gestorRoutePermission("/catalog")).toEqual({ perm: "shop.manage_catalog", what: "o Catálogo" });
    expect(gestorRoutePermission("/channels/ifood")?.perm).toBe("shop.manage_catalog");
    expect(gestorRoutePermission("/customers/CLI-003")?.perm).toBe("shop.manage_customers");
    expect(gestorRoutePermission("/history")?.perm).toBe("shop.manage_orders");
    expect(gestorRoutePermission("/workstations")?.perm).toBe("cashman.manage_operators");
    // O quadro e Ajustes são do Gestor inteiro: a antessala já respondeu por eles.
    expect(gestorRoutePermission("/")).toBeNull();
    expect(gestorRoutePermission("/settings")).toBeNull();
    expect(gestorRoutePermission("/catalogue")).toBeNull();
  });

  it("toda rota de Ajustes tem permissão declarada", () => {
    for (const route of SETTINGS_ROUTES) expect(gestorRoutePermission(route), route).not.toBeNull();
  });
});

// Beta 05/11 (GES-08): o Caixa via Catálogo e Canais e, ao entrar, lia "Sem conexão".
describe("Catálogo e Canais só para quem cuida do catálogo", () => {
  it("sem shop.manage_catalog (ou sem resposta) as duas linhas não existem", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: false,
    }).map((s) => s.key);
    expect(keys).toEqual([]);
    expect(
      gestorSections({ channelsAttention: "", canManageCustomers: false }).map((s) => s.key),
    ).not.toContain("catalog");
  });

  it("a URL direta fora do acesso diz o nome da seção; dentro dele, nada", () => {
    const semCatalogo = { channelsAttention: "", canManageCustomers: false };
    const caixa = [...gestorSections(semCatalogo), ...gestorSettingsSections(semCatalogo)];
    expect(deniedSettingsSection("/catalog", caixa)).toBe("o Catálogo");
    expect(deniedSettingsSection("/channels/web/catalog", caixa)).toBe("os Canais");
    expect(deniedSettingsSection("/feeds", caixa)).toBe("os Canais");
    expect(deniedSettingsSection("/customers/groups", caixa)).toBe("os Clientes");
    expect(deniedSettingsSection("/workstations", caixa)).toBe("os Postos");
    expect(deniedSettingsSection("/history", caixa)).toBe("");
    expect(deniedSettingsSection("/", caixa)).toBe("");
    expect(deniedSettingsSection("/WEB-261105-K38", caixa)).toBe("");
    const access = {
      channelsAttention: "",
      canManageCustomers: true,
      canManageCatalog: true,
      canManageWorkstations: true,
    };
    // Canais saiu de Ajustes para o rail: a recusa olha as duas listas, como a página.
    const gerente = [...gestorSections(access), ...gestorSettingsSections(access)];
    for (const path of ["/catalog", "/channels/web/catalog", "/feeds", "/customers", "/workstations"])
      expect(deniedSettingsSection(path, gerente)).toBe("");
  });
});
