// Presentation — chamar o entregador a partir de UM pedido (o cartão Pronto do Painel e
// o detalhe do pedido), no MESMO sheet das Entregas (`CourierCallSheet`, #2876). Puro:
// o composable `useCourierCall` guarda o estado, aqui só se decide o que mostrar.
//
// Decisão 1 = A do dono (16/11): o companheiro da sugestão da casa já vem marcado como
// "Sugestão da casa", e a cotação juntas×separadas é SÓ leitura (o ✔ não é botão).
import type { DeliveryStopProjection, RidePlanProjection } from "~/generated/ordersContract";
import { formatBRL } from "../../../operator-kit/app/utils/money";
import { deliveryServiceName } from "../../../operator-kit/app/presentation/deliveryService";
import { joinCodes } from "~/presentation/houseCouriers";
import type { RideSuggestion } from "~/presentation/deliveries";

/** Quem pode ir junto com o pedido que se está chamando, como o sheet desenha. */
export interface CompanionChoice {
  ref: string;
  code: string;
  customer: string;
  place: string;
  /** "Pronto" ou "Em preparo": a corrida pode sair antes do pronto. */
  stage: string;
  /** "Troco para R$ 50,00 · Leva a maquininha": o que a chamada vai perguntar dele. */
  note: string;
  /** É o companheiro da sugestão da casa (cotada e mais barata junta). */
  suggested: boolean;
  /** Vai nesta corrida agora. */
  checked: boolean;
  /** A corrida está cheia e ele ainda não está nela. */
  disabled: boolean;
}

/**
 * A sugestão da casa que leva este pedido (o plano `ride_plan`, o MESMO das Entregas),
 * ou `null`. Só ela marca alguém: sem sugestão, ninguém vem marcado.
 */
export function suggestionFor(
  ref: string,
  suggestions: readonly RideSuggestion[],
): RideSuggestion | null {
  return suggestions.find((item) => item.refs.includes(ref)) ?? null;
}

/**
 * Os pedidos que a corrida leva quando o sheet abre: o pedido e, se a casa sugere
 * juntar (cotada e mais barata), os companheiros da sugestão (decisão 1 = A).
 * Sem sugestão marcada, só o pedido. Quem já está em outra corrida em edição fica de fora.
 */
export function initialRide(
  ref: string,
  plan: RideSuggestion | null,
  maxStops: number,
  taken: ReadonlySet<string> = new Set(),
): string[] {
  if (!plan?.suggested) return [ref];
  const mates = plan.refs.filter((item) => item !== ref && !taken.has(item));
  return [ref, ...mates].slice(0, Math.max(1, maxStops));
}

/** Distância plana em graus (a mesma régua de `routeOrder`): só ordena. */
function flat(a: DeliveryStopProjection, b: DeliveryStopProjection): number | null {
  if (a.latitude === null || a.longitude === null || b.latitude === null || b.longitude === null) return null;
  return (a.latitude - b.latitude) ** 2 + (a.longitude - b.longitude) ** 2;
}

/**
 * "Vai junto nesta corrida?": quem pode ir com o pedido. Primeiro os companheiros da
 * sugestão da casa, depois os mais perto; sem coordenada, no fim. Fora: o próprio
 * pedido, quem não vai em corrida nenhuma (`group_refusal`, chamada sem resposta) e
 * quem já está em outra corrida em edição. No máximo `maxStops - 1`, o que cabe junto.
 */
