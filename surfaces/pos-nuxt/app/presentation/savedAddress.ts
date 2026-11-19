/**
 * OS ENDEREÇOS JÁ CADASTRADOS DO CLIENTE, como opções de uma lista.
 *
 * Cada endereço é uma LINHA INTEIRA que se identifica sozinha: a rua com o número
 * e o complemento, e embaixo o bairro e a cidade. Eram botõezinhos com o rótulo
 * cortado, e num cliente vindo de pedido de entrega todos diziam "Entrega", a
 * mesma palavra do botão de cima (pedido do dono, 19/11/2026, #2754).
 *
 * A ETIQUETA só aparece quando identifica: "Casa", "Trabalho" ou o nome que o
 * cliente deu ("Mãe"). A etiqueta neutra que o sistema põe em todo endereço
 * salvo de um pedido de entrega (`shop/services/customer.py`: "Entrega") repete
 * o canal e não distingue um endereço do outro; "Outro" sem nome também não. Nos
 * dois casos quem fala é o endereço.
 */
import type { SavedAddressProjection, StructuredAddressProjection } from "~/types/pos";
import { addressDisplay } from "./address";

export interface SavedAddressOption {
  /** O id do cadastro, em texto: o valor da opção na lista. */
  value: string;
  /** Rua, número e complemento: o que identifica o endereço sozinho. */
  label: string;
  /** Bairro e cidade: o que desempata duas ruas parecidas. */
  description: string;
  /** A etiqueta do cliente, quando ela identifica (senão, vazia). */
  tag: string;
}

function fold(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Etiquetas que não distinguem um endereço do outro: o canal e a categoria vazia. */
const TAGS_THAT_SAY_NOTHING = new Set(["entrega", "delivery", "outro", "other"]);

/** A etiqueta que vale mostrar: a que o cliente reconhece e que não é o próprio endereço. */
export function savedAddressTag(address: SavedAddressProjection): string {
  const tag = String(address.label || "").replace(/\s+/g, " ").trim();
  const folded = fold(tag);
  if (!folded || TAGS_THAT_SAY_NOTHING.has(folded)) return "";
  // Sem etiqueta, a projeção devolve o próprio endereço no lugar dela.
  if (folded === fold(address.formatted_address)) return "";
  return tag;
}

export function savedAddressOption(address: SavedAddressProjection): SavedAddressOption {
  // As duas linhas são as do endereço em qualquer lugar do PDV (`addressDisplay`):
  // o resumo do endereço escolhido diz o mesmo texto, com o mesmo separador.
  const { street, place } = addressDisplay(address);
  return {
    value: String(address.id),
    label: street,
    description: place,
    tag: savedAddressTag(address),
  };
}

/** O que a entrega em edição guarda do endereço (os campos do carrinho). */
export interface ChosenAddressState {
  route: string;
  streetNumber: string;
  neighborhood: string;
  complement: string;
  structured?: StructuredAddressProjection;
}

const digits = (value: unknown) => String(value ?? "").replace(/\D/g, "");

/**
 * Qual endereço cadastrado é o da entrega em edição ("" quando nenhum: sem
 * endereço, ou um endereço digitado na hora). Compara o LUGAR, campo a campo: se
 * o operador corrigiu o número depois de escolher, a entrega já não é a do
 * cadastro, e a lista não pode continuar dizendo que é.
 */
export function chosenSavedAddressValue(addresses: SavedAddressProjection[], state: ChosenAddressState): string {
  const route = fold(state.route);
  if (!route) return "";
  const postalCode = digits(state.structured?.postal_code);
  const match = addresses.find((address) => {
    if (fold(address.route || address.formatted_address) !== route) return false;
    if (fold(address.street_number) !== fold(state.streetNumber)) return false;
    if (fold(address.neighborhood) !== fold(state.neighborhood)) return false;
    if (fold(address.complement) !== fold(state.complement)) return false;
    const saved = digits(address.postal_code);
    return !saved || !postalCode || saved === postalCode;
  });
  return match ? String(match.id) : "";
}
