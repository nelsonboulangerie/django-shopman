import { computed, type ComputedRef } from "vue";

import { httpErrorMessage } from "../utils/httpError";
import { operatorSessionOnError } from "../utils/operatorSession";

/**
 * As leituras salvas de uma tela (os favoritos do painel de filtros, K4): por pessoa,
 * guardadas no servidor (`/api/v1/backstage/saved-views/`), que valida o recorte pela
 * gramática da tela. O B.I. guarda ali os cenários do explorador (`bi`/`explore`).
 *
 * `Q` é a forma do recorte da tela: o `OperatorFilterPanel` usa
 * `{ filters, period?, group? }`; o explorador do B.I., `{ metric, by, by2, window }`.
 */
export interface SavedViewRecord<Q = Record<string, unknown>> {
  id: number;
  surface: string;
  screen: string;
  name: string;
  query: Q;
  /** Fixado: aparece entre os filtros rápidos da tela. */
  pinned: boolean;
}

const ENDPOINT = "/api/v1/backstage/saved-views/";

export function useSavedViews<Q = Record<string, unknown>>(
  surface: string,
  screen: string,
): {
  views: ComputedRef<SavedViewRecord<Q>[]>;
  save: (name: string, query: Q, options?: { pinned?: boolean }) => Promise<SavedViewRecord<Q> | null>;
  setPinned: (view: SavedViewRecord<Q>, pinned: boolean) => Promise<void>;
  rename: (view: SavedViewRecord<Q>, name: string) => Promise<boolean>;
  remove: (view: SavedViewRecord<Q>) => Promise<void>;
  refresh: () => Promise<void>;
} {
  const { data, refresh } = useFetch<{ views: SavedViewRecord<Q>[] }>(ENDPOINT, {
    key: `saved-views:${surface}:${screen}`,
    query: { surface, screen },
    server: true,
    onResponseError: operatorSessionOnError,
  });

  const views = computed(() => data.value?.views ?? []);

  async function save(name: string, query: Q, options: { pinned?: boolean } = {}) {
    try {
      const result = await $fetch<{ view: SavedViewRecord<Q> }>(ENDPOINT, {
        method: "POST",
        body: { surface, screen, name, query, ...(options.pinned === undefined ? {} : { pinned: options.pinned }) },
      });
      await refresh();
      useSonner.success("Favorito salvo.");
      return result.view;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar o favorito."));
      return null;
    }
  }

  async function patch(view: SavedViewRecord<Q>, body: Record<string, unknown>, failure: string) {
    try {
      await $fetch(`${ENDPOINT}${view.id}/`, { method: "PATCH", body });
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, failure));
      return false;
    }
  }

  async function setPinned(view: SavedViewRecord<Q>, pinned: boolean) {
    await patch(view, { pinned }, "Não foi possível atualizar o favorito.");
  }

  function rename(view: SavedViewRecord<Q>, name: string) {
    return patch(view, { name }, "Não foi possível renomear o favorito.");
  }

  async function remove(view: SavedViewRecord<Q>) {
    try {
      await $fetch(`${ENDPOINT}${view.id}/`, { method: "DELETE" });
      await refresh();
      useSonner.success("Favorito apagado.");
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível apagar o favorito."));
    }
  }

  return { views, save, setPinned, rename, remove, refresh: async () => void (await refresh()) };
}
