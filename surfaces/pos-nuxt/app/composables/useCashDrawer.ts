import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { POSCashDrawerProjection, POSProjection } from "~/types/pos";

/**
 * O caminho físico que abre a gaveta de dinheiro.
 *
 * A gaveta não tem cabo próprio: ela pendura no RJ11 da impressora e abre
 * quando a impressora recebe `ESC p m t1 t2`. O navegador não fala ESC/POS e
 * não pode reivindicar a interface USB (o driver do sistema já é dono dela — é
 * assim que a impressão do recibo funciona). Então quem manda os cinco bytes é
 * um agente local, e quem alcança esse agente é ESTA página: ele vive na
 * loopback do balcão, longe do servidor.
 *
 * **Um caminho para os quatro momentos** — venda em dinheiro, sangria,
 * suprimento e abrir sem venda. Se algum ficasse de fora, o operador voltaria à
 * chave física e o controle de caixa se perderia junto.
 *
 * O que este composable NÃO faz é decidir *quem pode* abrir. Isso é da política
 * de caixa (retirada exige PIN em qualquer valor), que mora no servidor.
 */

/** Loopback responde em microssegundos; 3s só existe para agente pendurado. */
const AGENT_TIMEOUT_MS = 3000;

export function useCashDrawer(pos: ComputedRef<POSProjection | null>) {
  const config = computed<POSCashDrawerProjection | null>(() => pos.value?.cash_drawer ?? null);

  /** Este balcão tem caminho de software? `false` = gaveta de chave. */
  const canKick = computed(() => Boolean(config.value?.can_kick));
  /** O dono quer que a gaveta abra sozinha ao fechar venda em dinheiro? */
  const opensOnCashSale = computed(() => canKick.value && Boolean(config.value?.open_on_cash_sale));

  const probing = ref(false);

  async function callAgent(path: string, body?: Record<string, unknown>) {
    const drawer = config.value;
    if (!drawer?.agent_url) throw new Error("Terminal sem agente de gaveta configurado.");
    const response = await fetch(`${drawer.agent_url}${path}`, {
      method: body ? "POST" : "GET",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify({ token: drawer.token, ...body }) : undefined,
      signal: AbortSignal.timeout(AGENT_TIMEOUT_MS),
    });
    const payload = await response.json().catch(() => ({}));
    // Só o status HTTP é falha de transporte. `ok: false` no corpo é uma
    // RESPOSTA — no `/health` é o motivo do CUPS ("fila pausada"), que o
    // operador precisa ler. Tratar isso como exceção apagava justamente a
    // informação que a sonda existe para trazer.
    if (!response.ok) {
      throw new Error(payload?.error || `Agente respondeu ${response.status}.`);
    }
    return payload;
  }

  /**
   * Chuta a gaveta. Devolve `true` se o agente aceitou o trabalho.
   *
   * **Nunca lança.** Nos quatro momentos o dinheiro já mudou de mão e o
   * servidor já registrou; derrubar a tela agora só transformaria uma gaveta
   * emperrada numa venda perdida. Mas também nunca falha calado: gaveta que não
   * abriu e ninguém avisou é o operador procurando defeito na chave enquanto a
   * fila cresce.
   */
  async function kick(reason: string): Promise<boolean> {
    if (!import.meta.client || !canKick.value) return false;
    try {
      const payload = await callAgent("/kick", { reason, pulse: config.value?.pulse });
      if (payload?.ok === false) throw new Error(payload?.error || "O agente recusou o comando.");
      return true;
    } catch (error) {
      toast.error(`A gaveta não abriu: ${messageOf(error)}`);
      return false;
    }
  }

  /**
   * Sonda o agente. É o quanto dá para saber sem tocar no aparelho: a fila do
   * sistema está de pé. Se a gaveta está plugada na impressora, ou se abriu,
   * isto NÃO sabe — a resposta viria pelo canal bidirecional, que um trabalho
   * de spool não tem. Por isso o teste termina no olho do operador.
   */
  async function probe(): Promise<{ ok: boolean; message: string }> {
    if (!canKick.value) return { ok: false, message: "Este balcão abre a gaveta com a chave." };
    probing.value = true;
    try {
      const payload = await callAgent("/health");
      return payload?.ok
        ? { ok: true, message: `Fila ${payload.queue} respondendo.` }
        : { ok: false, message: payload?.reason || "A fila não está aceitando trabalho." };
    } catch (error) {
      return { ok: false, message: messageOf(error) };
    } finally {
      probing.value = false;
    }
  }

  return { canKick, opensOnCashSale, probing, kick, probe };
}

function messageOf(error: unknown): string {
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return "O agente não respondeu.";
  }
  // `fetch` para porta fechada vira TypeError sem detalhe útil — o operador
  // precisa de um próximo passo, não do nome da exceção.
  if (error instanceof TypeError) return "O agente da estação não está rodando.";
  return error instanceof Error ? error.message : String(error);
}
