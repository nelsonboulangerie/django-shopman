// Presentation — endereço de entrega no checkout do PDV.
//
// Transforms puros do autocomplete: detectar CEP, mascarar, e converter o que
// vem do Google Places (New) e do ViaCEP para a StructuredAddressProjection
// canônica do contrato. Mesmo desenho do `presentation/address` do storefront
// (a fonte do mecanismo); zero política — quem valida endereço é o servidor.

import type { StructuredAddressProjection } from "~/types/pos";
import type { GoogleAddressComponent } from "~/types/googleMaps";

export function cepDigits(value: string): string {
  return (value || "").replace(/\D/g, "").slice(0, 8);
}

export function maskCepInput(value: string): string {
  const digits = cepDigits(value);
  if (digits.length <= 5) return digits;
  return `${digits.slice(0, 5)}-${digits.slice(5)}`;
}

/** 8 dígitos (com ou sem hífen/ponto/espaço) parecem CEP — gatilho do fallback ViaCEP. */
export function looksLikeCep(query: string): boolean {
  const compact = (query || "").replace(/[\s.-]/g, "");
  return /^\d{8}$/.test(compact);
}

export interface ViaCepPayload {
  erro?: boolean | string;
  logradouro?: string;
  bairro?: string;
  localidade?: string;
  uf?: string;
  cep?: string;
}

/** Endereço estruturado a partir do ViaCEP; null quando o CEP não resolveu. */
export function structuredFromViaCep(
  payload: ViaCepPayload | null | undefined,
  queriedCep: string,
): StructuredAddressProjection | null {
  if (!payload || payload.erro) return null;
  const route = (payload.logradouro || "").trim();
  const neighborhood = (payload.bairro || "").trim();
  const city = (payload.localidade || "").trim();
  const stateCode = (payload.uf || "").trim().toUpperCase();
  if (!city || !stateCode) return null;
  const cityState = [city, stateCode].filter(Boolean).join("/");
  return {
    formatted_address: [route, neighborhood, cityState].filter(Boolean).join(", "),
    route,
    neighborhood,
    city,
    state_code: stateCode,
    postal_code: maskCepInput(payload.cep || queriedCep),
    country: "Brasil",
    country_code: "BR",
    latitude: null,
    longitude: null,
    place_id: null,
    is_verified: false,
  };
}

function componentText(
  components: GoogleAddressComponent[],
  types: string[],
  short = false,
): string {
  const wanted = new Set(types);
  for (const component of components) {
    if ((component.types || []).some((type) => wanted.has(type))) {
      const text = short ? component.shortText : component.longText;
      if (text) return String(text).trim();
    }
  }
  return "";
}

/**
 * Consulta por CEP no Places devolve FAIXA ("1-494") como street_number — não é
 * número de porta; melhor vazio, e o operador digita o número real.
 */
function cleanStreetNumber(value: string): string {
  return /^\d+\s*-\s*\d+$/.test(value.trim()) ? "" : value;
}

export interface PlaceFields {
  id?: string | null;
  formattedAddress?: string | null;
  addressComponents?: GoogleAddressComponent[] | null;
  latitude?: number | null;
  longitude?: number | null;
}

/** Endereço estruturado a partir de um Place da Places API (New). */
export function structuredFromPlaceFields(place: PlaceFields): StructuredAddressProjection {
  const components = place.addressComponents || [];
  return {
    formatted_address: place.formattedAddress || "",
    route: componentText(components, ["route"]),
    street_number: cleanStreetNumber(componentText(components, ["street_number"])),
    neighborhood: componentText(components, ["sublocality_level_1", "sublocality", "neighborhood"]),
    city: componentText(components, ["administrative_area_level_2", "locality"]),
    state_code: componentText(components, ["administrative_area_level_1"], true),
    postal_code: maskCepInput(componentText(components, ["postal_code"])),
    country: componentText(components, ["country"]),
    country_code: componentText(components, ["country"], true),
    latitude: place.latitude ?? null,
    longitude: place.longitude ?? null,
    place_id: place.id || null,
    is_verified: Boolean(place.id),
  };
}
