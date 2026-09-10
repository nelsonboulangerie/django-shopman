import type { HubTileProjection } from "~/types/hub";

// Presentation pura da Central — sem estado, sem Nuxt; testável isolada.

/** O ícone do tile vem sem prefixo do Django; o <Icon> do @nuxt/icon quer `lucide:x`. */
export function tileIcon(icon: string): string {
  return icon.startsWith("lucide:") ? icon : `lucide:${icon}`;
}

/** Launch (superfície de operador) fica na mesma aba; external (loja do cliente) abre em nova. */
export function tileTarget(tile: Pick<HubTileProjection, "kind">): "_self" | "_blank" {
  return tile.kind === "external" ? "_blank" : "_self";
}

/** Grade vazia = operador autenticado sem nenhum app liberado (estado acolhedor). */
export function hubIsEmpty(tiles: HubTileProjection[]): boolean {
  return tiles.length === 0;
}

/** Saudação sóbria (sem hora do dia — o operador entra em qualquer turno). */
export function hubGreeting(operatorName: string): string {
  const name = (operatorName || "").trim();
  return name ? `Olá, ${name}` : "Central de Apps";
}

// ── Por que a Central falhou, e o que isso pede da tela ──────────────────────
//
// ⚠️ `useFetch` popula `error` em qualquer não-2xx, e a Central reduzia CINCO causas
// distintas a um booleano que subia o formulário de senha. No balcão isso significa:
// API fora do ar → formulário de senha; deploy em andamento → formulário de senha;
// estação travada → formulário de SENHA, num balcão onde a credencial é PIN ou crachá.
//
// O código da recusa já chega no payload (`error.code`); a Central simplesmente não o
// lia. Classificar é ler o que o servidor já diz.

export type HubFailure = "none" | "login" | "station" | "forbidden" | "unavailable";

/**
 * Traduz o erro do fetch na ÚNICA saída que a tela deve oferecer.
 *
 * A ordem importa: `station_locked` é um 403 e cairia em "sem permissão" se a
 * checagem genérica viesse antes. E `not_authenticated` chega como **403**, não 401 —
 * o backstage roda com um authenticator só, e o DRF rebaixa o 401 (ver
 * `shop/api_errors.py`). Por isso o narrowing é por CÓDIGO, e o `isUnauthenticatedError`
 * do kit já sabe disso.
 */
export function hubFailure(
  error: unknown,
  helpers: {
    isUnauthenticated: (e: unknown) => boolean;
    isStationLocked: (e: unknown) => boolean;
    isTransient: (e: unknown) => boolean;
    status: (e: unknown) => number;
  },
): HubFailure {
  if (!error) return "none";
  if (helpers.isStationLocked(error)) return "station";
  if (helpers.isUnauthenticated(error)) return "login";
  if (helpers.isTransient(error)) return "unavailable";
  return helpers.status(error) === 403 ? "forbidden" : "unavailable";
}

/** O que a tela diz em cada caso — copy do operador, não jargão de HTTP. */
export function hubFailureCopy(failure: HubFailure): { title: string; hint: string; retry: boolean } {
  switch (failure) {
    case "login":
      return {
        title: "Sua sessão expirou",
        hint: "Entre de novo para continuar.",
        retry: false,
      };
    case "station":
      return {
        title: "Estação travada",
        hint: "Identifique-se com o PIN ou o crachá para liberar.",
        retry: false,
      };
    case "forbidden":
      return {
        title: "Você não tem acesso à Central",
        hint: "Fale com o gerente para liberar os aplicativos do seu turno.",
        retry: false,
      };
    case "unavailable":
      return {
        title: "Central indisponível",
        hint: "Pode ser a rede ou uma atualização em andamento. Tente de novo em instantes.",
        retry: true,
      };
    default:
      return { title: "", hint: "", retry: false };
  }
}
