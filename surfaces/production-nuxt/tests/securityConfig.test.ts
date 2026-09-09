import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(surfaceRoot, "../..");

function read(path: string): string {
  return readFileSync(resolve(repositoryRoot, path), "utf8");
}

describe("Produção — configuração segura de release", () => {
  it("aposenta o menuboard paralelo sem manter fetch ou bypass público", () => {
    expect(existsSync(resolve(surfaceRoot, "app/pages/menuboard.vue"))).toBe(false);
    const shell = read("surfaces/production-nuxt/app/app.vue");
    expect(shell).not.toContain("isPublicBoard");
    expect(shell).not.toContain("/storefront/menu/");
    expect(read("surfaces/production-nuxt/public/robots.txt")).toContain("Disallow: /");
  });

  it("ativa headers e fail-fast no runtime privado do Produção", () => {
    const config = read("surfaces/production-nuxt/nuxt.config.ts");
    expect(config).toContain("djangoBaseUrl = configuredDjangoBaseUrl()");
    expect(config).toContain("operatorSecurityHeaders: true");
    expect(config).toContain("operatorUpstreamFailFast: true");
    expect(config).not.toContain("NUXT_PUBLIC_DJANGO_BASE_URL");
  });

  it("mantém build de imagem inerte e exige opt-in duplo no harness local", () => {
    const dockerfile = read("surfaces/Dockerfile.surface");
    expect(dockerfile).toContain('"${SURFACE}" = "production-nuxt"');
    expect(dockerfile).toContain("https://django-upstream.invalid");
    expect(dockerfile).not.toContain("https://api.boulangerie.com.br");

    const harness = read("scripts/run_omotenashi_browser_ci.sh");
    expect(harness).toContain("SHOPMAN_ENVIRONMENT=test");
    expect(harness).toContain("SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM=1");
    expect(harness).toContain('NUXT_DJANGO_BASE_URL="${DJANGO_BASE_URL}"');
  });
});
