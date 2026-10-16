// Cenários salvos do explorador (F9): as leituras salvas da tela `bi`/`explore`, no
// modelo genérico da suíte (`useSavedViews`, K4). A config é validada pelo servidor
// com a mesma gramática do explorador; o cliente só transporta.
import type { SavedViewRecord } from "../../../operator-kit/app/composables/useSavedViews";

export interface ScenarioConfig {
  metric: string;
  by: string;
  by2: string;
  window?: Record<string, string>;
}

export type SavedView = SavedViewRecord<ScenarioConfig>;

export function useBiViews() {
  const saved = useSavedViews<ScenarioConfig>("bi", "explore");

  async function save(name: string, config: ScenarioConfig): Promise<boolean> {
    return Boolean(await saved.save(name, config));
  }

  async function toggleFavorite(view: SavedView): Promise<void> {
    await saved.setPinned(view, !view.pinned);
  }

  return { views: saved.views, save, toggleFavorite, remove: saved.remove, refresh: saved.refresh };
}
