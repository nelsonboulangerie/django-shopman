import { expect, test, type Page } from "@playwright/test";

import { captureOperatorEvidence, expectOperatorLabelsFit } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

const form = {
  channels: [
    { value: "pdv", label: "Balcão" },
    { value: "web", label: "Loja online" },
  ],
  listings: [{ value: "parceiros", label: "Tabela parceiros · parceiros" }],
  collections: [
    { value: "finos", label: "Finos" },
    { value: "torneira", label: "Torneira" },
  ],
  discount_types: [
    { value: "", label: "Sem desconto" },
    { value: "percent", label: "Percentual em cada item" },
    { value: "fixed", label: "Valor em reais por pedido" },
  ],
};

const group = {
  ref: "alianca-francesa",
  name: "Aliança Francesa",
  description: "Condição comercial para alunos e equipe da escola parceira.",
  listing_ref: "",
  listing_name: "",
  priority: 20,
  is_default: false,
  customer_count: 42,
  customer_count_label: "42 clientes",
  discount_type: "percent",
  discount_value: "15",
  discount_label: "15% em cada item",
  channel_refs: ["pdv", "web"],
  channels_label: "Balcão, Loja online",
  pickup_only: false,
  discount_kind: "parceiro",
  rounding: true,
  savings_message: "Hoje você economizou {amount} por ser {group}",
  advantages: [
    {
      kind: "free_shipping",
      kind_label: "Frete grátis",
      is_active: true,
      priority: 3,
      summary_label: "Frete grátis em pedidos a partir de R$ 80,00",
      min_order_q: 8000,
      min_order_display: "R$ 80,00",
      collection_refs: [],
      campaign_refs: [],
    },
    {
      kind: "exclusive_collections",
      kind_label: "Coleções exclusivas",
      is_active: true,
      priority: 0,
      summary_label: "1 coleção exclusiva",
      min_order_q: 0,
      min_order_display: "",
      collection_refs: ["finos"],
      campaign_refs: [],
    },
    {
      kind: "exclusive_notifications",
      kind_label: "Notificações exclusivas",
      is_active: false,
      priority: 0,
      summary_label: "Nenhum aviso exclusivo escolhido",
      min_order_q: 0,
      min_order_display: "",
      collection_refs: [],
      campaign_refs: [],
    },
  ],
  revision: "2026-10-14T22:00:00Z",
};

function customerRow(ref: string, name: string, groups: { ref: string; name: string }[]) {
  return {
    ref, name, phone_display: "(43) 99999-0101", email: "", document_display: "",
    source_label: "", is_ifood: false, orders_label: "3 pedidos", last_order_display: "",
    duplicate_hint: "",
    groups: groups.map((item, index) => ({ ...item, is_primary: index === 0 })),
  };
}

async function mockGroups(page: Page) {
  await page.route("**/api/v1/backstage/customers/groups/**", async (route) => {
    await route.fulfill({ json: { groups: {
      items: [group], total: 1, total_label: "1 grupo", form,
    } } });
  });
  // A busca do "Adicionar clientes" usa a mesma lista de clientes.
  await page.route((url) => url.pathname === "/api/v1/backstage/customers/", async (route) => {
    const varejo = { ref: "varejo", name: "Varejo" };
    await route.fulfill({ json: { list: {
      query: "", filter: "all", group: "", filters: [],
      items: [
        customerRow("CLI-ANA", "Ana Beatriz Lima", [varejo]),
        customerRow("CLI-BRUNO", "Bruno Carvalho", [{ ref: "alianca-francesa", name: "Aliança Francesa" }, varejo]),
        customerRow("CLI-CARLA", "Carla Nogueira", [varejo]),
      ],
      page: 1, page_size: 30, total: 3, has_next: false, total_label: "3 clientes", sort: "recent",
      form: { customer_types: [], price_tiers: [] },
    } } });
  });
}

async function pageAction(page: Page, name: string) {
  const direct = page.getByRole("button", { name, exact: true }).filter({ visible: true });
  if (await direct.count()) {
    await direct.first().click();
    return;
  }
  await page.locator("[data-page-header-more]").click();
  await page.getByRole("menuitem", { name, exact: true }).click();
}

/**
 * Nenhuma chamada da tela pode terminar em erro. Um 4xx/5xx aqui vira "lista vazia"
 * na captura, e a evidência passaria mostrando uma tela que não carregou.
 */
function trackHttpFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failures.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });
  return failures;
}

for (const viewport of selectedOperatorViewports()) {
  test(`grupos de clientes CRUD · ${viewport.id}`, async ({ page }, testInfo) => {
    const httpFailures = trackHttpFailures(page);
    await page.setViewportSize({
      width: Math.round(viewport.width / (viewport.zoom || 1)),
      height: Math.round(viewport.height / (viewport.zoom || 1)),
    });
    await mockGroups(page);
    await page.goto("/customers/groups");
    await expect(page.getByText("Aliança Francesa", { exact: true })).toBeVisible();
    await expect(page.getByText("15% em cada item", { exact: true })).toBeVisible();

    await pageAction(page, "Criar grupo");
    await expect(page.getByRole("heading", { name: "Criar grupo de clientes", exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `criar grupo ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customer-groups-create", route: "/customers/groups",
      scenario: "form", state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Adicionar clientes ao grupo Aliança Francesa", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Adicionar clientes ao grupo Aliança Francesa", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Já está no grupo", { exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `adicionar clientes ao grupo ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customer-groups-add-members", route: "/customers/groups",
      scenario: "form", state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Editar", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Editar Aliança Francesa", exact: true })).toBeVisible();
    await expect(page.getByText("Hoje você economizou R$ 12,50 por ser Aliança Francesa", { exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `editar grupo ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customer-groups-edit", route: "/customers/groups",
      scenario: "form", state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });

    // As vantagens tipadas ficam abaixo da dobra: a evidência precisa mostrá-las.
    await page.locator('[data-focus-target="advantages"]').scrollIntoViewIfNeeded();
    await expect(page.getByText("Pedido mínimo (R$)", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Avisos que só este grupo recebe. Quem escolhe os avisos é o Marketing.", { exact: true }),
    ).toBeVisible();
    await expectOperatorLabelsFit(page, `vantagens do grupo ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customer-groups-advantages", route: "/customers/groups",
      scenario: "form", state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });

    expect(httpFailures).toEqual([]);
  });
}
