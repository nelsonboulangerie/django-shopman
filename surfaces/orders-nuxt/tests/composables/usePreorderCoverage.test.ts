// WP-G10: a leitura da agenda com cobertura. Rota própria, relida quando as encomendas
// da lista mudam e num poll calmo (nenhum evento de produção chega ao Gestor). A falha
// não derruba a lista: a cobertura some e a tela oferece tentar de novo.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  PREORDER_COVERAGE_PATH,
  PREORDER_COVERAGE_POLL_MS,
  usePreorderCoverage,
} from "../../app/composables/usePreorderCoverage";
import { coveredDay, day } from "../support/preorderCoverage";

const env = installNuxtGlobals();
let mounts: Array<() => void> = [];
let unmounts: Array<() => void> = [];
let visibility = "visible";
const documentListeners = new Map<string, () => void>();
const windowListeners = new Map<string, () => void>();

const response = (...days: unknown[]) => ({
  coverage: { days },
  generated_at: "2026-11-18T12:00:00-03:00",
  contract_version: 1,
});
const reads = () =>
  env.fetchMock.mock.calls.filter(([url]) => url === PREORDER_COVERAGE_PATH).length;
const settle = () => vi.advanceTimersByTimeAsync(0);
const mount = () => {
  for (const run of mounts) run();
};

