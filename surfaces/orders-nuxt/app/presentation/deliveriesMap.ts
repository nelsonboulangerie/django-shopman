// Presentation — o mapa das Entregas. Puro: o componente só desenha o que estas
// funções dizem.
//
// O mapa é sempre claro, no tema claro e no escuro: é papel com ruas (ou o Google
// Maps de verdade, que também é claro). Por isso as cores dele são FIXAS, e não os
// tokens do tema: um `text-toned` do tema escuro é um cinza claro, e sobre o branco
// do mapa some (revisão das Entregas, 16/11/2026, UXE-08).

export const MAP_TOKENS = {
  /** O papel do desenho próprio (sem Google). */
  paper: "#f3ede3",
  /** Fundo das etiquetas e da legenda. */
  chip: "#ffffff",
  /** Texto sobre o papel e sobre as etiquetas. */
  text: "#3a3631",
  /** A loja: o único preto cheio do mapa. */
  store: "#111111",
  storeText: "#ffffff",
  /** O cinza neutro da legenda (a legenda fala de FORMA, não de cor). */
  neutral: "#5f6670",
} as const;

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return 0.2126 * channel(r!) + 0.7152 * channel(g!) + 0.0722 * channel(b!);
}

/** Contraste WCAG entre duas cores sólidas (1 a 21). */
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x! + 0.05) / (y! + 0.05);
}

/** Um marcador já em pixels, com a chave que o identifica no desenho. */
export interface PlacedMarker {
  key: string;
  x: number;
  y: number;
}

/**
 * Marcadores que caem quase no mesmo pixel (duas paradas no mesmo prédio, a moto
 * em cima da parada) se abrem num círculo pequeno, para cada um ter o seu toque.
 * Devolve o deslocamento de cada chave; quem está sozinho não sai do lugar.
 */
export function spreadOverlaps(
  markers: readonly PlacedMarker[],
  minDistance = 28,
  radius = 18,
): Map<string, { dx: number; dy: number }> {
  const out = new Map<string, { dx: number; dy: number }>();
  const groups: PlacedMarker[][] = [];
  for (const marker of markers) {
    const group = groups.find((g) => g.some((m) => Math.hypot(m.x - marker.x, m.y - marker.y) < minDistance));
    if (group) group.push(marker);
    else groups.push([marker]);
  }
  for (const group of groups) {
    if (group.length < 2) {
      out.set(group[0]!.key, { dx: 0, dy: 0 });
      continue;
    }
    group.forEach((marker, i) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * i) / group.length;
      out.set(marker.key, { dx: Math.round(Math.cos(angle) * radius), dy: Math.round(Math.sin(angle) * radius) });
    });
  }
  return out;
}

/**
 * A chave do enquadramento: as paradas e a loja, NUNCA a moto. O mapa se
 * reenquadra quando muda o que se entrega, não a cada posição do entregador
 * (revisão das Entregas, P2 "Posição do entregador": o fit corria atrás da moto).
 */
export function fitKey(points: readonly { latitude: number; longitude: number }[]): string {
  return points
    .map((p) => `${p.latitude.toFixed(5)},${p.longitude.toFixed(5)}`)
    .sort()
    .join("|");
}
