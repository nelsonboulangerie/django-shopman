import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES as APPS } from "./support/surfaceRegistry";

// Guardrail do CABEÇALHO: a barra de seções do app é peça da layer, não markup de cada
// app.
//
// ## O que foi medido (22/09/2026)
//
// Sete apps desenhavam o próprio cabeçalho, e "o mesmo" já não era o mesmo:
// `px-4 py-2.5` no Gestor/B.I./Compras, `px-4 py-2` no PDV, `px-4 py-3` no Hub,
// `px-3 py-2 sm:px-4` no Marketing; aba de `min-h-control` (44px) no Gestor, `h-11` no
// Marketing e **`h-8`** no B.I. e no Compras — metade do alvo de toque que o token
// `--spacing-control` define para a casa. O `chipClass(active)` do B.I. e o do Compras
// eram cópia byte a byte um do outro. E a aba ativa só era trazida para a área visível
// no Marketing, onde o defeito tinha aparecido de verdade.
//
// ## Por que a trava é por LISTA e não por proibição
//
// Um cabeçalho ainda é legítimo como está: o do PDV carrega a comanda editável (o da
// Cozinha e o da Produção viraram o `OperatorPageHeader` da suíte na onda V4). Não é
// deriva — é cabeçalho rico que ainda não foi convertido, e a conversão é WP próprio.
// A trava não o proíbe: ela impede que a
// lista CRESÇA em silêncio, que é como os quatro convertidos aqui nasceram.
//
// Um arquivo novo com `<header>` + `<RailToggle>` reprova até ser adicionado a esta
// lista de propósito — e aí quem adicionar escreve por quê.
const here = dirname(fileURLToPath(import.meta.url));
const SURFACES = resolve(here, "../..");

/** Cabeçalhos ricos ainda não convertidos. Cada linha é uma dívida com endereço. */
const CABECALHOS_PROPRIOS_CONHECIDOS: string[] = [
  // Vazia desde a onda V4: Produção (V4-PROD) e PDV (V4-PDV) migraram para o cabeçalho
  // da layer. Cabeçalho próprio novo volta a reprovar até ser declarado aqui com motivo.
].sort();

function vueFiles(dir: string): string[] {
  let found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) found = found.concat(vueFiles(full));
    else if (entry.endsWith(".vue")) found.push(full);
  }
  return found;
}

