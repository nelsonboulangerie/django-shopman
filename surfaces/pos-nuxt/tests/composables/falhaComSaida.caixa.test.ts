import { computed, ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import type { Action, POSProjection } from "~/types/pos";
import { usePosCashSession } from "~/composables/usePosCashSession";

import { makeProjection } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  TODA FALHA DO PDV TEM SAÍDA — §1, o dinheiro, pelo COMPORTAMENTO        ║
// ╚══════════════════════════════════════════════════════════════════════════╝
//
// O PDV é a superfície onde o erro custa mais caro — tem cliente esperando no
// balcão — e era a que menos dizia o que fazer. Medido em 22/09/2026, contando
// as mensagens que começavam com "Falha …" e quantas continham algum gesto:
//
//     pos-nuxt          33 falhas →  1 com saída
//     orders-nuxt       19        →  5
//     production-nuxt    4        →  2
//     kds-nuxt           3        →  2
//
// A única com saída era `saveTab`: *"Os itens seguem na tela; confira a conexão
// e tente de novo."* Ela é o formato, e o formato tem três partes:
//
//     o que aconteceu  +  o que sobrevive  +  o que fazer agora
//
// "Falha ao registrar movimento." tem a primeira e mente por omissão nas outras
// duas: o operador não sabe se o dinheiro saiu da gaveta, e é exatamente o que
// ele precisa saber antes de decidir se toca o botão de novo.
//
// ## Por que a saída mora FORA do `httpErrorMessage`
//
// `httpErrorMessage(erro, fallback)` devolve o `detail` do servidor quando ele
// manda um, e SÓ cai no fallback quando não manda. Gesto escrito dentro do
// fallback, portanto, desaparece justamente quando o servidor explica a causa —
// e o backend manda `detail` em quase toda recusa de negócio. Por isso o padrão
// é `` `${httpErrorMessage(erro, causa)} ${saida}` ``: a causa é do servidor
// quando ele a tem, a saída é sempre nossa.
//
// ## Por que a trava tem duas metades
//
// A varredura de fonte (a metade §2, em `tests/falhaComSaida.test.ts`) não
// enxerga indireção: em `usePosCashSession` a
// saída viaja como ARGUMENTO até um `run()` compartilhado, e a linha do
// `toast.error` não contém gesto nenhum — o gesto está nos nove chamadores.
// Ler aquele arquivo com regex daria verde falso ou vermelho falso. Então o
// arquivo do dinheiro é travado pelo COMPORTAMENTO (§1): a mutação é executada
// contra um servidor que recusa, e a trava lê o toast que o operador leria.

/** O que conta como saída: um verbo que o operador pode executar agora. */
const GESTO =
  /\b(tente|tenta|confira|confirme|avise|chame|peça|refaça|digite|atualize|reabra|feche|corrija|cancele|siga|repetir|repita|identifique|configure|reinicie|escolha|informe|aguarde|volte|busque|selecione|copie|mande|reimprima)\b/i;

// ───────────────────────────────────────────────────────────────────────────
// §1 — O DINHEIRO, pelo comportamento
// ───────────────────────────────────────────────────────────────────────────

function sessaoDeCaixa(actionCall: ReturnType<typeof vi.fn>) {
  const posValue = ref<POSProjection | null>(makeProjection());
  const actionsValue = ref<Action[]>([]);
  return usePosCashSession({
    pos: computed(() => posValue.value),
    actions: computed(() => actionsValue.value),
    refresh: vi.fn().mockResolvedValue(undefined),
    action: { call: actionCall },
  });
}

type Sessao = ReturnType<typeof sessaoDeCaixa>;

/**
 * As nove mutações de caixa. Uma entrada por gesto que mexe — ou parece mexer —
 * no dinheiro da gaveta. Somar uma décima sem somar aqui deixa a trava cega
 * para ela, que é como as 33 nasceram.
 */
const MUTACOES: Array<{ nome: string; executar: (s: Sessao) => Promise<unknown> }> = [
  { nome: "abrir caixa", executar: (s) => s.openCashShift("50,00") },
  { nome: "fechar caixa", executar: (s) => s.closeCashShift({ amount: "10", notes: "" }) },
  {
    nome: "sangria/suprimento",
    executar: (s) => s.registerCashMovement({ kind: "sangria", amount: "200", reason: "cofre" }),
  },
  { nome: "abrir gaveta sem venda", executar: (s) => s.openDrawerWithoutSale("conferência") },
  {
    nome: "pedir troco",
    executar: (s) => s.requestChange({ amount: "50", denominations: [10], note: "" }),
  },
  { nome: "atender pedido de troco", executar: (s) => s.serveChangeRequest({ ref: "TR-1" }) },
  { nome: "cancelar pedido de troco", executar: (s) => s.cancelChangeRequest("TR-1") },
  { nome: "devolver dinheiro", executar: (s) => s.refundCash({ orderRef: "PED-1" }) },
  {
    nome: "acertar conta na casa",
    executar: (s) => s.settleAccount({ customerRef: "CLI-1", amount: "30", method: "cash" }),
  },
];

describe("§1 toda mutação de caixa que falha diz o que fazer agora", () => {
  for (const { nome, executar } of MUTACOES) {
    it(`${nome}: o toast traz um gesto`, async () => {
      vi.mocked(toast.error).mockClear();
      const recusa = vi.fn().mockRejectedValue(new Error("rede caiu"));
      await executar(sessaoDeCaixa(recusa));

      expect(toast.error).toHaveBeenCalledTimes(1);
      const mensagem = String(vi.mocked(toast.error).mock.calls[0]?.[0] ?? "");
      expect(mensagem, `"${mensagem}" não oferece saída nenhuma`).toMatch(GESTO);
    });
  }

  it("a causa do SERVIDOR sobrevive, e a saída vem junto", async () => {
    // O ponto do padrão: `httpErrorMessage` troca o fallback pelo `detail`, e
    // mesmo assim o operador continua sabendo o que fazer.
    vi.mocked(toast.error).mockClear();
    const recusa = vi.fn().mockRejectedValue({
      status: 400,
      data: { detail: "Caixa não aberto neste terminal." },
    });
    await sessaoDeCaixa(recusa).registerCashMovement({ kind: "sangria", amount: "200", reason: "" });

    const mensagem = String(vi.mocked(toast.error).mock.calls[0]?.[0] ?? "");
    expect(mensagem).toContain("Caixa não aberto neste terminal.");
    expect(mensagem).toMatch(GESTO);
  });

  it("o desafio de gerente NÃO ganha 'tente de novo' — o diálogo de PIN é a saída", async () => {
    // Exceção deliberada, e a única do §1: mandar repetir o gesto empurraria o
    // operador para longe da assinatura que está faltando, ali na tela.
    const recusa = vi.fn().mockRejectedValue({
      status: 403,
      data: { detail: "Esta retirada precisa de um gerente.", error: { code: "manager_approval_required" } },
    });
    const sessao = sessaoDeCaixa(recusa);
    await sessao.registerCashMovement({ kind: "sangria", amount: "200", reason: "cofre" });

    expect(sessao.managerChallenge.value?.message).toBe("Esta retirada precisa de um gerente.");
  });
});


// A metade que varre a fonte do resto do PDV mora em `tests/falhaComSaida.test.ts`:
// ela só lê arquivo, então roda no projeto `unit`, enquanto esta precisa do
// ambiente `nuxt` (auto-imports) que o vitest.config dá a `tests/composables/**`.
