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
  // O PDV monta o cabeçalho por página porque cada uma carrega um contexto diferente
  // (comanda aberta, caixa) — e o `PosTabHeader` é editável. As Encomendas já
  // nasceram no `OperatorAppBar` (`PosPreordersShell`), e a antiga tela de fichas
  // saiu da lista com elas.
  "pos-nuxt/app/pages/index.vue",
  "pos-nuxt/app/pages/session/index.vue",
  // A Cozinha carrega relógio ao vivo e seletor de dia operacional no cabeçalho.
  "kds-nuxt/app/pages/[ref].vue",
  "kds-nuxt/app/pages/index.vue",
  // A Produção carrega progresso do dia, timers e atalhos ensinados na aba.
  "production-nuxt/app/components/ProductionHeader.vue",
  "production-nuxt/app/components/RecipeHeader.vue",
  // O Hub é a home: o cabeçalho dele é a saudação, e não há seções para navegar.
  "hub-nuxt/app/app.vue",
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

  it("os quatro convertidos consomem a peça da layer", () => {
    const convertidos = [
      "orders-nuxt/app/components/GestorTopBar.vue",
      "bi-nuxt/app/components/BiTopBar.vue",
      "marketing-nuxt/app/components/CampaignTopBar.vue",
      "purchase-nuxt/app/components/PurchaseTopBar.vue",
    ];
    for (const file of convertidos) {
      const source = readFileSync(join(SURFACES, file), "utf8");
      expect(source, file).toContain("<OperatorAppBar");
      // E a navegação de seção não volta a ser markup local: quem precisar divergir
      // tira o arquivo desta lista e escreve o motivo.
      expect(source, file).not.toContain("<nav");
    }
  });
});
