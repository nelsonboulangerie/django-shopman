// O rótulo de uma ação que se adapta ao espaço (pedido do dono, 10/10/2026: copy de
// botão estourando em vários apps). Política da suíte, nesta ordem:
//
//   1. o rótulo completo ("Enviar à cozinha");
//   2. o rótulo curto DECLARADO pela própria ação (`shortLabel`, "Cozinha"). Nunca uma
//      abreviação inventada pelo código: quem conhece a ação escreve o curto;
//   3. só o ícone, com o rótulo completo como nome acessível e como dica (`title`).
//
// Nunca cortar no meio sem reticências, nunca vazar do botão, nunca empurrar a barra
// para fora da tela. Texto que NÃO é ação (nome de produto, de cliente) tem outra regra
// (`op-fixed-lines`, no `operator-fit.css`).
//
// A troca é pelo espaço do CONTÊINER, não pela largura da tela, e não roda em JS: o
// contêiner declara `container-type: inline-size` (`@container` no Tailwind, ou a classe
// `op-fit-scope`) e o CSS compara `100cqi` (a largura dele) com a largura que a ação
// precisa. Essa largura sai daqui, calculada no servidor e no cliente pelo mesmo código
// a partir do texto (as larguras de glifo da Instrument Sans, a fonte da suíte), e entra
// como variável CSS (`--op-fit-full`, `--op-fit-short`). SSR e hidratação desenham a
// mesma coisa: não há medição no navegador, nem troca depois de montar.
//
// Funções puras: o componente (`OperatorButton`) e as barras do kit só aplicam o que
// elas decidem, e os testes travam a conta sem montar nada.

export type OperatorFitSize = "xs" | "sm" | "md" | "lg" | "xl";

/** Uma ação que pode encolher: o rótulo, o curto que a ação escreveu e o ícone. */
export interface OperatorAdaptiveLabel {
  label: string;
  /** O rótulo curto, escrito por quem conhece a ação ("Cozinha" para "Enviar à cozinha"). */
  shortLabel?: string;
  icon?: string;
}

/**
 * Avanço de cada glifo da Instrument Sans em `em`, o maior entre os pesos 500 e 600
 * (o `font-medium` do botão e o `font-semibold` de quem o engrossa). Medido no Chromium
 * do CI com a fonte da suíte (`marketing-nuxt/public/fonts/instrument-sans-latin-*.woff2`),
 * corpo de 1000 px, dez repetições por glifo. Glifo fora da tabela conta como largo.
 */
const GLYPH_EM: Record<string, number> = {
  "0": 0.688, "1": 0.385, "2": 0.567, "3": 0.587, "4": 0.618, "5": 0.581, "6": 0.624,
  "7": 0.568, "8": 0.609, "9": 0.626,
  a: 0.544, b: 0.621, c: 0.55, d: 0.621, e: 0.577, f: 0.376, g: 0.621, h: 0.612,
  i: 0.255, j: 0.26, k: 0.558, l: 0.26, m: 0.941, n: 0.612, o: 0.597, p: 0.621,
  q: 0.621, r: 0.39, s: 0.501, t: 0.413, u: 0.591, v: 0.541, w: 0.72, x: 0.584,
  y: 0.541, z: 0.502,
  A: 0.733, B: 0.643, C: 0.745, D: 0.755, E: 0.634, F: 0.598, G: 0.764, H: 0.731,
  I: 0.254, J: 0.426, K: 0.712, L: 0.589, M: 0.902, N: 0.731, O: 0.799, P: 0.667,
  Q: 0.806, R: 0.663, S: 0.637, T: 0.667, U: 0.705, V: 0.733, W: 1.077, X: 0.701,
  Y: 0.7, Z: 0.625,
  " ": 0.197, ".": 0.241, ",": 0.241, ":": 0.275, ";": 0.275, "!": 0.267, "?": 0.58,
  "-": 0.458, "/": 0.32, "(": 0.341, ")": 0.342, $: 0.637, "%": 0.786, "+": 0.52,
  "&": 0.768, "'": 0.229, '"': 0.423, "#": 0.727, "@": 0.867, "*": 0.411, "=": 0.528,
  "<": 0.499, ">": 0.5, _: 0.503, "·": 0.144, "…": 0.728, "×": 0.544,
  á: 0.544, à: 0.544, â: 0.544, ã: 0.544, é: 0.577, ê: 0.577, í: 0.268, ó: 0.597,
  ô: 0.597, õ: 0.597, ú: 0.591, ü: 0.591, ç: 0.55,
  Á: 0.733, À: 0.733, Â: 0.733, Ã: 0.733, É: 0.634, Ê: 0.634, Í: 0.254, Ó: 0.799,
  Ô: 0.799, Õ: 0.799, Ú: 0.705, Ç: 0.745,
};

