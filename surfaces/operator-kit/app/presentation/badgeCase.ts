// Selo é sentença: só a primeira letra maiúscula, o resto como foi escrito (dono,
// 16/11/2026: "'Procurando Outro Entregador' -> 'Procurando outro entregador'. A regra
// é clara: Maiúscula para primeira letra da sentença!", e vale para todo selo).
//
// Revertido em 16/11/2026: a regra de 03/11 e 04/11/2026 dava iniciais maiúsculas ao
// selo curto ("Loja Online", "A Receber", "Saiu para Entrega"). Não volta: a trava é
// `tests/badgeCase.test.ts`.
//
// A regra mora num ponto só: o `NuxtBadge` do kit (components/NuxtBadge.vue) passa o
// `label` e o texto escrito dentro do selo por aqui. Nenhum app precisa lembrar dela.
// Quem escreve o texto escreve em sentença; aqui só se garante a primeira maiúscula.

import { Text, createTextVNode, isVNode, type VNode, type VNodeArrayChildren } from "vue";

/** Separador de selos compostos ("Turno aberto · parcial"): cada parte é uma sentença. */
const SEGMENT_SEPARATOR = " · ";

function caseSegment(segment: string): string {
  const text = segment.trim();
  const first = text.split(/\s+/, 1)[0] ?? "";
  // Marca, sigla e código ficam como são ("iFood", "NFC-e", "NB-1042", "2 kg").
  if (!first || /[A-Z]/.test(first.slice(1)) || /\d/.test(first)) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * "loja online" → "Loja online"; "a receber" → "A receber"; "Pix · não pago" →
 * "Pix · Não pago". Só a primeira letra de cada parte muda; o resto fica como foi
 * escrito, então nome próprio ("Cozinha", "Diego") e sigla no meio continuam certos.
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
