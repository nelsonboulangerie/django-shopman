// O estado da busca da suíte que não é de um componente só.
//
// - Pedido de abertura: a lupa da barra de 56px do celular (`OperatorPageHeader`) e o
//   campo da Central pedem "abra a busca"; quem abre é a `OperatorSuiteSearch` montada.
// - Teclas: `/` e Ctrl K valem na tela inteira, mas só para UMA busca (a última montada).
//   Duas buscas montadas não abrem duas vezes.
// - Leitura: `GET /api/v1/backstage/search/?q=` com espera entre teclas; resposta que
//   chega depois de outra mais nova é descartada (digitar rápido não pisca resultado velho).
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";

import {
  SUITE_SEARCH_DEBOUNCE_MS,
  normalizeSuiteQuery,
  suiteQueryReady,
  type SuiteSearchAppCount,
  type SuiteSearchGroup,
  type SuiteSearchResponse,
} from "../presentation/suiteSearch";

const owners: symbol[] = [];

/** A lupa (ou outro gatilho) pede a busca aberta; a busca montada atende. */
export function useSuiteSearchRequest() {
  const requests = useState<number>("suite-search-request", () => 0);
  return {
    requests,
    request: () => {
      requests.value += 1;
    },
  };
}

/**
 * Registra a busca como dona das teclas enquanto montada; ``isOwner()`` diz se é ela
 * quem atende agora (a última montada que ainda está de pé).
 */
export function useSuiteSearchOwnership() {
  const id = Symbol("suite-search");
  onMounted(() => owners.push(id));
  onBeforeUnmount(() => {
    const index = owners.indexOf(id);
    if (index >= 0) owners.splice(index, 1);
  });
  return { isOwner: () => owners[owners.length - 1] === id };
}

export type SuiteSearchStatus = "idle" | "loading" | "ready" | "error";

export function useSuiteSearchResults(query: Ref<string>, enabled: Ref<boolean>) {
  const apiPath = useApiPath();
  const groups = ref<SuiteSearchGroup[]>([]);
  const apps = ref<SuiteSearchAppCount[]>([]);
  const status = ref<SuiteSearchStatus>("idle");
  const searchedFor = ref("");
  let sequence = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function load(term: string) {
    const mine = ++sequence;
    status.value = "loading";
    try {
      const response = await $fetch<SuiteSearchResponse>(apiPath("/api/v1/backstage/search/"), {
        query: { q: term },
      });
      if (mine !== sequence) return;
      groups.value = response.search.groups;
      apps.value = response.search.apps;
      searchedFor.value = response.search.query;
      status.value = "ready";
    } catch {
      if (mine !== sequence) return;
      status.value = "error";
    }
  }

  function schedule(immediate = false) {
    if (timer) clearTimeout(timer);
    const term = normalizeSuiteQuery(query.value);
    if (!enabled.value || !suiteQueryReady(term)) {
      sequence += 1;
      groups.value = [];
      apps.value = [];
      searchedFor.value = "";
      status.value = "idle";
      return;
    }
    if (term === searchedFor.value && status.value === "ready") return;
    status.value = "loading";
    timer = setTimeout(() => void load(term), immediate ? 0 : SUITE_SEARCH_DEBOUNCE_MS);
  }

  watch([query, enabled], () => schedule());
  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer);
    sequence += 1;
  });

  return {
    groups,
    apps,
    status,
    searchedFor,
    retry: () => {
      searchedFor.value = "";
      schedule(true);
    },
  };
}
