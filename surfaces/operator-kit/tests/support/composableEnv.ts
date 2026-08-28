import { vi } from "vitest";
import { computed, nextTick, reactive, readonly, ref, shallowRef, watch } from "vue";

// Utilitários REAIS do kit (auto-imports em runtime) — implementação verdadeira (não
// mock) para o teste exercitar o narrowing/mensagem de fato (os `catch` dos composables
// dos apps usam httpError/httpErrorMessage do kit).
import { httpError, httpErrorMessage } from "../../app/utils/httpError";
import { retryWithBackoff } from "../../app/utils/retryBackoff";
import { useStationLock } from "../../app/composables/useStationLock";

/**
 * Harness ÚNICO para testar composables de operador em env `node` — do próprio kit e
 * dos apps que fazem `extends` (kds/orders/production importam DAQUI; não há cópia
 * por app).
 *
 * Por que node e não o env `nuxt`: o `@nuxt/test-utils` 4.0.3 quebra no SETUP para
 * apps COM router/pages — `nuxtApp._route` fica undefined e o ambiente nem inicia
 * (correção provada em orders-nuxt, B-ORD.1, e replicada em kds/production).
 *
 * Por que NÃO é gambiarra: a REATIVIDADE é o Vue REAL — `computed`/`ref`/`reactive`/
 * `watch` são as implementações verdadeiras, então os derivados recomputam de fato.
 * Só a **fronteira de dados/framework** é mockada (`useFetch`/`$fetch`/`useSonner`/
 * config e os auto-imports de app: `operatorSessionOnError`, `useAdaptivePoll`,
 * `refreshNuxtData`) — exatamente o que se mocka em QUALQUER teste unitário desses
 * composables. Lifecycle (onMounted/onBeforeUnmount/onUnmounted) vira no-op:
 * SSE/poll/beep/timers são território de e2e e de testes dedicados.
 *
 * ⚠️ Instância única do Vue: os projetos `unit` dos apps consumidores declaram
 * `resolve.dedupe: ["vue"]` no vitest.config para que o `vue` importado aqui e o
 * importado pelos testes do app sejam o MESMO módulo (reatividade não rastreia entre
 * cópias distintas).
 *
 * Se um composable passar a usar um auto-import não previsto aqui, o teste falha ALTO
 * (ReferenceError), nunca silenciosamente errado — o harness é auto-revelador.
 */
export interface ComposableEnv {
  /** Payload que o `useFetch` mockado devolve (definir ANTES de chamar o composable). */
  fetchData: { value: unknown };
  /** Erro que o `useFetch` mockado devolve (definir ANTES de chamar o composable).
   *  Existe porque o `error` fixo em `null` deixava passar tudo que a leitura faz
   *  COM o erro — foi assim que "403 station_locked vira banner de falha de rede"
   *  atravessou a suíte inteira verde. */
  fetchError: { value: unknown };
  /** `refresh` do useFetch. */
  refresh: ReturnType<typeof vi.fn>;
  /** `$fetch` (transporte de ação/escrita). */
  fetchMock: ReturnType<typeof vi.fn>;
  /** `useSonner` (toast). */
  sonner: { error: ReturnType<typeof vi.fn>; success: ReturnType<typeof vi.fn> };
  /** `refreshNuxtData` (usado pelo unlock e pelo operatorSessionOnError). */
  refreshNuxtData: ReturnType<typeof vi.fn>;
  /** `reportClientError` (observabilidade — fronteira, mockada). */
  clientErrorReport: ReturnType<typeof vi.fn>;
  /** `useAdaptivePoll` — no-op observável (o poll de verdade é testado à parte). */
  adaptivePoll: ReturnType<typeof vi.fn>;
  /** `useRuntimeConfig()`. */
  runtimeConfig: Record<string, unknown>;
  /** Estado compartilhado do `useState` (por chave), para inspeção e limpeza. */
  states: Map<string, ReturnType<typeof ref>>;
  /** Zera histórico dos mocks e o payload (chamar no `beforeEach`). */
  reset(): void;
}

export function installNuxtGlobals(): ComposableEnv {
  const env: ComposableEnv = {
    fetchData: { value: null },
    fetchError: { value: null },
    refresh: vi.fn(),
    fetchMock: vi.fn(),
    sonner: { error: vi.fn(), success: vi.fn() },
    refreshNuxtData: vi.fn(),
    clientErrorReport: vi.fn(),
    adaptivePoll: vi.fn(),
    runtimeConfig: { app: { baseURL: "/" }, public: { djangoBaseUrl: "" } },
    states: new Map(),
    reset() {
      env.fetchData.value = null;
      env.fetchError.value = null;
      env.refresh.mockReset();
      env.fetchMock.mockReset().mockResolvedValue({});
      env.sonner.error.mockReset();
      env.sonner.success.mockReset();
      env.refreshNuxtData.mockReset();
      env.clientErrorReport.mockReset().mockResolvedValue(true);
      env.adaptivePoll.mockReset();
      // Estado compartilhado é por-app em runtime; entre testes ele tem que morrer,
      // senão uma estação travada num teste vaza travada para o seguinte.
      env.states.clear();
    },
  };

  // Reatividade REAL do Vue.
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("readonly", readonly);
  vi.stubGlobal("shallowRef", shallowRef);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("nextTick", nextTick);
  // Lifecycle: sem componente montado → no-op.
  vi.stubGlobal("onMounted", () => {});
  vi.stubGlobal("onBeforeUnmount", () => {});
  vi.stubGlobal("onUnmounted", () => {});
  vi.stubGlobal("onScopeDispose", () => {});
  // Fronteira de dados/framework — mockada.
  vi.stubGlobal("useRuntimeConfig", () => env.runtimeConfig);
  // `useState`: um ref REAL por chave, compartilhado entre chamadas — é o que o Nuxt
  // dá, e é o que faz dois composables enxergarem o mesmo cadeado.
  vi.stubGlobal("useState", (key: string, init?: () => unknown) => {
    if (!env.states.has(key)) env.states.set(key, ref(init ? init() : undefined));
    return env.states.get(key)!;
  });
  vi.stubGlobal("useSonner", env.sonner);
  vi.stubGlobal("refreshNuxtData", env.refreshNuxtData);
  vi.stubGlobal("operatorSessionOnError", () => {});
  vi.stubGlobal("useAdaptivePoll", env.adaptivePoll);
  vi.stubGlobal("httpError", httpError); // implementação REAL do kit (narrowing tipado)
  vi.stubGlobal("httpErrorMessage", httpErrorMessage); // implementação REAL do kit
  vi.stubGlobal("retryWithBackoff", retryWithBackoff); // implementação REAL do kit
  vi.stubGlobal("useStationLock", useStationLock); // implementação REAL do kit (sobre o useState mockado)
  vi.stubGlobal("reportClientError", env.clientErrorReport);
  vi.stubGlobal("useFetch", () => ({
    data: ref(env.fetchData.value),
    pending: ref(false),
    error: ref(env.fetchError.value),
    refresh: env.refresh,
  }));
  vi.stubGlobal("$fetch", env.fetchMock);

  return env;
}
