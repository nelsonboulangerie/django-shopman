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
  ORDERS_EXIT_POST,
  orderDetailDenial,
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
    expect(sections.map((s) => s.key)).toEqual(["orders", "deliveries", "history", "customers", "settings"]);
    expect(
      sections.filter((s) => s.group === "Operação").map((s) => s.key),
    ).toEqual(["orders", "deliveries", "history", "customers"]);
    expect(sections.find((s) => s.key === "settings")?.foot).toBe(true);
  });

  it("Pedidos abre o painel como o posto deixou; não há seção Saída", () => {
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
    ).toEqual(["orders", "deliveries", "history", "catalog", "feeds"]);
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
    expect(keys).toEqual(["orders", "deliveries"]);
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

  it("os selos contam o que o painel vê; zero não é selo", () => {
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
      "deliveries",
      "settings",
    ]);
    expect(quickBarProblems(sections)).toEqual([]);
  });

  it("estar numa seção de Ajustes acende o item Ajustes", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    for (const path of ["/workstations", "/settings"]) {
      expect(activeSectionKey(path, sections)).toBe("settings");
    }
    expect(activeSectionKey("/", sections)).toBe("orders");
    expect(sections.find((s) => s.key === "settings")?.match).not.toContain("/customers");
  });

  // Dono, 16/11/2026 ("Sobe"): Clientes é o que o gerente procura quando um cliente
  // liga no meio do turno.
  it("Clientes sobe para a operação, logo depois de Histórico, com o ícone de sempre", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
      canManageCatalog: true,
    });
    expect(
      sections.filter((s) => s.group === "Operação").map((s) => s.label),
    ).toEqual(["Pedidos", "Entregas", "Histórico", "Clientes", "Catálogo", "Canais"]);
    expect(sections.find((s) => s.key === "customers")).toMatchObject({
      label: "Clientes",
      icon: "lucide:users",
      to: "/customers",
      group: "Operação",
    });
    expect(sections.find((s) => s.key === "customers")?.foot).toBeUndefined();
  });

  it("em /customers e subrotas o item ativo é Clientes, não Ajustes", () => {
    const sections = gestorSections({
      channelsAttention: "",
      canManageCustomers: true,
    });
    for (const path of ["/customers", "/customers/groups", "/customers/merges", "/customers/CLI-003"]) {
      expect(activeSectionKey(path, sections), path).toBe("customers");
    }
    // A recusa pela URL direta continua conhecendo a rota.
    expect(SETTINGS_ROUTES).toContain("/customers");
  });

  it("sem shop.manage_customers (ou sem resposta ainda) Clientes não aparece no rail", () => {
    const keys = gestorSections({
      channelsAttention: "",
      canManageCustomers: false,
      canManageCatalog: true,
    }).map((s) => s.key);
    expect(keys).not.toContain("customers");
    expect(keys).toEqual(["orders", "deliveries", "history", "catalog", "feeds", "settings"]);
  });
});

describe("gestorSettingsSections (andar Ajustes)", () => {
  it("Clientes saiu de Ajustes: mora no rail, como Histórico, Catálogo e Canais", () => {
    const keys = gestorSettingsSections({
      channelsAttention: "",
      canManageCustomers: true,
      canManageCatalog: true,
      canManageWorkstations: true,
    }).map((s) => s.key);
    expect(keys).toEqual(["workstations"]);
    expect(keys).not.toContain("customers");
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
      "deliveries:floor",
      "history:floor",
      "customers:office",
      "catalog:floor",
      "feeds:floor",
    ]);
    // Nada duplicado entre o rail e Ajustes.
    expect(all().filter((s) => s.key === "customers")).toHaveLength(1);
  });

  it("a barra de baixo do chão: a operação inteira", () => {
    const floor = all().filter((s) => s.form === "floor");
    expect(quickBarLayout(floor).items.map((s) => s.label)).toEqual(["Pedidos", "Entregas", "Histórico", "Catálogo", "Canais"]);
    expect(quickBarProblems(floor)).toEqual([]);
    expect(all().filter((s) => s.quick).map((s) => s.key)).toEqual(["orders", "deliveries", "history", "catalog", "feeds"]);
  });

  it("sem Catálogo, o chão fica com Pedidos e Histórico", () => {
    const sections = gestorSwitcherSections(
      gestorSections({ ...input, canManageCatalog: false }),
      gestorSettingsSections({ ...input, canManageCatalog: false }),
    );
    expect(sections.filter((s) => s.form === "floor").map((s) => s.key)).toEqual(["orders", "deliveries", "history"]);
  });

  it("antes de montar (Ajustes ainda sem resposta) o trocador já tem a operação inteira", () => {
    expect(
      gestorSwitcherSections(gestorSections(input), []).map((s) => s.key),
    ).toEqual(["orders", "deliveries", "history", "customers", "catalog", "feeds"]);
  });
});

// Beta 05/11 (CEN-05, GES-17): a Caixa via Catálogo e Canais em Ajustes e, ao abrir,
// "Sem conexão" com "Tentar de novo"; o servidor respondia 403 a cada minuto.
describe("Ajustes só lista o que a conta abre", () => {
  it("sem shop.manage_catalog, Catálogo e Canais saem de Ajustes e do rail", () => {
    const access = { channelsAttention: "", canManageCustomers: true, canManageCatalog: false };
    const keys = [...gestorSections(access), ...gestorSettingsSections(access)].map((s) => s.key);
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
    // O painel e Ajustes são do Gestor inteiro: a antessala já respondeu por eles.
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

// P1-20: o 403 do detalhe do pedido tem texto próprio. Quem só expede chega pelo sino.
describe("orderDetailDenial", () => {
  it("quem só expede lê por que não abre e volta para a Saída", () => {
    const denial = orderDetailDenial("S84", { expeditesOnly: true });
    expect(denial.title).toBe("Sua conta não abre o detalhe do pedido");
    expect(denial.description).toBe(
      "O detalhe do pedido S84 é de quem gerencia pedidos. Os pedidos prontos para sair ficam no painel da Saída, onde você marca a saída e a retirada.",
    );
    expect(denial.back).toEqual({ label: "Abrir a Saída", to: ORDERS_EXIT_POST });
    // A recusa não sabe o estado do pedido: não afirma onde ele está (#2879).
    expect(denial.description).not.toMatch(/continua/);
  });

  it("outra conta sem a permissão pede o acesso e volta para onde ela entra", () => {
    const denial = orderDetailDenial("S84", { landingPath: "/catalog" });
    expect(denial.description).toBe("O detalhe é de quem gerencia pedidos. Peça o acesso a um gerente.");
    expect(denial.back).toEqual({ label: "Voltar ao Gestor", to: "/catalog" });
  });

  it("nenhuma das frases diz que o pedido não foi encontrado, nem usa travessão", () => {
    for (const denial of [orderDetailDenial("S84", { expeditesOnly: true }), orderDetailDenial("S84")]) {
      const text = `${denial.title} ${denial.description} ${denial.back.label}`;
      expect(text).not.toMatch(/não encontrado|[—–]/);
    }
  });
});
