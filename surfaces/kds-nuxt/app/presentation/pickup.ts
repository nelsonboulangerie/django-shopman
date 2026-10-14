// O Painel de retirada CHAMA: quando um número entra em "Pronto para retirar", o
// cartão dele fica em destaque por alguns segundos e a TV toca a chamada. O que já
// estava pronto quando o painel abriu não chama (ninguém precisa ouvir de novo o
// que já está na tela), e um número que sai e volta chama outra vez.

/** Quanto tempo o cartão recém-pronto fica em destaque. */
export const PICKUP_CALL_MS = 10_000;

/** A figura da chamada: ding-dong, duas notas descendo, o "sua vez" de balcão.
 *  Mesma voz da casa (o kit), figura própria: quem ouve é o cliente no salão. */
export const PICKUP_CALL_NOTES = [
  { f: 783.99, t: 0, d: 1.2 },
  { f: 659.25, t: 0.42, d: 1.6 },
] as const;

/**
 * Compara a leitura nova da coluna Pronto com a anterior.
 *
 * `previous === null` é a primeira leitura do painel: guarda o que já está pronto,
 * sem chamar nada. Depois disso, `fresh` são os números que acabaram de entrar.
 */
export function newlyReadyRefs(
  previous: ReadonlySet<string> | null,
  readyRefs: readonly string[],
): { ready: Set<string>; fresh: string[] } {
  const ready = new Set(readyRefs.filter(Boolean));
  const fresh = previous ? [...ready].filter((ref) => !previous.has(ref)) : [];
  return { ready, fresh };
}
