import { expect, test, type Page } from "@playwright/test";

type Viewport = { width: number; height: number; label: string };
type Theme = "light" | "dark";

const V320: Viewport = { width: 320, height: 568, label: "320x568" };
const V375: Viewport = { width: 375, height: 812, label: "375x812" };
const V390: Viewport = { width: 390, height: 844, label: "390x844" };
const V768: Viewport = { width: 768, height: 1024, label: "768x1024" };
const V1024: Viewport = { width: 1024, height: 768, label: "1024x768" };
const V1280: Viewport = { width: 1280, height: 800, label: "1280x800" };
const V1440: Viewport = { width: 1440, height: 900, label: "1440x900" };

async function openScenario(
  page: Page,
  scenario: string,
  path: string,
  viewport: Viewport,
  theme: Theme = "light",
) {
  await page.setViewportSize(viewport);
  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: scenario,
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.addInitScript(
    ({ selectedTheme, now }) => {
      localStorage.setItem("marketing-nuxt-color-mode", selectedTheme);
      Date.now = () => now;
    },
    { selectedTheme: theme, now: Date.parse("2026-09-10T13:30:00Z") },
  );
  await page.emulateMedia({
    colorScheme: theme,
    reducedMotion: "reduce",
  });
  await page.goto(path, { waitUntil: "domcontentloaded" });
  // Dev assets can compile on first request while another worktree is using the
  // local CPU. The visual assertion remains exact; only bootstrap gets room to
  // finish instead of turning machine contention into a false UI regression.
  await expect(page.getByRole("main")).toBeVisible({ timeout: 30_000 });
  await page.waitForFunction(() =>
    document.querySelector("#__nuxt")?.hasAttribute("data-v-app"),
  );
}

async function expectStableScreenshot(
  page: Page,
  name: string,
  viewport: Viewport,
  theme: Theme = "light",
  options: { fullPage?: boolean } = {},
) {
  await expect(page).toHaveScreenshot(
    [`${name}__${viewport.label}__${theme}.png`],
    { fullPage: options.fullPage ?? true },
  );
  const width = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(width.scroll, `${name}: overflow horizontal`).toBeLessThanOrEqual(
    width.client + 1,
  );
}

async function waitForFaithfulPreview(page: Page) {
  await expect(
    page.getByText("Exemplo com Pão artesanal").first(),
  ).toBeVisible();
}

async function seedDraft(
  page: Page,
  resource: string,
  baseVersion: string,
  base: Record<string, unknown>,
  payload: Record<string, unknown>,
) {
  await page.addInitScript(
    ({ draftResource, version, draftBase, draftPayload, now }) => {
      const owner = "operator:7";
      const key = `shopman.marketing.draft.v1:${encodeURIComponent(owner)}:${encodeURIComponent(draftResource)}`;
      localStorage.setItem(
        key,
        JSON.stringify({
          schema: 1,
          owner,
          resource: draftResource,
          baseVersion: version,
          base: draftBase,
          payload: draftPayload,
          savedAt: now - 60_000,
          expiresAt: now + 7 * 24 * 60 * 60 * 1_000,
        }),
      );
    },
    {
      draftResource: resource,
      version: baseVersion,
      draftBase: base,
      draftPayload: payload,
      now: Date.parse("2026-09-10T13:30:00Z"),
    },
  );
}

