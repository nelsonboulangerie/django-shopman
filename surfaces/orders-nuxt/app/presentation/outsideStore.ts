// "Fora da loja" (G18): a distância entre o dispositivo e o ponto da loja, e a escolha
// de quem o segura. Puro: testado em `tests/outsideStore.test.ts`.

/** Onde o dispositivo guarda o sim/não do operador (preferência dele, por dispositivo). */
export const OUTSIDE_CONSENT_KEY = "gestor-outside-store-consent";

export type OutsideConsent = "unknown" | "granted" | "declined";

export function outsideConsent(raw: string | null): OutsideConsent {
  return raw === "granted" || raw === "declined" ? raw : "unknown";
}

/** Distância em metros entre dois pontos (haversine; a Terra como esfera de 6.371 km). */
export function distanceMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = rad(lat2 - lat1);
  const dLng = rad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.min(1, Math.sqrt(a)));
}
