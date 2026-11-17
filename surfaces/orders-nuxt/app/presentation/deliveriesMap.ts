// Presentation — o mapa das Entregas. Puro: o componente só desenha o que estas
// funções dizem.
//
// O mapa acompanha o tema (dono, 17/11: "porque ele não pode acompanhar o tema
// claro/escuro?"). As cores dele continuam FIXAS por tema, e não os tokens do tema:
// um `text-toned` do escuro sobre o papel do mapa some (revisão das Entregas, UXE-08).
// O que não muda com o tema são os PINOS (octógono, redondo do aguardando, selo de
// preparo): são brancos nos dois, como placa, e por isso leem sobre o papel escuro.
//
// No escuro, a linha da corrida que não lê sozinha sobre o papel escuro (o azul e o
// preto) ganha um contorno CLARO por baixo (`halo`); no claro o contorno é a tinta.

export interface MapTokens {
  /** O papel do desenho próprio (sem Google). */
  paper: string;
  /** As ruas da trama do desenho próprio: a rua e o fio dela. */
  street: string;
  streetEdge: string;
  /** Fundo das etiquetas e da legenda. */
  chip: string;
  /** Texto sobre o papel e sobre as etiquetas. */
  text: string;
  /** A loja: no claro, o único preto cheio do mapa; no escuro, o único branco cheio. */
  store: string;
  storeText: string;
  /** O cinza neutro da legenda (a legenda fala de FORMA, não de cor). */
  neutral: string;
  /** O contorno da linha da corrida; "" usa a tinta da corrida. */
  halo: string;
}

export const MAP_LIGHT: MapTokens = {
  paper: "#f3ede3",
  street: "#ffffff",
  streetEdge: "#e4dccd",
  chip: "#ffffff",
  text: "#3a3631",
  store: "#111111",
  storeText: "#ffffff",
  neutral: "#5f6670",
  halo: "",
};

export const MAP_DARK: MapTokens = {
  paper: "#211d19",
  street: "#2f2a24",
  streetEdge: "#3a342d",
  chip: "#2c2722",
  text: "#f1ece4",
  store: "#ffffff",
  storeText: "#111111",
  neutral: "#b4bac2",
  halo: "#f1ece4",
};

/** As cores do mapa no tema da tela. */
export function mapTokens(dark: boolean): MapTokens {
  return dark ? MAP_DARK : MAP_LIGHT;
}

/** O texto dos pinos (sempre brancos): o mesmo nos dois temas. */
export const PIN_TEXT = "#3a3631";

/**
 * O contorno da linha (e da parada entregue) de uma corrida. No claro, a tinta da
 * corrida (o amarelo e o laranja leem sobre o papel por ela). No escuro, a própria
 * cor quando ela já destaca do papel (3:1); senão (o azul e o preto), o halo claro.
 */
export function lineOutline(tokens: MapTokens, ride: { bg: string; ink: string }): string {
  if (!tokens.halo) return ride.ink;
  return contrast(ride.bg, tokens.paper) >= 3 ? ride.bg : tokens.halo;
}

/**
 * O Google Maps de verdade no escuro (sem mapId, pelo array `styles`): o mesmo
 * papel do desenho próprio, ruas um tom acima, água e rótulos apagados. Sempre sem
 * comércio e ônibus: o que importa são as nossas paradas.
 */
const GOOGLE_BASE = [
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];
const GOOGLE_DARK = [
  { elementType: "geometry", stylers: [{ color: MAP_DARK.paper }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#9a9187" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: MAP_DARK.paper }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: MAP_DARK.street }] },
  { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: MAP_DARK.streetEdge }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#3d362e" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#141a1f" }] },
  { featureType: "landscape.natural", elementType: "geometry", stylers: [{ color: "#1c1916" }] },
  { featureType: "administrative", elementType: "geometry.stroke", stylers: [{ color: "#4a433a" }] },
];
export function googleMapStyles(dark: boolean): Record<string, unknown>[] {
  return dark ? [...GOOGLE_DARK, ...GOOGLE_BASE] : [...GOOGLE_BASE];
}

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
  /** Largura e altura do que se desenha (a moto é mais larga que a parada). */
  w?: number;
  h?: number;
}

/**
 * Marcadores que se cobrem (duas paradas no mesmo prédio, a moto em cima da parada)
 * se abrem num círculo pequeno, para cada um ter o seu toque. Dois se cobrem quando
 * as caixas se tocam; quem está sozinho não sai do lugar.
 */
export function spreadOverlaps(
  markers: readonly PlacedMarker[],
  size = 40,
  radius = 22,
): Map<string, { dx: number; dy: number }> {
  const out = new Map<string, { dx: number; dy: number }>();
  const touches = (a: PlacedMarker, b: PlacedMarker) =>
    Math.abs(a.x - b.x) < ((a.w ?? size) + (b.w ?? size)) / 2 &&
    Math.abs(a.y - b.y) < ((a.h ?? size) + (b.h ?? size)) / 2;
  const groups: PlacedMarker[][] = [];
  for (const marker of markers) {
    const group = groups.find((g) => g.some((m) => touches(m, marker)));
    if (group) group.push(marker);
    else groups.push([marker]);
  }
  for (const group of groups) {
    if (group.length < 2) {
      out.set(group[0]!.key, { dx: 0, dy: 0 });
      continue;
    }
    // Abre o bastante para as caixas deixarem de se tocar.
    const widest = Math.max(...group.map((m) => m.w ?? size));
    const r = Math.max(radius, Math.ceil(widest / 2) + 4);
    group.forEach((marker, i) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * i) / group.length;
      out.set(marker.key, { dx: Math.round(Math.cos(angle) * r), dy: Math.round(Math.sin(angle) * r) });
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