test.describe("gate global", () => {
  test("entrada anônima e erro de credenciais em 320", async ({ page }) => {
    await openScenario(page, "login-invalid", "/", V320);
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toBeVisible();
    await page.getByLabel("Usuário").fill("operadora-visual");
    await page.getByLabel("Senha").fill("senha-incorreta");
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByRole("alert")).toContainText("Usuário ou senha incorretos");
    await expectStableScreenshot(page, "login__anonymous-invalid", V320);
  });

  test("entrada anônima em desktop", async ({ page }) => {
    await openScenario(page, "login-anonymous", "/", V1280);
    await expectStableScreenshot(page, "login__anonymous", V1280);
  });

  test("acesso proibido não recomenda novo login", async ({ page }) => {
    await openScenario(page, "login-forbidden", "/", V1280);
    await expect(page.getByRole("heading", { name: "Seu acesso não inclui Marketing" })).toBeVisible();
    await expect(page.getByText("Entrar novamente não amplia permissões")).toBeVisible();
    await expectStableScreenshot(page, "login__forbidden", V1280);
  });

  test("falha de sessão mantém o app fechado", async ({ page }) => {
    await openScenario(page, "login-offline", "/", V390);
    await expect(page.getByText("nenhum dado de Marketing foi carregado")).toBeVisible();
    await expectStableScreenshot(page, "login__offline", V390);
  });

  test("teclado mantém foco e ação visíveis", async ({ page }) => {
    await openScenario(page, "login-anonymous", "/", V390);
    await page.getByLabel("Senha").focus();
    await expect(page.getByLabel("Senha")).toBeFocused();
    await expectStableScreenshot(page, "login__keyboard-focus", V390);
  });

  test("limite de tentativas dá espera acionável", async ({ page }) => {
    await openScenario(page, "login-rate-limited", "/", V390);
    await page.getByLabel("Usuário").fill("operadora-visual");
    await page.getByLabel("Senha").fill("senha-incorreta");
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByRole("alert")).toContainText("Aguarde um minuto");
    await expectStableScreenshot(page, "login__rate-limited", V390);
  });

  test("sessão expirada explica que o rascunho foi preservado", async ({ page }) => {
    await seedDraft(
      page,
      "announcement:41",
      "2",
      { body: "Texto anterior" },
      { body: "Rascunho preservado" },
    );
    await openScenario(page, "login-expired", "/", V1280);
    await expect(page.getByRole("heading", { name: "Sua sessão terminou" })).toBeVisible();
    await expect(page.getByText(/rascunho.*preservados/i)).toBeVisible();
    await expectStableScreenshot(page, "login__expired-with-draft", V1280);
  });
});

test.describe("painel", () => {
  for (const [scenario, state, viewport] of [
    ["board-pending", "pending", V320],
    ["board-degraded", "degraded", V390],
    ["board-empty", "empty", V768],
    ["board-normal", "normal", V1280],
  ] as const) {
    test(`${state} em ${viewport.label}`, async ({ page }) => {
      await openScenario(page, scenario, "/", viewport);
      await expect(page.getByRole("heading", { level: 1, name: "Painel" })).toBeVisible();
      if (scenario !== "board-empty" && scenario !== "board-normal")
        await waitForFaithfulPreview(page);
      await expectStableScreenshot(page, `panel__${state}`, viewport);
    });
  }

  test("SSE desconectado fica explícito na caixa de alertas", async ({ page }) => {
    await openScenario(page, "notifications-dedupe", "/", V1440);
    await page.getByRole("button", { name: /^Alertas:/ }).click();
    await expect(page.getByRole("dialog", { name: "Alertas pessoais" })).toContainText("reconectando");
    await expectStableScreenshot(page, "panel__sse-disconnected", V1440);
  });
});

