// Tipos MÍNIMOS da Google Maps JS API que a superfície realmente toca — a SDK é
// carregada dinamicamente por <script> (sem pacote npm/@types), então declaramos só o
// slice usado no autocomplete de endereço. Não é a API inteira, é o contrato de fato.
//
// O slice é o da Places API (New) — AutocompleteSuggestion.fetchAutocompleteSuggestions
// + Place.fetchFields — o MESMO mecanismo do storefront (AddressPicker). O widget
// legado (places.Autocomplete) ficou de fora de propósito: não está disponível para
// chaves novas da plataforma e o dropdown dele (.pac-container) nasce fora do modal.

export interface GoogleAddressComponent {
  types?: string[];
  longText?: string | null;
  shortText?: string | null;
}

export interface GooglePlace {
  id?: string | null;
  formattedAddress?: string | null;
  addressComponents?: GoogleAddressComponent[] | null;
  location?: { lat: () => number; lng: () => number } | null;
  fetchFields: (options: { fields: string[] }) => Promise<unknown>;
}

export interface GooglePlacePrediction {
  placeId?: string;
  text?: { text?: string };
  mainText?: { text?: string };
  secondaryText?: { text?: string };
  toPlace: () => GooglePlace;
}

export interface GoogleAutocompleteSuggestion {
  placePrediction?: GooglePlacePrediction | null;
}

export interface GoogleAutocompleteRequest {
  input: string;
  sessionToken?: unknown;
  includedRegionCodes?: string[];
  language?: string;
  region?: string;
  locationBias?: { center: { lat: number; lng: number }; radius: number };
}

export interface GooglePlacesLibrary {
  AutocompleteSuggestion?: {
    fetchAutocompleteSuggestions: (
      request: GoogleAutocompleteRequest,
    ) => Promise<{ suggestions?: GoogleAutocompleteSuggestion[] }>;
  };
  AutocompleteSessionToken?: new () => unknown;
}

export interface GoogleMapsNamespace {
  places?: GooglePlacesLibrary;
  importLibrary?: (name: string) => Promise<GooglePlacesLibrary | undefined>;
}

export interface GoogleNamespace {
  maps?: GoogleMapsNamespace;
}
