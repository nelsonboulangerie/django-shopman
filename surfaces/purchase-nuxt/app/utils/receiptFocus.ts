import type { ReceiptFieldAnchor } from "~/types/purchase";

/**
 * O anel âmbar que aponta o campo por alguns segundos.
 *
 * Rolar até o campo resolve metade do problema: o operador chega lá e ainda
 * precisa achar QUAL dos quatro campos é o que falta. O anel some sozinho — é
 * um dedo apontando, não um estado do recebimento.
 */
export const FLASH_RING = "rounded-md ring-2 ring-warning ring-offset-2 ring-offset-background";

/**
 * O endereço de um campo do item DENTRO da gaveta.
 *
 * A gaveta mora num portal, no fim do `<body>`, e não dentro da linha da lista.
 * Procurar o campo a partir da linha (`[data-receipt-line=…] [data-receipt-field=…]`)
 * não acha nada — era assim que "Ir até lá" ficaria mudo depois de o formulário
 * sair do card para o overlay.
 */
export function receiptFieldSelector(lineId: string, field: ReceiptFieldAnchor | null): string {
  const sheet = `[data-receipt-sheet="${lineId}"]`;
  return field ? `${sheet} [data-receipt-field="${field}"]` : sheet;
}

function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => resolve());
    else setTimeout(resolve, 16);
  });
}

/**
 * Espera o elemento APARECER — a gaveta monta depois do quadro.
 *
 * Abrir a gaveta e procurar o campo no mesmo gesto devolve `null`: o portal
 * ainda não escreveu nada no documento. Um `nextTick` sozinho tampouco basta,
 * porque a montagem do portal e a animação de entrada custam alguns quadros. A
 * espera é curta e limitada: se em `attempts` quadros o campo não apareceu, é
 * porque ele não existe, e a tela não fica presa esperando.
 */
export async function waitForElement(selector: string, attempts = 12): Promise<HTMLElement | null> {
  if (typeof document === "undefined") return null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const found = document.querySelector<HTMLElement>(selector);
    if (found) return found;
    await nextFrame();
  }
  return document.querySelector<HTMLElement>(selector);
}
