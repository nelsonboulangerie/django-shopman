import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../../operator-kit/visual/playwright";
import type { OperatorVisualViewport } from "../../../operator-kit/visual/matrix";

const AUDIT_STATE: Record<string, string> = {
  loading: "loading-initial",
  empty: "empty",
  error: "recoverable-error",
  offline: "offline",
  reconnecting: "reconnecting",
  "slow-network": "slow-network",
  readonly: "readonly",
  forbidden: "insufficient-permission",
  success: "success",
};

test("dashboard compõe contagens, gráficos, progresso, tabs e identidade", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(!["desktop-common", "mobile-narrow"].includes(viewport.id), "Receita rica em desktop e no limite mobile.");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator('[data-hydrated="true"]')).toBeAttached();
  await expect(page.getByRole("banner")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.getByRole("region", { name: "Atalhos do catálogo" }).locator('..')).toHaveCSS("background-color", "rgb(255, 255, 255)");
  const dashboard = page.locator("#dashboard-exercises");
  await expect(dashboard.locator('[data-operator-trend-chart] svg').first()).toBeVisible();
  await expect(dashboard.getByRole("table", { name: "Dados do gráfico de pedidos" })).toBeVisible();
  const progress = dashboard.getByRole("progressbar", { name: "Pedidos separados, 18 de 24" });
  await expect(progress).toHaveAttribute("aria-valuenow", "18");
  await dashboard.getByRole("button", { name: "Separar próximo", exact: true }).click();
  await expect(dashboard.getByRole("progressbar", { name: "Pedidos separados, 19 de 24" })).toHaveAttribute("aria-valuenow", "19");
  await dashboard.getByRole("switch", { name: "Mostrar em barras" }).click();
  await expect(dashboard.locator('[data-operator-trend-chart] svg').first()).toBeVisible();
  await dashboard.getByRole("tab", { name: /^Fila/ }).click();
  await dashboard.getByRole("button", { name: "Revisar NB-1048", exact: true }).click();
  const detail = page.getByRole("dialog", { name: "NB-1048" });
  await expect(detail).toBeVisible();
  await expect(detail).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await detail.getByRole("button", { name: "Voltar à fila" }).click();
  await dashboard.getByRole("tab", { name: /^Equipe/ }).click();
  await expect(dashboard.getByText("Ana Ferreira", { exact: true })).toBeVisible();
  await expect(dashboard.getByText("Em pausa", { exact: true })).toBeVisible();
  await dashboard.getByRole("tab", { name: "Resumo", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(dashboard.getByRole("tab", { name: /^Fila/ })).toBeFocused();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(errors).toEqual([]);
});

test("toggle mobile abre e fecha navegação canônica", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "mobile-standard", "Contrato de sidebar mobile.");
  await page.goto("/");
  await expect(page.locator('[data-hydrated="true"]')).toBeAttached();
  await page.getByRole("button", { name: "Abrir barra lateral" }).click();
  const navigation = page.getByRole("navigation", { name: "Seções do catálogo" });
  await expect(navigation.getByRole("button", { name: "Dashboard, 3 decisões pendentes" })).toBeVisible();
  await navigation.getByRole("button", { name: "Estados", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByRole("banner")).toBeVisible();
});

test("captura canônica por viewport", async ({ page }, testInfo) => {
  const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport;
  const state =
    viewport.id === "zoom-200" ? "keyboard-focus" : viewport.touch ? "touch" : "normal";
  await page.goto("/");
  await expect(page.locator('[data-operator-catalog][data-hydrated="true"]')).toBeAttached();
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "kitchensink",
      surface: "home",
      route: "/",
      scenario: "normal",
      state,
      theme: "light",
      viewport,
    },
    { allowedFindings: [] },
  );
});

