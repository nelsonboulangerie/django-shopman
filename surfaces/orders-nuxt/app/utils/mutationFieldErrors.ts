import { httpError } from "../../../operator-kit/app/utils/httpError";

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? value as Record<string, unknown> : null;
}

/** Mensagens de validação do dialeto canônico, indexadas pelo nome do payload. */
export function mutationFieldErrors(error: unknown): Record<string, string> {
  const data = record(httpError(error).data);
  const errors = record(data?.errors);
  const result: Record<string, string> = {};
  for (const [field, raw] of Object.entries(errors ?? {})) {
    const message = Array.isArray(raw) ? raw.find((item) => typeof item === "string") : raw;
    if (typeof message === "string" && message) result[field] = message;
  }
  if (!Object.keys(result).length && typeof data?.field === "string" && typeof data?.detail === "string") {
    result[data.field] = data.detail;
  }
  return result;
}
