// Presentation — "Promessa em risco" e "Esperando o lote" (WP-G08). Puro.
//
// Quem decide se a promessa do pedido tem lastro é o servidor
// (`shopman/backstage/projections/order_promise.py`): o estado, o nome dele, a frase de
// cada item, o PRÓXIMO PASSO (o que fazer, com o que a casa pode oferecer no lugar) e
// as saídas ("Resolver" e, quando couber, "Abrir a Produção"), com a recomendada
// marcada, chegam prontos em `card.promise`. Aqui só se escolhe o que o cartão, a Fila,
// a Tabela e a lista de Encomendas desenham, com as palavras que vieram. Nenhuma conta
// de reserva, de lote ou de hora mora neste arquivo. O que cada escolha faz (trocar,
// remarcar, tirar o item, cancelar) mora no diálogo "Resolver" (`promiseResolution.ts`).
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

/** Um item da promessa em risco: o que falta ("Faltam 4x Baguete"), o porquê e o que
 *  a casa pode oferecer no lugar, uma sugestão por linha. */
export interface PromiseRiskItem {
  key: string;
  /** O nome do produto, para o título da lista quando a linha fala de mais de um. */
  name: string;
  label: string;
  detail: string;
  /** "Fendu · 6 livres para amanhã": o nome e o quanto há, com as palavras do servidor. */
  suggestions: string[];
}

/** Um grupo de sugestões para quem escreve os itens numa frase só (a faixa do detalhe). */
export interface PromiseSuggestionGroup {
  key: string;
  heading: string;
  options: string[];
}

export const SUGGESTIONS_HEADING = "Sugestões:";

/** Uma saída da promessa em risco, como a tela a desenha. */
export interface PromiseExit {
  ref: string;
  label: string;
  icon: string;
  /** "Resolver": botão que abre o diálogo das escolhas (avisa quem o monta), não link. */
  opensDialog: boolean;
  /** Para onde o atalho leva (outro app: a Produção); vazio em quem abre o diálogo. */
  href: string;
  /** Abre fora do Gestor. */
  external: boolean;
  disabled: boolean;
  /** A saída que o servidor recomenda (`priority: "primary"`): o único botão cheio. */
  recommended: boolean;
}

export interface PromiseRisk {
  /** "Promessa em risco", o nome que o servidor deu ao estado. */
  label: string;
  items: PromiseRiskItem[];
  /** O que a tela ainda precisa dizer, numa frase do servidor ("Peça à Produção para
   *  planejar."); vazio quando as sugestões ou a saída cheia já dizem tudo. */
  nextStep: string;
  /** A `ref` da saída que a situação pede, mesmo quando esta conta não a recebe. */
  recommendedAction: string;
  exits: PromiseExit[];
  /** Por que uma saída não pode agora, escrito (o `title` não existe no toque). */
  blockedReasons: string[];
}

/** A saída que abre o diálogo "Resolver": as escolhas, a mensagem ao cliente e o que conclui. */
export const RESOLVE = "resolve";
/** A saída que abre o plano do dia na Produção, quando ela ainda resolve. */
export const OPEN_PRODUCTION = "open-production";

const EXIT_ICONS: Record<string, string> = {
  [RESOLVE]: "i-lucide-list-checks",
  [OPEN_PRODUCTION]: "i-lucide-croissant",
};

function exit(action: Action): PromiseExit {
  const opensDialog = action.ref === RESOLVE;
  const href = action.enabled && !opensDialog ? String(action.href ?? "") : "";
  return {
    ref: action.ref,
    label: action.label,
    icon: EXIT_ICONS[action.ref] ?? "i-lucide-arrow-right",
    opensDialog,
    href,
    external: /^https?:\/\//.test(href),
    // Atalho sem destino não é botão que se toca: o servidor diz o porquê em `reason`.
    disabled: !action.enabled || (!opensDialog && !href),
    recommended: action.priority === "primary",
  };
}

/**
 * A promessa em risco do pedido, pronta para desenhar; `null` quando não há risco.
 *
 * Os itens são os que o servidor marcou em risco, na ordem dele, com as frases dele.
 * As saídas são as ações que vieram em `promise.actions`, na ordem do servidor:
 * "Resolver" (abre o diálogo) e, quando a Produção ainda resolve, "Abrir a Produção".
 */
export function promiseRisk(source: PromiseSource): PromiseRisk | null {
  const promise = source.promise;
  if (!promise || promise.state !== PROMISE_AT_RISK) return null;
  const actions = promise.actions ?? [];
  return {
    label: promise.label,
    items: (promise.items ?? [])
      .filter((item) => item.at_risk)
      .map((item) => ({
        key: item.sku,
        name: item.name,
        label: item.label,
        detail: item.detail,
        suggestions: (item.alternatives ?? []).map((option) =>
          [option.name, option.available_display].filter(Boolean).join(" · "),
        ),
      })),
    nextStep: String(promise.next_step ?? "").trim(),
    recommendedAction: String(promise.recommended_action ?? ""),
    exits: actions.map(exit),
    blockedReasons: reasonLines(
      actions
        .filter((action) => !action.enabled)
        .map((action) => ({ label: action.label, reason: action.reason })),
      actions.length,
    ),
  };
}

/**
 * A saída recomendada da promessa em risco é o botão cheio do pedido: o gesto da etapa
 * ("Iniciar preparo") continua lá, em contorno. Iniciar o preparo de um pedido sem
 * lastro não é o próximo passo (dono, 19/11/2026: o aviso diz o que fazer). Vale para
 * o cartão do Painel e para a linha da Fila.
 */
export function promiseRiskLeads(source: PromiseSource): boolean {
  return Boolean(promiseRisk(source)?.exits.some((exit) => exit.recommended && !exit.disabled));
}

/**
 * As sugestões por item, para quem escreve os itens numa frase só. Um item com
 * sugestão: "Sugestões:". Mais de um: "Sugestões para Baguete:", para a lista dizer de
 * quem é.
 */
export function promiseSuggestionGroups(risk: PromiseRisk | null): PromiseSuggestionGroup[] {
  const offered = (risk?.items ?? []).filter((item) => item.suggestions.length);
  return offered.map((item) => ({
    key: item.key,
    heading: offered.length > 1 ? `Sugestões para ${item.name}:` : SUGGESTIONS_HEADING,
    options: item.suggestions,
  }));
}

/** Os itens em risco numa linha só, para quem lista ("Faltam 4x Baguete · Faltam 2x Brioche"). */
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
 * Onde as saídas aparecem, o que decide a COR do botão recomendado:
 * - `alert`: dentro do aviso do cartão, tudo na cor do aviso (a regra do kit, D8);
 * - `row`: numa linha (a Fila, a Tabela), na cor principal.
 */
export type ExitTone = "alert" | "row";

export interface ExitButton extends PromiseExit {
  color: "primary" | "neutral" | "error";
  variant: "solid" | "outline";
}

/**
 * O botão de cada saída. Cheio é só o que o servidor recomenda (`recommended`); sem
 * recomendada entre as saídas, nenhum é cheio e a frase do próximo passo diz o que
 * fazer. Saída travada nunca é cheia.
 */
export function exitButtons(
  exits: readonly PromiseExit[],
  tone: ExitTone,
): ExitButton[] {
  return exits.map((item) => {
    const lead = item.recommended && !item.disabled;
    return {
      ...item,
      color: tone === "alert" ? "error" : lead ? "primary" : "neutral",
      variant: lead ? "solid" : "outline",
    };
  });
}
