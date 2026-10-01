// A estrela do operador sobre uma receita do inventário.
// POST marca e DELETE desmarca em /api/v1/backstage/recipes/<ref>/favorite/, os dois
// idempotentes no servidor; a resposta traz o estado que valeu. Preferência de quem
// lê: basta a leitura do inventário. Um toque em voo por receita (dois toques
// cruzados não têm ordem certa); falha vira toast e devolve `null` para a tela
// manter a estrela como estava.
import type { RecipeFavoriteResponse } from "~/types/recipeBook";

export function useRecipeFavorite() {
  const busyRefs = ref<string[]>([]);

  function isFavoriteBusy(entryRef: string): boolean {
    return busyRefs.value.includes(entryRef);
  }

  async function setFavorite(entryRef: string, next: boolean): Promise<boolean | null> {
    if (!entryRef || isFavoriteBusy(entryRef)) return null;
    busyRefs.value = [...busyRefs.value, entryRef];
    try {
      const response = await $fetch<RecipeFavoriteResponse>(
        `/api/v1/backstage/recipes/${encodeURIComponent(entryRef)}/favorite/`,
        { method: next ? "POST" : "DELETE" },
      );
      return !!response.is_favorite;
    } catch (err) {
      useSonner.error(
        httpErrorMessage(err, next ? "Não foi possível marcar a favorita." : "Não foi possível tirar das favoritas."),
      );
      return null;
    } finally {
      busyRefs.value = busyRefs.value.filter((busyRef) => busyRef !== entryRef);
    }
  }

  return { setFavorite, isFavoriteBusy };
}
