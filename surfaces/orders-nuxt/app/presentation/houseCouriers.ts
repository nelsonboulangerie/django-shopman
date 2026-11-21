// Presentation — "Quem leva" (DEV-2026-030, frente M3, #2526).
//
// O operador escolhe quem leva no MESMO gesto de chamar: o serviço padrão do Admin (hoje
// a TaOn) vem marcado; os entregadores da casa na escala de hoje aparecem como opção, a
// um toque. Sem ninguém da casa na escala (ou o serviço da casa desligado), a linha não
// existe e a tela é a de antes. Tudo aqui é puro: a página busca, isto só decide o que
// desenhar e o que enviar.
import type { Action, DeliveryRideProjection, DeliveryStopProjection } from "~/generated/ordersContract";
import { formatBRL } from "../../../operator-kit/app/utils/money";
import type { QuoteLine } from "~/presentation/deliveries";

export const HOUSE_RIDE_PATH = "/api/v1/backstage/deliveries/couriers/ride/";
export const HOUSE_CREW_PATH = "/api/v1/backstage/deliveries/couriers/";
export const houseShiftPath = (ref: string) =>
  `/api/v1/backstage/deliveries/couriers/${encodeURIComponent(ref)}/shift/`;

/** A chave do chip do serviço padrão. Entregador da casa usa o próprio `ref`. */
export const DEFAULT_CARRIER = "";

export interface HouseCourier {
  ref: string;
  name: string;
  on_shift: boolean;
  state: "free" | "busy";
  /** "Livre" ou "Na rua". */
  state_label: string;
  value_q: number | null;
  /** "R$ 15,00", ou vazio sem valor na tabela. */
  value: string;
}

export interface HouseCrew {
  active: boolean;
  service: { ref: string; name: string } | null;
  default: { ref: string; name: string } | null;
  couriers: HouseCourier[];
}

export interface CarrierChip {
  /** `DEFAULT_CARRIER` para o serviço padrão; o `ref` do entregador para a casa. */
  key: string;
  label: string;
  /** "Livre", "Na rua"; vazio no chip do serviço. */
  state: string;
  /** "R$ 11,00", "Sem cotação agora", "Cotando…", ou vazio. */
  value: string;
  busy: boolean;
  /** O marcado: leva o ✔ no fim da linha, como a cotação juntas×separadas (dono, 16/11). */
  chosen: boolean;
}

/** O que a casa respondeu ao enviar a corrida. */
export interface HouseRideResult {
  outcome?: string;
  detail?: string;
  ride_ref?: string;
  link_url?: string;
  whatsapp_url?: string;
  ride_number?: number | null;
  ride_letter?: string;
}

function money(amountQ: number): string {
  return formatBRL(amountQ).replace(/\u00a0/g, " ");
}

/** Quem da casa está na escala de hoje (a linha "Quem leva" só existe com alguém). */
export function onShift(crew: HouseCrew | null | undefined): HouseCourier[] {
  if (!crew?.active) return [];
  return crew.couriers.filter((courier) => courier.on_shift);
}

/**
 * Os chips de uma corrida: o serviço padrão primeiro, com a cotação dele, e depois cada
 * pessoa da casa na escala, com o estado e o valor da tabela para ESTA rota. Vazio quando
 * não há ninguém da casa na escala: a tela fica como era.
 */
export function carrierChips(
  crew: HouseCrew | null | undefined,
  ride: {
    quoteQ: number | null;
    quoting: boolean;
    values?: Readonly<Record<string, string>>;
    /** O chip marcado (`DEFAULT_CARRIER` ou o `ref` da pessoa). */
    chosen?: string;
  },
): CarrierChip[] {
  const people = onShift(crew);
  if (!people.length) return [];
  const service: CarrierChip = {
    key: DEFAULT_CARRIER,
    label: crew?.default?.name || "Central",
    state: "",
    value: ride.quoting ? "Cotando…" : ride.quoteQ !== null ? money(ride.quoteQ) : "Sem cotação agora",
    busy: false,
    chosen: (ride.chosen ?? DEFAULT_CARRIER) === DEFAULT_CARRIER,
  };
  return [
    service,
    ...people.map((courier) => ({
      key: courier.ref,
      label: courier.name,
      state: courier.state_label,
      value: ride.values?.[courier.ref] ?? courier.value,
      busy: courier.state === "busy",
      chosen: ride.chosen === courier.ref,
    })),
  ];
}

