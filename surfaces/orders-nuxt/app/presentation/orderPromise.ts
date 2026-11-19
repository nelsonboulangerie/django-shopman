// Presentation — "Promessa em risco" e "Esperando o lote" (WP-G08). Puro.
//
// Quem decide se a promessa do pedido tem lastro é o servidor
// (`shopman/backstage/projections/order_promise.py`): o estado, o nome dele, a frase de
// cada item e as saídas chegam prontos em `card.promise`. Aqui só se escolhe o que o
// cartão, a Fila, a Tabela e a lista de Encomendas desenham, com as palavras que
// vieram. Nenhuma conta de reserva, de lote ou de hora mora neste arquivo.
import type {
  Action,
  OrderPromiseProjection,
} from "~/generated/ordersContract";
import { reasonLines } from "./cardBlocks";

export const PROMISE_AT_RISK = "at_risk";
export const PROMISE_WAITING_BATCH = "waiting_batch";

/** O que estas funções leem do cartão. `promise` falta em quem ainda não recebeu a leitura. */
export interface PromiseSource {
  promise?: OrderPromiseProjection | null;
}

/** Um item da promessa em risco: o que falta ("4x Baguete sem reserva") e o porquê. */
export interface PromiseRiskItem {
  key: string;
  label: string;
  detail: string;
}

/** Uma saída da promessa em risco, como a tela a desenha. */
export interface PromiseExit {
  ref: string;
  label: string;
  icon: string;
  /** Para onde leva: rota do Gestor ("/REF#promise") ou outro app (o PDV). */
  href: string;
  /** Abre fora do Gestor. */
  external: boolean;
  /** Cancelar: vermelho, como no menu do pedido. */
  danger: boolean;
  disabled: boolean;
}

export interface PromiseRisk {
  /** "Promessa em risco", o nome que o servidor deu ao estado. */
  label: string;
  items: PromiseRiskItem[];
  exits: PromiseExit[];
  /** Por que uma saída não pode agora, escrito (o `title` não existe no toque). */
  blockedReasons: string[];
}

const EXIT_ICONS: Record<string, string> = {
  "contact-customer": "i-lucide-message-circle",
  "reschedule-at-pos": "i-lucide-calendar-clock",
  cancel: "i-lucide-ban",
};

function exit(action: Action): PromiseExit {
  const href = action.enabled ? String(action.href ?? "") : "";
  return {
    ref: action.ref,
    label: action.label,
    icon: EXIT_ICONS[action.ref] ?? "i-lucide-arrow-right",
    href,
    external: /^https?:\/\//.test(href),
    danger: action.ref === "cancel",
    // Atalho sem destino não é botão que se toca: o servidor diz o porquê em `reason`.
    disabled: !action.enabled || !href,
  };
}

/**
 * A promessa em risco do pedido, pronta para desenhar; `null` quando não há risco.
 *
 * Os itens são os que o servidor marcou em risco, na ordem dele, com as frases dele.
 * As saídas são as três ações que vieram em `promise.actions` (no cartão, atalhos).
 */
export function promiseRisk(source: PromiseSource): PromiseRisk | null {
  const promise = source.promise;
  if (!promise || promise.state !== PROMISE_AT_RISK) return null;
  const actions = promise.actions ?? [];
  return {
    label: promise.label,
    items: (promise.items ?? [])
      .filter((item) => item.at_risk)
      .map((item) => ({ key: item.sku, label: item.label, detail: item.detail })),
    exits: actions.map(exit),
    blockedReasons: reasonLines(
      actions
        .filter((action) => !action.enabled)
        .map((action) => ({ label: action.label, reason: action.reason })),
      actions.length,
    ),
  };
}

/** Os itens em risco numa linha só, para quem lista ("4x Baguete sem reserva · 2x Brioche sem reserva"). */
export function promiseRiskSummary(risk: PromiseRisk): string {
  return risk.items.map((item) => item.label).join(" · ");
}

/**
 * O bloqueio do cartão é a espera saudável do lote?
 *
 * "Esperando o lote" não é risco nem pede alguém: a reserva está inteira e o pão ainda
 * não ficou pronto. Só vale quando o bloqueio que o servidor mandou leva o mesmo nome
 * do estado da promessa: o pagamento que falta e o dia da encomenda barram antes do
 * lote, cada um com a sua frase, e seguem como bloqueio.
 */
export function waitsForBatch(
  source: PromiseSource & { advance_block_label?: string | null },
): boolean {
  const promise = source.promise;
  if (!promise || promise.state !== PROMISE_WAITING_BATCH) return false;
  const block = String(source.advance_block_label ?? "").replace(/…$/, "").trim();
  return block !== "" && block === promise.label;
}

/** A frase do item depois de "Produto: " continua a oração, em minúscula (como o servidor). */
const afterColon = (sentence: string) => sentence.charAt(0).toLowerCase() + sentence.slice(1);

/**
 * O lote que o pedido espera, uma frase por produto: "Baguete de tradição: o lote de
 * hoje não começou. Fica pronto às 12h." (as palavras do servidor).
 *
 * Só o item que espera, nunca o item em risco (esse tem o aviso dele). E só quando o
 * cartão ainda não disse a frase: o bloqueio "Esperando o lote" já traz o produto e a
 * hora no motivo, e a mesma frase duas vezes no cartão é ruído (P2-19).
 */
export function promiseWaitLines(
  source: PromiseSource & { advance_block_reason?: string | null },
): Array<{ ref: string; text: string }> {
  // O motivo do bloqueio traz a mesma frase em minúscula, depois de "Produto: ".
  const said = String(source.advance_block_reason ?? "").toLowerCase();
  return (source.promise?.items ?? [])
    .filter((item) => !item.at_risk && item.detail && !said.includes(item.detail.toLowerCase()))
    .map((item) => ({ ref: item.sku, text: `${item.name}: ${afterColon(item.detail)}` }));
}

/**
 * Onde as saídas aparecem, o que decide o peso de cada botão:
 * - `alert`: dentro do aviso do cartão, na cor do aviso (a regra do kit, D8);
 * - `lead`: na Fila, quando a promessa em risco é O fato que o pedido espera: a
 *   primeira saída é o gesto principal da linha;
 * - `plain`: ao lado de outro gesto principal (a etapa do pedido vem antes).
 */
export type ExitTone = "alert" | "lead" | "plain";

export interface ExitButton extends PromiseExit {
  color: "primary" | "neutral" | "error";
  variant: "solid" | "outline";
}

/** O botão de cada saída. Um principal por grupo, no máximo; cancelar é sempre vermelho. */
export function exitButtons(
  exits: readonly PromiseExit[],
  tone: ExitTone,
): ExitButton[] {
  return exits.map((item, index) => {
    const lead = index === 0 && tone !== "plain" && !item.disabled;
    if (tone === "alert")
      return { ...item, color: "error", variant: lead ? "solid" : "outline" };
    return {
      ...item,
      color: item.danger ? "error" : lead ? "primary" : "neutral",
      variant: lead && !item.danger ? "solid" : "outline",
    };
  });
}
