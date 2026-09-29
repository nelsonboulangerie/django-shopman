// Presentation — o detalhe da encomenda no PDV (o que é só do balcão; as seções
// comuns são do `OperatorOrderDetail` do kit).

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
