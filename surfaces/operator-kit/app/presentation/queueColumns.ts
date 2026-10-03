// Colunas de fila ajustáveis e recolhíveis (forma FILA do kit): transformações puras.
//
// Uma fila em colunas (Entrada, Preparo, Saída do Gestor; amanhã qualquer outra)
// deixa cada posto arrumar a tela para o trabalho dele: a coluna aberta tem um PESO
// (a fração da largura que ela ocupa), a recolhida vira uma faixa estreita. O tablet
// do passe fica só com a Saída; o PC do gestor fica com as três.
//
// O componente só desenha o que sai daqui, então "o que acontece ao arrastar, ao
// tocar na faixa e ao apertar 2" é testável sem montar Vue. Quem guarda a arrumação
// (o servidor, por posto) é o app; aqui ela entra e sai higienizada.

export interface QueueColumnSetting {
  open: boolean;
  /** Fração da largura entre as colunas abertas (1 = parte igual). */
  weight: number;
}

export type QueueColumnLayout = Record<string, QueueColumnSetting>;

/** Largura da faixa recolhida, em px. */
export const QUEUE_STRIP_PX = 56;
/** Abaixo disto a coluna aberta para de encolher enquanto se arrasta. */
export const QUEUE_COLUMN_MIN_PX = 220;
/** Soltar a alça com a coluna mais estreita que isto recolhe a coluna. */
export const QUEUE_COLLAPSE_PX = 140;
/** Passo da alça pelo teclado (setas). */
export const QUEUE_KEYBOARD_STEP_PX = 48;

export const QUEUE_WEIGHT_MIN = 0.25;
export const QUEUE_WEIGHT_MAX = 4;

function clampWeight(value: number): number {
  if (!Number.isFinite(value)) return 1;
  const clamped = Math.min(QUEUE_WEIGHT_MAX, Math.max(QUEUE_WEIGHT_MIN, value));
  return Math.round(clamped * 100) / 100;
}

/** As colunas todas abertas, em partes iguais: a arrumação de quem nunca mexeu. */
export function defaultQueueLayout(keys: readonly string[]): QueueColumnLayout {
  return Object.fromEntries(keys.map((key) => [key, { open: true, weight: 1 }]));
}

/**
 * Arrumação higienizada contra as colunas vivas. Coluna que não existe mais some,
 * coluna nova entra aberta, peso fora da faixa volta para dentro dela, e nunca sai
 * daqui uma tela com todas recolhidas (a fila não pode desaparecer).
 */
export function normalizeQueueLayout(keys: readonly string[], raw: unknown): QueueColumnLayout {
  const source = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const layout: QueueColumnLayout = {};
  for (const key of keys) {
    const item = source[key];
    const entry = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
    layout[key] = {
      open: typeof entry.open === "boolean" ? entry.open : true,
      weight: clampWeight(typeof entry.weight === "number" ? entry.weight : 1),
    };
  }
  if (keys.length && !keys.some((key) => layout[key]!.open)) return defaultQueueLayout(keys);
  return layout;
}

export function openQueueKeys(layout: QueueColumnLayout, keys: readonly string[]): string[] {
  return keys.filter((key) => layout[key]?.open);
}

export function isDefaultQueueLayout(layout: QueueColumnLayout, keys: readonly string[]): boolean {
  return keys.every((key) => layout[key]?.open && layout[key]?.weight === 1);
}

export function allQueueColumnsOpen(layout: QueueColumnLayout, keys: readonly string[]): boolean {
  return keys.every((key) => layout[key]?.open);
}

/** Abre a coluna recolhida ou recolhe a aberta. Recolher a última aberta não faz nada. */
export function toggleQueueColumn(layout: QueueColumnLayout, keys: readonly string[], key: string): QueueColumnLayout {
  const current = layout[key];
  if (!current) return layout;
  if (current.open && openQueueKeys(layout, keys).length <= 1) return layout;
  return { ...layout, [key]: { ...current, open: !current.open } };
}

export function openQueueColumn(layout: QueueColumnLayout, key: string): QueueColumnLayout {
  const current = layout[key];
  if (!current || current.open) return layout;
  return { ...layout, [key]: { ...current, open: true } };
}

