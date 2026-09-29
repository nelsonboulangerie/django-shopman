// EventSource que se recria sozinho, com backoff — o SSE das superfícies de operador.
//
// O EventSource do navegador só reconecta sozinho quando a conexão cai no meio do
// stream. Se a RECONEXÃO recebe status diferente de 200 (o 502 do BFF/ingress em
// todo deploy, várias vezes por dia), ele fica CLOSED para sempre: a tela seguia
// só no poll até alguém recarregar. E quando o Django recusa o canal (convidado
// sem sessão no painel de retirada), a resposta é 200 com um `stream-error` e o
// stream fecha — o navegador reconecta a cada ~3 s, num laço sem fim.
//
// Aqui os dois casos viram a mesma coisa: fecha, espera (2 s, 4 s, 8 s… teto de
// 60 s) e cria um EventSource novo. O backoff só volta ao começo depois de um
// stream que ficou de pé (`STABLE_MS`); um canal que abre e cai na hora continua
// esticando a espera. ADR-016: o push é só o sinal; quem segura a tela nesse meio
// tempo é o poll, e cada reabertura avisa (`onOpen(true)`) para o chamador refazer
// o fetch canônico e cobrir o que passou.

/** `EventSource.CLOSED` — numérico para não depender do construtor global. */
const CLOSED = 2;

/** Um stream aberto por este tempo conta como saudável e zera o backoff. */
const STABLE_MS = 30_000;

export interface ResilientEventSourceOptions {
  /** URL same-origin do BFF (use `ssePath`). */
  url: string;
  /** Eventos nomeados que significam "algo mudou" (além de `message`). */
  events: readonly string[];
  onEvent: (event: MessageEvent) => void;
  /** Stream de pé. `reconnected` é true a partir da segunda abertura. */
  onOpen?: (reconnected: boolean) => void;
  /** Stream caiu (o poll segura até voltar). */
  onDown?: () => void;
  /** Primeira espera. Padrão 2 s. */
  baseDelayMs?: number;
  /** Teto da espera. Padrão 60 s. */
  capMs?: number;
}

export interface ResilientEventSource {
  /** Tenta agora (aba voltou, rede voltou), sem esperar o backoff. */
  reconnectNow(): void;
  /** Encerra de vez. */
  close(): void;
}

export function openResilientEventSource(options: ResilientEventSourceOptions): ResilientEventSource {
  const baseDelayMs = options.baseDelayMs ?? 2_000;
  const capMs = options.capMs ?? 60_000;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let openedAt = 0;
  let everOpened = false;
  let closed = false;

  function drop() {
    if (!source) return;
    source.onopen = null;
    source.onerror = null;
    source.close();
    source = null;
  }

  function scheduleReconnect() {
    drop();
    options.onDown?.();
    if (closed || timer) return;
    if (openedAt && Date.now() - openedAt >= STABLE_MS) attempt = 0;
    openedAt = 0;
    const delay = Math.min(capMs, baseDelayMs * 2 ** attempt);
    attempt += 1;
    timer = setTimeout(() => {
      timer = null;
      connect();
    }, delay);
  }

  function connect() {
    if (closed || source) return;
    let created: EventSource;
    try {
      created = new EventSource(options.url, { withCredentials: true });
    } catch {
      scheduleReconnect();
      return;
    }
    source = created;
    const onEvent = (event: Event) => options.onEvent(event as MessageEvent);
    for (const name of ["message", ...options.events]) created.addEventListener(name, onEvent);
    // O Django recusou o canal: 200 + `stream-error` e o stream fecha. Deixar o
    // navegador reconectar sozinho é o laço de 3 s; aqui vira backoff.
    created.addEventListener("stream-error", () => {
      if (source === created) scheduleReconnect();
    });
    created.onopen = () => {
      openedAt = Date.now();
      options.onOpen?.(everOpened);
      everOpened = true;
    };
    created.onerror = () => {
      if (source !== created) return;
      // CLOSED = o navegador desistiu (status não-200 na reconexão). Fora isso,
      // ele mesmo reconecta; só avisamos que o push está fora.
      if (created.readyState === CLOSED) scheduleReconnect();
      else options.onDown?.();
    };
  }

  connect();

  return {
    reconnectNow() {
      if (closed) return;
      if (source && source.readyState !== CLOSED) return;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      drop();
      connect();
    },
    close() {
      closed = true;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      drop();
    },
  };
}
