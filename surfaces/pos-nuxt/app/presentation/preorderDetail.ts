// Presentation — o detalhe da encomenda no PDV (o que é só do balcão; as seções
// comuns são do `OperatorOrderDetail` do kit).
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import type { PreorderPromise } from "../types/preorders";

/** Para onde a volta do detalhe leva quando não há histórico para voltar. */
export const PREORDERS_HOME = "/preorders";

/**
 * A volta do detalhe, respeitando DE ONDE o operador veio.
 *
 * A lista das Encomendas guarda modo, data e filtros na URL; quem a abre de novo
 * tem de cair no mesmo recorte, não na casa da seção. Dois caminhos, nesta ordem:
 *
 * 1. `?back=<caminho>` — a lista (ou quem linkar o detalhe) diz para onde voltar.
 *    Só vale caminho INTERNO da seção (`/preorders…`): qualquer outra coisa é
 *    ignorada, para o parâmetro não virar um redirecionamento aberto.
 * 2. Sem `back`: o histórico do navegador (a página anterior, com a query dela).
 *
 * `null` aqui = "use o histórico"; a página cai em {@link PREORDERS_HOME} se
 * nem histórico houver (detalhe aberto direto, por link ou bookmark).
 */
export function preorderBackTarget(raw: unknown): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== "string") return null;
  const target = value.trim();
  if (!target.startsWith(PREORDERS_HOME)) return null;
  // "/preordersX" não é a seção; "//host" e "/\\host" nunca chegam aqui (não
  // começam por "/preorders"), mas a barra seguinte fecha a porta de vez.
  const rest = target.slice(PREORDERS_HOME.length);
  if (rest && !["/", "?", "#"].includes(rest[0]!)) return null;
  if (/[\r\n\\]/.test(target)) return null;
  return target;
}

/**
 * O endereço do detalhe, levando a volta junto: `/preorders/NB-7?back=…`.
 *
 * `from` é o recorte da lista (`viewPath`: modo, data, filtros, busca). A volta
 * só pelo histórico falha justamente quando mais importa: detalhe recarregado,
 * aberto noutra aba, ou kiosk cujo histórico começa em outro app. Recorte que é
 * a própria casa da seção não vai na URL (a volta sem `back` já cai nela).
 */
export function preorderDetailPath(ref: string, from = ""): string {
  const path = `${PREORDERS_HOME}/${encodeURIComponent(ref)}`;
  const back = preorderBackTarget(from);
  if (!back || back === PREORDERS_HOME) return path;
  return `${path}?${new URLSearchParams({ back }).toString()}`;
}

/** O título do aviso: o mesmo nome do Gestor. */
export const PROMISE_ALERT_TITLE = "Promessa em risco";

/**
 * A promessa em risco da encomenda, como aviso no topo do detalhe (#2721 item 3).
 *
 * O fato vem do servidor, item a item, com as frases do Gestor; a saída é a ação
 * que ele manda ("Resolver no Gestor"), que abre o pedido lá com o diálogo das
 * escolhas. Travada, a saída some e o motivo entra no texto: aviso sem o botão que
 * resolve diz por quê. Sem promessa em risco, nada.
 */
export function promiseAlert(
  promise: PreorderPromise | null | undefined,
  open: (href: string) => void,
): OperatorScreenAlert | null {
  if (!promise || promise.state !== "at_risk") return null;
  const facts = promise.items
    .filter((item) => item.at_risk)
    .map((item) => [item.label, item.detail].filter(Boolean).join(". "));
  const resolve = promise.actions.find((action) => action.ref === "resolve");
  const reason = resolve && !resolve.enabled ? resolve.reason : "";
  const description = [...facts, reason].filter(Boolean).map(sentence).join(" ");
  return {
    id: "preorder-promise-at-risk",
    title: PROMISE_ALERT_TITLE,
    description,
    color: "error",
    icon: "i-lucide-package-x",
    ...(resolve?.enabled && resolve.href
      ? { action: { label: resolve.label, onSelect: () => open(resolve.href) } }
      : {}),
  };
}

function sentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}
