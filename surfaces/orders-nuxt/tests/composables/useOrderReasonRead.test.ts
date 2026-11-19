import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrderReasonRead } from "../../app/composables/useOrderReasonRead";

// WP-G06: o diálogo de recusa do painel lê o detalhe do pedido ao abrir, para dizer o
// que acontece com o dinheiro. O cartão não ganha campo.

const env = installNuxtGlobals();
const detail = (over: Record<string, unknown> = {}) => ({
  order: { ref: "NB-261118-W33", cancel_money_effect: "R$ 48,00 serão estornados ao Pix do cliente.", ...over },
});

describe("useOrderReasonRead", () => {
  beforeEach(() => env.reset());

  it("lê o detalhe do pedido e entrega a frase do dinheiro", async () => {
    env.fetchMock.mockResolvedValue(detail());
    const read = useOrderReasonRead();
    const pending = read.read("NB-261118-W33");
    expect(read.state.value).toBe("loading");
    expect(read.order.value).toBeNull();
    await pending;
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/orders/NB-261118-W33/", { timeout: 8000 });
    expect(read.state.value).toBe("ready");
    expect(read.order.value?.cancel_money_effect).toBe("R$ 48,00 serão estornados ao Pix do cliente.");
  });

  it("só lê: nenhuma gravação sai daqui", async () => {
    env.fetchMock.mockResolvedValue(detail());
    await useOrderReasonRead().read("NB-261118-W33");
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    const options = env.fetchMock.mock.calls[0]![1] as Record<string, unknown>;
    expect(options.method).toBeUndefined();
    expect(options.body).toBeUndefined();
  });

  // Enquanto lê, o confirmar espera: a leitura pendurada prenderia a recusa de um
  // pedido que se confirma sozinho no prazo.
  it("a leitura tem prazo, e a que estoura vira erro em vez de ficar lendo", async () => {
    env.fetchMock.mockRejectedValue(Object.assign(new Error("timeout"), { name: "TimeoutError" }));
    const read = useOrderReasonRead();
    await read.read("NB-261118-W33");
    expect(env.fetchMock.mock.calls[0]![1]).toEqual({ timeout: 8000 });
    expect(read.state.value).toBe("error");
  });

  it("leitura que falha vira estado de erro, não silêncio", async () => {
    env.fetchMock.mockRejectedValue(new Error("offline"));
    const read = useOrderReasonRead();
    await read.read("NB-261118-W33");
    expect(read.state.value).toBe("error");
    expect(read.order.value).toBeNull();
    // Tentar de novo lê outra vez.
    env.fetchMock.mockResolvedValue(detail());
    await read.read("NB-261118-W33");
    expect(read.state.value).toBe("ready");
  });

  it("a resposta que chega depois de o diálogo fechar é descartada", async () => {
    let resolve!: (value: unknown) => void;
    env.fetchMock.mockReturnValue(new Promise((done) => { resolve = done; }));
    const read = useOrderReasonRead();
    const pending = read.read("NB-261118-W33");
    read.clear();
    resolve(detail());
    await pending;
    expect(read.order.value).toBeNull();
    expect(read.state.value).toBe("ready");
  });

  it("abrir outro pedido antes de a primeira leitura voltar: vale a mais nova", async () => {
    let first!: (value: unknown) => void;
    env.fetchMock
      .mockReturnValueOnce(new Promise((done) => { first = done; }))
      .mockResolvedValueOnce(detail({ ref: "NB-261118-W34", cancel_money_effect: "Nada foi cobrado do cliente." }));
    const read = useOrderReasonRead();
    const stale = read.read("NB-261118-W33");
    await read.read("NB-261118-W34");
    first(detail());
    await stale;
    expect(read.order.value?.ref).toBe("NB-261118-W34");
    expect(read.order.value?.cancel_money_effect).toBe("Nada foi cobrado do cliente.");
  });
});
