/** URL enviada no erro de composição fiscal; a nota não foi impressa. */
export function fiscalRecoveryUrl(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const raw = (data as Record<string, unknown>).danfe_url;
  if (typeof raw !== "string") return "";
  try {
    const url = new URL(raw);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : "";
  } catch {
    return "";
  }
}