/** Glifo que a tabela não conhece: conta largo (melhor encolher cedo que vazar). */
const UNKNOWN_GLYPH_EM = 0.8;

/**
 * Folga da conta: a fonte de reserva (antes do webfont carregar, ou sem ele) e o
 * arredondamento do navegador nunca fazem o rótulo passar da estimativa.
 */
const SAFETY = 1.06;

/** Largura do texto em `em` da fonte do botão. */
export function labelWidthEm(text: string): number {
  let width = 0;
  for (const glyph of text) width += GLYPH_EM[glyph] ?? UNKNOWN_GLYPH_EM;
  return width * SAFETY;
}

/**
 * A anatomia do `NuxtButton` por tamanho (o tema oficial do Nuxt UI 4: `px-*`, `gap-*`
 * e o `size-*` do ícone), em `rem`. `square` é o respiro do botão só de ícone.
 */
export const FIT_SIZE_METRICS: Record<
  OperatorFitSize,
  { padding: number; gap: number; icon: number; square: number }
> = {
  xs: { padding: 0.5, gap: 0.25, icon: 1, square: 0.25 },
  sm: { padding: 0.625, gap: 0.375, icon: 1, square: 0.375 },
  md: { padding: 0.625, gap: 0.375, icon: 1.25, square: 0.375 },
  lg: { padding: 0.75, gap: 0.5, icon: 1.25, square: 0.5 },
  xl: { padding: 0.75, gap: 0.5, icon: 1.5, square: 0.5 },
};

/** O espaço entre ações irmãs numa barra (`gap-2`), em `rem`. */
export const FIT_GROUP_GAP_REM = 0.5;

/** Respiro de 1 px por botão para borda/anel e arredondamento. */
const BORDER_REM = 0.0625;

interface Width {
  em: number;
  rem: number;
}

function cssLength({ em, rem }: Width): string {
  const parts: string[] = [];
  if (em > 0) parts.push(`${round(em)}em`);
  if (rem > 0 || parts.length === 0) parts.push(`${round(rem)}rem`);
  return parts.length === 1 ? parts[0]! : `calc(${parts.join(" + ")})`;
}