describe("guardrail do cabeçalho de seções", () => {
  it("nenhum cabeçalho novo nasce à mão", () => {
    const proprios: string[] = [];
    for (const app of APPS) {
      for (const file of vueFiles(join(SURFACES, app, "app"))) {
        const source = readFileSync(file, "utf8");
        if (source.includes("<header") && source.includes("<RailToggle")) {
          proprios.push(relative(SURFACES, file));
        }
      }
    }
    expect(proprios.sort()).toEqual(CABECALHOS_PROPRIOS_CONHECIDOS);
  });

  it("os convertidos consomem a peça da layer", () => {
    // O B.I. saiu desta lista para a do rail da suíte (V4-BI).
    // O Marketing também saiu (V4-MKT): a lista ficou vazia, e a trava segue valendo
    // para quem voltar a usar a barra de seções do topo.
    const convertidos: string[] = [];
    // Navegação local que ainda não é peça da layer, declarada com o motivo.
    const navLocalDeclarada: Record<string, string> = {};
    for (const file of convertidos) {
      const source = readFileSync(join(SURFACES, file), "utf8");
      expect(source, file).toContain("<OperatorAppBar");
      // E a navegação de seção não volta a ser markup local: quem precisar divergir
      // declara o arquivo em `navLocalDeclarada` e escreve o motivo.
      if (!navLocalDeclarada[file]) expect(source, file).not.toContain("<nav");
    }
  });

  // UX-KIT-V1: o app que veste a camada visual da suíte tira a barra de seções do topo
  // e passa as seções para o rail da suíte (tablet e desktop) e para a barra do polegar
  // (celular), as duas peças da layer. O Gestor é o piloto; quem migrar entra aqui.
  it("os que migraram para o rail da suíte usam as duas peças da layer", () => {
    const migrados = [
      "kds-nuxt/app/components/KdsNav.vue",
      // V4-PDV: o rail e a barra do polegar do PDV (`place`), como o GestorNav.
      "pos-nuxt/app/components/PosFunctionRail.vue",
      // V4-PROD: o ciclo do lote no rail (Alt1 a Alt5 impressos) e na barra do polegar.
      "production-nuxt/app/components/ProductionNav.vue",
      // V4-COMPRAS: as seções do Compras são estado (não rotas); as duas peças recebem
      // `current` e devolvem `select`.
      "purchase-nuxt/app/components/PurchaseNav.vue",
    ];
    for (const file of migrados) {
      const source = readFileSync(join(SURFACES, file), "utf8");
      expect(source, file).toContain("<OperatorSuiteRail");
      expect(source, file).toContain("<OperatorSectionBar");
      expect(source, file).not.toContain("<nav");
      expect(source, file).not.toContain("<OperatorAppBar");
    }

    // O piloto já eliminou o adaptador intermediário: o app entrega suas seções
    // diretamente ao shell canônico, que monta rail e barra móvel uma única vez.
    const orders = readFileSync(
      join(SURFACES, "orders-nuxt/app/app.vue"),
      "utf8",
    );
    expect(orders).toContain("<OperatorSuiteShell");
    expect(orders).toContain(':sections="sections"');
    expect(orders).toContain(':current="current"');
    expect(orders).not.toContain("<GestorNav");

    // PR-B1 (WP-BI-CANON-LAUDO): o B.I. segue o Gestor. Sem adaptador de navegação,
    // sem a pele legada `data-suite`, e sem gesto próprio de troca de seção.
    const bi = readFileSync(join(SURFACES, "bi-nuxt/app/app.vue"), "utf8");
    expect(bi).toContain("<OperatorSuiteShell");
    expect(bi).toContain(':sections="sections"');
    expect(bi).not.toContain("<BiNav");
    expect(bi).not.toMatch(/data-suite=/);

    // Fase 2 (onda do Marketing): o Marketing segue o Gestor. As sub-seções de Ajustes
    // moram em `MarketingSettingsNav.vue`, na faixa esquerda da toolbar.
    const marketing = readFileSync(join(SURFACES, "marketing-nuxt/app/app.vue"), "utf8");
    expect(marketing).toContain("<OperatorSuiteShell");
    expect(marketing).toContain(':sections="sections"');
    expect(marketing).not.toContain("<MarketingNav");
    expect(marketing).not.toMatch(/data-suite=/);
  });
});

// V6-KIT (auditoria v4, 04/10/2026): o chrome da suíte é UM em todo app. Cada trava
// abaixo nasceu de uma divergência medida que pode voltar.
const NAVS = [
  "kds-nuxt/app/components/KdsNav.vue",
  "pos-nuxt/app/components/PosFunctionRail.vue",
  "production-nuxt/app/components/ProductionNav.vue",
  "purchase-nuxt/app/components/PurchaseNav.vue",
];
const KIT = (name: string) =>
  readFileSync(join(SURFACES, "operator-kit/app/components", name), "utf8");

function sourcesOf(app: string): Array<[string, string]> {
  return vueFiles(join(SURFACES, app, "app")).map((file) => [
    relative(SURFACES, file),
    readFileSync(file, "utf8"),
  ]);
}

