import { computed, watch, type ComputedRef, type Ref } from "vue";

import {
  operatorTableViewCookie,
  parseTableView,
  toggleHidden,
  visibilityFromHidden,
  type OperatorTableDensity,
  type OperatorTableViewState,
} from "../presentation/operatorTable";

/**
 * A forma de uma tabela neste dispositivo (densidade e colunas ocultas), partilhada por
 * quem a desenha (`OperatorTable`) e por quem a muda (`OperatorTableView`, o "Exibir"
 * da toolbar). As duas peças só precisam da mesma `key`.
 *
 * Cookie por dispositivo (SSR-safe: o servidor já desenha a densidade e as colunas
 * certas) com a verdade reativa num `useState` do app, o mesmo desenho do
 * `useRailState`. A tabela também publica aqui as colunas que podem sumir, para o
 * "Exibir" listá-las sem a tela repetir a lista.
 */
export function useOperatorTableView(key: string): {
  view: Ref<OperatorTableViewState>;
  density: ComputedRef<OperatorTableDensity>;
  visibility: ComputedRef<Record<string, boolean>>;
  columns: Ref<{ id: string; label: string }[]>;
  setDensity: (next: OperatorTableDensity) => void;
  setVisible: (id: string, visible: boolean) => void;
  showAll: () => void;
} {
  const cookieName = operatorTableViewCookie(key);
  const cookie = useCookie<OperatorTableViewState>(cookieName, {
    default: () => parseTableView(null),
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 365,
    path: "/",
  });
  const view = useState<OperatorTableViewState>(`operator-table-view:${key}`, () =>
    parseTableView(cookie.value),
  );
  watch(
    view,
    (next) => {
      cookie.value = next;
    },
    { deep: true },
  );
  const columns = useState<{ id: string; label: string }[]>(`operator-table-columns:${key}`, () => []);

  return {
    view,
    density: computed(() => view.value.density),
    visibility: computed(() => visibilityFromHidden(view.value.hidden)),
    columns,
    setDensity(next) {
      view.value = { ...view.value, density: next };
    },
    setVisible(id, visible) {
      view.value = { ...view.value, hidden: toggleHidden(view.value.hidden, id, visible) };
    },
    showAll() {
      view.value = { ...view.value, hidden: [] };
    },
  };
}