test.describe("cartão de anúncio", () => {
  test("edição longa não perde ações no menor mobile", async ({ page }) => {
    await openScenario(page, "board-pending", "/", V320);
    await waitForFaithfulPreview(page);
    const body = page.getByLabel("Texto do anúncio");
    await body.fill(
      "A fornada artesanal acabou de sair 👩🏽‍🍳🥖✨. أهلاً وسهلاً · ברוכים הבאים. " +
        "Reserve pelo site para retirar hoje: " +
        "https://example.invalid/produtos/pao-artesanal-com-um-caminho-muito-longo-sem-quebras-nem-rastreamento",
    );
    const hashtags = page.getByLabel("Hashtags");
    await hashtags.fill(
      "#padaria #fornada #artesanal #bairro #hoje #quentinho #pao #familia #local #novidade",
    );
    await body.evaluate((element) => {
      const field = element as HTMLTextAreaElement;
      field.setSelectionRange(0, 0);
      field.scrollTop = 0;
      field.blur();
    });
    await hashtags.evaluate((element) => {
      const field = element as HTMLInputElement;
      field.setSelectionRange(0, 0);
      field.scrollLeft = 0;
      field.blur();
    });
    await expectStableScreenshot(page, "announcement-card__long-edit", V320);
  });

  test("entregar agora abre confirmação factual", async ({ page }) => {
    await openScenario(page, "board-pending", "/", V390);
    await waitForFaithfulPreview(page);
    await page.getByRole("button", { name: "Entregar agora" }).click();
    await expect(page.getByRole("dialog")).toContainText("12");
    await expectStableScreenshot(page, "announcement-card__confirm-now", V390, "light", { fullPage: false });
  });

  test("conflito de rascunho compara as duas versões", async ({ page }) => {
    const base = {
      body: "Texto antigo do servidor",
      hashtags: ["padaria"],
      image_url: "",
      platforms: ["instagram", "whatsapp"],
      publish_at: "",
    };
    await seedDraft(page, "announcement:41", "2", base, {
      ...base,
      body: "Minha edição local para a fornada",
    });
    await openScenario(page, "board-pending", "/", V768);
    await expect(page.getByText("Este conteúdo também mudou em outra sessão.")).toBeVisible();
    await expect(page.getByText(/Dados conferidos às/)).toBeVisible();
    await expectStableScreenshot(page, "announcement-card__draft-conflict", V768);
  });

  test("prévia de plataforma permanece ao lado da decisão", async ({ page }) => {
    await openScenario(page, "board-pending", "/", V1280);
    await expect(page.getByText("Prévia fiel")).toBeVisible();
    await expect(page.getByText(/Dados conferidos às/)).toBeVisible();
    await expectStableScreenshot(page, "announcement-card__platform-preview", V1280);
  });
});