function round(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

/** Quanto um botão precisa mostrando um texto (com o ícone, se houver). */
function buttonWidth(text: string, icon: boolean, size: OperatorFitSize): Width {
  const metric = FIT_SIZE_METRICS[size];
  return {
    em: labelWidthEm(text),
    rem: metric.padding * 2 + (icon ? metric.icon + metric.gap : 0) + BORDER_REM * 2,
  };
}

function sum(widths: Width[], gapRem: number): Width {
  const total = widths.reduce((acc, width) => ({ em: acc.em + width.em, rem: acc.rem + width.rem }), {
    em: 0,
    rem: 0,
  });
  return { em: total.em, rem: total.rem + Math.max(0, widths.length - 1) * gapRem };
}

export function shortOf(action: OperatorAdaptiveLabel): string {
  const short = action.shortLabel?.trim();
  return short && short !== action.label.trim() ? short : "";
}

/** A ação tem para onde encolher (um curto declarado, ou um ícone). */
export function isAdaptive(action: OperatorAdaptiveLabel): boolean {
  return Boolean(shortOf(action) || action.icon);
}

export interface OperatorFitOptions {
  size?: OperatorFitSize;
  /** Espaço entre as ações do grupo, em `rem` (padrão `gap-2`). */
  gap?: number;
  /** Largura que o contêiner gasta com o que não é ação (o ×, a frase), em `rem`. */
  reserve?: number;
}

/**
 * As variáveis CSS do encaixe de um grupo de ações que dividem o mesmo contêiner (uma
 * barra). Todas trocam juntas, para a barra nunca misturar "Enviar à cozinha" com um
 * ícone solto ao lado:
 *
 *   `--op-fit-full`   a largura em que todas cabem com o rótulo completo;
 *   `--op-fit-short`  a largura em que todas cabem com o curto (quem não tem curto, com
 *                     o completo). Abaixo dela, quem tem ícone vira só ícone.
 *
 * Uma ação sozinha é um grupo de uma (`OperatorButton` faz isso sozinho).
 */
export function actionFitVars(
  actions: readonly OperatorAdaptiveLabel[],
  options: OperatorFitOptions = {},
): Record<"--op-fit-full" | "--op-fit-short", string> {
  const size = options.size ?? "md";
  const gap = options.gap ?? FIT_GROUP_GAP_REM;
  const reserve = options.reserve ?? 0;
  const full = sum(
    actions.map((action) => buttonWidth(action.label, Boolean(action.icon), size)),
    gap,
  );
  // Abaixo de `--op-fit-short` quem tem ícone vira só ícone. Quem não tem ícone nunca
  // chega lá: fica com o curto (ou o completo) e quebra linha. Sem nenhum ícone no
  // grupo, o degrau 3 não existe e o limite é zero. Sem nenhum curto, o limite é o do
  // completo (do completo direto ao ícone).
  const anyIcon = actions.some((action) => action.icon);
  const short = sum(
    actions.map((action) => buttonWidth(shortOf(action) || action.label, Boolean(action.icon), size)),
    gap,
  );
  return {
    "--op-fit-full": cssLength({ em: full.em, rem: full.rem + reserve }),
    "--op-fit-short": anyIcon ? cssLength({ em: short.em, rem: short.rem + reserve }) : "0px",
  };
}

/**
 * Os atributos do botão que encolhe: o nome acessível (o completo, ou o `ariaLabel`
 * mais longo da ação), o degrau de tamanho (`data-op-fit`), se há ícone para o degrau 3
 * (`data-op-fit-icon`), a dica e, fora de um grupo, a própria necessidade (`style`).
 * Botão que não pode encolher leva só o `ariaLabel`, se a ação tiver um.
 */
export function actionFitAttrs(
  action: OperatorAdaptiveLabel & { ariaLabel?: string },
  options: { size?: OperatorFitSize; grouped?: boolean } = {},
): Record<string, string | Record<string, string> | undefined> {
  if (!isAdaptive(action)) return action.ariaLabel ? { "aria-label": action.ariaLabel } : {};
  const size = options.size ?? "md";
  return {
    "aria-label": action.ariaLabel || action.label,
    "data-op-fit": size,
    "data-op-fit-icon": action.icon ? "" : undefined,
    title: adaptiveTitle(action),
    style: options.grouped ? undefined : actionFitVars([action], { size }),
  };
}

/**
 * O que o leitor de tela e a dica dizem. O nome acessível é sempre o rótulo completo
 * (`ariaLabel` da ação quando ela já tem um nome mais longo, "Desfazer o Pronto do 0131").
 * A dica (`title`) só existe quando a ação pode encolher: botão que mostra sempre o
 * texto inteiro não repete o texto numa dica.
 */
export function adaptiveTitle(action: OperatorAdaptiveLabel & { ariaLabel?: string }): string | undefined {
  if (!isAdaptive(action)) return undefined;
  return action.ariaLabel || action.label;
}