/** A linha de baixo do chip: "Livre · R$ 15,00", com o ✔ no fim quando é o marcado. */
export function chipLine(chip: CarrierChip): string {
  const line = [chip.state, chip.value].filter(Boolean).join(" · ");
  return chip.chosen ? `${line} ✔` : line;
}

/**
 * Quanto custa a corrida para quem leva: a casa pela tabela, o serviço pela cotação.
 * `null` quando o valor de quem leva ainda não existe (nunca o de outro serviço).
 */
export function rideValueQ(ride: {
  house: boolean;
  houseValueQ?: number | null;
  quoteQ?: number | null;
}): number | null {
  const value = ride.house ? ride.houseValueQ : ride.quoteQ;
  return typeof value === "number" ? value : null;
}

/**
 * "2 pedidos em 1 corrida · R$ 15,00": o total soma o valor de CADA corrida pelo
 * serviço que a leva (TaOn pela cotação, a casa pela tabela). Faltou um, sem total:
 * soma com buraco mente.
 */
export function callSummaryByCarrier(orders: number, rides: number, values: readonly (number | null)[]): string {
  const head = `${orders} ${orders === 1 ? "pedido" : "pedidos"} em ${rides} ${rides === 1 ? "corrida" : "corridas"}`;
  if (!values.length || values.length !== rides || values.some((value) => value === null)) return head;
  return `${head} · ${money(values.reduce<number>((sum, value) => sum + (value ?? 0), 0))}`;
}

/** O total do sheet quando alguma corrida é da casa: uma linha, a soma por quem leva. */
export function mixedTotalLines(values: readonly (number | null)[]): QuoteLine[] {
  if (!values.length || values.some((value) => value === null)) return [];
  return [{ text: `Total: ${money(values.reduce<number>((sum, value) => sum + (value ?? 0), 0))}`, strong: true }];
}

/** O chip marcado: a escolha do operador, se a pessoa ainda está na escala; senão o padrão. */
export function chosenCarrier(
  crew: HouseCrew | null | undefined,
  choice: string | undefined,
): HouseCourier | null {
  if (!choice) return null;
  return onShift(crew).find((courier) => courier.ref === choice) ?? null;
}

/** A cotação de quem é da casa: uma linha, o valor da tabela. */
export function houseQuoteLines(value: string): QuoteLine[] {
  return value
    ? [{ text: `Valor da tabela: ${value}`, strong: true }]
    : [{ text: "Sem valor na tabela para esta rota. Confira a tabela no Admin.", strong: false }];
}

/** "A47", "A47 e C03", "A47, B12 e C03". */
export function joinCodes(codes: readonly string[]): string {
  if (codes.length <= 1) return codes[0] ?? "";
  return `${codes.slice(0, -1).join(", ")} e ${codes[codes.length - 1]}`;
}

/** O botão diz o que acontece: "Enviar para Diego: A47 e C03". */
export function sendLabel(name: string, codes: readonly string[]): string {
  return `Enviar para ${name}: ${joinCodes(codes)}`;
}

/** Aviso do chip quando a pessoa está com outra rota: a corrida espera por ela. */
export function busyNotice(courier: HouseCourier | null): string {
  return courier?.state === "busy" ? `${courier.name} está na rua. A corrida espera a volta.` : "";
}

/**
 * A ação de enviar à casa, montada das ações `courier-dispatch` de cada parada (a
 * revisão que a tela leu de cada pedido). Faltou alguma, sai desabilitada com o motivo.
 */
