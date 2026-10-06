import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("catálogo vivo", () => {
  const source = readFileSync(new URL("../catalog/OperatorKitCatalogPage.vue", import.meta.url), "utf8");
  const officeShell = readFileSync(new URL("../app/components/OperatorOfficeShell.vue", import.meta.url), "utf8");
  const config = readFileSync(new URL("../nuxt.config.ts", import.meta.url), "utf8");

  it("demonstra layouts completos e famílias oficiais", () => {
    for (const component of [
      "OperatorOfficeShell",
      "OperatorOperationalShell",
      "NuxtSidebar",
      "NuxtNavigationMenu",
      "OperatorPage",
      "OperatorSplitter",
      "NuxtForm",
      "NuxtTable",
      "UiModal",
      "NuxtSkeleton",
      "NuxtEmpty",
      "NuxtAlert",
    ]) expect(source, component).toContain(component);
    for (const component of ["NuxtDashboardGroup", "NuxtDashboardSidebar", "NuxtDashboardPanel", "NuxtDashboardNavbar", "NuxtDashboardToolbar"]) {
      expect(officeShell, component).toContain(component);
    }
  });

  it("só registra a rota sob a env do harness", () => {
    expect(config).toContain('process.env.OPERATOR_KIT_CATALOG === "1"');
    expect(config).toContain('path: "/__operator_kit_catalog"');
  });

  it("mantém uma instância dos runtimes globais entre a layer e o app", () => {
    expect(config).toContain('dedupe: ["reka-ui", "vue-sonner"]');
  });
});