describe("usePreorderCoverage", () => {
  beforeEach(() => {
    env.reset();
    mounts = [];
    unmounts = [];
    visibility = "visible";
    documentListeners.clear();
    windowListeners.clear();
    vi.stubGlobal("onMounted", (fn: () => void) => mounts.push(fn));
    vi.stubGlobal("onBeforeUnmount", (fn: () => void) => unmounts.push(fn));
    vi.stubGlobal("document", {
      get visibilityState() {
        return visibility;
      },
      addEventListener: (name: string, fn: () => void) => {
        documentListeners.set(name, fn);
      },
      removeEventListener: (name: string) => {
        documentListeners.delete(name);
      },
    });
    vi.stubGlobal("window", {
      addEventListener: (name: string, fn: () => void) => {
        windowListeners.set(name, fn);
      },
      removeEventListener: (name: string) => {
        windowListeners.delete(name);
      },
    });
    vi.useFakeTimers();
  });
  afterEach(() => {
    for (const unmount of unmounts) unmount();
    vi.useRealTimers();
    vi.stubGlobal("onMounted", () => {});
    vi.stubGlobal("onBeforeUnmount", () => {});
  });

  it("lê a rota da cobertura quando há encomenda na lista", async () => {
    env.fetchMock.mockResolvedValue(response(day()));
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    expect(read.reading.value).toBe(true);
    await settle();

    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/orders/preorder-coverage/",
      { timeout: 8000 },
    );
    expect(read.coverage.value?.days[0]?.headline).toBe(
      "Faltam 6 Baguete de tradição. Sem lote para Ciabatta.",
    );
    expect(read.failed.value).toBe(false);
    expect(read.reading.value).toBe(false);
  });

  it("só lê: nenhuma gravação sai daqui", async () => {
    env.fetchMock.mockResolvedValue(response(day()));
    usePreorderCoverage(ref("NB-1@2026-11-21"));
    await settle();

    const options = env.fetchMock.mock.calls[0]![1] as Record<string, unknown>;
    expect(options.method).toBeUndefined();
    expect(options.body).toBeUndefined();
  });

  it("sem encomenda na lista, nada é lido", async () => {
    const read = usePreorderCoverage(ref(""));
    mount();
    await vi.advanceTimersByTimeAsync(PREORDER_COVERAGE_POLL_MS * 2);

    expect(reads()).toBe(0);
    expect(read.coverage.value).toBeNull();
    expect(read.failed.value).toBe(false);
  });

  it("relê quando o conjunto de encomendas muda", async () => {
    env.fetchMock.mockResolvedValueOnce(response(coveredDay()));
    const signature = ref("NB-1@2026-11-19");
    const read = usePreorderCoverage(signature);
    await settle();
    expect(read.coverage.value?.days).toHaveLength(1);

    env.fetchMock.mockResolvedValueOnce(response(coveredDay(), day()));
    signature.value = "NB-1@2026-11-19|NB-2@2026-11-21";
    await nextTick();
    await settle();

    expect(reads()).toBe(2);
    expect(read.coverage.value?.days.map((d) => d.date)).toEqual(["2026-11-19", "2026-11-21"]);
  });

  it("a rajada de mudanças da fila vira uma releitura só depois da que está em curso", async () => {
    let first!: (value: unknown) => void;
    env.fetchMock
      .mockReturnValueOnce(new Promise((done) => { first = done; }))
      .mockResolvedValue(response(day()));
    const signature = ref("a@2026-11-21");
    usePreorderCoverage(signature);
    for (const next of ["a|b", "a|b|c", "a|b|c|d"]) {
      signature.value = next;
      await nextTick();
    }
    expect(reads()).toBe(1);
    first(response(coveredDay()));
    await settle();

    expect(reads()).toBe(2);
  });

  it("a lista esvaziou: a cobertura some, e a resposta atrasada é descartada", async () => {
    let late!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((done) => { late = done; }));
    const signature = ref("NB-1@2026-11-21");
    const read = usePreorderCoverage(signature);
    signature.value = "";
    await nextTick();
    expect(read.reading.value).toBe(false);
    late(response(day()));
    await settle();

    expect(read.coverage.value).toBeNull();
    expect(read.failed.value).toBe(false);
  });

  it("poll calmo: o lote que a Produção planejou aparece na próxima volta", async () => {
    env.fetchMock.mockResolvedValueOnce(response(day()));
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    mount();
    await settle();
    expect(read.coverage.value?.days[0]?.state).toBe("short");

    env.fetchMock.mockResolvedValueOnce(
      response(day({ state: "covered", headline: "A produção cobre as encomendas." })),
    );
    await vi.advanceTimersByTimeAsync(PREORDER_COVERAGE_POLL_MS);

    expect(PREORDER_COVERAGE_POLL_MS).toBe(60_000);
    expect(reads()).toBe(2);
    expect(read.coverage.value?.days[0]?.headline).toBe("A produção cobre as encomendas.");
  });

  it("aba oculta não lê; ao voltar, relê na hora", async () => {
    env.fetchMock.mockResolvedValue(response(day()));
    usePreorderCoverage(ref("NB-1@2026-11-21"));
    mount();
    await settle();
    visibility = "hidden";
    await vi.advanceTimersByTimeAsync(PREORDER_COVERAGE_POLL_MS * 3);
    expect(reads()).toBe(1);

    visibility = "visible";
    documentListeners.get("visibilitychange")!();
    await settle();
    expect(reads()).toBe(2);
  });

  it("a falha não lança: a cobertura some e a tela sabe que falhou", async () => {
    env.fetchMock.mockResolvedValueOnce(response(day()));
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    mount();
    await settle();
    expect(read.coverage.value).not.toBeNull();

    env.fetchMock.mockRejectedValueOnce(new Error("offline"));
    await vi.advanceTimersByTimeAsync(PREORDER_COVERAGE_POLL_MS);

    // Melhor calar do que dizer "a produção cobre" com dado velho.
    expect(read.coverage.value).toBeNull();
    expect(read.failed.value).toBe(true);
    expect(read.reading.value).toBe(false);
  });

  it("\"Tentar de novo\" relê sem recarregar a página, e o sucesso apaga a falha", async () => {
    env.fetchMock.mockRejectedValueOnce(new Error("offline"));
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    await settle();
    expect(read.failed.value).toBe(true);

    let answer!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((done) => { answer = done; }));
    const retrying = read.retry();
    // Enquanto relê, a falha continua dita e o botão gira.
    expect(read.reading.value).toBe(true);
    expect(read.failed.value).toBe(true);
    answer(response(day()));
    await retrying;

    expect(read.failed.value).toBe(false);
    expect(read.coverage.value?.days).toHaveLength(1);
  });

  it("enquanto falha, o poll continua tentando sozinho", async () => {
    env.fetchMock.mockRejectedValueOnce(new Error("offline"));
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    mount();
    await settle();
    expect(read.failed.value).toBe(true);

    env.fetchMock.mockResolvedValueOnce(response(day()));
    await vi.advanceTimersByTimeAsync(PREORDER_COVERAGE_POLL_MS);

    expect(read.failed.value).toBe(false);
    expect(read.coverage.value?.days).toHaveLength(1);
  });

  it("resposta sem a agenda é falha de leitura, não \"nenhum dia\"", async () => {
    env.fetchMock.mockResolvedValueOnce({});
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    await settle();

    expect(read.coverage.value).toBeNull();
    expect(read.failed.value).toBe(true);
  });

  it("agenda vazia é leitura boa: nenhum dia para dizer", async () => {
    env.fetchMock.mockResolvedValueOnce(response());
    const read = usePreorderCoverage(ref("NB-1@2026-11-21"));
    await settle();

    expect(read.coverage.value).toEqual({ days: [] });
    expect(read.failed.value).toBe(false);
  });

  it("ao sair da tela, o poll e os ouvintes param", async () => {
    env.fetchMock.mockResolvedValue(response(day()));
    usePreorderCoverage(ref("NB-1@2026-11-21"));
    mount();
    await settle();
    expect([...documentListeners.keys()]).toEqual(["visibilitychange"]);
    expect([...windowListeners.keys()]).toEqual(["online"]);
    for (const unmount of unmounts) unmount();
    unmounts = [];
    await vi.advanceTimersByTimeAsync(PREORDER_COVERAGE_POLL_MS * 2);

    expect(reads()).toBe(1);
    expect(documentListeners.size).toBe(0);
    expect(windowListeners.size).toBe(0);
  });
});
