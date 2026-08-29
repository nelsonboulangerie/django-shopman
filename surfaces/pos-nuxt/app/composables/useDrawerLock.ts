import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { DrawerState } from "~/composables/useCounterAgent";
import type { Action } from "~/types/pos";
import { actionHref } from "~/utils/posIntent";

interface DrawerLockDeps {
  drawer: { readState: () => Promise<DrawerState> };
  actions: ComputedRef<Action[]>;
  action: {
    call: <T = unknown>(path: string, opts?: { body?: Record<string, unknown> }) => Promise<T>;
  };
}

/**
 * Cadência da espera. Curta de propósito: fechar a gaveta é o gesto que vai
 * acontecer dezenas de vezes por dia, e ele precisa PARECER instantâneo — quem
 * espera dois segundos olhando para um diálogo aprende a procurar o botão de
 * fugir dele. O agente vive na loopback (microssegundos), então 400ms não custa
 * nada e devolve o balcão quase no tempo do empurrão da gaveta.
 */
const CLOSE_POLL_MS = 400;

/**
 * Como um bloqueio por gaveta aberta terminou.
 *
 * `closed` é o caminho normal — o operador fechou a gaveta. Os outros três são
 * exceção, e cada um precisa ser distinguível dele no B.I.: exceção que se
 * confunde com rotina some na média, e some junto o padrão que interessa.
 */
export type DrawerOutcome = "closed" | "sensor_lost" | "dismissed";

/**
 * A trava da gaveta: o PDV **não anda** enquanto a gaveta estiver aberta.
 *
 * ⚠️ Isto mudou de natureza (decisão do dono, 29/08). Antes era um pedágio: a
 * trava barrava a próxima venda e o gerente liberava UMA venda com a gaveta
 * ainda aberta. Cobrava caro do espertinho, mas deixava o comportamento
 * possível. Agora é trava dura, e **quem libera é o mundo físico**: o bloqueio
 * cai sozinho quando o sensor disser que a gaveta fechou.
 *
 * O efeito colateral é o melhor da mudança: o caminho normal para destravar
 * passou a ser **fechar a gaveta**, que é exatamente o hábito que se quer criar.
 * O gerente sai do fluxo do dia a dia, e a fadiga de autorização — PIN digitado
 * no automático até virar reflexo — desaparece por construção.
 *
 * As regras que ficam de pé:
 *
 * - **Trava ao iniciar** a próxima venda, nunca no meio de uma. Venda começada
 *   não vira refém.
 * - **Só trava quando SABE.** Estado desconhecido (agente fora, estação sem
 *   medição, gaveta de chave) NUNCA trava. O modo de falha é "sem controle",
 *   jamais "balcão parado com fila".
 * - **Mas degradar é BARULHENTO.** Estação que MEDIU e parou de responder avisa
 *   o operador e abre alerta para o gerente, com linha no livro. Sem isso,
 *   desligar a trava era mais fácil que obedecê-la: puxa o cabo da gaveta e a
 *   proteção some para sempre, calada.
 * - **O PIN do gerente continua existindo — como EXCEÇÃO.** Gaveta emperrada
 *   fisicamente aberta e sensor morto são reais, e o balcão não pode ficar
 *   inutilizável com fila na frente. Mas agora ele é a saída de emergência, não
 *   o fluxo: a linha do livro diz isso, e um gerente que usa 20× por dia tem
 *   que aparecer como anomalia.
 *
 * ❌ **Não existe mais "Já fechei".** Auto-declaração era a mentira que o sensor
 * existe justamente para desmentir — e era o bypass mais barato do sistema:
 * com o diálogo na tela, puxar o cabo e clicar nele liberava a venda em
 * silêncio. Com liberação automática, ele não tem função legítima.
 *
 * Quem lê a gaveta é a página (o agente vive na loopback do balcão; o servidor
 * não alcança). O servidor entra para REGISTRAR: quanto tempo ficou aberta e
 * como o bloqueio terminou.
 */
