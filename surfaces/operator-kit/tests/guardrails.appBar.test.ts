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
// Três cabeçalhos ainda são legítimos como estão: o do PDV carrega a comanda editável,
// o da Cozinha carrega relógio e dia operacional, o da Produção carrega progresso do
// dia e timers. Eles não são deriva — são cabeçalhos ricos que ainda não foram
// convertidos, e a conversão é WP próprio. A trava não os proíbe: ela impede que a
// lista CRESÇA em silêncio, que é como os quatro convertidos aqui nasceram.
//
// Um arquivo novo com `<header>` + `<RailToggle>` reprova até ser adicionado a esta
// lista de propósito — e aí quem adicionar escreve por quê.
const here = dirname(fileURLToPath(import.meta.url));
const SURFACES = resolve(here, "../..");

/** Cabeçalhos ricos ainda não convertidos. Cada linha é uma dívida com endereço. */
const CABECALHOS_PROPRIOS_CONHECIDOS = [
  // A Produção carrega progresso do dia, timers e atalhos ensinados na aba.
  "production-nuxt/app/components/ProductionHeader.vue",
  "production-nuxt/app/components/RecipeHeader.vue",
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

  it("os três convertidos consomem a peça da layer", () => {
    const convertidos = [
      "bi-nuxt/app/components/BiTopBar.vue",
      "marketing-nuxt/app/components/CampaignTopBar.vue",
    ];
    // Navegação local que ainda não é peça da layer, declarada com o motivo.
    const navLocalDeclarada: Record<string, string> = {
      // UX-M1 (decisão do dono, 03/10/2026, SUITE-UX §6): no celular as quatro
      // seções do Marketing (Decisões, Agendados, Enviados, Ajustes) vão para a
      // barra do polegar, no pé da tela, e Ajustes entra por um item só, com as
      // próprias seções numa segunda linha. A barra do topo continua sendo a do
      // kit. A barra do pé mora em `MarketingSectionBar.vue`, no fim da coluna de
      // conteúdo (fixa na janela ela cobria o rail). Quando outro app pedir a barra
      // do pé, ela vira peça da layer e esta linha sai.
      "marketing-nuxt/app/components/CampaignTopBar.vue":
        "segunda linha de Ajustes (a barra do pé é MarketingSectionBar.vue)",
    };
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
      "orders-nuxt/app/components/GestorNav.vue",
      "kds-nuxt/app/components/KdsNav.vue",
      // V4-PDV: o rail e a barra do polegar do PDV (`place`), como o GestorNav.
      "pos-nuxt/app/components/PosFunctionRail.vue",
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
  });
});