test.describe("listas operacionais", () => {
  test("campanhas no menor mobile", async ({ page }) => {
    await openScenario(page, "campaigns-dense", "/campaigns", V320);
    await expectStableScreenshot(page, "campaigns__list", V320);
  });

  test("campanhas com filtros persistidos", async ({ page }) => {
    await openScenario(
      page,
      "campaigns-filters",
      "/campaigns?state=inactive&platform=facebook&q=artesanal",
      V390,
    );
    await expect(page.getByRole("heading", { level: 2, name: "Encontrar uma campanha" })).toBeVisible();
    await expect(page.getByLabel("Situação")).toHaveValue("inactive");
    await expectStableScreenshot(page, "campaigns__filters", V390);
  });

  test("campanhas densas paginam sem ocultar estado", async ({ page }) => {
    await openScenario(page, "campaigns-dense", "/campaigns", V1280);
    await expect(page.getByRole("navigation", { name: "Páginas de campanhas" })).toBeVisible();
    await expectStableScreenshot(page, "campaigns__dense-paginated", V1280);
  });

  test("lista de campanhas realmente vazia", async ({ page }) => {
    await openScenario(page, "campaigns-empty", "/campaigns", V1440);
    await expectStableScreenshot(page, "campaigns__empty", V1440);
  });

  test("nova campanha preserva formulário e CTA com foco", async ({ page }) => {
    await openScenario(page, "campaigns-dense", "/campaigns", V320);
    await page.getByRole("button", { name: "Nova campanha" }).click();
    await page.getByLabel("Nome da campanha").focus();
    await expectStableScreenshot(page, "campaign-form__new-keyboard", V320, "light", { fullPage: false });
  });

  test("edição longa mostra schema completo", async ({ page }) => {
    await openScenario(page, "campaigns-dense", "/campaigns", V390);
    await page.locator("main li").first().locator("button").nth(1).click();
    await expect(page.getByRole("dialog")).toContainText("Avisar quem");
    await expectStableScreenshot(page, "campaign-form__long-rules", V390, "light", { fullPage: false });
  });

  test("intervalo recorrente inválido explica o campo", async ({ page }) => {
    await openScenario(page, "campaigns-dense", "/campaigns", V768);
    await page.getByRole("button", { name: "Nova campanha" }).click();
    await page.getByLabel("Quando acontecer").selectOption("schedule");
    await page.getByLabel("Começar em (opcional)").fill("2026-12-31");
    await page.getByLabel("Parar depois de (opcional)").fill("2026-01-01");
    await expect(page.getByRole("alert")).toContainText("data final");
    await expectStableScreenshot(page, "campaign-form__validation", V768, "light", { fullPage: false });
  });

  test("edição completa em desktop", async ({ page }) => {
    await openScenario(page, "campaigns-dense", "/campaigns", V1280);
    await page.locator("main li").first().locator("button").nth(1).click();
    await waitForFaithfulPreview(page);
    await expectStableScreenshot(page, "campaign-form__edit-full", V1280, "light", { fullPage: false });
  });

  test("conflito de campanha mostra diff antes de decidir", async ({ page }) => {
    const base = {
      name: "Nome anterior",
      trigger: "production_finished",
      template_id: 1,
      platforms: ["instagram", "whatsapp"],
      requires_approval: true,
      expires_after_minutes: 90,
      promotion_ref: "",
      is_active: true,
      audience_rules: { tags: ["clientes-da-casa"] },
    };
    await seedDraft(page, "campaign:1", "2026-09-09T09:40:00-03:00", base, {
      ...base,
      name: "Minha campanha local",
    });
    await openScenario(page, "campaigns-dense", "/campaigns", V1440);
    await page.locator("main li").first().locator("button").nth(1).click();
    await expect(page.getByText("Este conteúdo também mudou em outra sessão.")).toBeVisible();
    await expectStableScreenshot(page, "campaign-form__conflict-diff", V1440, "light", { fullPage: false });
  });

  test("falha de modelos não parece lista vazia", async ({ page }) => {
    await openScenario(page, "templates-outage", "/templates", V390);
    await expect(page.getByRole("alert")).toContainText("não significa que ela esteja vazia");
    await expectStableScreenshot(page, "templates__outage", V390);
  });

  test("modelo mostra dependências antes de apagar", async ({ page }) => {
    await openScenario(page, "templates-dependency", "/templates", V1280);
    await page.getByRole("button", { name: "Apagar o modelo Novidades da padaria" }).click();
    await expect(page.getByRole("dialog")).toContainText("está em uso");
    await expectStableScreenshot(page, "templates__dependency-blocked", V1280, "light", { fullPage: false });
  });

  test("edição de modelo cabe no menor mobile", async ({ page }) => {
    await openScenario(page, "templates-list", "/templates", V320);
    await page.locator("main ul li").first().locator("button").first().click();
    await expectStableScreenshot(page, "templates__edit", V320, "light", { fullPage: false });
  });

  test("documentação de variável fica no contexto", async ({ page }) => {
    await openScenario(page, "templates-list", "/templates", V390);
    await page.getByRole("button", { name: "Novo modelo" }).click();
    await expect(page.getByText("Variáveis disponíveis")).toBeVisible();
    await expectStableScreenshot(page, "templates__placeholder-help", V390, "light", { fullPage: false });
  });

  test("variantes reais aparecem no formulário", async ({ page }) => {
    await openScenario(page, "templates-list", "/templates", V768);
    await page.locator("main ul li").first().locator("button").first().click();
    await expectStableScreenshot(page, "templates__platform-variant", V768, "light", { fullPage: false });
  });

  test("lista de modelos realmente vazia", async ({ page }) => {
    await openScenario(page, "templates-empty", "/templates", V1440);
    await expectStableScreenshot(page, "templates__empty", V1440);
  });

  test("falha de plataformas não parece ausência de configuração", async ({ page }) => {
    await openScenario(page, "platforms-outage", "/platforms", V390);
    await expect(page.getByRole("alert")).toContainText("indisponibilidade de leitura");
    await expectStableScreenshot(page, "platforms__outage", V390);
  });

  test("plataforma pronta em desktop", async ({ page }) => {
    await openScenario(page, "platforms-ready", "/platforms", V1280);
    await expectStableScreenshot(page, "platforms__ready", V1280);
  });

  test("plataforma bloqueada explica reparo no mobile", async ({ page }) => {
    await openScenario(page, "platforms-blocked", "/platforms", V320);
    await page.locator("main ul li").first().locator("button").click();
    await expectStableScreenshot(page, "platforms__blocked", V320, "light", { fullPage: false });
  });

  test("teste sandbox preserva comprovante", async ({ page }) => {
    await openScenario(page, "platforms-ready", "/platforms", V768);
    await page.getByRole("button", { name: /WhatsApp/ }).click();
    await page.getByRole("button", { name: "Enviar teste" }).click();
    await expect(page.getByText(/Comprovante visual-test-receipt/)).toBeVisible();
    await expectStableScreenshot(page, "platforms__test-receipt", V768, "light", { fullPage: false });
  });

  test("conflito de configuração mantém consequência visível", async ({ page }) => {
    await openScenario(page, "platforms-conflict", "/platforms", V1440);
    await page.getByRole("button", { name: /WhatsApp/ }).click();
    await page.getByRole("button", { name: /Aviso de fornada — versão revisada/ }).click();
    const code = page.getByRole("group", {
      name: "Código de 6 dígitos do autenticador",
    });
    for (const [index, digit] of Array.from("123456").entries()) {
      await code.getByLabel(`Dígito ${index + 1} de 6`).fill(digit);
    }
    await page.getByRole("button", { name: "Salvar configuração" }).click();
    await expect(page.getByText(/mudou em outra sessão/)).toBeVisible();
    await expectStableScreenshot(page, "platforms__configuration-conflict", V1440, "light", { fullPage: false });
  });
});

