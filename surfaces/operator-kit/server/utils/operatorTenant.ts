// Nome da casa ("Nelson") dos apps de operador, lido do Django em RUNTIME.
//
// A fonte é uma só: `Shop.short_name` ("nome curto (PWA)", editável no Admin), servido
// por `GET /api/v1/backstage/operator/tenant/` (público, sem sessão — o navegador busca
// o manifesto sem cookie). Não pode ser default do nuxt.config: aquilo é avaliado no
// BUILD, e a mesma imagem serve todo deployment.
//
// Cache curto em memória do processo para o manifesto e a primeira pintura não baterem
// no Django a cada pedido. Falha é macia: sem resposta, vale o último nome que o Django
// deu; sem nenhum desde o boot, o app mostra só o rótulo ("PDV"). Nunca um nome escrito
// no código — isso seria uma segunda fonte.

export const OPERATOR_TENANT_PATH = "/api/v1/backstage/operator/tenant/";
export const OPERATOR_TENANT_TTL_MS = 5 * 60_000;
export const OPERATOR_TENANT_RETRY_MS = 30_000;
export const OPERATOR_TENANT_TIMEOUT_MS = 2_000;

interface OperatorTenantResponse {
  tenant?: { short_name?: unknown } | null;
}

export type OperatorTenantFetcher = (url: string, options: { timeout: number }) => Promise<OperatorTenantResponse>;

export interface OperatorTenantCacheOptions {
  fetcher: OperatorTenantFetcher;
  now?: () => number;
  ttlMs?: number;
  retryMs?: number;
}

export function operatorTenantPrefixFrom(response: OperatorTenantResponse | null | undefined): string | null {
  const value = response?.tenant?.short_name;
  return typeof value === "string" ? value.trim() : null;
}

/**
 * Cache do prefixo com "último bom" em caso de falha. `resolve(baseUrl)` nunca lança.
 * Pedidos simultâneos com o cache vencido compartilham a mesma ida ao Django.
 */
export function createOperatorTenantCache(options: OperatorTenantCacheOptions) {
  const now = options.now || Date.now;
  const ttlMs = options.ttlMs ?? OPERATOR_TENANT_TTL_MS;
  const retryMs = options.retryMs ?? OPERATOR_TENANT_RETRY_MS;
  let prefix = "";
  let expiresAt = 0;
  let inflight: Promise<string> | null = null;

  async function load(baseUrl: string): Promise<string> {
    try {
      const response = await options.fetcher(`${baseUrl.replace(/\/+$/, "")}${OPERATOR_TENANT_PATH}`, {
        timeout: OPERATOR_TENANT_TIMEOUT_MS,
      });
      const fetched = operatorTenantPrefixFrom(response);
      if (fetched === null) throw new TypeError("operator tenant sem short_name");
      prefix = fetched;
      expiresAt = now() + ttlMs;
    } catch {
      // silêncio-deliberado: nome de janela não derruba manifesto nem tela; mantém o
      // último nome bom e tenta de novo em `retryMs`.
      expiresAt = now() + retryMs;
    }
    return prefix;
  }

  return {
    async resolve(baseUrl: string): Promise<string> {
      if (now() < expiresAt) return prefix;
      inflight ||= load(baseUrl).finally(() => {
        inflight = null;
      });
      return inflight;
    },
  };
}

let processCache: ReturnType<typeof createOperatorTenantCache> | null = null;

/** Prefixo do tenant para este processo Nitro (cache compartilhado entre pedidos). */
export function resolveOperatorTenantPrefix(baseUrl: string): Promise<string> {
  processCache ||= createOperatorTenantCache({
    fetcher: (url, fetchOptions) => $fetch<OperatorTenantResponse>(url, {
      ...fetchOptions,
      headers: { accept: "application/json" },
      retry: 0,
    }),
  });
  return processCache.resolve(baseUrl);
}