test("navegação, busca e feedback preservam o chrome do dashboard", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "desktop-common", "Contrato do dashboard desktop.");
  await page.goto("/?state=error");
  await expect(page.locator('[data-hydrated="true"]')).toBeAttached();
  const header = page.getByRole("banner");
  const before = await header.boundingBox();
  await page.getByRole("button", { name: "Recolher barra lateral" }).click();
  const references = page
    .getByRole("navigation", { name: "Referências aninhadas" })
    .getByRole("button", { name: "Referências", exact: true });
  await references.click();
  const nestedOption = page.getByRole("button", {
    name: "Matriz de necessidades",
    exact: true,
  });
  await expect(nestedOption).toBeVisible();
  await page.keyboard.press("Escape");
  await references.focus();
  await page.keyboard.press("Enter");
  await expect(nestedOption).toBeVisible();
  await nestedOption.click();
  expect((await header.boundingBox())!.y).toBe(before!.y);
  await expect(
    page.getByRole("heading", { name: "Catálogo do kit" }),
  ).toHaveClass("sr-only");
  await expect(
    page
      .getByRole("button", { name: "Guia de composição" })
      .locator('[data-slot="label"]'),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Expandir barra lateral" }).click();
  await expect(
    page
      .getByRole("button", { name: "Guia de composição" })
      .locator('[data-slot="label"]'),
  ).toHaveClass(/truncate/);
  await page.getByRole("button", { name: "Referências", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Matriz de necessidades", exact: true }),
  ).toBeVisible();
  const navigation = page.getByRole("navigation", {
    name: "Seções do catálogo",
  });
  await navigation
    .getByRole("button", { name: "Estados", exact: true })
    .click();
  await expect(
    navigation.getByRole("button", { name: "Estados", exact: true }),
  ).toHaveAttribute("data-active", "");
  expect((await header.boundingBox())!.y).toBe(before!.y);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  const alert = page
    .locator('#states [data-slot="root"]')
    .filter({ hasText: "Não foi possível atualizar" })
    .first();
  await expect(alert.locator('[data-slot="icon"]')).toBeVisible();
  await alert.getByRole("button").click();
  await expect(
    page.getByText("Não foi possível atualizar", { exact: true }),
  ).toBeHidden();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+k" : "Control+k");
  const search = page.getByRole("dialog", { name: "Buscar no catálogo" });
  await expect(search).toBeVisible();
  await expect(search).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await search
    .getByRole("textbox", { name: "Buscar seção..." })
    .fill("Receitas");
  await search.getByRole("option", { name: "Receitas" }).click();
  await expect(search).toBeHidden();
  expect((await header.boundingBox())!.y).toBe(before!.y);
  await page
    .getByRole("button", { name: "Mostrar toast", exact: true })
    .click();
  await expect(
    page.getByText("Confirmação local, sem envio ao servidor.", {
      exact: true,
    }),
  ).toBeVisible();
});

test("toque amplia alvo sem deformar switch e checkbox", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "mobile-standard", "Contrato de toque no celular.");
  await page.goto("/");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const control = page.getByRole("switch", { name: "Avisos desta tarefa" });
  await control.scrollIntoViewIfNeeded();
  const bounds = (await control.boundingBox())!;
  expect(bounds.height).toBeLessThanOrEqual(24);
  expect(bounds.width).toBeLessThanOrEqual(44);
  await page.mouse.click(
    bounds.x + bounds.width / 2,
    bounds.y + bounds.height / 2 + 18,
  );
  await expect(control).toHaveAttribute("aria-checked", "false");
  const checkbox = page.getByRole("checkbox", { name: "Exige revisão" });
  expect((await checkbox.boundingBox())!.width).toBeLessThanOrEqual(20);
});

test("shell operacional preserva ação, foco e navegação", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  await page.goto("/?mode=operational");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  await page
    .getByRole("button", { name: "Concluir etapa", exact: true })
    .click();
  await expect(
    page.getByText("Etapa concluída", { exact: true }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "kitchensink",
      surface: "home",
      route: "/?mode=operational",
      scenario: "operational-shell",
      state: "success",
      theme: "light",
      viewport,
    },
    { allowedFindings: [] },
  );
});

