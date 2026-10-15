import { expect, test, type Page } from "@playwright/test";

import { captureOperatorEvidence, expectOperatorLabelsFit } from "../../../operator-kit/visual/playwright";
import { selectedOperatorViewports } from "../../../operator-kit/visual/matrix";

const form = {
  channels: [
    { value: "pdv", label: "Balcão" },
    { value: "web", label: "Loja online" },
  ],
  listings: [{ value: "parceiros", label: "Tabela parceiros · parceiros" }],
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
  revision: "2026-10-14T22:00:00Z",
};

async function mockGroups(page: Page) {
  await page.route("**/api/v1/backstage/customers/groups/**", async (route) => {
    await route.fulfill({ json: { groups: {
      items: [group], total: 1, total_label: "1 grupo", form,
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

for (const viewport of selectedOperatorViewports()) {
  test(`grupos de clientes CRUD · ${viewport.id}`, async ({ page }, testInfo) => {
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

    await page.getByRole("button", { name: "Editar", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Editar Aliança Francesa", exact: true })).toBeVisible();
    await expect(page.getByText("Hoje você economizou R$ 12,50 por ser Aliança Francesa", { exact: true })).toBeVisible();
    await expectOperatorLabelsFit(page, `editar grupo ${viewport.id}`);
    await captureOperatorEvidence(page, testInfo, {
      app: "orders", surface: "customer-groups-edit", route: "/customers/groups",
      scenario: "form", state: "normal", theme: "light", viewport,
    }, { fullPage: false, scan: false });
  });
}
