// Presentation — a seção Entregas (corridas da TaOn). Puro: a página e o espelho só
// desenham o que estas funções dizem. Desenho aprovado pelo dono em 14/11/2026
// (PR #2462): Aguardando · Editando · Corridas, cada corrida com a sua letra e cor.
import type {
  DeliveryRideProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import { moneyInput } from "../../../operator-kit/app/presentation/custody";
import { clockHHMM } from "../../../operator-kit/app/presentation/courierProgress";

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
    case "late":
      return { icon: "i-lucide-hourglass", title: "Ninguém aceitou ainda", hint: missing };
    case "coming": {
      const minutes = ride.pickup_eta_at ? minutesUntil(ride.pickup_eta_at, now) : null;
      return {
        icon: "i-lucide-bike",
        title: minutes === null ? `${who} vem para a loja` : minutes <= 1 ? `${who} está chegando` : `${who} chega em ${minutes} min`,
        hint: missing || (ride.bags ? `Separe ${bagsWord(ride.bags)} no balcão de saída` : ""),
      };
    }
    case "atStore":
      return { icon: "i-lucide-store", title: `${who} está na loja`, hint: missing };
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

/** As sacolas só importam até saírem da loja. */
export function beforeHandoff(ride: Pick<DeliveryRideProjection, "state">): boolean {
  return ["searching", "late", "coming", "atStore"].includes(ride.state);
}

/** O link do WhatsApp do entregador (só dígitos, com o 55 do Brasil). */
export function whatsappLink(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (!digits) return "";
  return `https://wa.me/${digits.startsWith("55") ? digits : `55${digits}`}`;
}
