function roundedDuration(seconds: number): string {
  if (seconds < 120) return `${seconds} segundo${seconds === 1 ? "" : "s"}`;
  if (seconds < 7_200) {
    const minutes = Math.ceil(seconds / 60);
    return `${minutes} minuto${minutes === 1 ? "" : "s"}`;
  }
  const hours = Math.max(2, Math.round(seconds / 3_600));
  return `${hours} hora${hours === 1 ? "" : "s"}`;
}

export function marketingThrottleMessage(
  rawSeconds: number,
  timezone: string,
  now = new Date(),
): string {
  const seconds = Math.max(1, Math.ceil(rawSeconds));
  const availableAt = new Date(now.getTime() + seconds * 1_000);
  const time = new Intl.DateTimeFormat("pt-BR", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(availableAt);
  return `Muitas tentativas em pouco tempo. Tente novamente em cerca de ${roundedDuration(seconds)}, às ${time}. Nada foi criado.`;
}
