// As cores das corridas (dono, 14/11): fora da família das cores de estado da casa
// (latão, tijolo, verde-folha, âmbar, azul-poeira), saturadas e de contraste máximo
// entre si. A cor é a identidade da corrida enquanto ela vive: no mapa, no cartão do
// Saída e na sacola. Ela nunca vem sozinha: a letra da corrida vai junto.
//
// Quantas: a corrida vive ~45 a 60 min (chamar, esperar, entregar, voltar). Com 15
// entregas no dia e o pico concentrando ~40% numa hora, são 2 a 3 corridas vivas ao
// mesmo tempo; com o triplo de entregas, 6 a 8. Seis cores, devolvidas quando a
// corrida fecha, cobrem o caso de hoje com folga e o de amanhã quase sempre; a sétima
// corrida simultânea repete a cor da mais antiga, e a letra desfaz a dúvida.
export interface RideColor {
  name: string;
  bg: string;
  /** O texto sobre a cor: branco ou preto, o que passa de 4,5:1. */
  fg: string;
  /** A cor escrita sobre branco (a letra da parada): o mesmo matiz, escurecido até
   * passar de 4,5:1. Igual a `bg` quando ele já passa. */
  ink: string;
}

// Como linhas de metrô (dono, 14/11): cada cor num matiz bem longe das outras.
// Matizes: azul 223°, verde 142°, amarelo 48°, laranja 21°, magenta 327°, mais o preto,
// sem matiz. A ordem de uso é a do dono.
export const RIDE_PALETTE: readonly RideColor[] = [
  { name: "Azul", bg: "#0047ff", fg: "#ffffff", ink: "#0047ff" },
  // Verde escurecido (dono, 16/11: a moto com número no verde pedia letra branca;
  // #00a03c com branco dava 3,4:1). #008933 com branco: 4,5:1.
  { name: "Verde", bg: "#008933", fg: "#ffffff", ink: "#008933" },
  // A tinta do amarelo e do laranja tinha 4,50:1 e 4,56:1 sobre branco, no fio do AA;
  // o número da parada no detalhe da corrida mediu abaixo (#2983). Mesmo matiz, 4,64:1.
  { name: "Amarelo", bg: "#ffd000", fg: "#000000", ink: "#8c7200" },
  { name: "Laranja", bg: "#ff5a00", fg: "#000000", ink: "#cd4800" },
  { name: "Magenta", bg: "#e4007c", fg: "#ffffff", ink: "#e4007c" },
  { name: "Preto", bg: "#111111", fg: "#ffffff", ink: "#111111" },
];

export function rideColor(index: number): RideColor {
  return RIDE_PALETTE[((index % RIDE_PALETTE.length) + RIDE_PALETTE.length) % RIDE_PALETTE.length]!;
}
