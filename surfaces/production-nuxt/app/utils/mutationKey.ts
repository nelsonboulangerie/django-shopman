/** Create the attempt identity before the first POST.  Callers keep this value
 * across network retries and shortage confirmation; the backend owns dedupe. */
export function newProductionMutationKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid;
  return `prod-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