describe("guardrail do chrome da suíte (V6-KIT)", () => {
  // K01/T-01: a v4 tem UM "Avisos". O Gestor tinha Alertas + Avisos (dois ícones no
  // rail, dois sinos no celular), a Produção só "Alertas", o Marketing nenhum.
  it("um só item de Avisos: o sino é da caixa do kit, e app nenhum monta o seu", () => {
    const proprios: string[] = [];
    for (const app of APPS) {
      for (const [file, source] of sourcesOf(app)) {
        if (file.startsWith("operator-kit/")) continue;
        if (
          /<(NotificationBell|AlertsBell|OperatorInbox)\b/.test(source) &&
          !file.endsWith("hub-nuxt/app/app.vue") &&
          !file.endsWith("pos-nuxt/app/pages/index.vue")
        )
          proprios.push(file);
        if (/\s:?label="(Alertas|Avisos)"/.test(source)) proprios.push(file);
        if (/["']lucide:bell["']/.test(source)) proprios.push(file);
      }
    }
    expect(proprios).toEqual([]);
    expect(
      KIT("OperatorSuiteRail.vue").match(/<OperatorInbox\b/g),
    ).toHaveLength(2); // uma por ordem do pé, só uma renderiza
    expect(
      KIT("OperatorPageHeader.vue").match(/<OperatorInbox\b/g),
    ).toHaveLength(1);
  });

  // K02/T-03: o velocímetro com ponto vermelho saiu do rail para o menu das iniciais
  // (e para a caixa de Avisos quando passa do limite).
  it("sem medidor de capacidade no rail; ele mora no menu do operador", () => {
    expect(KIT("OperatorSuiteRail.vue")).not.toContain(
      "<OperatorCapacityStatus",
    );
    expect(KIT("OperatorMenuItems.vue")).toContain(
      "data-operator-menu-capacity",
    );
    for (const file of NAVS)
      expect(readFileSync(join(SURFACES, file), "utf8"), file).not.toContain(
        "Capacity",
      );
  });

  // K04/T-14: a ordem do pé é a da v4 (`_rail3bottom.html`): seções do pé e o slot do
  // app, traço, Avisos, Atalhos, Bloquear, iniciais.
  it("a ordem do pé do rail", () => {
    const rail = KIT("OperatorSuiteRail.vue");
    const at = (marker: string, from = 0) => rail.indexOf(marker, from);
    const foot = at("data-rail-foot");
    const sections = at('v-for="section in footSections"', foot);
    const slot = at('<slot name="foot" />', foot);
    const rule = at("data-rail-foot-rule", foot);
    const inbox = at("<OperatorInbox", rule);
    const shortcuts = at('label="Atalhos"', foot);
    const lock = at('label="Bloquear"', foot);
    const menu = at("data-suite-rail-menu", lock);
    expect(
      [sections, slot, rule, inbox, shortcuts, lock, menu].every(
        (n) => n > foot,
      ),
    ).toBe(true);
    expect([sections, slot, rule, inbox, shortcuts, lock, menu]).toEqual(
      [sections, slot, rule, inbox, shortcuts, lock, menu].sort(
        (a, b) => a - b,
      ),
    );
  });

  // K11/H02/T-04: Bloquear em todo app, a Central inclusive. A prop que o escondia morreu.
  it("Bloquear em todo app: ninguém esconde o item", () => {
    expect(KIT("OperatorSuiteRail.vue")).not.toContain("lockable");
    for (const app of APPS) {
      for (const [file, source] of sourcesOf(app))
        expect(source, file).not.toContain("lockable");
    }
  });

  // K06/T-07: sem o rail (celular, tablet em pé), Bloquear e trocar de operador ficam
  // a um toque: o "Mais" da barra do polegar (ou as iniciais da Central).
  it("o menu do operador existe no celular de todo app", () => {
    expect(KIT("OperatorSectionBar.vue")).toContain("<OperatorPhoneMenu");
    for (const file of NAVS) {
      const source = readFileSync(join(SURFACES, file), "utf8");
      const bar = source.slice(source.indexOf("<OperatorSectionBar"));
      expect(bar, file).toContain(":operator-name=");
      expect(bar, file).toContain("@lock=\"emit('lock')\"");
    }
    // A Central está no shell da suíte (fase 2): o menu do operador é o da gaveta do
    // shell, alimentado pelo nome do operador.
    const hub = readFileSync(join(SURFACES, "hub-nuxt/app/app.vue"), "utf8");
    const shell = hub.slice(hub.indexOf("<OperatorSuiteShell"));
    expect(shell).toContain(":operator-name=");
    expect(shell).toContain('@lock="lockDevice"');
  });

  // K08/T-09: no tablet em pé a navegação é a barra de baixo. A régua é uma só (a
  // variante `rail:`); `md:` para decidir rail × barra é a régua velha.
  it("rail e barra decidem pela variante rail:, não por md:", () => {
    expect(KIT("OperatorSuiteRail.vue")).toContain("rail:flex");
    expect(KIT("OperatorSectionBar.vue")).toContain("rail:hidden");
    expect(KIT("OperatorSectionBar.vue")).not.toContain("md:hidden");
    for (const file of NAVS) {
      expect(readFileSync(join(SURFACES, file), "utf8"), file).not.toContain(
        "767.98px",
      );
    }
  });

  // T-02: a ajuda de atalhos é peça do kit; cópia por app não volta.
  it("a ajuda de atalhos é uma, do kit", () => {
    for (const app of APPS) {
      for (const [file] of sourcesOf(app)) {
        if (file.startsWith("operator-kit/")) continue;
        expect(file, file).not.toMatch(/ShortcutsHelp\.vue$/);
      }
    }
    expect(KIT("OperatorSuiteRail.vue")).toContain("<OperatorShortcutsHelp");
  });
});
