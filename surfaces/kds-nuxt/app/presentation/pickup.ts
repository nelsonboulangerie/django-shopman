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

// ── A TV não rola (beta 05/11, KDS-09) ────────────────────────────────────────
// O painel ocupa a tela e nunca passa dela: com mais pedidos, os cartões ficam mais
// densos (mais colunas, número menor), e o que ainda não couber vira "+N" no fim da
// coluna, em vez de cair abaixo da dobra de uma tela que ninguém consegue rolar.
// As faixas são medidas para a menor TV da casa (1024x768); TV maior só sobra.

export type PickupDensity = "roomy" | "compact" | "dense";

export interface PickupColumnLayout<T> {
  density: PickupDensity;
  shown: T[];
  /** Quantos ficaram de fora ("+N"). Zero = todos à vista. */
  more: number;
}

/** Quantos cartões cabem em cada densidade, por coluna, na tela de 1024x768. */
export const PICKUP_CAPACITY: Record<PickupDensity, number> = { roomy: 4, compact: 10, dense: 18 };

export function pickupDensity(count: number): PickupDensity {
  if (count <= PICKUP_CAPACITY.roomy) return "roomy";
  if (count <= PICKUP_CAPACITY.compact) return "compact";
  return "dense";
}

export function pickupColumn<T>(items: readonly T[]): PickupColumnLayout<T> {
  const density = pickupDensity(items.length);
  const capacity = PICKUP_CAPACITY[density];
  if (items.length <= capacity) return { density, shown: [...items], more: 0 };
  // O último lugar vira o "+N": nenhum cartão cortado pela metade.
  const shown = items.slice(0, capacity - 1);
  return { density, shown, more: items.length - shown.length };
}

/** A grade e o cartão de cada densidade. */
export const PICKUP_DENSITY_CLASSES: Record<PickupDensity, { grid: string; card: string; code: string }> = {
  roomy: { grid: "grid-cols-1", card: "px-6 py-5", code: "text-5xl md:text-7xl" },
  compact: { grid: "grid-cols-2", card: "px-4 py-3", code: "text-4xl md:text-5xl" },
  dense: { grid: "grid-cols-3", card: "px-3 py-2", code: "text-3xl md:text-4xl" },
};

/** O que o cliente lê no cartão: só o código. O prefixo do ref ("PDV-261105-") é
 *  da casa, e em cima do número se lia como parte dele (beta 05/11, KDS-16). */
export function pickupCode(ref: string): string {
  const i = ref.lastIndexOf("-");
  return i < 0 ? ref : ref.slice(i + 1);
}
