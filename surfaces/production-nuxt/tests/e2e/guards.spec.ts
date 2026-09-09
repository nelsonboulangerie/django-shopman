import { test, expect } from "@playwright/test";

// Gate de operador (Opção C, Camada 1) e roteamento — o mock ramifica pelo cookie
// `e2e_session` que o BFF encaminha. Login efetivo/lock com dados reais = reviewer local.

const authed = {
  name: "e2e_session",
  value: "authed",
  domain: "127.0.0.1",
  path: "/",
};

test.describe("Produção — gate de operador", () => {
  test("device não autenticado → tela de login (sem sessão)", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Entre para operar" }),
    ).toBeVisible();
    await expect(page.getByLabel("Usuário")).toBeVisible();
    await expect(page.getByLabel("Senha")).toBeVisible();
    await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  });

  test("sessão autenticada → grade + rail canônico (kit), sem login", async ({
    page,
    context,
  }) => {
    await context.addCookies([authed]);
    await page.goto("/");
    await expect(page.getByText("Nada planejado para produzir")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Entre para operar" }),
    ).toHaveCount(0);
    // Tela de operador embrulhada pelo OperatorRail compartilhado + RailToggle no cabeçalho.
    await expect(
      page.locator('aside[aria-label="Barra do app Produção"]'),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /barra/i })).toBeVisible();
  });
});

test.describe("Produção — menuboard paralelo aposentado", () => {
  test("/menuboard nega a rota e nunca consulta o storefront", async ({
    page,
  }) => {
    const storefrontRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/storefront/"))
        storefrontRequests.push(request.url());
    });

    const response = await page.goto("/menuboard");
    expect(response?.status()).toBe(404);
    expect(storefrontRequests).toEqual([]);
  });
});

test.describe("Produção — borda HTTP", () => {
  test("documento e BFF são privados, não enquadráveis e preservam cookie/Vary", async ({
    request,
  }) => {
    const document = await request.get("/", {
      headers: { "x-forwarded-proto": "https" },
    });
    expect(document.headers()["content-security-policy"]).toContain(
      "frame-ancestors 'none'",
    );
    expect(document.headers()["content-security-policy"]).toContain(
      "object-src 'none'",
    );
    expect(document.headers()["x-frame-options"]).toBe("DENY");
    expect(document.headers()["x-content-type-options"]).toBe("nosniff");
    expect(document.headers()["referrer-policy"]).toBe("no-referrer");
    expect(document.headers()["strict-transport-security"]).toMatch(
      /^max-age=31536000/,
    );
    expect(document.headers()["cache-control"]).toContain("private");
    expect(document.headers()["cache-control"]).toContain("no-store");

    const session = await request.get("/api/v1/backstage/operator/session/");
    expect(session.status()).toBe(403);
    expect(session.headers()["cache-control"]).toContain("private");
    expect(session.headers()["cache-control"]).toContain("no-store");
    expect(session.headers().vary).toContain("Cookie");
    expect(session.headers().vary).toContain("Accept-Language");
    expect(session.headers()["set-cookie"]).toContain("csrftoken=e2e-mock");
  });
});

test.describe("Produção — roteamento", () => {
  test("rota inexistente responde 404", async ({ page, context }) => {
    await context.addCookies([authed]);
    const resp = await page.goto("/rota-que-nao-existe");
    expect(resp?.status()).toBe(404);
  });
});
