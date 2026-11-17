/**
 * Relógio da faixa de homologação: data e hora de Brasília com segundos e o fuso
 * escrito, para quem confere o vídeo contra o log do iFood (que vem em UTC).
 */
export function homologationClock(now: Date): string {
  const local = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(now);
  const utc = now.toISOString().slice(11, 19);
  return `${local.replace(",", "")} (Brasília) · ${utc} UTC`;
}