export function companionChoices(
  anchor: DeliveryStopProjection,
  waiting: readonly DeliveryStopProjection[],
  ride: readonly string[],
  options: { plan: RideSuggestion | null; maxStops: number; taken?: ReadonlySet<string> },
): CompanionChoice[] {
  const mates = options.plan ? options.plan.refs.filter((ref) => ref !== anchor.ref) : [];
  const marked = Boolean(options.plan?.suggested);
  const pool = waiting.filter(
    (stop) =>
      stop.ref !== anchor.ref &&
      !stop.group_refusal &&
      !stop.dispatch_again_action &&
      !(options.taken?.has(stop.ref) ?? false),
  );
  const rank = (stop: DeliveryStopProjection): [number, number, number] => {
    const mate = mates.indexOf(stop.ref);
    const distance = flat(anchor, stop);
    return [mate === -1 ? 1 : 0, mate === -1 ? 0 : mate, distance === null ? Infinity : distance];
  };
  const sorted = [...pool].sort((a, b) => {
    const [ra, rb] = [rank(a), rank(b)];
    return ra[0] - rb[0] || ra[1] - rb[1] || (ra[2] === rb[2] ? 0 : ra[2] < rb[2] ? -1 : 1);
  });
  const full = ride.length >= options.maxStops;
  return sorted.slice(0, Math.max(0, options.maxStops - 1)).map((stop) => {
    const checked = ride.includes(stop.ref);
    return {
      ref: stop.ref,
      code: stop.code,
      customer: stop.customer,
      place: stop.place,
      stage: stop.stage,
      note: [stop.change_label, stop.needs_machine ? "Leva a maquininha" : ""].filter(Boolean).join(" · "),
      suggested: marked && mates.includes(stop.ref),
      checked,
      disabled: !checked && full,
    };
  });
}

/**
 * O nome do serviço que leva a corrida que ainda vai abrir: o sugerido no plano
 * (`ride_plan.service`, o padrão do Admin), como o cadastro diz; "central" sem ele.
 */
export function planServiceName(plan: Pick<RidePlanProjection, "service" | "service_options"> | null | undefined): string {
  const option = plan?.service_options?.find((item) => item.ref === plan.service);
  return deliveryServiceName(option?.name);
}

/**
 * A frase sob os companheiros quando a sugestão não vem com preço, ou quando um
 * companheiro ainda está em preparo. `null` quando a cotação já diz tudo.
 */
export function companionNote(
  plan: RideSuggestion | null,
  choices: readonly CompanionChoice[],
  service?: string,
): { text: string; warning: boolean } | null {
  if (plan && !plan.quoted) {
    const mates = choices.filter((choice) => plan.refs.includes(choice.ref)).map((choice) => choice.code);
    if (mates.length)
      return {
        text: `A ${deliveryServiceName(service)} não cotou agora. Marque ${joinCodes(mates)} se quiser levar junto.`,
        warning: true,
      };
  }
  const preparing = choices.filter((choice) => choice.stage && choice.stage !== "Pronto");
  if (preparing.length) {
    const codes = joinCodes(preparing.map((choice) => choice.code));
    const verb = preparing.length === 1 ? "ainda está" : "ainda estão";
    return {
      text: `${codes} ${verb} em preparo e a casa não sabe a hora em que fica pronto. Marque só se sai agora.`,
      warning: false,
    };
  }
  return null;
}

/**
 * O botão principal do sheet aberto por um pedido: "Chamar entregador para A47", ou,
 * com quem vai junto, "Chamar corrida com A47 e C03".
 */
export function orderCallLabel(codes: readonly string[]): string {
  if (codes.length <= 1) return `Chamar entregador para ${codes[0] ?? ""}`.trim();
  return `Chamar corrida com ${joinCodes(codes)}`;
}

/** "Chamar entregador para A47", o título do sheet aberto por um pedido. */
export function orderCallTitle(code: string): string {
  return `Chamar entregador para ${code}`;
}

/** "A47 · Ana · Gleba Palhano · Pronto. A corrida é paga pela casa e o frete dos clientes não muda." */
export function orderCallDescription(
  stop: Pick<DeliveryStopProjection, "code" | "customer" | "place" | "stage">,
): string {
  const who = [stop.code, stop.customer, stop.place, stop.stage].filter(Boolean).join(" · ");
  return `${who}. A corrida é paga pela casa e o frete dos clientes não muda.`;
}

/** "50,00", "R$ 1.250,00" ou "" em centavos; `null` quando não é dinheiro. */
export function moneyToQ(text: string): number | null {
  const clean = text.replace(/R\$/g, "").replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
  if (!clean) return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

/**
 * "Sai da gaveta: R$ 70,00 de troco.": a soma do troco que os entregadores levam em
 * todas as paradas do sheet. Vazio sem troco, ou com um valor ilegível (soma com
 * buraco mente).
 */
export function drawerLine(changes: readonly string[]): string {
  const values = changes.map(moneyToQ);
  if (values.some((value) => value === null)) return "";
  const total = values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  if (total <= 0) return "";
  return `Sai da gaveta: ${formatBRL(total).replace(/\u00a0/g, " ")} de troco.`;
}