test("overlays, seleção e reordenação mantêm contratos oficiais", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    !["desktop-common", "mobile-narrow"].includes(viewport.id),
    "Interações em desktop e mobile.",
  );
  await page.goto("/");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const lateral = page.getByRole("button", {
    name: "Abrir detalhe lateral",
    exact: true,
  });
  await lateral.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await dialog
    .getByRole("textbox", { name: "Observação do pedido" })
    .fill("Retirada revisada");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(lateral).toBeFocused();
  const popover = page.getByRole("button", {
    name: "Abrir popover",
    exact: true,
  });
  await popover.click();
  await expect(
    page.getByText("Informação curta, contextual e não bloqueante.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(popover).toBeFocused();
  const down = page.getByRole("button", {
    name: "Descer PED-001",
    exact: true,
  });
  await down.click();
  await expect(
    page.getByRole("button", { name: "Subir PED-001", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Subir PED-001", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Subir PED-001", exact: true }),
  ).toBeDisabled();
});

test("tema escuro preserva contraste e geometria em todo o catálogo", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  await page.goto("/");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  await page.getByRole("button", { name: "Alternar tema" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "kitchensink",
      surface: "home",
      route: "/",
      scenario: "normal",
      state: "normal",
      theme: "dark",
      viewport,
    },
    { allowedFindings: [] },
  );
});

test("estados endereçáveis não escondem controles nem quebram acessibilidade", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    !["desktop-common", "mobile-narrow"].includes(viewport.id),
    "Estados completos em desktop e no limite mobile.",
  );
  for (const state of [
    "loading",
    "empty",
    "error",
    "offline",
    "reconnecting",
    "slow-network",
    "readonly",
    "forbidden",
    "success",
  ]) {
    await page.goto(`/?state=${state}`);
    await expect(
      page.locator(
        `[data-operator-catalog][data-hydrated="true"][data-scenario="${state}"]`,
      ),
    ).toBeAttached();
    await page.locator("#states").scrollIntoViewIfNeeded();
    expect(
      (await new AxeBuilder({ page }).include("#states").analyze()).violations,
      state,
    ).toEqual([]);
    await captureOperatorEvidence(
      page,
      testInfo,
      {
        app: "kitchensink",
        surface: "home",
        route: `/?state=${state}`,
        scenario: state,
        state: AUDIT_STATE[state] ?? state,
        theme: "light",
        viewport,
      },
      { allowedFindings: [] },
    );
  }
});

test("consumer real preserva SSR, hidratação, acessibilidade e geometria", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" || /hydration/i.test(message.text()))
      errors.push(message.text());
  });

  await page.goto("/?state=extreme-content");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "kitchensink",
      surface: "home",
      route: "/?state=extreme-content",
      scenario: "extreme-content",
      state: "extreme-content",
      theme: "light",
      viewport,
    },
    { allowedFindings: [] },
  );
  expect(errors).toEqual([]);
});

