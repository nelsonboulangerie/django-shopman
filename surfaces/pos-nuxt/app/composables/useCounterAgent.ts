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
/**
 * A leitura da gaveta acontece no toque que INICIA a venda. Se o agente pendurar,
 * o balcão não pode esperar 3s por cliente: 1s e a resposta vira "não sei", que
 * é o modo de falha desejado (sem controle, nunca fila parada).
 */
const DRAWER_READ_TIMEOUT_MS = 1000;

/** O que aconteceu com o papel. `skipped` = este balcão não tem impressora. */
export type PrintOutcome = { status: "printed" | "failed" | "skipped"; detail: string };

/**
 * A gaveta está aberta AGORA? Só duas respostas honestas: sei (e é isto), ou não
 * sei (e é por isto). Nunca um palpite: quem trava uma venda por palpite ensina o
 * balcão a ignorar a trava, e o aviso legítimo morre junto.
 */
export type DrawerState =
  | { known: true; open: boolean; raw: string }
  | { known: false; reason: string; calibrated: boolean };

/**
 * `calibrated` separa dois "não sei" que exigem respostas opostas.
 *
 * - `false` — esta estação nunca mediu a gaveta. A trava não existe aqui, e
 *   isso é fato de instalação: ficar quieto é o certo.
 * - `true` — a estação MEDIU e o sensor parou de responder. A trava existia e
 *   sumiu, e essa é a fuga mais barata que existe contra ela: puxar o cabo da
 *   gaveta custa menos que deixá-la aberta, e desliga a proteção para sempre.
 *   Continua sem travar o balcão (fila na frente manda), mas não pode ser
 *   silencioso — "falhar aberto" é aceitável, "falhar aberto e calado" não.
 */

/**
 * O agente da estação é mais antigo que o recurso que acabou de ser pedido.
 *
 * Vale a classe própria porque a saída é diferente de toda outra falha: não é
 * fila parada, não é cabo solto, não é token errado. É software velho, e o
 * conserto é uma frase — reinstalar. Sem isto, a tela repetia "rota
 * desconhecida" e mandava o operador procurar defeito na impressora.
 */
class AgentTooOldError extends Error {
  constructor(readonly route: string) {
    super(
      "O agente desta estação está desatualizado e não conhece esta função. "
      + "Baixe e reinstale pelo gestor, em Terminais do PDV.",
    );
    this.name = "AgentTooOldError";
  }
}

