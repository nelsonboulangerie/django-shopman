// Narrowing tipado de erros de rede/HTTP para o código de operador.
//
// `$fetch` (ofetch) lança um erro cujo `status`/`data`/`statusCode` carregam a resposta
// do Django. Em vez de `catch (e: any)`, o código de operador usa `httpError(e)` para
// obter uma view segura e `isTransientError(e)` para decidir retry.

export interface HttpErrorInfo {
  status: number;
  data: unknown;
  message: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

/** Extrai `{ status, data, message }` de um erro do ofetch/H3 sem `any`. */
export function httpError(error: unknown): HttpErrorInfo {
  const record = asRecord(error);
  const status = Number(
    (record?.status ?? record?.statusCode ?? asRecord(record?.response)?.status) as number,
  );
  const data = record?.data ?? asRecord(record?.response)?._data ?? null;
  const message = typeof record?.message === "string" ? record.message : "";
  return { status: Number.isFinite(status) ? status : 0, data, message };
}

/**
 * Erro transiente = vale a pena retentar: falha de rede (status 0) ou 502/503/504.
 * 4xx (exceto 429, tratado com backoff próprio) NÃO é transiente — não martelar o
 * backend com um pedido que ele recusou.
 */
export function isTransientError(error: unknown): boolean {
  const { status } = httpError(error);
  return status === 0 || status === 502 || status === 503 || status === 504;
}

/**
 * Autenticação perdida: a sessão do operador expirou no meio da operação.
 * Consumido pelo `useOperatorSession` para forçar re-autenticação em vez de falhar
 * gravações no vácuo.
 *
 * ⚠️ **Na zona de operador isto quase nunca chega como 401.** O Django roda com um
 * authenticator só (`SessionAuthentication`), que não manda header de desafio — e
 * sem ele o DRF rebaixa o `NotAuthenticated` para **403**. Enquanto este narrowing
 * testava só `status === 401` o ramo era inalcançável no backstage, e a sessão
 * caída caía no tratamento genérico: o operador via erro de rede para um problema
 * que o login resolveria.
 *
 * A correção é por **código**, não por status. Continua distinto de um 403 comum
 * (falta de permissão, que login NÃO resolve): só o `not_authenticated` que o
 * servidor nomeia entra aqui. Aceitar "todo 403" mandaria o operador digitar senha
 * para uma recusa que senha não conserta — mesmo raciocínio do
 * `isStationLockedError` abaixo.
 */
export function isUnauthenticatedError(error: unknown): boolean {
  const { status } = httpError(error);
  if (status === 401) return true;
  return status === 403 && httpErrorCode(error) === "not_authenticated";
}

/**
 * Mensagem amigável de um erro do backstage, com tipagem (substitui `catch (e: any)` +
 * `e?.data?.detail || e?.message`). Prioriza a mensagem do servidor — `data.detail`
 * (DRF) e depois `data.error.message` (erros de domínio) — e cai no `fallback`
 * localizado. NUNCA devolve a string técnica do ofetch ("[POST] …: 500"): o operador
 * vê ou a mensagem do servidor ou o texto amigável, jamais ruído de stack.
 */
export function httpErrorMessage(error: unknown, fallback: string): string {
  const data = asRecord(httpError(error).data);
  const detail = data?.detail;
  if (typeof detail === "string" && detail) return detail;
  const nested = asRecord(data?.error)?.message;
  if (typeof nested === "string" && nested) return nested;
  return fallback;
}

/**
 * Código de domínio do erro (`data.error.code` do dialeto canônico), ou "" quando o
 * servidor não mandou um. É o que permite a tela REAGIR a uma recusa específica —
 * abrir o desafio de PIN num `manager_approval_required`, por exemplo — em vez de
 * cair no toast genérico e deixar o operador sem saída.
 */
export function httpErrorCode(error: unknown): string {
  const code = asRecord(asRecord(httpError(error).data)?.error)?.code;
  return typeof code === "string" ? code : "";
}

/**
 * A estação está TRAVADA do lado do servidor (403 `station_locked`): o operador
 * ativo saiu e nenhuma leitura ou gravação passa mais. Distinto de 403 por falta
 * de permissão — este se resolve com o PIN ali mesmo, e a tela precisa subir a
 * identificação em vez de seguir desenhando uma superfície vazia.
 */
export function isStationLockedError(error: unknown): boolean {
  return httpError(error).status === 403 && httpErrorCode(error) === "station_locked";
}