test.describe("disparo manual seguro", () => {
  for (const [scenario, state, viewport] of [
    ["fire-zero", "zero-audience", V320],
    ["fire-normal", "confirmation-readiness", V390],
    ["fire-degraded", "degraded-audience", V768],
    ["fire-large", "large-audience", V1280],
  ] as const) {
    test(`${state}`, async ({ page }) => {
      await openScenario(page, scenario, "/campaigns", viewport);
      await page.getByRole("button", { name: /Disparar a campanha Fornada artesanal 01.*agora/ }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.waitForTimeout(450);
      if (scenario === "fire-large") {
        await expect(page.getByRole("dialog").getByText("1.999", { exact: true })).toBeVisible();
      }
      await page.getByRole("dialog").locator('button[type="submit"]').scrollIntoViewIfNeeded();
      await expectStableScreenshot(page, `fire-campaign__${state}`, viewport, "light", { fullPage: false });
    });
  }

  test("contagem em andamento mantém o CTA bloqueado", async ({ page }) => {
    await openScenario(page, "fire-loading", "/campaigns", V390);
    await page.getByRole("button", { name: /Disparar a campanha Fornada artesanal 01.*agora/ }).click();
    await page.waitForTimeout(400);
    await expect(page.getByText("Contando…")).toBeVisible();
    await expect(page.getByRole("dialog").locator('button[type="submit"]')).toBeDisabled();
    await expectStableScreenshot(page, "fire-campaign__count-loading", V390, "light", { fullPage: false });
  });

  test("confirmação mostra a consequência calculada pelo servidor", async ({ page }) => {
    await openScenario(page, "fire-normal", "/campaigns", V390);
    await page.getByRole("button", { name: /Disparar a campanha Fornada artesanal 01.*agora/ }).click();
    await page.waitForTimeout(450);
    await page.getByRole("button", { name: "Disparar agora" }).click();
    await expect(page.getByRole("heading", { name: "Confirmar este disparo?" })).toBeVisible();
    await expect(page.getByText(/cria somente um anúncio para revisão/i)).toBeVisible();
    await expectStableScreenshot(page, "fire-campaign__confirmation", V390, "light", { fullPage: false });
  });

  test("throttle explica a espera sem perder o painel", async ({ page }) => {
    await openScenario(page, "fire-throttled", "/campaigns", V768);
    await page.getByRole("button", { name: /Disparar a campanha Fornada artesanal 01.*agora/ }).click();
    await page.waitForTimeout(450);
    await page.getByRole("button", { name: "Disparar agora" }).click();
    await expect(page.getByRole("alert")).toContainText("em cerca de 20 minutos");
    await expect(page.getByRole("alert")).toContainText("Nada foi criado");
    await expectStableScreenshot(page, "fire-campaign__throttled", V768, "light", { fullPage: false });
  });

  test("conflito atualiza a versão e mantém recuperação inline", async ({ page }) => {
    await openScenario(page, "fire-conflict", "/campaigns", V1024);
    await page.getByRole("button", { name: /Disparar a campanha Fornada artesanal 01.*agora/ }).click();
    await page.waitForTimeout(450);
    await page.getByRole("button", { name: "Disparar agora" }).click();
    await page.getByLabel("Sua senha").fill("senha-visual");
    await page.getByLabel("Digite exatamente").fill("PUBLICAR 48");
    await page.getByRole("button", { name: "Criar para revisão" }).click();
    await expect(page.getByLabel("Disparar agora").getByRole("alert")).toContainText("mudou em outra sessão");
    await expectStableScreenshot(page, "fire-campaign__conflict", V1024, "light", { fullPage: false });
  });

  test("aceite mantém comprovante e próximo passo no mesmo painel", async ({ page }) => {
    await openScenario(page, "fire-accepted", "/campaigns", V1440);
    await page.getByRole("button", { name: /Disparar a campanha Fornada artesanal 01.*agora/ }).click();
    await page.waitForTimeout(450);
    await page.getByRole("button", { name: "Disparar agora" }).click();
    await page.getByLabel("Sua senha").fill("senha-visual");
    await page.getByLabel("Digite exatamente").fill("PUBLICAR 48");
    await page.getByRole("button", { name: "Criar para revisão" }).click();
    await expect(page.getByRole("heading", { name: "Anúncio criado para revisão" })).toBeVisible();
    await expect(page.getByText("visual-fire-receipt-20260910")).toBeVisible();
    await expect(page.getByText(/Nenhuma publicação ou mensagem foi enviada/)).toBeVisible();
    await expectStableScreenshot(page, "fire-campaign__receipt", V1440, "light", { fullPage: false });
  });
});

test.describe("resultado e histórico", () => {
  for (const [scenario, state, viewport] of [
    ["detail-403", "forbidden", V320],
    ["detail-expired", "expired", V390],
    ["detail-partial", "partial", V768],
    ["detail-pending", "pending", V1280],
    ["detail-unknown", "unknown-reconcile", V1440],
  ] as const) {
    test(`detalhe ${state}`, async ({ page }) => {
      await openScenario(page, scenario, "/announcements/41", viewport);
      if (scenario === "detail-pending") await waitForFaithfulPreview(page);
      await expectStableScreenshot(page, `announcement__${state}`, viewport);
    });
  }

  for (const [scenario, state, viewport] of [
    ["history-filters", "filters", V320],
    ["history-partial", "partial", V390],
    ["history-pagination", "pagination", V768],
    ["history-normal", "normal", V1280],
    ["history-unknown", "unknown", V1440],
  ] as const) {
    test(`histórico ${state}`, async ({ page }) => {
      await openScenario(page, scenario, "/history", viewport);
      await expectStableScreenshot(page, `history__${state}`, viewport);
    });
  }
});

test.describe("alertas pessoais", () => {
  for (const [scenario, state, viewport] of [
    ["notifications-unseen", "sheet", V320],
    ["notifications-unseen", "action", V390],
    ["notifications-dedupe", "dedupe", V768],
    ["notifications-unseen", "popover", V1280],
    ["notifications-stale", "stale-action", V375],
  ] as const) {
    test(`${state} em ${viewport.label}`, async ({ page }) => {
      await openScenario(page, scenario, "/", viewport);
      await waitForFaithfulPreview(page);
      await page.getByRole("button", { name: /^Alertas:/ }).click();
      const dialog = page.getByRole("dialog", { name: "Alertas pessoais" });
      await expect(dialog).toBeVisible();
      if (scenario === "notifications-stale") {
        await expect(dialog.getByRole("button", { name: "Revisar anúncio" })).toBeDisabled();
        await expect(dialog).toContainText("já foi decidido");
      }
      await expectStableScreenshot(page, `notifications__${state}`, viewport, "light", { fullPage: false });
    });
  }
});

test.describe("erros globais", () => {
  test("offline em 320", async ({ page, context }) => {
    await openScenario(page, "board-normal", "/__visual_error/500", V320);
    await context.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event("offline")));
    await expect(page.getByRole("heading", { name: "Você está sem conexão" })).toBeVisible();
    await expectStableScreenshot(page, "global-error__offline", V320, "light", { fullPage: false });
  });

  test("404 verdadeiro em 390", async ({ page }) => {
    await openScenario(page, "board-normal", "/__visual_error/404", V390);
    await expect(page.getByRole("heading", { name: "Esta página não existe" })).toBeVisible();
    await expectStableScreenshot(page, "global-error__404", V390, "light", { fullPage: false });
  });

  test("500 preserva referência segura em 1280", async ({ page }) => {
    await openScenario(page, "board-normal", "/__visual_error/500", V1280);
    await expect(page.getByText("visual-mkt046-request")).toBeVisible();
    await expectStableScreenshot(page, "global-error__500", V1280, "light", { fullPage: false });
  });

  test("manutenção se distingue de falha genérica", async ({ page }) => {
    await openScenario(page, "board-normal", "/__visual_error/503", V1024);
    await expect(page.getByRole("heading", { name: "Marketing temporariamente indisponível" })).toBeVisible();
    await expectStableScreenshot(page, "global-error__maintenance", V1024, "light", { fullPage: false });
  });

  test("contrato incompatível não recomenda novo login", async ({ page }) => {
    await openScenario(page, "board-normal", "/__visual_error/426", V375);
    await expect(page.getByRole("heading", { name: "Esta versão precisa ser atualizada" })).toBeVisible();
    await expectStableScreenshot(page, "global-error__unsupported-contract", V375, "light", { fullPage: false });
  });
});