/** "Mostrar as 3 colunas": todas abertas, em partes iguais. */
export function showAllQueueColumns(keys: readonly string[]): QueueColumnLayout {
  return defaultQueueLayout(keys);
}

/** O `grid-template-columns` da arrumação: faixa fixa para a recolhida, fração para a aberta. */
export function queueGridTemplate(layout: QueueColumnLayout, keys: readonly string[]): string {
  return keys
    .map((key) => (layout[key]?.open ? `minmax(0, ${layout[key]!.weight}fr)` : `${QUEUE_STRIP_PX}px`))
    .join(" ");
}

/** A próxima coluna aberta à direita: com quem a alça desta coluna divide a largura. */
export function nextOpenQueueKey(layout: QueueColumnLayout, keys: readonly string[], key: string): string | null {
  const index = keys.indexOf(key);
  if (index < 0) return null;
  return keys.slice(index + 1).find((candidate) => layout[candidate]?.open) ?? null;
}

export interface QueueResizeInput {
  left: string;
  right: string;
  /** Larguras medidas no começo do arraste. */
  leftPx: number;
  rightPx: number;
  /** Deslocamento total desde o começo do arraste (positivo = alça para a direita). */
  deltaPx: number;
  /** Fim do arraste: só aqui a coluna estreita demais recolhe. */
  final: boolean;
}

/**
 * Arrasta a alça entre duas colunas abertas. A soma dos dois pesos não muda: o que
 * uma ganha a outra perde, e as demais ficam onde estavam. Durante o arraste nenhuma
 * fica mais estreita que o mínimo; ao soltar, a que passou do ponto recolhe (desde
 * que sobre outra aberta, e sempre sobra: a vizinha).
 */
export function resizeQueueColumns(layout: QueueColumnLayout, keys: readonly string[], input: QueueResizeInput): QueueColumnLayout {
  const left = layout[input.left];
  const right = layout[input.right];
  if (!left?.open || !right?.open) return layout;
  const total = input.leftPx + input.rightPx;
  if (total <= 0) return layout;
  const wantLeft = input.leftPx + input.deltaPx;
  const wantRight = input.rightPx - input.deltaPx;
  if (input.final && wantLeft < QUEUE_COLLAPSE_PX) return toggleQueueColumn(layout, keys, input.left);
  if (input.final && wantRight < QUEUE_COLLAPSE_PX) return toggleQueueColumn(layout, keys, input.right);
  const min = Math.min(QUEUE_COLUMN_MIN_PX, total / 2);
  const leftPx = Math.min(total - min, Math.max(min, wantLeft));
  const pairWeight = left.weight + right.weight;
  const leftWeight = clampWeight((pairWeight * leftPx) / total);
  const rightWeight = clampWeight(pairWeight - leftWeight);
  return {
    ...layout,
    [input.left]: { ...left, weight: leftWeight },
    [input.right]: { ...right, weight: rightWeight },
  };
}

/** Tecla de 1 a 9 → a coluna daquela posição, ou null. */
export function queueColumnForKey(key: string, keys: readonly string[]): string | null {
  if (!/^[1-9]$/.test(key)) return null;
  return keys[Number(key) - 1] ?? null;
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

/** "Visão: Saída" quando alguma coluna está recolhida; vazio com todas abertas. */
export function queueViewLabel(layout: QueueColumnLayout, keys: readonly string[], titles: Record<string, string>): string {
  if (allQueueColumnsOpen(layout, keys)) return "";
  return `Visão: ${joinNames(openQueueKeys(layout, keys).map((key) => titles[key] ?? key))}`;
}

/** Nome acessível da faixa recolhida: o que ela abre e o que há lá dentro. */
export function queueStripLabel(
  title: string,
  count: number,
  late: number,
  noun: readonly [string, string] = ["pedido", "pedidos"],
): string {
  const orders = `${count} ${count === 1 ? noun[0] : noun[1]}`;
  const lateText = late ? `, ${late === 1 ? "1 atrasado" : `${late} atrasados`}` : "";
  return `Abrir a coluna ${title}: ${orders}${lateText}`;
}
