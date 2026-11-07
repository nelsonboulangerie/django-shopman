// Selo leva iniciais maiúsculas, sempre, na suíte inteira (dono, 03/11/2026: "Loja
// Online", "A Receber"; 04/11/2026: vale para todos os apps, não só para as Encomendas).
// Frase dentro de selo não é nome, e fica com só a primeira maiúscula (beta 06/11:
// "Falhou em Todos os Canais", "Não Mostrar Valores").
//
// A regra mora num ponto só: o `NuxtBadge` do kit (components/NuxtBadge.vue) passa o
// `label` e o texto escrito dentro do selo por aqui. Nenhum app precisa lembrar dela.

import { Text, createTextVNode, isVNode, type VNode, type VNodeArrayChildren } from "vue";

/** Artigo e preposição no meio do selo ficam em minúscula ("Pagar na Retirada"). */
const LOWER_WORDS = new Set([
  "a", "o", "as", "os", "e", "de", "da", "do", "das", "dos",
  "na", "no", "nas", "nos", "em", "com", "por", "para",
  "à", "às", "ao", "aos", "sem", "até", "ou", "num", "numa", "pelo", "pela", "pelos", "pelas",
]);

/** Unidade de medida se escreve como é ("2 kg", não "2 Kg"). */
const UNITS = new Set(["kg", "g", "mg", "l", "ml", "un", "min", "h", "s", "x", "cm", "mm", "km"]);

/** Separador de selos compostos ("Turno aberto · parcial"): cada parte é um selo. */
const SEGMENT_SEPARATOR = " · ";

/** A partir de quantas palavras a parte é uma frase, não um nome. */
const PHRASE_MIN_WORDS = 5;

/**
 * Frase não é nome de selo: "Falhou em todos os canais", "Não mostrar valores",
 * "Aceito pelo provedor, sem comprovante". Com iniciais maiúsculas ela vira grito
 * ("Falhou em Todos os Canais", beta 06/11), e o padrão da casa para frase é só a
 * primeira maiúscula. É frase a parte com negação ("não"), com vírgula ou com
 * cinco palavras ou mais; o nome curto ("Loja Online", "Saiu para Entrega")
 * segue com iniciais maiúsculas.
 */
function isPhrase(words: readonly string[]): boolean {
  if (words.length >= PHRASE_MIN_WORDS) return true;
  return words.some((word) => word.includes(",") || word.toLowerCase() === "não");
}

function caseWord(word: string, index: number): string {
  if (!word) return word;
  if (/[A-Z]/.test(word.slice(1)) || /\d/.test(word)) return word;
  const lower = word.toLowerCase();
  if (UNITS.has(lower)) return word;
  if (index > 0 && LOWER_WORDS.has(lower)) return lower;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function caseSegment(segment: string): string {
  const words = segment.trim().split(/\s+/);
  if (isPhrase(words)) {
    // Frase: só a primeira letra maiúscula, o resto como foi escrito.
    const first = words[0] ?? "";
    words[0] = /[A-Z]/.test(first.slice(1)) || /\d/.test(first)
      ? first
      : first.charAt(0).toUpperCase() + first.slice(1);
    return words.join(" ");
  }
  return words.map(caseWord).join(" ");
}

/**
 * "Loja online" → "Loja Online"; "a receber" → "A Receber"; "Pagar na retirada" →
 * "Pagar na Retirada". A primeira palavra é sempre maiúscula. Marca e sigla com
 * maiúscula no meio ("iFood", "PDV"), palavra com número ("NB-1042", "2x") e unidade
 * ("kg") ficam como estão. Frase (ver `isPhrase`) fica com só a primeira maiúscula.
 */
export function badgeCase(label: string): string {
  return label.trim().split(SEGMENT_SEPARATOR).map(caseSegment).join(SEGMENT_SEPARATOR);
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