test.describe("modos transversais", () => {
  test("tema escuro", async ({ page }) => {
    await openScenario(page, "board-normal", "/", V390, "dark");
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expectStableScreenshot(page, "panel__normal", V390, "dark");
  });

  test("equivalente a zoom 200% sem perder ação", async ({ page }) => {
    const zoom = { width: 640, height: 800, label: "zoom-200" };
    await openScenario(page, "platforms-blocked", "/platforms", zoom);
    await expectStableScreenshot(page, "platforms__blocked", zoom, "light", { fullPage: false });
  });

  test("foco visível com cores forçadas", async ({ page }) => {
    await openScenario(page, "board-normal", "/", V390);
    await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
    const campaigns = page.getByRole("link", { name: "Campanhas", exact: true });
    await campaigns.focus();
    await expect(campaigns).toBeFocused();
    await expectStableScreenshot(page, "panel__focus-forced-colors", V390);
  });

  test("espaçamento de texto WCAG preserva conteúdo e ações", async ({ page }) => {
    await openScenario(page, "board-pending", "/", V1024);
    await waitForFaithfulPreview(page);
    await page.addStyleTag({
      content: `
        * { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; }
        p { margin-bottom: 2em !important; }
      `,
    });
    await expect(page.getByRole("button", { name: "Entregar agora" })).toBeVisible();
    await expectStableScreenshot(page, "panel__text-spacing", V1024);
  });
});
