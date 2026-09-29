/**
 * PARA ONDE o PDV manda o operador quando o trabalho continua em OUTRO app.
 *
 * O defeito medido em 22/09/2026: o PDV CITA o app vizinho e não leva. O
 * fechamento do dia lista as ordens de produção abertas por `ref` numa tabela
 * e o botão "Resolver na produção" apontava para a RAIZ da Produção — o dado
 * que o operador precisa estava na tela e era descartado no clique, e ele
 * reencontrava a ordem à mão. O checkout dizia "Registre o recebimento no
 * Gestor" e a trava de cobrança dizia "confira no Gestor", sem link nenhum,
 * com o `ordersUrl` já no `runtimeConfig`.
 *
 * O padrão que já existia na casa e que estas funções generalizam:
 * `usePosSale` montava `${ordersUrl}/${orderRef}` à mão para o "Abrir no
 * gestor" da tela de resultado. Uma função só, testada, em vez de
 * interpolação solta repetida.
 *
 * ⚠️ O ALVO na Produção é a RAIZ (`/`), não `/board`. `/board` é o painel
 * Solari da TV (kiosk, sem filtro); quem tem a grade de ordens de trabalho é
 * `pages/index.vue` (lente "produce", via `ProductionStageGrid`), e é ela que
 * lê `?date=` e `?q=`. O `q` casa contra SKU, nome da ficha E o `ref` das
 * ordens (`production-nuxt/app/presentation/production.ts::matchesRowQuery`),
 * então o `ref` sozinho isola a linha.
 *
 * ⚠️ A DATA não é enfeite. A grade da Produção é recortada por
 * `WorkOrder.target_date` EXATO, e o fechamento lista ordens com
 * `target_date <= hoje` — ou seja, as atrasadas são de ontem ou antes. Sem
 * `?date=`, a grade abre em hoje e a ordem atrasada não está lá: o link
 * levaria a uma tela onde a ordem prometida não aparece. Por isso a projection
 * do fechamento passou a carregar `target_date` em ISO.
 */

/** Tira a(s) barra(s) final(is) para a junção não virar `//`. */
function trimBase(baseUrl: string): string {
  return (baseUrl || "").trim().replace(/\/+$/, "");
}

/** A fila do Gestor — onde os pedidos do dia estão. */
export function ordersQueueUrl(baseUrl: string): string {
  return trimBase(baseUrl);
}

/** UM pedido no Gestor. Sem `ref` em mão, cai na fila (nunca em `/undefined`). */
export function orderUrl(baseUrl: string, orderRef: string): string {
  const base = trimBase(baseUrl);
  if (!base) return "";
  const ref = (orderRef || "").trim();
  return ref ? `${base}/${encodeURIComponent(ref)}` : base;
}

/**
 * A grade de ordens da Produção. Com `dateISO`, abre NAQUELE dia.
 *
 * A data importa mesmo sem ordem escolhida: a grade abre em HOJE por padrão, e
 * uma pendência atrasada é de ontem — sem a data, o operador chega numa grade
 * onde não há o que resolver.
 */
export function productionGridUrl(baseUrl: string, dateISO = ""): string {
  const base = trimBase(baseUrl);
  if (!base) return "";
  const date = (dateISO || "").trim();
  return date ? `${base}/?date=${encodeURIComponent(date)}` : base;
}

/**
 * A data mais ANTIGA entre as ordens pendentes — onde o bloqueio mais velho
 * está. Vazio quando nenhuma linha tem data (aí o link abre a grade de hoje).
 */
export function oldestPendingDate(rows: ReadonlyArray<{ target_date: string }>): string {
  return rows
    .map((row) => (row.target_date || "").trim())
    .filter(Boolean)
    .sort()[0] || "";
}

/**
 * A grade da Produção JÁ na ordem de trabalho pedida: a data que a contém e a
 * busca pelo `ref`. Sem `ref`, devolve a grade sem recorte — link honesto em
 * vez de filtro vazio.
 */
export function productionWorkOrderUrl(
  baseUrl: string,
  workOrder: { ref: string; target_date: string },
): string {
  const base = trimBase(baseUrl);
  if (!base) return "";
  const ref = (workOrder.ref || "").trim();
  if (!ref) return base;
  const params = new URLSearchParams();
  const date = (workOrder.target_date || "").trim();
  if (date) params.set("date", date);
  params.set("q", ref);
  return `${base}/?${params.toString()}`;
}
