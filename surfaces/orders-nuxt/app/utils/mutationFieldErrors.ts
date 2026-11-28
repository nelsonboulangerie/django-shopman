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

/** O cadastro dono do contato recusado (`error.owner` da recusa `contact_conflict`). */
export interface ContactOwner {
  field: "phone" | "email";
  ref: string;
  name: string;
}

export function contactOwner(error: unknown): ContactOwner | null {
  const data = record(httpError(error).data);
  const owner = record(record(data?.error)?.owner);
  const field = data?.field;
  if (!owner || (field !== "phone" && field !== "email")) return null;
  const ref = typeof owner.ref === "string" ? owner.ref : "";
  const name = typeof owner.name === "string" ? owner.name : "";
  return ref ? { field, ref, name: name || ref } : null;
}
