// Presentation — endereço de entrega do PDV.
//
// A REGRA do formulário (CEP, Google, ViaCEP, endereço completo, ponto no mapa) é
// a da loja online e mora no módulo gêmeo `addressForm.ts` (byte a byte igual ao
// do storefront). Aqui ficam só as pontes do PDV: o rascunho a partir do que o
// carrinho guarda, o rascunho de volta para o contrato (`StructuredAddressProjection`)
// e a ordem do Enter do balcão.

import type { StructuredAddressProjection } from "~/types/pos";
import {
  composedAddressLine,
  draftFromGooglePlace,
  draftFromViaCep,
  maskCepInput,
  type AddressDraft,
  type GooglePlaceFields,
  type ViaCepPayload,
} from "./addressForm";

export {
  BR_STATES,
  addressDraftErrors,
  cepDigits,
  composedAddressLine,
  draftSummaryLine,
  emptyAddressDraft,
  looksLikeCep,
  maskCepInput,
  mergeConfirmedPoint,
  pointMoved,
} from "./addressForm";
export type { AddressDraft, AddressPoint, ViaCepPayload } from "./addressForm";

/** Endereço estruturado a partir do ViaCEP; null quando o CEP não resolveu. */
export function structuredFromViaCep(
  payload: ViaCepPayload | null | undefined,
  queriedCep: string,
): StructuredAddressProjection | null {
  const draft = draftFromViaCep(payload, queriedCep);
  if (!draft) return null;
  return {
    formatted_address: draft.formatted_address,
    route: draft.route,
    neighborhood: draft.neighborhood,
    city: draft.city,
    state_code: draft.state_code,
    postal_code: draft.postal_code,
    country: "Brasil",
    country_code: "BR",
    latitude: null,
    longitude: null,
    place_id: null,
    is_verified: false,
  };
}

export type PlaceFields = GooglePlaceFields;

/** Endereço estruturado a partir de um Place da Places API (New). */
export function structuredFromPlaceFields(place: PlaceFields): StructuredAddressProjection {
  const draft = draftFromGooglePlace(place);
  const components = place.addressComponents || [];
  const country = components.find((component) => (component.types || []).includes("country"));
  return {
    formatted_address: draft.formatted_address,
    route: draft.route,
    street_number: draft.street_number,
    neighborhood: draft.neighborhood,
    city: draft.city,
    state_code: draft.state_code,
    postal_code: draft.postal_code,
    country: String(country?.longText || "").trim(),
    country_code: String(country?.shortText || "").trim(),
    latitude: draft.latitude ?? null,
    longitude: draft.longitude ?? null,
    place_id: draft.place_id || null,
    is_verified: Boolean(place.id),
  };
}

/** O que o carrinho guarda do endereço, campo a campo (as props do Recebimento). */
export interface DeliveryAddressState {
  route: string;
  streetNumber: string;
  neighborhood: string;
  complement: string;
  instructions: string;
  structured: StructuredAddressProjection;
}

/** O rascunho do formulário a partir do carrinho: os campos digitados vencem o estruturado. */
export function draftFromDeliveryState(state: DeliveryAddressState): AddressDraft {
  const structured = state.structured || {};
  return {
    formatted_address: structured.formatted_address || "",
    route: state.route,
    street_number: state.streetNumber,
    complement: state.complement,
    neighborhood: state.neighborhood,
    city: structured.city || "",
    state_code: structured.state_code || "",
    postal_code: structured.postal_code || "",
    latitude: structured.latitude ?? null,
    longitude: structured.longitude ?? null,
    place_id: structured.place_id || "",
    coordinates_source: null,
    delivery_instructions: state.instructions,
  };
}

/**
 * O rascunho de volta para o contrato. A linha formatada é RECOMPOSTA dos campos,
 * como na loja: a do Google fica velha no instante em que o operador corrige o
 * número.
 */
export function structuredFromDraft(
  draft: AddressDraft,
  base: StructuredAddressProjection = {},
): StructuredAddressProjection {
  const structured: StructuredAddressProjection = {
    ...base,
    formatted_address: composedAddressLine(draft) || draft.formatted_address,
    route: draft.route.trim(),
    street_number: draft.street_number.trim(),
    neighborhood: draft.neighborhood.trim(),
    city: draft.city.trim(),
    state_code: draft.state_code.trim().toUpperCase(),
    postal_code: maskCepInput(draft.postal_code),
    complement: draft.complement.trim(),
    delivery_instructions: draft.delivery_instructions.trim(),
    latitude: draft.latitude,
    longitude: draft.longitude,
    place_id: draft.place_id || null,
  };
  return structured;
}

/**
 * Os campos do endereço de entrega, na ORDEM DA TELA do Recebimento (a mesma da
 * loja: rua; número e complemento; bairro e CEP; cidade e UF; instruções). É a
 * ordem do Enter: cada Enter leva ao próximo campo AINDA VAZIO, pulando o que o CEP
 * ou o Google já trouxe. Complemento e instruções são opcionais, mas vazios são a
 * vez: é o operador quem decide deixá-los em branco, com mais um Enter.
 */
export const DELIVERY_ADDRESS_FIELDS = [
  "route",
  "number",
  "complement",
  "neighborhood",
  "postal_code",
  "city",
  "state",
  "instructions",
] as const;
export type DeliveryAddressField = (typeof DELIVERY_ADDRESS_FIELDS)[number];
export type DeliveryAddressValues = Record<DeliveryAddressField, string>;

/** O campo da tela de cada chave do rascunho (para a validação apontar o lugar). */
export const DRAFT_FIELD_OF: Record<string, DeliveryAddressField> = {
  route: "route",
  street_number: "number",
  complement: "complement",
  neighborhood: "neighborhood",
  postal_code: "postal_code",
  city: "city",
  state_code: "state",
  delivery_instructions: "instructions",
};

export function deliveryValuesFromDraft(draft: AddressDraft): DeliveryAddressValues {
  return {
    route: draft.route,
    number: draft.street_number,
    complement: draft.complement,
    neighborhood: draft.neighborhood,
    postal_code: draft.postal_code,
    city: draft.city,
    state: draft.state_code,
    instructions: draft.delivery_instructions,
  };
}

/**
 * O próximo campo vazio DEPOIS de `after` (ou desde o primeiro, com `after`
 * nulo: o endereço acabou de chegar da busca). `null` quando não sobra nenhum:
 * o endereço está completo e a vez é do próximo passo da encomenda.
 */
export function nextEmptyAddressField(
  after: DeliveryAddressField | null,
  values: DeliveryAddressValues,
): DeliveryAddressField | null {
  const start = after ? DELIVERY_ADDRESS_FIELDS.indexOf(after) + 1 : 0;
  return DELIVERY_ADDRESS_FIELDS.slice(start).find((field) => !(values[field] || "").trim()) ?? null;
}

/** O primeiro campo da tela com erro de validação (para o foco ir até ele). */
export function firstInvalidField(errors: Record<string, string>): DeliveryAddressField | null {
  return DELIVERY_ADDRESS_FIELDS.find((field) =>
    Object.keys(errors).some((key) => DRAFT_FIELD_OF[key] === field),
  ) ?? null;
}
