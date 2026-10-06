import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("catálogo vivo", () => {
  const page = readFileSync(
    new URL("../catalog/OperatorKitCatalogPage.vue", import.meta.url),
    "utf8",
  );
  const source = readFileSync(
    new URL("../app/components/OperatorKitchenSink.vue", import.meta.url),
    "utf8",
  );
  const fixtures = readFileSync(
    new URL("../app/fixtures/operatorKitchenSink.ts", import.meta.url),
    "utf8",
  );
  const officeShell = readFileSync(
    new URL("../app/components/OperatorOfficeShell.vue", import.meta.url),
    "utf8",
  );
  const config = readFileSync(
    new URL("../nuxt.config.ts", import.meta.url),
    "utf8",
  );

  it("demonstra layouts completos e famílias oficiais", () => {
    for (const component of [
      "OperatorOfficeShell",
      "OperatorOperationalShell",
      "NuxtNavigationMenu",
      "OperatorPage",
      "OperatorSplitter",
      "NuxtForm",
      "NuxtTable",
      "NuxtModal",
      "NuxtStepper",
      "NuxtCheckbox",
      "NuxtSwitch",
      "NuxtSkeleton",
      "NuxtEmpty",
      "NuxtAlert",
    ])
      expect(source, component).toContain(component);
    for (const component of [
      "NuxtDashboardGroup",
      "NuxtDashboardSidebar",
      "NuxtDashboardPanel",
      "NuxtDashboardNavbar",
      "NuxtDashboardToolbar",
    ]) {
      expect(officeShell, component).toContain(component);
    }
  });

  it("não reintroduz navegação independente dentro do dashboard nem formulário decorativo", () => {
    expect(source).not.toContain("<NuxtSidebar");
    expect(source).not.toContain(':state="{}"');
    expect(source).toContain(':validate="validateForm"');
    expect(source).toContain('name="name"');
    expect(officeShell).not.toContain('role="presentation"');
    expect(officeShell).toContain("NuxtDashboardSidebarCollapse");
  });

  it("mantém a implementação no kit e a página do harness como composição", () => {
    expect(page).toContain("<OperatorKitchenSink />");
    expect(page).not.toContain("NuxtCard");
    expect(fixtures).toContain("kitchenSinkNeeds");
    expect(fixtures).toContain("kitchenSinkExceptions");
  });

  it("expõe os estados operacionais pedidos como cenários determinísticos", () => {
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
      "extreme-content",
    ]) {
      expect(fixtures, state).toContain(`value: "${state}"`);
      expect(source, state).toContain(`activeState === '${state}'`);
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
