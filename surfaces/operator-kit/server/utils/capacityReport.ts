// A amostra de capacidade vai ao Django na MESMA chamada que prova o operador.
//
// Autenticação segue o padrão do BFF da layer: o Nitro não decide quem é
// operador — repassa o cookie de sessão ao Django e obedece a resposta
// (`IsBackstageOperator`). A resposta traz de volta os limites do Admin
// (atenção/crítico) para o indicador colorir, e o Django anda a regra do aviso.
// Nada do navegador vira número: o corpo sai inteiro deste processo.
import { getRequestHeader, type H3Event } from "h3";
import { resolveDjangoBaseUrl } from "./djangoBaseUrl";
import { csrfTokenFromCookieHeader } from "./djangoProxy";
import { operatorCookieHeaderForDjango } from "./operatorCookies";
import type { ContainerCapacityReading } from "./containerCapacity";

export const CAPACITY_REPORT_PATH = "/api/v1/backstage/operator/capacity/";

const SERVICE_NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;

export interface CapacityThresholds {
  attention_percent: number;
  critical_percent: number;
  sustain_minutes: number;
}

export interface CapacityReportResult {
  status: number;
  data: Record<string, unknown> | null;
}

/**
 * Nome do serviço que aparece no aviso ao gestor. Com a junção dos apps em dois
 * serviços, o deploy declara `NUXT_OPERATOR_SERVICE_NAME` (`operator-floor`,
 * `operator-office`) e todos os processos do contêiner reportam como UM serviço.
 * Sem a env (hoje: um app por contêiner), vale a identidade do app
 * (`operatorPwa.app`: pos, kds…). Valor fora do formato é ignorado, não repassado.
 */
export function resolveOperatorServiceName(config: {
  operatorServiceName?: unknown;
  public?: { operatorPwa?: { app?: unknown } };
}): string {
  for (const candidate of [config.operatorServiceName, config.public?.operatorPwa?.app]) {
    const name = typeof candidate === "string" ? candidate.trim().toLowerCase() : "";
    if (SERVICE_NAME.test(name)) return name;
  }
  return "operator";
}

export function capacityReportBody(service: string, reading: ContainerCapacityReading) {
  return {
    service,
    available: reading.available,
    memory_percent: reading.available ? reading.memory?.percent ?? null : null,
    cpu_percent: reading.available ? reading.cpu?.percent ?? null : null,
  };
}

export async function reportCapacityToDjango(
  event: H3Event,
  service: string,
  reading: ContainerCapacityReading,
): Promise<CapacityReportResult> {
  const config = useRuntimeConfig(event);
  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl);
  const djangoOrigin = new URL(djangoBaseUrl).origin;

  const headers: Record<string, string> = {
    accept: "application/json",
    "content-type": "application/json",
    // POST de sessão passa pelo CSRF do DRF: mesmo Origin/Referer que o proxy forja.
    origin: djangoOrigin,
    referer: `${djangoOrigin}/`,
  };
  const cookie = operatorCookieHeaderForDjango(getRequestHeader(event, "cookie"));
  if (cookie) headers.cookie = cookie;
  const csrf = csrfTokenFromCookieHeader(cookie);
  if (csrf) headers["x-csrftoken"] = decodeURIComponent(csrf);
  const forwardedFor = getRequestHeader(event, "x-forwarded-for");
  if (forwardedFor) headers["x-forwarded-for"] = forwardedFor;
  const proxySecret = String(config.djangoProxySecret || "");
  if (proxySecret) headers["x-shopman-proxy-secret"] = proxySecret;

  const response = await $fetch.raw(`${djangoBaseUrl}${CAPACITY_REPORT_PATH}`, {
    method: "POST",
    headers,
    body: capacityReportBody(service, reading),
    ignoreResponseError: true,
    redirect: "manual",
    timeout: 5_000,
  });
  const data = response._data;
  return {
    status: response.status,
    data: data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : null,
  };
}

export function parseCapacityThresholds(value: unknown): CapacityThresholds | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const attention = record.attention_percent;
  const critical = record.critical_percent;
  const sustain = record.sustain_minutes;
  if (typeof attention !== "number" || typeof critical !== "number" || typeof sustain !== "number") return null;
  return { attention_percent: attention, critical_percent: critical, sustain_minutes: sustain };
}
