// Selo leva iniciais maiúsculas, sempre, na suíte inteira (dono, 03/11/2026: "Loja
// Online", "A Receber"; 04/11/2026: vale para todos os apps, não só para as Encomendas).
//
// A regra mora num ponto só: o `NuxtBadge` do kit (components/NuxtBadge.vue) passa o
// `label` e o texto escrito dentro do selo por aqui. Nenhum app precisa lembrar dela.

import { Text, createTextVNode, isVNode, type VNode, type VNodeArrayChildren } from "vue";

/** Artigo e preposição no meio do selo ficam em minúscula ("Pagar na Retirada"). */
const LOWER_WORDS = new Set([
  "a", "o", "as", "os", "e", "de", "da", "do", "das", "dos",
  "na", "no", "nas", "nos", "em", "com", "por", "para",
  "à", "às", "ao", "aos", "sem", "até", "ou", "num", "numa",
]);

/** Unidade de medida se escreve como é ("2 kg", não "2 Kg"). */
const UNITS = new Set(["kg", "g", "mg", "l", "ml", "un", "min", "h", "s", "x", "cm", "mm", "km"]);

/**
 * "Loja online" → "Loja Online"; "a receber" → "A Receber"; "Pagar na retirada" →
 * "Pagar na Retirada". A primeira palavra é sempre maiúscula. Marca e sigla com
 * maiúscula no meio ("iFood", "PDV"), palavra com número ("NB-1042", "2x") e unidade
 * ("kg") ficam como estão.
 */
export function badgeCase(label: string): string {
  return label
    .trim()
    .split(/\s+/)
    .map((word, index) => {
      if (!word) return word;
      if (/[A-Z]/.test(word.slice(1)) || /\d/.test(word)) return word;
      const lower = word.toLowerCase();
      if (UNITS.has(lower)) return word;
      if (index > 0 && LOWER_WORDS.has(lower)) return lower;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

/**
 * O mesmo, aplicado ao texto escrito dentro do selo (`<NuxtBadge>pago</NuxtBadge>` ou
 * `{{ estado }}`): troca só os nós de texto, e deixa ícone e componente como estão.
 */
export function badgeCaseNodes(nodes: VNodeArrayChildren): VNodeArrayChildren {
  return nodes.map((node) => {
    if (typeof node === "string") return badgeCase(node);
    if (Array.isArray(node)) return badgeCaseNodes(node);
    if (!isVNode(node)) return node;
    return badgeCaseNode(node);
  });
}

function badgeCaseNode(node: VNode): VNode {
  if (node.type === Text && typeof node.children === "string") {
    return node.children.trim() ? createTextVNode(badgeCase(node.children)) : node;
  }
  if (typeof node.type === "object" || typeof node.type === "function") return node;
  // Fragmento ou elemento nativo (`<span>`): desce até o texto. Elemento só com texto
  // guarda o texto direto em `children`, sem nó de texto.
  if (typeof node.children === "string") return { ...node, children: badgeCase(node.children) } as VNode;
  if (Array.isArray(node.children)) return { ...node, children: badgeCaseNodes(node.children) } as VNode;
  return node;
}
