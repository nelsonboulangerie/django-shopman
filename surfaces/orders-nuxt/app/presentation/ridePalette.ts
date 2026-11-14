// As cores das corridas (dono, 14/11): fora da família das cores de estado da casa
// (latão, tijolo, verde-folha, âmbar, azul-poeira), saturadas e de contraste máximo
// entre si. A cor é a identidade da corrida enquanto ela vive: no mapa, no cartão do
// Saída e na sacola. Ela nunca vem sozinha: o número da corrida vai junto.
//
// Quantas: a corrida vive ~45 a 60 min (chamar, esperar, entregar, voltar). Com 15
// entregas no dia e o pico concentrando ~40% numa hora, são 2 a 3 corridas vivas ao
// mesmo tempo; com o triplo de entregas, 6 a 8. Seis cores, devolvidas quando a
// corrida fecha, cobrem o caso de hoje com folga e o de amanhã quase sempre; a sétima
// corrida simultânea repete a cor da mais antiga, e o número desfaz a dúvida.
export interface RideColor {
  name: string;
  bg: string;
  /** O texto sobre a cor: branco ou preto, o que passa de 4,5:1. */
  fg: string;
}

export const RIDE_PALETTE: readonly RideColor[] = [
  { name: "Preto", bg: "#111111", fg: "#ffffff" },
  { name: "Azul", bg: "#1f4fff", fg: "#ffffff" },
  { name: "Violeta", bg: "#7a2cff", fg: "#ffffff" },
  { name: "Magenta", bg: "#d6127f", fg: "#ffffff" },
  { name: "Ciano", bg: "#0089a8", fg: "#000000" },
  { name: "Laranja", bg: "#ff6a00", fg: "#000000" },
];

export function rideColor(index: number): RideColor {
  return RIDE_PALETTE[((index % RIDE_PALETTE.length) + RIDE_PALETTE.length) % RIDE_PALETTE.length]!;
}
