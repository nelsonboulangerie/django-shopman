import { expect, test, type Page } from "@playwright/test";

import { captureOperatorEvidence, expectOperatorLabelsFit } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

const form = {
  customer_types: [
    { value: "individual", label: "Pessoa física" },
    { value: "business", label: "Pessoa jurídica" },
  ],
  price_tiers: [
    { value: "PADRAO", label: "Padrão" },
    { value: "ATACADO", label: "Atacado" },
  ],
};

const row = {
  ref: "CLI-MARIA",
  name: "Maria Aparecida Souza",
  phone_display: "(43) 99999-0101",
  email: "maria@example.com",
  document_display: "123.456.789-09",
  source_label: "Cadastro manual",
  is_ifood: false,
  orders_label: "18 pedidos",
  last_order_display: "ontem",
  duplicate_hint: "",
};

const detail = {
  ...row,
  is_active: true,
  merged_into_ref: "",
  birthday_display: "12/05/1988",
  created_display: "há 2 anos",
  notes: "Prefere contato depois das 10h.",
  total_spent_display: "R$ 1.842,30",
  identifiers: [{ type_label: "WhatsApp", value: "+5543999990101" }],
  consents: [{
    channel_label: "WhatsApp", purpose_label: "Marketing geral", status_label: "Opt-in",
    allowed: true, proof_label: "Verificado", source: "checkout", updated_display: "14/10/2026 às 18:20",
  }],
  addresses: [{
    id: 7, revision: "2026-10-14T21:00:00Z", label: "Casa", label_code: "home",
    formatted_address: "Rua das Flores, 10 — Centro, Londrina — PR", route: "Rua das Flores",
    street_number: "10", complement: "Fundos", neighborhood: "Centro", city: "Londrina",
    state_code: "PR", postal_code: "86000-000", delivery_instructions: "Portão azul",
    is_default: true, is_verified: true,
  }],
  recent_orders: [{
    ref: "WEB-261014-A01", channel_label: "Loja online", status_label: "Entregue",
    ordered_at_display: "ontem às 16:42", total_display: "R$ 86,40",
  }],
  candidates: [],
  actions: [{ ref: "merge_preview" }],
  revision: "2026-10-14T21:00:00Z",
  first_name: "Maria Aparecida",
  last_name: "Souza",
  customer_type: "individual",
  document: "12345678909",
  birthday: "1988-05-12",
  phone: "+5543999990101",
  price_tier_ref: "PADRAO",
  price_tier_name: "Padrão",
  tags: ["vizinha", "encomendas"],
  house_account: true,
  house_account_limit: "500,00",
  fiscal_cpf_na_nota: true,
  fiscal_email_receipt: true,
  form,
};

async function mockCustomers(page: Page) {
  await page.route("**/api/v1/backstage/customers/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/backstage/customers/") {
      await route.fulfill({ json: { list: {
        query: "", filter: "all", filters: [
          { ref: "all", label: "Todos", active: true },
          { ref: "possible_duplicates", label: "Possíveis duplicados", active: false },
          { ref: "ifood", label: "Vindos do iFood", active: false },
          { ref: "no_phone", label: "Sem telefone", active: false },
        ],
        items: [row], page: 1, page_size: 30, total: 1, has_next: false,
        total_label: "1 cliente", sort: "recent", form,
      } } });
      return;
    }
    if (url.pathname === "/api/v1/backstage/customers/CLI-MARIA/") {
      await route.fulfill({ json: { customer: detail } });
      return;
    }
    await route.fallback();
  });
}

async function pageAction(page: Page, name: string) {
  // A barra da mesa pode reaparecer um instante depois de fechar um painel; esperar
  // pela ação antes de cair no ⋯ evita o clique no menu que só existe no celular.
  const direct = page.getByRole("button", { name, exact: true }).filter({ visible: true });
  try {
    await direct.first().waitFor({ state: "visible", timeout: 5000 });
    await direct.first().click();
    return;
  } catch {
    // Sem a ação na barra da mesa: ela mora no ⋯ da barra do topo (celular).
  }
  await page.locator("[data-page-header-more]").click();
  await page.getByRole("menuitem", { name, exact: true }).click();
}

for (const viewport of selectedOperatorViewports()) {
  test(`clientes CRUD · ${viewport.id}`, async ({ page }, testInfo) => {
    await page.setViewportSize({
      width: Math.round(viewport.width / (viewport.zoom || 1)),
      height: Math.round(viewport.height / (viewport.zoom || 1)),
    });
    await mockCustomers(page);

    await page.goto("/customers");
    await expect(page.getByText("Maria Aparecida Souza", { exact: true })).toBeVisible();
    await pageAction(page, "Cadastrar cliente");
    await expect(page.getByRole("heading", { name: "Cadastrar cliente", exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `cadastrar cliente ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customers-create", route: "/customers", scenario: "form",
      state: "normal", theme: "light", viewport,
    // O casco canônico é rolável: o scanner global interpreta campos legítimos
    // abaixo da dobra como fora do viewport. A trava deste estado é de rótulos,
    // recorte e sobreposição; a geometria da página fechada já pertence ao kit.
    }, { fullPage: false, scan: false });
    await page.keyboard.press("Escape");

    // Seleção + barra de lote: etiquetar a seleção numa ida e exportar o CSV.
    await page.locator("[data-operator-table-select]").first().click();
    await expect(
      page.locator("[data-operator-bulk-action]").filter({ visible: true }).first(),
    ).toBeVisible();
    await expectOperatorLabelsFit(page, `seleção de clientes ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customers-bulk", route: "/customers", scenario: "selection",
      state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
    await page.locator('[data-operator-bulk-action="Etiquetar…"]').filter({ visible: true }).click();
    await expect(page.getByRole("heading", { name: "Etiquetas em lote", exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `etiquetas em lote ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customers-bulk-tags", route: "/customers", scenario: "form",
      state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
    await page.keyboard.press("Escape");

    await page.goto("/customers/CLI-MARIA");
    await expect(page.getByText("Consentimentos", { exact: true })).toBeVisible();
    await pageAction(page, "Editar cliente");
    await expect(page.getByRole("heading", { name: "Editar Maria Aparecida Souza", exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `editar cliente ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customers-edit", route: "/customers/CLI-MARIA", scenario: "form",
      state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
    await page.keyboard.press("Escape");

    await pageAction(page, "Duplicar cliente");
    await expect(page.getByRole("heading", { name: "Duplicar cliente", exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `duplicar cliente ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customers-duplicate", route: "/customers/CLI-MARIA", scenario: "form",
      state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Adicionar", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Adicionar endereço", exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `adicionar endereço ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customers-address", route: "/customers/CLI-MARIA", scenario: "form",
      state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
  });
}
