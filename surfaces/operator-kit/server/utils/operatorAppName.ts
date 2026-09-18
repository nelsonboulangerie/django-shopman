import type { H3Event } from "h3";
import { operatorAppName, type OperatorAppName } from "../../app/presentation/windowTitle";
import type { ResolvedOperatorPwa } from "../../pwa.config";
import { resolveDjangoBaseUrl } from "./djangoBaseUrl";
import { resolveOperatorTenantPrefix } from "./operatorTenant";

/**
 * Nome do app de operador para este pedido: casa (`Shop.short_name`, via Django, com
 * cache) + rótulo declarado na capability PWA. Nunca lança — sem Django e sem nome
 * anterior, devolve só o rótulo.
 */
export async function resolveOperatorAppName(event: H3Event): Promise<OperatorAppName> {
  const config = useRuntimeConfig(event);
  const options = config.public.operatorPwa as ResolvedOperatorPwa | undefined;
  const label = options?.manifest?.label || "";
  let baseUrl: string;
  try {
    baseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl);
  } catch {
    // silêncio-deliberado: upstream mal configurado já responde 503 em todo proxy do
    // BFF; o nome da janela cai para o rótulo em vez de derrubar o manifesto.
    return operatorAppName("", label);
  }
  return operatorAppName(await resolveOperatorTenantPrefix(baseUrl), label);
}
