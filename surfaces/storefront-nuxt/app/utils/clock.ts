// A HORA DA CASA: "12h45", "9h05", "9h" (decisão do dono, 16/11/2026, para a
// suíte inteira, operador e cliente). Sem zero à esquerda na hora, minuto com
// dois dígitos, hora cheia sem minuto. A regra e o que fica de fora (formato de
// máquina, campo de formulário) estão em `docs/reference/suite-vocabulary.md`,
// seção "Hora".
//
// Este módulo é o ÚNICO lugar de uma superfície que formata hora para gente ler.
// As travas `guardrails.clock.test.ts` (kit, loja e status) reprovam
// `toLocaleTimeString`, `hour: "2-digit"`, `timeStyle` e a hora montada à mão
// fora dele. O servidor tem o par em `shopman.utils.formatting.format_clock`.
//
// ⚠️ ARQUIVO GÊMEO. Existe byte a byte igual em
//   surfaces/operator-kit/app/presentation/clock.ts   (os apps de operador)
//   surfaces/storefront-nuxt/app/utils/clock.ts       (a loja)
//   surfaces/status-nuxt/app/utils/clock.ts           (a página de status)
// e o teste `clockTwin` de cada lado reprova a menor diferença. A loja e o
// status buildam sozinhos e não estendem o operator-kit, então o módulo não
// pode morar num lugar só.

/** Um instante (`Date`, epoch em ms, ISO) ou o texto `"HH:MM"` dos contratos. */
export type ClockInput = Date | number | string | null | undefined;

const CONTRACT_CLOCK = /^(\d{1,2}):(\d{2})(?::\d{2})?$/;

function house(hour: number, minute: number): string {
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) return "";
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return "";
  return minute ? `${hour}h${String(minute).padStart(2, "0")}` : `${hour}h`;
}

function instant(input: ClockInput): Date | null {
  if (input === null || input === undefined || input === "") return null;
  const date = input instanceof Date ? input : new Date(input);
  return Number.isFinite(date.getTime()) ? date : null;
}

/**
 * A hora como a casa escreve: "12h45", "9h05", "9h". Vazio quando não dá para
 * ler (cadastro torto não vira promessa de meia-noite).
 *
 * `timeZone` escolhe o fuso do instante; sem ele vale o do dispositivo. O texto
 * `"HH:MM"` não tem fuso: é a hora que o servidor já escolheu.
 */
export function formatClock(input: ClockInput, timeZone?: string): string {
  if (typeof input === "string") {
    const match = CONTRACT_CLOCK.exec(input.trim());
    if (match) return house(Number(match[1]), Number(match[2]));
  }
  const date = instant(input);
  if (!date) return "";
  const parts = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timeZone || undefined,
  }).formatToParts(date);
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value);
  return house(part("hour"), part("minute"));
}

/**
 * A hora com segundos, só onde o segundo É a informação (a leitura que prova
 * que a tela não parou, o prazo de poucos segundos): "12h45min30s".
 */
export function formatClockSeconds(input: ClockInput, timeZone?: string): string {
  const date = instant(input);
  if (!date) return "";
  const parts = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
    timeZone: timeZone || undefined,
  }).formatToParts(date);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  if (!part("hour") || !part("minute") || !part("second")) return "";
  return `${Number(part("hour"))}h${part("minute")}min${part("second")}s`;
}

/**
 * Data e hora juntas: `formatDateClock(at, { day: "2-digit", month: "2-digit" })`
 * dá "16/11, 12h45". `date` são as opções de DATA do `Intl` (dia, mês, ano, dia
 * da semana); a hora é sempre a da casa. `joiner` é o que vai entre as duas
 * (", " por padrão; " às " quando a frase pede).
 */
export function formatDateClock(
  input: ClockInput,
  date: Intl.DateTimeFormatOptions,
  options: { timeZone?: string; joiner?: string } = {},
): string {
  const at = instant(input);
  if (!at) return "";
  const day = new Intl.DateTimeFormat("pt-BR", {
    ...date,
    timeZone: options.timeZone || undefined,
  }).format(at);
  return `${day}${options.joiner ?? ", "}${formatClock(at, options.timeZone)}`;
}

/** "das 12h às 14h30": o intervalo, das duas pontas `"HH:MM"` ou de dois instantes. */
export function formatClockRange(start: ClockInput, end: ClockInput, timeZone?: string): string {
  const from = formatClock(start, timeZone);
  const to = formatClock(end, timeZone);
  if (!from || !to) return from || to;
  return `${from} às ${to}`;
}
