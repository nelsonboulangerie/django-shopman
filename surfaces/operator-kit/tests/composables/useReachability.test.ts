import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { nextTick } from "vue";

// "Sem conexão" tem duas metades: o navegador na rede E o servidor respondendo.
// Wi-fi de pé com o link caído só aparece pela falha de TRANSPORTE; a sonda leve
// é o que devolve o "alcançável" quando ninguém está pedindo nada.
const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);

describe("isTransportFailure", () => {
  it("sem resposta (status 0, sem corpo) é transporte", () => {
    expect(isTransportFailure(new Error("network"))).toBe(true);
    expect(isTransportFailure(new DOMException("timeout", "TimeoutError"))).toBe(true);
  });

  it("o BFF dizendo que não alcançou o Django é transporte", () => {
    for (const [status, code] of [[502, "upstream_unreachable"], [504, "upstream_timeout"], [503, "upstream_unavailable"]] as const) {
      expect(isTransportFailure({ status, data: { detail: "x", error: { code } } })).toBe(true);
    }
  });

  it("uma resposta do Django, mesmo 5xx, NÃO é transporte", () => {
    expect(isTransportFailure({ status: 500, data: { detail: "Erro" } })).toBe(false);
    expect(isTransportFailure({ status: 502, data: { detail: "Erro do gateway de pagamento" } })).toBe(false);
    expect(isTransportFailure({ status: 403, data: { detail: "Sem permissão" } })).toBe(false);
    expect(isTransportFailure({ data: { detail: "corpo sem status" } })).toBe(false);
  });
});

describe("useReachability + useConnectivity", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
    resetReachability();
  });
  afterEach(() => {
    resetReachability();
    vi.useRealTimers();
  });

  it("falha de transporte põe o operador sem conexão com o navegador online", () => {
    const reachability = useReachability();
    const { isOnline } = useConnectivity();
    expect(isOnline.value).toBe(true);

    expect(reachability.noteFailure(new Error("network"))).toBe(true);
    expect(isOnline.value).toBe(false);

    reachability.noteSuccess();
    expect(isOnline.value).toBe(true);
  });

  it("resposta de erro do Django prova que o caminho está de pé", () => {
    const reachability = useReachability();
    reachability.noteFailure(new Error("network"));
    expect(reachability.noteFailure({ status: 409, data: { detail: "Conflito" } })).toBe(false);
    expect(reachability.reachable.value).toBe(true);
  });

  it("a sonda leve devolve o alcançável e conta como reconexão", async () => {
    const reachability = useReachability();
    const { onReconnect } = useConnectivity();
    const handler = vi.fn();
    onReconnect(handler);

    fetchMock.mockRejectedValue(new Error("network"));
    reachability.noteFailure(new Error("network"));
    await nextTick();
    await vi.advanceTimersByTimeAsync(REACHABILITY_PROBE_EVERY_MS);
    expect(String(fetchMock.mock.calls[0]![0])).toContain(REACHABILITY_PROBE_PATH);
    expect((fetchMock.mock.calls[0]![1] as { signal?: AbortSignal }).signal).toBeInstanceOf(AbortSignal);
    expect(reachability.reachable.value).toBe(false);
    expect(handler).not.toHaveBeenCalled();

    // O link voltou: a sessão responde 403 (não importa o status: houve resposta).
    fetchMock.mockRejectedValue({ status: 403, data: { detail: "Autenticação necessária." } });
    await vi.advanceTimersByTimeAsync(REACHABILITY_PROBE_EVERY_MS);
    await nextTick();
    expect(reachability.reachable.value).toBe(true);
    expect(handler).toHaveBeenCalledTimes(1);

    // Alcançável, a sonda para.
    const calls = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(REACHABILITY_PROBE_EVERY_MS * 3);
    expect(fetchMock.mock.calls.length).toBe(calls);
  });
});
