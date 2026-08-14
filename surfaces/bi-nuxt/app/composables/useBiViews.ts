// Cenários salvos (F9): CRUD leve sobre /bi/views/. Config é validada pelo
// servidor com a mesma gramática do explorador — o cliente só transporta.
export interface SavedView {
  id: number;
  name: string;
  config: { metric: string; by: string; by2: string; window?: Record<string, string> };
  is_favorite: boolean;
}

export function useBiViews() {
  const { data, refresh } = useFetch<{ views: SavedView[] }>("/api/v1/backstage/bi/views/", {
    key: "bi-views",
    server: true,
    onResponseError: operatorSessionOnError,
  });

  const views = computed(() => data.value?.views ?? []);

  async function save(name: string, config: SavedView["config"]): Promise<boolean> {
    try {
      await $fetch("/api/v1/backstage/bi/views/", { method: "POST", body: { name, config } });
      await refresh();
      useSonner.success("Cenário salvo.");
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não deu para salvar o cenário."));
      return false;
    }
  }

  async function toggleFavorite(view: SavedView): Promise<void> {
    try {
      await $fetch(`/api/v1/backstage/bi/views/${view.id}/`, {
        method: "PATCH",
        body: { is_favorite: !view.is_favorite },
      });
      await refresh();
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não deu para atualizar o cenário."));
    }
  }

  async function remove(view: SavedView): Promise<void> {
    try {
      await $fetch(`/api/v1/backstage/bi/views/${view.id}/`, { method: "DELETE" });
      await refresh();
      useSonner.success("Cenário apagado.");
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não deu para apagar o cenário."));
    }
  }

  return { views, save, toggleFavorite, remove, refresh };
}
