// Presentation — a seção Entregas (corridas da TaOn). Puro: a página e o espelho só
// desenham o que estas funções dizem. Desenho aprovado pelo dono em 14/11/2026
// (PR #2462): Aguardando · Editando · Corridas, cada corrida com a sua letra e cor.
import type {
  Action,
  DeliveryRideProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import { moneyInput } from "../../../operator-kit/app/presentation/custody";
import { formatBRL } from "../../../operator-kit/app/utils/money";
import {
  courierChargeNotice,
  type CourierChargeNotice,
  type CourierChargeOutdated,
} from "../../../operator-kit/app/presentation/courierCharge";
import {
  clockHHMM,
  GROUPED_HINT,
  groupedTitle,
  reopenedHint,
  TRANSFER_HINT,
  transferTitle,
  withdrawalTitle,
} from "../../../operator-kit/app/presentation/courierProgress";
import { deliveryServiceName } from "../../../operator-kit/app/presentation/deliveryService";

/** Uma corrida que o operador está juntando, antes de chamar (estado só da tela). */
export interface EditingRide {
  number: number;
  refs: string[];
}

/**
 * A letra da corrida, como o operador a chama: 1 é A, 2 é B, 26 é Z. Corrida se
 * nomeia por letra em toda tela (decisão do dono, 16/11/2026); o número segue
 * sendo o que o servidor grava e o que escolhe a cor. Espelha `courier.ride_letter`.
 */
export function rideLetter(number: number | null | undefined): string {
  if (typeof number !== "number" || !Number.isInteger(number) || number < 1) return "";
  return String.fromCharCode(65 + ((number - 1) % 26));
}

/**
 * O menor número livre para uma corrida em edição: dos que o servidor diz livres
 * (`free_numbers`, as corridas na rua já descontadas, até 26 letras), o primeiro
 * que nenhuma corrida em edição pegou. Quem grava o número é a chamada; a tela
 * manda o que mostrava e o servidor o mantém se continuar livre.
 */
export function nextFreeNumber(
  free: readonly number[],
  editing: readonly number[],
): number | null {
  for (const n of free) if (!editing.includes(n)) return n;
  return null;
}

/** As sacolas, como o balcão fala. */
export function bagsWord(n: number): string {
  return n === 1 ? "1 sacola" : `${n} sacolas`;
}

/** "Entreguei as 3 sacolas" / "Entreguei a sacola". */
export function handoffLabel(n: number): string {
  return n === 1 ? "Entreguei a sacola" : `Entreguei as ${n} sacolas`;
}

export interface RideCall {
  /** single: um pedido (``courier-dispatch``); group: vários (``courier-ride``). */
  kind: "single" | "group";
  /** O número (letra e cor) que a corrida tinha na edição. */
  number: number;
  refs: string[];
  change_out: Record<string, string>;
  machine: string;
}

/**
 * As chamadas, uma por corrida em edição. Cada corrida leva a SUA maquininha
 * (`machines[number]`, P1-12: antes uma só ia para todas) e o troco que o operador
 * conferiu (`change[ref]`, quando ele mexeu; senão o sugerido).
 */
export function rideCalls(
  editing: readonly EditingRide[],
  stops: readonly DeliveryStopProjection[],
  machines: Readonly<Record<number, string>>,
  change: Readonly<Record<string, string>> = {},
): RideCall[] {
  const byRef = new Map(stops.map((stop) => [stop.ref, stop]));
  return editing
    .filter((ride) => ride.refs.length > 0)
    .sort((a, b) => a.number - b.number)
    .map((ride) => {
      const chosen = ride.refs
        .map((ref) => byRef.get(ref))
        .filter((stop): stop is DeliveryStopProjection => Boolean(stop));
      return {
        kind: chosen.length > 1 ? "group" : "single",
        number: ride.number,
        refs: chosen.map((stop) => stop.ref),
        change_out: Object.fromEntries(
          chosen
            .map((stop) => [stop.ref, changeValue(stop, change)] as const)
            .filter(([, value]) => value !== ""),
        ),
        machine: chosen.some((stop) => stop.needs_machine) ? (machines[ride.number] ?? "") : "",
      };
    });
}

/** O troco que vai com o pedido: o que o operador digitou, ou o sugerido. */
export function changeValue(
  stop: Pick<DeliveryStopProjection, "ref" | "change_out_suggested_q">,
  change: Readonly<Record<string, string>>,
): string {
  if (stop.ref in change) return change[stop.ref]!.trim();
  return stop.change_out_suggested_q > 0 ? moneyInput(stop.change_out_suggested_q) : "";
}

/** As corridas em edição que levam cartão (alguma parada pede a maquininha). */
export function ridesNeedingMachine(
  editing: readonly EditingRide[],
  stops: readonly DeliveryStopProjection[],
): number[] {
  const needs = new Set(stops.filter((stop) => stop.needs_machine).map((stop) => stop.ref));
  return editing
    .filter((ride) => ride.refs.some((ref) => needs.has(ref)))
    .map((ride) => ride.number)
    .sort((a, b) => a - b);
}

/**
 * Uma maquininha DIFERENTE para cada corrida que leva cartão (P1-12). Mantém o que
 * o operador já escolheu quando ainda vale e não repete; o resto recebe a próxima
 * livre, na ordem das letras. Corrida sem maquininha livre fica com "".
 */
export function assignMachines(
  needing: readonly number[],
  free: readonly string[],
  current: Readonly<Record<number, string>> = {},
): Record<number, string> {
  const out: Record<number, string> = {};
  const taken = new Set<string>();
  for (const number of needing) {
    const mine = current[number];
    if (mine && free.includes(mine) && !taken.has(mine)) {
      out[number] = mine;
      taken.add(mine);
    }
  }
  for (const number of needing) {
    if (out[number]) continue;
    const next = free.find((ref) => !taken.has(ref));
    out[number] = next ?? "";
    if (next) taken.add(next);
  }
  return out;
}

/** "Faltam maquininhas: 2 corridas levam cartão e só 1 está livre." ("" quando dá.) */
export function machineShortfall(needing: number, free: number): string {
  if (needing <= free) return "";
  const rides = `${needing} corridas levam cartão`;
  if (free === 0) return `Faltam maquininhas: ${rides} e nenhuma está livre.`;
  return `Faltam maquininhas: ${rides} e só ${free} ${free === 1 ? "está livre" : "estão livres"}.`;
}

// ── ordem do percurso ───────────────────────────────────────────────────────

export interface RoutePoint {
  ref: string;
  latitude: number | null;
  longitude: number | null;
}

/**
 * As paradas na ordem que o entregador segue: a mais perto da loja, depois a mais
 * perto dessa, e assim por diante. ESPELHO de ``courier._route`` (o servidor manda
 * esta ordem à TaOn): distância plana em graus, empate fica com quem veio antes,
 * parada sem coordenada no fim. A fixture ``tests/fixtures/route-order.json`` roda
 * nos dois lados (vitest e pytest), para os dois nunca discordarem.
 */
export function routeOrder<T extends RoutePoint>(
  origin: { latitude: number; longitude: number } | null,
  stops: readonly T[],
): T[] {
  if (!origin) return [...stops];
  const located = stops.filter((stop) => stop.latitude !== null && stop.longitude !== null);
  const rest = stops.filter((stop) => !located.includes(stop));
  const route: T[] = [];
  let here: [number, number] = [origin.latitude, origin.longitude];
  while (located.length) {
    let best = 0;
    let bestDistance = Infinity;
    located.forEach((stop, index) => {
      const distance = (stop.latitude! - here[0]) ** 2 + (stop.longitude! - here[1]) ** 2;
      if (distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    });
    const [nearest] = located.splice(best, 1);
    route.push(nearest!);
    here = [nearest!.latitude!, nearest!.longitude!];
  }
  return [...route, ...rest];
}

// ── cotação ─────────────────────────────────────────────────────────────────

/** "R$ 15,00" com espaço comum, como o `display` que o servidor manda na mesma linha. */
function money(amountQ: number): string {
  return formatBRL(amountQ).replace(/\u00a0/g, " ");
}

export interface EditingQuote {
  value_q: number;
  /** "R$ 16,50 · 24 min · 5,7 km · ida e volta" */
  display: string;
  stops: string[];
  separate_value_q?: number;
  saving_q?: number;
}

export interface QuoteLine {
  text: string;
  /** A linha que vale (a mais barata, com ✔): em destaque; a outra esmaece. */
  strong: boolean;
}

/**
 * A cotação da corrida em duas linhas, com o ✔ na mais barata (regra do dono,
 * 16/11): "Juntas: R$ 10,00 · 10 min · 5 km ✔" / "Separadas sairiam R$ 15,00", ou
 * "Juntas: …" / "Separadas sai mais barato: R$ 7,00 ✔". Uma parada só: uma linha.
 * Sem cotação: a frase do servidor, e a chamada continua possível.
 */
export function quoteLines(
  quote: EditingQuote | null,
  stopCount: number,
  failure = "",
): QuoteLine[] {
  if (!quote) return failure ? [{ text: failure, strong: false }] : [];
  if (stopCount < 2) return [{ text: quote.display, strong: true }];
  if (quote.separate_value_q === undefined || quote.saving_q === undefined)
    return [{ text: `Juntas: ${quote.display}`, strong: true }];
  const separate = money(quote.separate_value_q);
  if (quote.saving_q >= 0)
    return [
      { text: `Juntas: ${quote.display} ✔`, strong: true },
      { text: `Separadas sairiam ${separate}`, strong: false },
    ];
  return [
    { text: `Juntas: ${quote.display}`, strong: false },
    { text: `Separadas sai mais barato: ${separate} ✔`, strong: true },
  ];
}

/**
 * "5 pedidos em 2 corridas · R$ 31,30": o total só quando TODAS as corridas
 * cotaram (soma com buraco mente).
 */
export function callSummary(
  orders: number,
  rides: number,
  quotes: readonly (EditingQuote | null)[],
): string {
  const head = `${orders} ${orders === 1 ? "pedido" : "pedidos"} em ${rides} ${rides === 1 ? "corrida" : "corridas"}`;
  if (!quotes.length || quotes.length !== rides || quotes.some((quote) => !quote)) return head;
  return `${head} · ${money(quotes.reduce((sum, quote) => sum + quote!.value_q, 0))}`;
}

// ── balanço por corrida ─────────────────────────────────────────────────────

export interface RideFailure {
  number: number;
  refs: string[];
  /** "A corrida B não abriu (A47, C03)" */
  title: string;
  /** A frase do servidor (ou a genérica, sem rede). */
  detail: string;
}

/**
 * Depois de uma chamada que falhou: seguir para a próxima corrida ou parar. A
 * recusa do servidor (4xx) é DESTA corrida, e as outras seguem; sem rede ou com o
 * servidor fora (5xx, status 0), a próxima falharia igual, e para.
 */
export function failureStops(status: number): boolean {
  return !(status >= 400 && status < 500);
}

export function rideFailureTitle(number: number, codes: readonly string[]): string {
  return `A corrida ${rideLetter(number)} não abriu (${codes.join(", ")})`;
}

function minutesUntil(iso: string, now: number): number | null {
  const at = Date.parse(iso);
  return Number.isFinite(at) ? Math.max(0, Math.round((at - now) / 60000)) : null;
}

/** Minutos inteiros desde um instante (0 quando ilegível ou no futuro). */
function minutesSince(iso: string, now: number): number {
  const at = Date.parse(iso);
  return Number.isFinite(at) ? Math.max(0, Math.floor((now - at) / 60000)) : 0;
}

export interface RideLine {
  icon: string;
  title: string;
  hint: string;
}

/** O momento da corrida numa linha: o título e o que importa agora. */
export function rideLine(ride: DeliveryRideProjection, now: number): RideLine {
  const who = ride.driver?.name || "O entregador";
  const pending = ride.stops.filter((stop) => !stop.done);
  const done = ride.stops.length - pending.length;
  const missing = ride.undeclared.length
    ? `Falta dizer quantas sacolas: ${ride.undeclared.join(", ")}`
    : "";
  switch (ride.state) {
    case "searching":
      return { icon: "i-lucide-radar", title: "Procurando entregador", hint: missing };
    case "late": {
      // Com os minutos: "Ninguém aceitou em 12 min" diz se é hora de olhar a central.
      const called = Date.parse(ride.called_at);
      const minutes = Number.isFinite(called) ? Math.max(0, Math.floor((now - called) / 60000)) : null;
      return {
        icon: "i-lucide-hourglass",
        title: minutes ? `Ninguém aceitou em ${minutes} min` : "Ninguém aceitou ainda",
        hint: missing,
      };
    }
    case "reopened": {
      // O entregador desistiu, ou a TaOn está trocando o entregador, e ela
      // redistribui a MESMA corrida: nada a chamar.
      if (ride.reopened_reason === "transfer")
        return { icon: "i-lucide-repeat", title: transferTitle(ride.service_name), hint: TRANSFER_HINT };
      const at = Date.parse(ride.reopened_at);
      return {
        icon: "i-lucide-user-x",
        title: Number.isFinite(at) ? withdrawalTitle(ride.reopened_driver, at) : ride.status_label,
        hint: reopenedHint(ride.service_name),
      };
    }
    case "grouped":
      return { icon: "i-lucide-link", title: groupedTitle(ride.service_name), hint: GROUPED_HINT };
    case "coming": {
      const minutes = ride.pickup_eta_at ? minutesUntil(ride.pickup_eta_at, now) : null;
      return {
        icon: "i-lucide-bike",
        // Nas redondezas (``AN`` da TaOn), a previsão já não importa: está chegando.
        title: ride.near_pickup_at || (minutes !== null && minutes <= 1)
          ? `${who} está chegando`
          : minutes === null ? `${who} vem para a loja` : `${who} chega em ${minutes} min`,
        hint:
          missing ||
          (ride.bags
            ? ride.driver?.name
              ? `Separe ${bagsWord(ride.bags)} para ${ride.driver.name}`
              : `Separe ${bagsWord(ride.bags)} no balcão de saída`
            : ""),
      };
    }
    case "atStore": {
      // O relógio da espera no balcão conta da chegada (TAON-12).
      const waited = ride.arrived_pickup_at ? minutesSince(ride.arrived_pickup_at, now) : 0;
      const codes = pending.map((stop) => stop.code);
      return {
        icon: "i-lucide-store",
        title: waited >= 1 ? `${who} espera na loja há ${waited} min` : `${who} está na loja`,
        hint: missing || (ride.bags && codes.length ? `Entregue ${bagsWord(ride.bags)} de ${listCodes(codes)}` : ""),
      };
    }
    case "route":
      return {
        icon: "i-lucide-navigation",
        title: `${who} em rota`,
        hint: [
          `${done} de ${ride.stops.length} entregues`,
          ride.delivery_eta_at ? `termina por volta de ${clockHHMM(Date.parse(ride.delivery_eta_at))}` : "",
        ].filter(Boolean).join(" · "),
      };
    case "back":
      return { icon: "i-lucide-undo-2", title: "Tudo entregue", hint: `${who} está voltando` };
    default:
      return { icon: "i-lucide-bike", title: ride.status_label, hint: "" };
  }
}

/** Um motivo de cancelamento que a confirmação oferece: o botão já é o `reason_id`. */
export interface CancelReason {
  id: number;
  label: string;
  icon: string;
}

/** A confirmação de "Cancelar corrida", com as frases do servidor. */
export interface CancelConfirmation {
  /** "Cancelar a corrida B? A05 e C12 voltam para Aguardando." */
  question: string;
  /** "Cancelar a corrida B" */
  confirmLabel: string;
  /** Depois do aceite: "Por que cancelar a corrida B?" */
  reasonQuestion: string;
  /** "A05 e C12 voltam para Aguardando." */
  consequence: string;
  /** Vazio antes do aceite (a central só aceita um motivo, e ninguém escolhe). */
  reasons: CancelReason[];
}

/** O ícone de cada motivo que a casa oferece (`order_queue.COURIER_CANCEL_REASONS`). */
const CANCEL_REASON_ICONS: Record<number, string> = {
  12: "i-lucide-user-x",
  37: "i-lucide-timer-off",
  40: "i-lucide-phone-off",
};

/**
 * Lê `Action.confirmation` do "Cancelar corrida". O servidor manda as frases
 * (`courier_cancel_confirmation`); aqui só se dá forma, sem inventar motivo:
 * entrada sem `id` inteiro ou sem rótulo não vira botão.
 */
export function cancelConfirmation(
  action: Pick<Action, "confirmation" | "label"> | null | undefined,
): CancelConfirmation {
  const raw = (action?.confirmation ?? {}) as Record<string, unknown>;
  const text = (value: unknown) => (typeof value === "string" ? value : "");
  const reasons = (Array.isArray(raw.reasons) ? raw.reasons : [])
    .map((item) => item as { id?: unknown; label?: unknown })
    .filter((item) => Number.isInteger(item.id) && text(item.label))
    .map((item) => ({
      id: item.id as number,
      label: text(item.label),
      icon: CANCEL_REASON_ICONS[item.id as number] ?? "i-lucide-ban",
    }));
  return {
    question: text(raw.description) || "Cancelar a corrida?",
    confirmLabel: text(raw.confirm_label) || action?.label || "Cancelar corrida",
    reasonQuestion: text(raw.reason_question) || "Por que cancelar a corrida?",
    consequence: text(raw.consequence),
    reasons,
  };
}

/** As sacolas só importam até saírem da loja. */
export function beforeHandoff(ride: Pick<DeliveryRideProjection, "state">): boolean {
  return ["searching", "late", "reopened", "grouped", "coming", "atStore"].includes(ride.state);
}

export interface RideNotice {
  /** A causa: o aviso dispensado volta quando ela muda. */
  key: string;
  color: "info" | "neutral" | "warning";
  icon: string;
  title: string;
  description: string;
  /** O rodapé do detalhe, no lugar da frase de cancelar (sem ele, fica a de sempre). */
  footer?: string;
}


/** "A47", "A47 e C03", "A47, C03 e D12". */
export function listCodes(codes: readonly string[]): string {
  return codes.length > 1 ? `${codes.slice(0, -1).join(", ")} e ${codes.at(-1)}` : (codes[0] ?? "");
}

/**
 * A corrida segue chamada e não há o que fazer: o entregador desistiu (a TaOn
 * redistribui a mesma corrida) ou a TaOn a juntou a outra. O aviso existe para
 * o operador NÃO chamar de novo: seria uma segunda corrida paga.
 */
export function rideNotice(ride: DeliveryRideProjection, now: number): RideNotice | null {
  const line = rideLine(ride, now);
  const service = deliveryServiceName(ride.service_name);
  if (ride.open_too_long)
    return {
      key: "open_too_long",
      color: "warning",
      icon: "i-lucide-clock-alert",
      title: "Corrida aberta há muito tempo.",
      description:
        `A ${service} ainda não encerrou esta corrida. Confira no painel da central se ela já terminou; a tela segue perguntando a cada 10 min.`,
    };
  if (ride.state === "atStore" && ride.waited_pickup_at)
    return {
      key: `waited:${ride.waited_pickup_at}`,
      color: "warning",
      icon: "i-lucide-timer",
      title: `${line.title}.`,
      description: line.hint
        ? `A ${service} avisou que a espera passou do combinado. ${line.hint}.`
        : `A ${service} avisou que a espera passou do combinado.`,
    };
  if (ride.state === "reopened")
    return {
      key: `reopened:${ride.reopened_at}`,
      color: "info",
      icon: line.icon,
      title: `${line.title}. ${line.hint}.`,
      description:
        "A corrida continua chamada, com as mesmas paradas. Chamar de novo faria uma segunda corrida paga.",
      footer: "Nada a fazer agora. Quando outro entregador aceitar, o nome dele aparece aqui.",
    };
  if (ride.state === "grouped") {
    const codes = ride.stops.map((stop) => stop.code);
    const who =
      codes.length > 1
        ? `${codes.slice(0, -1).join(", ")} e ${codes.at(-1)} foram`
        : `${codes[0] ?? "O pedido"} foi`;
    return {
      key: "grouped",
      color: "neutral",
      icon: line.icon,
      title: `${line.title}.`,
      description: `${who} para uma corrida que já tem entregador. Não precisa chamar de novo.`,
      footer:
        `A ${service} cuida desta entrega junto com a outra corrida. Quando ela disser quem leva, o nome aparece aqui.`,
    };
  }
  return null;
}

/** O link do WhatsApp do entregador (só dígitos, com o 55 do Brasil). */
export function whatsappLink(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (!digits) return "";
  return `https://wa.me/${digits.startsWith("55") ? digits : `55${digits}`}`;
}

/**
 * O serviço parou de informar a corrida: a frase do Painel do pedido
 * (`courierProgress.stale`), para as duas telas dizerem o mesmo. Vazio com a
 * leitura em dia e depois que tudo foi entregue.
 */
export function rideStale(ride: Pick<DeliveryRideProjection, "sync_since" | "state" | "service_name">): string {
  if (ride.state === "back") return "";
  const since = Date.parse(ride.sync_since ?? "");
  return Number.isFinite(since)
    ? `A ${deliveryServiceName(ride.service_name)} não informa a corrida desde ${clockHHMM(since)}.`
    : "";
}

export interface RideChargeNotice extends CourierChargeNotice {
  code: string;
  /** O entregador já coletou: o gesto é ligar para ele. */
  collected: boolean;
}

/**
 * As paradas cuja cobrança ficou para trás (o pedido mudou depois da chamada), com
 * a frase do Painel (`courierChargeNotice`). Na página, cancelar mora no detalhe.
 */
export function rideChargeNotices(
  ride: Pick<DeliveryRideProjection, "stops" | "cancel_action" | "service_name">,
): RideChargeNotice[] {
  return ride.stops.flatMap((stop) => {
    const outdated = stop.charge_outdated as unknown as CourierChargeOutdated | null | undefined;
    const notice = courierChargeNotice(outdated, { cancelHere: Boolean(ride.cancel_action), service: ride.service_name });
    return notice && !stop.done
      ? [{ ...notice, title: `${stop.code}: ${notice.title.toLowerCase()}`, code: stop.code, collected: Boolean(outdated?.collected) }]
      : [];
  });
}

/** O que o diálogo "Entregador voltou" confere: os pedidos da corrida e o que volta na mão. */
export function backCheck(ride: Pick<DeliveryRideProjection, "stops" | "back_lines">) {
  return {
    courier_return_orders: ride.stops.map((stop) => stop.ref),
    courier_return_lines: [...ride.back_lines],
  };
}

export interface ToggleResult {
  editing: EditingRide[];
  active: number;
  /** O que o toque não fez como pedido, em uma frase ("" quando fez). */
  notice: string;
}

/**
 * O toque num pedido de Aguardando. Pedido que não vai em corrida nenhuma
 * (`group_refusal`, chamada sem resposta) não entra, e a frase diz por quê. A
 * corrida ativa cheia não engole o toque em silêncio: o pedido vai para a próxima
 * corrida com lugar (ou uma nova), e a frase diz para qual.
 */
export function toggleStop(
  editing: readonly EditingRide[],
  active: number,
  ref: string,
  stops: readonly DeliveryStopProjection[],
  maxStops: number,
  free: readonly number[],
): ToggleResult {
  const stop = stops.find((item) => item.ref === ref);
  const rides = editing.map((ride) => ({ number: ride.number, refs: [...ride.refs] }));
  if (!stop) return { editing: rides, active, notice: "" };
  if (stop.dispatch_again_action || stop.group_refusal)
    return { editing: rides, active, notice: stop.group_refusal || stop.error };
  let mine = rides.find((ride) => ride.number === active);
  if (!mine) {
    const number = nextFreeNumber(free, rides.map((ride) => ride.number)) ?? 1;
    mine = { number, refs: [] };
    rides.push(mine);
    active = number;
  }
  const at = rides.find((ride) => ride.refs.includes(ref));
  if (at === mine) {
    mine.refs = mine.refs.filter((item) => item !== ref);
    return { editing: rides, active, notice: "" };
  }
  if (mine.refs.length >= maxStops) {
    const full = `A corrida ${rideLetter(mine.number)} já tem ${maxStops} pedidos.`;
    let other = rides.find((ride) => ride !== mine && ride !== at && ride.refs.length < maxStops);
    if (!other) {
      const number = nextFreeNumber(free, rides.map((ride) => ride.number));
      if (!number) return { editing: rides, active, notice: `${full} Tire um para pôr ${stop.code}.` };
      other = { number, refs: [] };
      rides.push(other);
    }
    if (at) at.refs = at.refs.filter((item) => item !== ref);
    other.refs = [...other.refs, ref];
    return {
      editing: rides,
      active: other.number,
      notice: `${full} ${stop.code} foi para a corrida ${rideLetter(other.number)}.`,
    };
  }
  if (at) at.refs = at.refs.filter((item) => item !== ref);
  mine.refs = [...mine.refs, ref];
  return { editing: rides, active, notice: "" };
}

// ── sugestões da casa (ride_plan, F5) ───────────────────────────────────────

/** A sugestão do plano, como a página a lê (`RideSuggestionProjection`). */
export interface RideSuggestion {
  key: string;
  refs: readonly string[];
  codes: readonly string[];
  places: string;
  quoted: boolean;
  suggested: boolean;
  late_code: string;
  late_minutes: number;
  together_q: number | null;
  minutes: number | null;
  km: number | null;
  with_return: boolean;
  separate_q: number | null;
  saving_q: number | null;
}

function kmText(km: number): string {
  return `${km.toFixed(1).replace(".", ",")} km`;
}

/** "R$ 11,00 · 18 min · 7,4 km · ida e volta": o mesmo desenho da cotação da corrida. */
function togetherDisplay(valueQ: number, minutes: number | null, km: number | null, withReturn: boolean): string {
  return [
    money(valueQ),
    minutes !== null ? `${minutes} min` : "",
    km !== null ? kmText(km) : "",
    withReturn ? "ida e volta" : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * A cotação da sugestão em duas linhas, a junta em destaque com o ✔ e a separada
 * esmaecida (regra do dono, 16/11). Só leitura: quem decide é o gesto. Sem cotação,
 * nenhuma linha (a tela diz que a central não cotou).
 */
export function suggestionQuoteLines(suggestion: RideSuggestion): QuoteLine[] {
  if (!suggestion.quoted || suggestion.together_q === null || suggestion.separate_q === null) return [];
  return quoteLines(
    {
      value_q: suggestion.together_q,
      display: togetherDisplay(suggestion.together_q, suggestion.minutes, suggestion.km, suggestion.with_return),
      stops: [...suggestion.refs],
      separate_value_q: suggestion.separate_q,
      saving_q: suggestion.saving_q ?? undefined,
    },
    suggestion.refs.length,
  );
}

/**
 * A etiqueta da rota sugerida no mapa (#2874): os códigos juntados e, cotada, o preço
 * das juntas ("A47 + C03 · R$ 16,50"). Sem cotação, só os códigos: o mapa não inventa preço.
 */
export function suggestionMapLabel(suggestion: Pick<RideSuggestion, "codes" | "quoted" | "together_q">): string {
  const codes = suggestion.codes.join(" + ");
  return suggestion.quoted && suggestion.together_q !== null ? `${codes} · ${money(suggestion.together_q)}` : codes;
}

/** "C03 chega uns 6 min depois.": quem mais espera a mais por ir junto. */
export function suggestionLate(suggestion: Pick<RideSuggestion, "late_code" | "late_minutes">): string {
  if (!suggestion.late_code || suggestion.late_minutes < 1) return "";
  return `${suggestion.late_code} chega uns ${suggestion.late_minutes} min depois.`;
}

/**
 * As sugestões que a tela mostra: nenhuma com pedido que o operador já pôs numa
 * corrida (aceitar soma, nunca apaga) e nenhuma que ele dispensou ("Agora não").
 */
export function visibleSuggestions(
  suggestions: readonly RideSuggestion[],
  editing: readonly EditingRide[],
  dismissed: readonly string[],
): RideSuggestion[] {
  const taken = new Set(editing.flatMap((ride) => ride.refs));
  return suggestions.filter(
    (suggestion) => !dismissed.includes(suggestion.key) && suggestion.refs.every((ref) => !taken.has(ref)),
  );
}

/**
 * O título do cartão: "2 corridas sugeridas: 5 pedidos." Com mais de uma e TODAS
 * cotadas, o total em duas linhas (juntas × separadas); soma com buraco mente.
 */
export function suggestionsHeadline(suggestions: readonly RideSuggestion[]): { title: string; lines: QuoteLine[] } {
  const orders = suggestions.reduce((sum, item) => sum + item.refs.length, 0);
  const rides = suggestions.length;
  const title = `${rides} ${rides === 1 ? "corrida sugerida" : "corridas sugeridas"}: ${orders} pedidos.`;
  if (rides < 2 || suggestions.some((item) => !item.quoted || item.together_q === null || item.separate_q === null))
    return { title, lines: [] };
  const together = suggestions.reduce((sum, item) => sum + item.together_q!, 0);
  const separate = suggestions.reduce((sum, item) => sum + item.separate_q!, 0);
  return {
    title,
    lines: quoteLines(
      {
        value_q: together,
        display: money(together),
        stops: suggestions.flatMap((item) => [...item.refs]),
        separate_value_q: separate,
        saving_q: separate - together,
      },
      orders,
    ),
  };
}

/** "Chamar as 2 corridas": só com mais de uma e todas cotadas e marcadas. */
export function callAllLabel(suggestions: readonly RideSuggestion[]): string {
  if (suggestions.length < 2 || suggestions.some((item) => !item.suggested)) return "";
  return `Chamar as ${suggestions.length} corridas`;
}

/**
 * As sugestões aceitas viram corridas em edição, cada uma com a próxima letra livre,
 * SOMADAS às que o operador já monta. `null` quando faltam letras.
 */
export function ridesFromSuggestions(
  suggestions: readonly RideSuggestion[],
  free: readonly number[],
  editing: readonly EditingRide[],
): EditingRide[] | null {
  const taken = editing.map((ride) => ride.number);
  const rides: EditingRide[] = [];
  for (const suggestion of suggestions) {
    const number = nextFreeNumber(free, [...taken, ...rides.map((ride) => ride.number)]);
    if (number === null) return null;
    rides.push({ number, refs: [...suggestion.refs] });
  }
  return rides;
}
