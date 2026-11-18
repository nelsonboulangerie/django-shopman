// Faixa de homologação do iFood: o relógio que aparece nos vídeos de evidência.
// Pura, testável sem runtime.

/** "17/11/2026 15:04:32 (UTC-03:00)": data, hora com segundos e o fuso explícito. */
export function homologationClock(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  return (
    `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())} ` +
    `(UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)})`
  );
}
