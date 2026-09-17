import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// ERRO DE REDE NÃO É SESSÃO MORTA.
//
// `canIdentify` é só `session !== null`. Quando a consulta a
// `/operator/session/` FALHA — 502/503/504 enquanto o alpha redeploya (o que
// acontece a cada push no `main`), rede caindo, Django ainda subindo — o `data`
// zera e, sem guarda, a tela sobe o formulário de SENHA. Ou seja: o app diz "você
// foi deslogado" para quem não foi. Era isso que o dono via como "o login cai
// toda hora".
//
// Provado em runtime contra um backend de mentira, no `bi-nuxt` construído:
//
//     servidor 200  →  painel            (certo nos dois)
//     servidor 503  →  PEDIA SENHA       →  agora "não foi possível conferir"
//     servidor 403  →  pede senha        (certo nos dois: sessão morta mesmo)
//
// O sinal que separa os dois casos (`sessionUnavailable`) já existia em
// `useOperatorLock` e só o Marketing consumia. Este guardrail existe para nenhum
// app de operador voltar a montar a tela de senha sem distinguir as duas coisas.
const surfaces = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Onde cada app decide mostrar a tela de senha. */
const GATES: Record<string, string> = {
  "bi-nuxt": "app/app.vue",
  "kds-nuxt": "app/app.vue",
  "orders-nuxt": "app/app.vue",
  "production-nuxt": "app/app.vue",
  "purchase-nuxt": "app/app.vue",
  "marketing-nuxt": "app/app.vue",
  "hub-nuxt": "app/app.vue",
  "pos-nuxt": "app/components/PosOperatorShell.vue",
};

/**
 * Cada app tem o direito de classificar a falha do seu jeito — o que ele NÃO
 * pode é ignorar que ela existe. A Central classifica com `hubFailure`; os
 * outros consomem `sessionUnavailable` direto.
 */
const GUARDAS = ["sessionUnavailable", "hubFailure"];

describe("nenhum app de operador confunde erro de rede com sessão morta", () => {
  for (const [app, caminho] of Object.entries(GATES)) {
    it(`${app} distingue "não consegui perguntar" de "você não está logado"`, () => {
      const fonte = readFileSync(resolve(surfaces, app, caminho), "utf8");
      expect(fonte, `${app}: monta <OperatorLogin> mas não classifica a falha`).toContain(
        "OperatorLogin",
      );
      const classifica = GUARDAS.some(guarda => fonte.includes(guarda));
      expect(classifica, `${app}: precisa de ${GUARDAS.join(" ou ")}`).toBe(true);
    });
  }
});
