// A conta do botão com prazo (`OperatorTimedButton`): pura, sem relógio próprio, para
// a peça e os testes lerem a mesma verdade. Quem chama passa o "agora" do dispositivo.
//
// O prazo é ABSOLUTO (`until`): a peça pode desmontar e montar de novo (teleporte, troca
// de foco, recarga da lista), a aba pode dormir em segundo plano, e o fim continua no
// mesmo instante. O tamanho da janela (`since` ou `duration`) só decide quanto do fundo
// ainda está cheio.

export type Instant = number | string;

export interface TimedWindowInput {
  /** Fim da janela: epoch em ms ou ISO. */
  until: Instant;
  /** Começo da janela (epoch em ms ou ISO). Com `until`, dá o tamanho exato. */
  since?: Instant;
  /** Tamanho da janela em ms, quando não há `since`. */
  duration?: number;
  /** Quanto o relógio de quem deu o prazo está à frente do dispositivo (ms). */
  offsetMs?: number;
  /** Primeiro instante em que a peça viu este prazo: o último recurso para o tamanho. */
  firstSeenMs?: number;
}

export interface TimedWindow {
  /** Fim, no relógio do dispositivo. */
  untilMs: number;
  /** Começo, no relógio do dispositivo. */
  startMs: number;
  totalMs: number;
  remainingMs: number;
  elapsedMs: number;
  /** De 1 (janela inteira) a 0 (acabou). */
  fraction: number;
  expired: boolean;
}

/** Epoch em ms de um instante, ou `NaN` quando não dá para ler. */
export function toEpochMs(value: Instant | undefined | null): number {
  if (value === undefined || value === null || value === "") return Number.NaN;
  if (typeof value === "number") return value;
  return Date.parse(value);
}

/** O desvio entre o relógio do servidor e o do dispositivo, lido de um `server_now`. */
export function clockOffsetMs(serverNow: string | undefined, deviceNowMs: number): number {
  const server = toEpochMs(serverNow);
  return Number.isFinite(server) ? server - deviceNowMs : 0;
}

export function timedWindow(input: TimedWindowInput, nowMs: number): TimedWindow {
  const offset = input.offsetMs ?? 0;
  const until = toEpochMs(input.until);
  const untilMs = Number.isFinite(until) ? until - offset : nowMs;
  const since = toEpochMs(input.since);
  let startMs: number;
  if (Number.isFinite(since)) startMs = since - offset;
  else if (input.duration && input.duration > 0) startMs = untilMs - input.duration;
  else startMs = Math.min(input.firstSeenMs ?? nowMs, untilMs);
  const totalMs = Math.max(0, untilMs - startMs);
  const remainingMs = Math.max(0, untilMs - nowMs);
  const elapsedMs = Math.min(totalMs, Math.max(0, nowMs - startMs));
  return {
    untilMs,
    startMs,
    totalMs,
    remainingMs,
    elapsedMs,
    fraction: totalMs > 0 ? Math.min(1, remainingMs / totalMs) : 0,
    expired: remainingMs <= 0,
  };
}

/** Segundos que faltam, arredondados para cima: "1 s" até o fim, nunca "0 s" aberto. */
export function remainingSeconds(remainingMs: number): number {
  return Math.max(0, Math.ceil(remainingMs / 1000));
}

/** A hora do fim, como o leitor de tela ouve: "10:42:15". */
export function deadlineClock(untilMs: number): string {
  return new Date(untilMs).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** A descrição fixa do botão (não muda a cada segundo). */
export function timedDescription(untilMs: number, expired: boolean): string {
  return expired ? "O prazo acabou." : `Disponível até ${deadlineClock(untilMs)}.`;
}

/** O que a região educada anuncia, só ao abrir e ao fechar a janela. */
export function timedAnnouncement(label: string, untilMs: number, expired: boolean): string {
  return expired
    ? `${label}: o prazo acabou.`
    : `${label}: disponível até ${deadlineClock(untilMs)}.`;
}