export function useCounterAgent(pos: ComputedRef<POSProjection | null>) {
  const config = computed<POSCashDrawerProjection | null>(() => pos.value?.cash_drawer ?? null);

  /** Este balcão tem caminho de software? `false` = gaveta de chave. */
  const canKick = computed(() => Boolean(config.value?.can_kick));
  /**
   * Por que não dá, quando não dá — para a tela DIZER em vez de esconder.
   *
   * Esconder o card fez o dono procurar um botão que nunca ia aparecer,
   * achando que o PDV estava quebrado. O servidor manda a frase pronta; aqui só
   * sobra o caso de o terminal não ter mandado nada.
   */
  const unavailableReason = computed(
    () => config.value?.reason || "Gaveta não configurada neste terminal. Configure em Terminais do PDV, no gestor.",
  );
  /** O dono quer que a gaveta abra sozinha ao fechar venda em dinheiro? */
  const opensOnCashSale = computed(() => canKick.value && Boolean(config.value?.open_on_cash_sale));

  const probing = ref(false);

  async function callAgent(path: string, body?: Record<string, unknown>, timeoutMs = AGENT_TIMEOUT_MS) {
    const drawer = config.value;
    if (!drawer?.agent_url) throw new Error("Terminal sem agente do balcão configurado.");
    const response = await fetch(`${drawer.agent_url}${path}`, {
      method: body ? "POST" : "GET",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify({ token: drawer.token, ...body }) : undefined,
      signal: AbortSignal.timeout(timeoutMs),
    });
    const payload = await response.json().catch(() => ({}));
    // Só o status HTTP é falha de transporte. `ok: false` no corpo é uma
    // RESPOSTA — no `/health` é o motivo do CUPS ("fila pausada"), que o
    // operador precisa ler. Tratar isso como exceção apagava justamente a
    // informação que a sonda existe para trazer.
    if (!response.ok) {
      // 404 do agente quer dizer uma coisa só: ele não conhece esta rota, ou
      // seja, está rodando uma versão anterior à que criou o endpoint. O agente
      // responde "rota desconhecida", que é exato e não ajuda ninguém — o
      // operador do balcão não tem como saber que aquilo significa "reinstale".
      if (response.status === 404) throw new AgentTooOldError(path);
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
  async function probe(): Promise<{ ok: boolean; message: string; drawerLock?: { calibrated: boolean } }> {
    if (!canKick.value) return { ok: false, message: "Este balcão abre a gaveta com a chave." };
    probing.value = true;
    try {
      const payload = await callAgent("/health");
      // A versão vai junto porque o balcão só se atualiza pelo download do
      // Admin — sem rede, sem pendrive. Comparar o que a estação roda com o que
      // o Admin entrega é a única forma de saber se a máquina está atrasada.
      const versao = payload?.build ? ` Versão ${payload.build}.` : "";
      // A trava está armada nesta estação? Só o agente sabe (a medição vive no
      // `agent.json` do balcão), e sem isto o card de saúde não tinha como
      // mostrar a diferença entre balcão protegido e balcão sem medição.
      const drawerLock = payload?.drawer_lock
        ? { calibrated: payload.drawer_lock.calibrated === true }
        : undefined;
      return payload?.ok
        ? { ok: true, message: `Fila ${payload.queue} respondendo.${versao}`, drawerLock }
        : { ok: false, message: (payload?.reason || "A fila não está aceitando trabalho.") + versao, drawerLock };
    } catch (error) {
      return { ok: false, message: messageOf(error) };
    } finally {
      probing.value = false;
    }
  }

  /**
   * Imprime bytes que o SERVIDOR compôs. O agente é um cano; esta função
   * também. Nenhuma das duas sabe o que é sangria.
   *
   * Devolve o que aconteceu, porque o servidor precisa registrar: papel que
   * faltou tem que constar como falha, senão parece papel que alguém escondeu.
   */
  async function print(payloadB64: string, title: string): Promise<PrintOutcome> {
    if (!import.meta.client) return { status: "skipped", detail: "Impressão fora do navegador." };
    if (!canKick.value) return { status: "skipped", detail: unavailableReason.value };
    try {
      const payload = await callAgent("/print", { payload_b64: payloadB64, title });
      if (payload?.ok === false) throw new Error(payload?.error || "O agente recusou a impressão.");
      return { status: "printed", detail: "" };
    } catch (error) {
      return { status: "failed", detail: messageOf(error) };
    }
  }

  /**
   * Lê se a gaveta está aberta agora. **Nunca lança**: toda falha vira
   * `{ known: false }` com o motivo.
   *
   * O agente responde `{known, open, raw}` e só diz `known: true` quando ESTA
   * estação mediu a polaridade (`--drawer-status`): no balcão da Nelson o bit
   * está LIGADO com a gaveta fechada, o inverso do que o manual sugere, e uma
   * constante cravada aqui gritaria o dia inteiro com a gaveta fechada. Por isso
   * a leitura é dado do agente, nunca conta desta função.
   *
   * Sem agente (gaveta de chave) nem tenta: a resposta é "não sei" na hora, sem
   * rede, e a trava simplesmente não existe naquele balcão.
   */
  async function readState(): Promise<DrawerState> {
    if (!import.meta.client || !canKick.value) {
      return { known: false, reason: "Este balcão não tem agente para ler a gaveta.", calibrated: false };
    }
    try {
      const payload = await callAgent("/drawer", undefined, DRAWER_READ_TIMEOUT_MS);
      if (payload?.known === true && typeof payload.open === "boolean") {
        return { known: true, open: payload.open, raw: String(payload.raw ?? "") };
      }
      return {
        known: false,
        reason: String(payload?.reason || "O agente não sabe o estado da gaveta."),
        calibrated: payload?.calibrated === true,
      };
    } catch (error) {
      // Agente fora do ar / velho demais: não dá para afirmar que ESTA estação
      // tinha medição, então não acusa regressão. O silêncio aqui é honesto —
      // e o card de saúde já mostra "agente offline" em vermelho.
      return { known: false, reason: messageOf(error), calibrated: false };
    }
  }

  return { canKick, unavailableReason, opensOnCashSale, probing, kick, print, probe, readState };
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
