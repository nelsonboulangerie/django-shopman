/** Shared client for the authenticated device agent on loopback.
 *
 * Domain apps compose and authorize their own documents. This module only
 * transports an already-authorized command to the operator's own device.
 * It is public to Nuxt operator surfaces through the operator-kit layer, but
 * the agent itself remains private to loopback + origin allowlist + token.
 */

export interface LocalDeviceAgentConfig {
  agent_url?: string;
  token?: string;
}

export type LocalDeviceAgentResponse = Record<string, unknown> & {
  ok?: boolean;
  error?: string;
  reason?: string;
  queue?: string;
  job_id?: string;
  build?: string;
  known?: boolean;
  open?: boolean;
  raw?: string;
  calibrated?: boolean;
  drawer_lock?: { calibrated?: boolean };
};

export class LocalDeviceAgentTooOldError extends Error {
  constructor(readonly route: string) {
    super(
      "O agente desta estação está desatualizado e não conhece esta função. "
      + "Baixe e reinstale pelo gestor, em Terminais do PDV.",
    );
    this.name = "LocalDeviceAgentTooOldError";
  }
}

export async function callLocalDeviceAgent(
  config: LocalDeviceAgentConfig | null | undefined,
  path: string,
  body?: Record<string, unknown>,
  timeoutMs = 3_000,
): Promise<LocalDeviceAgentResponse> {
  if (!config?.agent_url) throw new Error("Terminal sem agente local configurado.");
  const response = await fetch(`${config.agent_url}${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify({ token: config.token || "", ...body }) : undefined,
    signal: AbortSignal.timeout(timeoutMs),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 404) throw new LocalDeviceAgentTooOldError(path);
    throw new Error(String(payload?.error || `Agente respondeu ${response.status}.`));
  }
  return payload as LocalDeviceAgentResponse;
}

export async function printWithLocalDeviceAgent(
  config: LocalDeviceAgentConfig,
  payloadB64: string,
  title: string,
): Promise<LocalDeviceAgentResponse> {
  const payload = await callLocalDeviceAgent(config, "/print", {
    payload_b64: payloadB64,
    title,
  });
  if (payload.ok === false)
    throw new Error(String(payload.error || "O agente recusou a impressão."));
  return payload;
}

export function localDeviceAgentErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "TimeoutError")
    return "O agente local não respondeu.";
  if (error instanceof TypeError)
    return "O agente local desta estação não está rodando.";
  return error instanceof Error ? error.message : String(error);
}
