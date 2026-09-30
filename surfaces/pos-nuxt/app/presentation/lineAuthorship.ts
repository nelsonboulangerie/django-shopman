import type { POSCartItem, POSLineAuthorship } from "~/types/pos";

/** Aplica nas linhas do carrinho a autoria que o servidor carimbou no save.
 *
 *  Quem escreve a autoria é o servidor (`pos_intent.stamp_line_authorship`); o
 *  cliente só a mostra. Linha que o servidor não devolveu, ou devolveu sem
 *  carimbo, fica como estava. */
export function applyLineAuthors(
  items: POSCartItem[],
  lineAuthors: Record<string, POSLineAuthorship> | undefined | null,
): void {
  if (!lineAuthors) return;
  for (const item of items) {
    const authorship = lineAuthors[item.line_id];
    if (authorship && Object.keys(authorship).length) item.authorship = authorship;
  }
}