test("HTML SSR contém conteúdo útil sem JavaScript", async ({
  request,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(viewport.id !== "desktop-common", "SSR independe de viewport.");
  const response = await request.get("/?state=readonly");
  expect(response.ok()).toBe(true);
  const html = await response.text();
  expect(html).toContain("Anatomia canônica do operador");
  expect(html).toContain("Somente leitura");
  expect(html).toContain('data-hydrated="false"');
});

test("teclado percorre controles e modal devolve o foco", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    viewport.id !== "desktop-common",
    "Interação completa roda uma vez.",
  );
  await page.goto("/");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const trigger = page.getByRole("button", { name: "Abrir confirmação" });
  await trigger.focus();
  await expect(trigger).toBeFocused();
  await trigger.press("Enter");
  await expect(
    page.getByRole("dialog", { name: "Confirmar ação" }),
  ).toBeVisible();
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "kitchensink",
      surface: "home",
      route: "/",
      scenario: "modal",
      state: "modal",
      theme: "light",
      viewport,
    },
    { allowedFindings: [] },
  );
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("receitas interativas preservam dados, seleção, foco e tema", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    viewport.id !== "desktop-common",
    "Contratos interativos rodam uma vez.",
  );
  await page.goto("/");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const save = page.getByRole("button", {
    name: "Salvar exemplo",
    exact: true,
  });
  const nameBounds = await page
    .getByPlaceholder("Nome inequívoco")
    .boundingBox();
  const ownerBounds = await page
    .getByLabel("Responsável", { exact: true })
    .boundingBox();
  expect(Math.abs(nameBounds!.y - ownerBounds!.y)).toBeLessThanOrEqual(1);
  await expect(
    page.getByRole("switch", { name: "Avisos desta tarefa" }),
  ).toBeVisible();
  await expect(
    page.getByRole("switch", { name: "Avisos desta tarefa" }),
  ).toHaveAccessibleDescription(
    "Receba avisos quando esta tarefa mudar de estado.",
  );
  await page.getByRole("button", { name: "Salvar formulário" }).click();
  await expect(
    page.getByText("Informe o nome.", { exact: true }),
  ).toBeVisible();
  await page.getByPlaceholder("Nome inequívoco").fill("Pedido de teste");
  await page.getByRole("button", { name: "Salvar formulário" }).click();
  await expect(
    page.getByText("Formulário validado", { exact: true }),
  ).toBeVisible();
  const handle = page.locator('[data-operator-office-shell] > [data-slot="handle"]');
  await expect(handle).toHaveAttribute('aria-controls', /-sidebar-/);
  const beforeResize = await handle.boundingBox();
  await page.mouse.move(beforeResize!.x, beforeResize!.y + 100);
  await page.mouse.down();
  await page.mouse.move(beforeResize!.x + 40, beforeResize!.y + 100);
  await page.mouse.up();
  const afterResize = await handle.boundingBox();
  expect(afterResize!.x).toBeGreaterThan(beforeResize!.x + 20);
  // O handle nativo desenha a linha no pseudo-elemento `before`: o elemento tem
  // largura zero, então a ação por coordenadas exercita a mesma área que o
  // ponteiro usa. `locator.dblclick()` reprovaria por "não visível".
  await page.mouse.dblclick(afterResize!.x, afterResize!.y + 100);
  for (const label of ["Canal por select", "Buscar canal"]) {
    await page.getByLabel(label, { exact: true }).click();
    const option = page.getByRole("option").first();
    await expect(option).toBeVisible();
    expect(
      await option.evaluate(
        (element) => element.getBoundingClientRect().height,
      ),
    ).toBeGreaterThanOrEqual(44);
    await page.keyboard.press("Escape");
  }
  const tableRegion = page.getByRole("region", {
    name: "Tabela com rolagem externa",
  });
  expect(
    await tableRegion.evaluate(
      (element) => getComputedStyle(element.parentElement!).padding,
    ),
  ).toBe("0px");
  const lastDetails = tableRegion
    .getByRole("button", { name: /Detalhes de/ })
    .last();
  await lastDetails.click();
  const expandedDetails = tableRegion.getByText(/PED-\d+: retirada no balcão/);
  const detail = tableRegion.locator("[data-expanded-detail]");
  expect(
    await detail.evaluate((element) => getComputedStyle(element).whiteSpace),
  ).toBe("normal");
  expect(
    await detail.evaluate(
      (element) => getComputedStyle(element.parentElement!).paddingBottom,
    ),
  ).toBe("16px");
  await expandedDetails.scrollIntoViewIfNeeded();
  const bounds = await expandedDetails.boundingBox();
  const regionBounds = await tableRegion.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(
    regionBounds!.y + regionBounds!.height,
  );
  const columnFooter = tableRegion.locator("tfoot");
  expect(
    await columnFooter.evaluate(
      (element) => getComputedStyle(element).position,
    ),
  ).not.toBe("sticky");
  await lastDetails.click();
  await save.click();
  await expect(save).toBeDisabled();
  await page
    .getByRole("button", { name: "Concluir resposta simulada" })
    .click();
  await expect(save).toBeEnabled();
  await page.getByRole("textbox", { name: "Filtrar pedidos" }).fill("PED-001");
  const table = page
    .getByRole("region", { name: "Tabela com rolagem externa" })
    .getByRole("table");
  await expect(table.getByText("PED-001", { exact: true })).toBeVisible();
  await expect(table.getByText("PED-002", { exact: true })).toHaveCount(0);
  await table.getByRole("checkbox", { name: "Selecionar PED-001" }).check();
  await expect(
    page.getByText("1 selecionados.", { exact: false }),
  ).toBeVisible();
  await table.getByRole("button", { name: "Detalhes de PED-001" }).click();
  await expect(table.getByText("PED-001: retirada no balcão")).toBeVisible();
  await page.getByRole("button", { name: "Alternar tema" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