export function houseRideAction(
  stops: readonly Pick<DeliveryStopProjection, "ref" | "dispatch_action">[],
): Pick<Action, "enabled" | "reason" | "payload_schema" | "method"> {
  const actions = stops.map((stop) => stop.dispatch_action);
  const revisions: Record<string, string> = {};
  for (const stop of stops) {
    const revision = stop.dispatch_action?.payload_schema.base_revision;
    if (typeof revision === "string" && revision) revisions[stop.ref] = revision;
  }
  const complete = stops.length > 0 && Object.keys(revisions).length === stops.length;
  const enabled = complete && actions.every((action) => action?.enabled);
  const refused = actions.find((action) => action && !action.enabled)?.reason;
  return {
    enabled,
    method: "POST",
    reason: enabled ? "" : refused || "Os pedidos mudaram. Atualize antes de enviar a corrida.",
    payload_schema: {
      expected_actor_id: actions.find(Boolean)?.payload_schema.expected_actor_id,
      base_revisions: revisions,
    },
  };
}

/** Onde mora a intenção desta corrida da casa até a resposta definitiva. */
export function houseRideResource(refs: readonly string[]): string {
  return `house-ride:${[...refs].sort().join("+")}`;
}

/** O corpo além da ação: os pedidos, quem leva e a custódia. */
export function houseRideInputs(call: {
  refs: readonly string[];
  courier: string;
  change_out: Readonly<Record<string, string>>;
  machine: string;
  number?: number;
}): Record<string, unknown> {
  return {
    refs: [...call.refs],
    courier: call.courier,
    change_out: { ...call.change_out },
    machine: call.machine,
    ...(call.number ? { ride_number: call.number } : {}),
  };
}

/** Os chips "Entregadores de hoje": todo entregador ativo, marcado quem está na escala. */
export function shiftChips(crew: HouseCrew | null | undefined): {
  ref: string;
  label: string;
  on: boolean;
}[] {
  if (!crew?.active) return [];
  return crew.couriers.map((courier) => ({
    ref: courier.ref,
    label: courier.on_shift && courier.state === "busy" ? `${courier.name} · Na rua` : courier.name,
    on: courier.on_shift,
  }));
}

// ── a corrida da casa na página Entregas (M3b, #2898) ───────────────────────

/** Um gesto do balcão na corrida da casa: o que a página manda e o botão que o card desenha. */
export interface HouseGesture {
  /** Chave única no card ("depart", "deliver:WEB-A47"…). */
  key: string;
  gesture: "depart" | "deliver" | "resend" | "release";
  /** O pedido do "Entregue". */
  ref?: string;
  action: Action;
  icon: string;
  /** O gesto do momento (botão cheio); os outros em contorno. */
  primary: boolean;
}

/** Os gestos que a projeção oferece, na ordem do momento: o que avança, depois o link. */
export function houseGestures(ride: Pick<DeliveryRideProjection, "house">): HouseGesture[] {
  const house = ride.house;
  if (!house) return [];
  const list: HouseGesture[] = [];
  if (house.depart_action)
    list.push({ key: "depart", gesture: "depart", action: house.depart_action, icon: "i-lucide-navigation", primary: true });
  house.deliver_actions.forEach((item, index) =>
    list.push({
      key: `deliver:${item.ref}`, gesture: "deliver", ref: item.ref, action: item.action,
      icon: "i-lucide-package-check", primary: index === 0,
    }),
  );
  if (house.resend_action)
    list.push({ key: "resend", gesture: "resend", action: house.resend_action, icon: "i-lucide-send", primary: false });
  if (house.release_action)
    list.push({ key: "release", gesture: "release", action: house.release_action, icon: "i-lucide-unlink", primary: false });
  return list;
}

/** Os códigos do card, na ordem da rota, com o que já foi entregue. */
export function houseCodes(stops: readonly Pick<DeliveryStopProjection, "code" | "done">[]): { code: string; done: boolean }[] {
  return stops.map((stop) => ({ code: stop.code, done: stop.done }));
}

/** "1 pedido", "2 pedidos". */
export function ordersWord(count: number): string {
  return `${count} ${count === 1 ? "pedido" : "pedidos"}`;
}

/** Onde mora o gesto no servidor. */
export function houseGesturePath(rideKey: string, gesture: HouseGesture["gesture"]): string {
  return `/api/v1/backstage/deliveries/couriers/rides/${encodeURIComponent(rideKey)}/${gesture}/`;
}

/** Onde mora a intenção do gesto até a resposta definitiva (um por pedido no "Entregue"). */
export function houseGestureResource(rideKey: string, item: Pick<HouseGesture, "key">): string {
  return `house-ride:${rideKey}:${item.key}`;
}
