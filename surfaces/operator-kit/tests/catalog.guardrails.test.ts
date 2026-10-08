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
  const suiteShell = readFileSync(
    new URL("../app/components/OperatorSuiteShell.vue", import.meta.url),
    "utf8",
  );
  const pwaRuntime = readFileSync(
    new URL("../app/components/OperatorPwaRuntime.vue", import.meta.url),
    "utf8",
  );
  const offlineBanner = readFileSync(
    new URL("../app/components/OfflineBanner.vue", import.meta.url),
    "utf8",
  );
  const appConfig = readFileSync(
    new URL("../app/app.config.ts", import.meta.url),
    "utf8",
  );
  const operatorBase = readFileSync(
    new URL("../app/assets/css/operator-base.css", import.meta.url),
    "utf8",
  );
  const config = readFileSync(
    new URL("../nuxt.config.ts", import.meta.url),
    "utf8",
  );

  it("demonstra layouts completos e famílias oficiais", () => {
    for (const component of [
      "OperatorOfficeShell",
      "OperatorSuiteShell",
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

  it("usa o painel full-bleed oficial no shell operacional e mantém o chrome fora da rolagem", () => {
    expect(officeShell).toContain('<NuxtDashboardPanel v-if="navbar"');
    expect(officeShell).toContain("<NuxtDashboardPanel v-else");
    expect(suiteShell).not.toContain('class="min-h-0 flex-1 overflow-y-auto"');
    // A barra inferior é o `OperatorQuickBar` (o exemplo oficial "With bottom tab bar").
    expect(suiteShell).toContain("<OperatorQuickBar");
    expect(suiteShell).toContain("data-suite-rail-footer");
    expect(suiteShell).toContain("flex-col items-center");
  });

  it("mantém a implementação no kit e a página do harness como composição", () => {
    expect(page).toContain("<OperatorKitchenSink />");
    expect(page).not.toContain("NuxtCard");
    expect(fixtures).toContain("kitchenSinkNeeds");
    expect(fixtures).toContain("kitchenSinkExceptions");
  });

  it("empilha avisos persistentes sem sobreposição e delega a anatomia ao Alert", () => {
    expect(pwaRuntime).toContain("data-operator-pwa-notices");
    expect(pwaRuntime).toContain("flex flex-col gap-2");
    expect(pwaRuntime).toContain("<OperatorPwaUpdatePrompt");
    expect(pwaRuntime).toContain("<OperatorPushInvite");
    expect(pwaRuntime).toContain(
      "bottom-[calc(var(--ui-header-height)+1rem+env(safe-area-inset-bottom))]",
    );
    expect(pwaRuntime).toContain(
      "lg:bottom-[calc(1.5rem+env(safe-area-inset-bottom))]",
    );
  });

  it("usa Banner para o anúncio global de perda de conexão", () => {
    expect(offlineBanner).toContain("<NuxtBanner");
    expect(offlineBanner).not.toContain("<NuxtAlert");
  });

  // DECISÃO MUDOU (WP-OPERADOR-NUXTUI-ONDAS, onda 0, 08/10/2026): esta trava proibia
  // qualquer `h-control` no tema, e consagrou a perda dos 44 px de campo, select e item
  // de lista nos sete apps não migrados e no catálogo. O kit muda por opt-in: a altura
  // de toque volta SÓ sob `suite-page:` (página que veste a suíte, ou o catálogo). O
  // que a trava protege continua: nada infla controle globalmente, e o Gestor, que não
  // veste o marcador, fica na geometria oficial.
  it("mantém a geometria oficial do Nuxt UI sem inflar controles globalmente", () => {
    // Classe que começa em `h-control`/`min-h-control` sem variante na frente.
    expect(appConfig).not.toMatch(/(?<![\w:-])(?:min-)?h-control\b/);
    expect(appConfig).toMatch(/suite-page:h-control/);
    expect(operatorBase).not.toMatch(/@media\s*\(pointer:\s*coarse\)/);
    expect(operatorBase).not.toContain(
      "min-block-size: var(--spacing-control)",
    );
    expect(operatorBase).not.toContain('[role="tab"]');
  });

  it("preserva a anatomia oficial e a densidade operacional única do Card", () => {
    const cardConfig = appConfig.slice(
      appConfig.indexOf("card:"),
      appConfig.indexOf("// Altura de controle"),
    );
    expect(cardConfig).toContain('header: "p-4 sm:p-4"');
    // 16 px; zero quando a tabela é o conteúdo inteiro (integrada ao card), e sem
    // o vertical quando o conteúdo inteiro é um Accordion (lista emoldurada).
    expect(cardConfig).toContain(
      'body: "p-4 sm:p-4 has-[>[data-slot=root]:only-child>table]:p-0 has-[>[data-slot=root]:only-child>[data-slot=item][data-state]]:py-0"',
    );
    expect(cardConfig).toContain('footer: "p-4 sm:p-4"');
    expect(cardConfig).toContain('container: "p-4 sm:p-4"');
    expect(cardConfig).not.toMatch(/shadow-|rounded-|ring-/);
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