export function useDrawerLock({ drawer, actions, action }: DrawerLockDeps) {
  /** Diálogo "gaveta aberta" na tela. */
  const open = ref(false);
  /** Diálogo de PIN do gerente por cima da trava. */
  const managerOpen = ref(false);
  const managerError = ref("");
  /** Lendo o sensor ou registrando algo no servidor. */
  const busy = ref(false);
  /** O sensor parou de responder ENQUANTO o balcão estava travado. */
  const sensorLost = ref(false);

  // O que o sensor disse quando travou, para o registro levar a prova.
  let lastRaw = "";
  // Quando o bloqueio começou — é daqui que sai a duração real da gaveta
  // aberta. Antes o PIN mascarava esse número: liberava a venda e ninguém
  // sabia se a gaveta ficou aberta 10 segundos ou a manhã inteira.
  let blockedAt = 0;
  // Um episódio de cegueira rende UM aviso, não um por venda: repetir a cada
  // toque viraria ruído, e ruído é como um alerta morre. Rearma quando o sensor
  // volta a responder — a próxima queda é um episódio novo.
  let blindReported = false;
  // A venda que ficou esperando atrás da trava.
  let pending: (() => Promise<void>) | null = null;
  // O relógio que espera a gaveta fechar. Sempre morre com o diálogo: timer
  // órfão sondando a loopback para sempre é vazamento, e num kiosk que fica
  // meses ligado vira um problema que ninguém liga ao PDV.
  let poll: ReturnType<typeof setInterval> | null = null;

  function stopPolling() {
    if (poll) {
      clearInterval(poll);
      poll = null;
    }
  }

  /**
   * Guarda a próxima venda. Se a gaveta está sabidamente aberta, segura o
   * `proceed`, trava a tela e passa a esperar o fechamento. Em todos os outros
   * casos (fechada, desconhecida, sem agente) chama `proceed` na hora.
   */
  async function guard(proceed: () => Promise<void>): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    let state: DrawerState;
    try {
      state = await drawer.readState();
    } finally {
      busy.value = false;
    }
    if (!state.known) {
      // A estação MEDIU e o sensor sumiu: a trava existia e não existe mais.
      // A venda segue (fila na frente manda), mas o gerente fica sabendo.
      if (state.calibrated) await reportBlind(state.reason);
      await proceed();
      return;
    }
    blindReported = false;
    if (!state.open) {
      await proceed();
      return;
    }
    lastRaw = state.raw;
    blockedAt = Date.now();
    pending = proceed;
    sensorLost.value = false;
    managerError.value = "";
    open.value = true;
    startWaitingForClose();
  }

  /**
   * Espera o mundo físico. É o caminho NORMAL de saída da trava: o operador
   * fecha a gaveta e o balcão volta a andar sozinho, sem clique e sem PIN.
   *
   * Se o sensor morrer no meio da espera, o bloqueio cai também — a trava não
   * pode sobreviver ao sensor que a justifica, senão a fila paga por um cabo
   * solto. Mas cai marcando, e a marca é o que separa cabo solto de gesto.
   */
  function startWaitingForClose() {
    stopPolling();
    poll = setInterval(async () => {
      if (busy.value || !open.value) return;
      const state = await drawer.readState();
      if (state.known && state.open) return;
      if (!state.known) {
        sensorLost.value = true;
        if (state.calibrated) await reportBlind(state.reason);
        await finish("sensor_lost");
        return;
      }
      await finish("closed");
    }, CLOSE_POLL_MS);
  }

  /**
   * Avisa que a trava caiu. **Nunca lança e nunca segura a venda**: se o aviso
   * falhar, o balcão não pode parar por causa dele — o aviso existe para
   * proteger o caixa, não para virar mais um jeito de travá-lo.
   */
  async function reportBlind(reason: string): Promise<void> {
    if (blindReported) return;
    blindReported = true;
    toast.warning("O sensor da gaveta parou de responder. O gerente foi avisado.");
    try {
      await action.call(
        actionHref(actions.value, "drawer_blind", "/api/v1/backstage/pos/cash/drawer-blind/"),
        { body: { reason } },
      );
    } catch {
      // Servidor fora não pode virar venda perdida. O operador já viu o toast.
    }
  }

  /**
   * Esc abriu a tela de PIN. **Registra a abertura, não o destrave.**
   *
   * A saída é escondida de propósito — botão de PIN na tela ensina o bypass —,
   * e por isso quem a PROCURA é sinal. Se só o destrave bem-sucedido fosse ao
   * livro, o operador que tenta cinco vezes por turno e desiste não apareceria
   * em lugar nenhum, e é justamente ele que se quer enxergar.
   */
  function askManager() {
    managerError.value = "";
    managerOpen.value = true;
    void logAttempt("opened");
  }

  /** Esc na tela de PIN: volta para a trava, e a desistência também é dado. */
  function backToLock() {
    if (!managerOpen.value) return;
    managerOpen.value = false;
    managerError.value = "";
    void logAttempt("abandoned");
  }

  async function logAttempt(outcome: "opened" | "abandoned" | "denied"): Promise<void> {
    try {
      await action.call(
        actionHref(actions.value, "drawer_unlock_attempt", "/api/v1/backstage/pos/cash/drawer-unlock-attempt/"),
        { body: { outcome } },
      );
    } catch {
      // Rastro que não subiu não pode travar o balcão. O destrave em si,
      // quando acontece, tem registro próprio e obrigatório.
    }
  }

  /**
   * O gerente assina a EXCEÇÃO. Só existe para gaveta emperrada aberta ou
   * sensor com defeito: no dia normal ninguém digita PIN nenhum, porque fechar
   * a gaveta já destrava. Por isso a linha do livro carrega essa natureza — sem
   * ela, o destrave de emergência ficaria indistinguível de rotina, e a
   * anomalia (o gerente que libera 20× por dia) sumiria na média.
   */
  async function unlock(username: string, pin: string): Promise<void> {
    return autorizar({ username, pin });
  }

  /** Mesma autorização, pelo crachá. Ver `ManagerApproval` no `usePosCashSession`. */
  async function unlockWithBadge(badge: string): Promise<void> {
    return autorizar({ badge });
  }

  async function autorizar(aprovacao: Record<string, string>): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    try {
      const body: Record<string, unknown> = {
        manager_approval: aprovacao,
        duration_ms: elapsed(),
        outcome: sensorLost.value ? "sensor_lost" : "manager_override",
      };
      if (lastRaw) body.drawer_raw = lastRaw;
      await action.call(
        actionHref(actions.value, "drawer_unlock", "/api/v1/backstage/pos/cash/drawer-unlock/"),
        { body },
      );
      managerOpen.value = false;
      // O episódio já vai no `drawer_unlock` (com duração e natureza): consumir
      // aqui impede que o teardown mande uma segunda linha para o mesmo caso.
      takeEpisode();
      await release();
    } catch (error) {
      const code = httpErrorCode(error);
      const message = httpErrorMessage(error, "Falha ao liberar a gaveta.");
      if (code === "manager_approval_required" || code === "manager_approval_invalid") {
        managerError.value = message;
        void logAttempt("denied");
        return;
      }
      toast.error(message);
    } finally {
      busy.value = false;
    }
  }

  function elapsed(): number {
    return blockedAt ? Date.now() - blockedAt : 0;
  }

  /**
   * **Toma** o episódio: devolve a duração e o marca como encerrado.
   *
   * ⚠️ Um dono só, e é este. Antes cada saída zerava (ou esquecia de zerar) o
   * `blockedAt` por conta própria, e foi assim que a saída pelo X ficou sem
   * rastro: o episódio simplesmente evaporava. Devolver `null` na segunda
   * chamada é o que impede duas linhas para o mesmo bloqueio quando dois
   * caminhos correm juntos (a gaveta fecha no mesmo instante em que o operador
   * desiste).
   */
  function takeEpisode(): number | null {
    if (!blockedAt) return null;
    const duracao = Date.now() - blockedAt;
    blockedAt = 0;
    return duracao;
  }

  /** Manda o episódio para o livro. **Nunca lança**: B.I. não vale uma venda. */
  async function reportEpisode(duration: number, outcome: DrawerOutcome): Promise<void> {
    try {
      await action.call(
        actionHref(actions.value, "drawer_block", "/api/v1/backstage/pos/cash/drawer-block/"),
        { body: { duration_ms: duration, outcome, drawer_raw: lastRaw } },
      );
    } catch {
      // Dado de B.I. não vale uma venda perdida.
    }
  }

  /**
   * O bloqueio terminou sozinho. Registra QUANTO tempo a gaveta ficou aberta e
   * COMO terminou, e só então solta a venda — mas o registro nunca segura o
   * balcão: se o servidor estiver fora, a venda anda do mesmo jeito.
   */
  async function finish(outcome: "closed" | "sensor_lost"): Promise<void> {
    const duracao = takeEpisode();
    await release();
    if (duracao !== null) await reportEpisode(duracao, outcome);
  }

  /**
   * Desiste: a venda que esperava não acontece.
   *
   * ⚠️ **Desistir também é desfecho, e por muito tempo não foi.** O X do canto
   * derrubava o diálogo e o episódio sumia — nem linha, nem duração, nem nada.
   * Isso não era brecha de venda (a próxima tentativa trava de novo, porque a
   * gaveta continua aberta), mas era brecha de RASTRO, que é pior de outro
   * jeito: dava para deixar a gaveta aberta, esbarrar na trava e desistir a
   * manhã inteira sem deixar uma linha no livro. O oposto exato do
   * `drawer_never_blocked`, que existe para pegar o sensor calado — aqui o
   * sensor falava, a trava agia, e o episódio evaporava.
   */
  function dismiss() {
    const duracao = takeEpisode();
    stopPolling();
    open.value = false;
    managerOpen.value = false;
    sensorLost.value = false;
    pending = null;
    if (duracao !== null) void reportEpisode(duracao, "dismissed");
  }

  async function release(): Promise<void> {
    stopPolling();
    const proceed = pending;
    pending = null;
    open.value = false;
    sensorLost.value = false;
    if (proceed) await proceed();
  }

  // O timer morre com o componente — e o episódio vai junto para o livro.
  //
  // ⚠️ Parar o relógio não bastava. Sair da tela com a trava de pé (trocar de
  // operador, navegar, o componente ser destruído) encerrava o bloqueio pelo
  // silêncio, exatamente como o X fazia. Do ponto de vista da gaveta os dois
  // são o mesmo fato — o bloqueio acabou e ninguém fechou a gaveta —, então vão
  // com o mesmo desfecho em vez de inventar vocabulário.
  function encerrarPorSaida() {
    const duracao = takeEpisode();
    stopPolling();
    if (duracao !== null) void reportEpisode(duracao, "dismissed");
  }

  // Recarregar a página também encerra o bloqueio, e por um tempo isso era o
  // último jeito de sumir com o episódio. `pagehide` cobre recarregar e fechar
  // a aba; `takeEpisode` é o que torna seguro ter dois ouvintes para o mesmo
  // fim — o segundo recebe `null` e não duplica a linha.
  //
  // ⚠️ Não é garantia: aba que morre de vez (crash, queda de energia) leva o
  // episódio junto, e nenhum ouvinte alcança isso. O que segura esse resto é o
  // `drawer_never_blocked` do B.I. — recarregar antes de cada venda para fugir
  // do registro produz justamente um turno com dinheiro andando e zero
  // bloqueio, que é a anomalia.
  //
  // ⚠️ O ouvinte só é registrado quando existe escopo para removê-lo. Registrar
  // sem par de remoção acumularia um ouvinte por instância — invisível em
  // produção (aqui sempre há componente), mas suficiente para poluir a suíte,
  // que cria dezenas de travas soltas.
  if (getCurrentScope()) {
    if (import.meta.client) window.addEventListener("pagehide", encerrarPorSaida);
    onScopeDispose(() => {
      if (import.meta.client) window.removeEventListener("pagehide", encerrarPorSaida);
      encerrarPorSaida();
    });
  }

  return {
    open,
    managerOpen,
    managerError,
    busy,
    sensorLost,
    guard,
    askManager,
    backToLock,
    unlock,
    unlockWithBadge,
    dismiss,
  };
}
