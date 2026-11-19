// Presentation — a seção Entregas (corridas da TaOn). Puro: a página e o espelho só
// desenham o que estas funções dizem. Desenho aprovado pelo dono em 14/11/2026
// (PR #2462): Aguardando · Editando · Corridas, cada corrida com a sua letra e cor.
import type {
  Action,
  DeliveryRideProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import { moneyInput } from "../../../operator-kit/app/presentation/custody";
import {
  courierChargeNotice,
  type CourierChargeNotice,
  type CourierChargeOutdated,
} from "../../../operator-kit/app/presentation/courierCharge";
import {
  clockHHMM,
  GROUPED_HINT,
  GROUPED_TITLE,
  REOPENED_HINT,
  TRANSFER_HINT,
  TRANSFER_TITLE,
  withdrawalTitle,
} from "../../../operator-kit/app/presentation/courierProgress";

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
 * O que vai à TaOn para cada corrida editada com pelo menos um pedido. O troco
 * sugerido da gaveta vai como está (o mesmo do Painel); a maquininha só quando
 * algum pedido é de cartão na porta. Na ordem dos números: o servidor dá o
 * menor livre a quem chama primeiro, e a corrida fica com o número que mostrava.
 */
export function rideCalls(
  editing: readonly EditingRide[],
  stops: readonly DeliveryStopProjection[],
  machineRef: string,
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
            .filter((stop) => stop.change_out_suggested_q > 0)
            .map((stop) => [stop.ref, moneyInput(stop.change_out_suggested_q)]),
        ),
        machine: chosen.some((stop) => stop.needs_machine) ? machineRef : "",
      };
    });
}

/** Alguma corrida editada leva a maquininha da casa. */
export function needsMachine(
  editing: readonly EditingRide[],
  stops: readonly DeliveryStopProjection[],
): boolean {
  const refs = new Set(editing.flatMap((ride) => ride.refs));
  return stops.some((stop) => refs.has(stop.ref) && stop.needs_machine);
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
        return { icon: "i-lucide-repeat", title: TRANSFER_TITLE, hint: TRANSFER_HINT };
      const at = Date.parse(ride.reopened_at);
      return {
        icon: "i-lucide-user-x",
        title: Number.isFinite(at) ? withdrawalTitle(ride.reopened_driver, at) : ride.status_label,
        hint: REOPENED_HINT,
      };
    }
    case "grouped":
      return { icon: "i-lucide-link", title: GROUPED_TITLE, hint: GROUPED_HINT };
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
  if (ride.open_too_long)
    return {
      key: "open_too_long",
      color: "warning",
      icon: "i-lucide-clock-alert",
      title: "Corrida aberta há muito tempo.",
      description:
        "A TaOn ainda não encerrou esta corrida. Confira no painel da central se ela já terminou; a tela segue perguntando a cada 10 min.",
    };
  if (ride.state === "atStore" && ride.waited_pickup_at)
    return {
      key: `waited:${ride.waited_pickup_at}`,
      color: "warning",
      icon: "i-lucide-timer",
      title: `${line.title}.`,
      description: line.hint
        ? `A TaOn avisou que a espera passou do combinado. ${line.hint}.`
        : "A TaOn avisou que a espera passou do combinado.",
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
        "A TaOn cuida desta entrega junto com a outra corrida. Quando ela disser quem leva, o nome aparece aqui.",
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
 * A TaOn parou de informar a corrida: a frase do Painel do pedido
 * (`courierProgress.stale`), para as duas telas dizerem o mesmo. Vazio com a
 * leitura em dia e depois que tudo foi entregue.
 */
export function rideStale(ride: Pick<DeliveryRideProjection, "sync_since" | "state">): string {
  if (ride.state === "back") return "";
  const since = Date.parse(ride.sync_since ?? "");
  return Number.isFinite(since) ? `A TaOn não informa a corrida desde ${clockHHMM(since)}.` : "";
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
  ride: Pick<DeliveryRideProjection, "stops" | "cancel_action">,
): RideChargeNotice[] {
  return ride.stops.flatMap((stop) => {
    const outdated = stop.charge_outdated as unknown as CourierChargeOutdated | null | undefined;
    const notice = courierChargeNotice(outdated, { cancelHere: Boolean(ride.cancel_action) });
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
