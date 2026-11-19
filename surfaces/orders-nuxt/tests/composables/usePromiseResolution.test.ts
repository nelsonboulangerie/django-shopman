import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrderIntention } from "../../app/composables/useOrderIntention";
import { usePromiseResolution } from "../../app/composables/usePromiseResolution";
import type { PromiseResolutionConclude } from "../../app/presentation/promiseResolution";
import { EDIT_ITEMS, EDIT_PAYLOAD, RESOLUTION_REF, concludeOf, resolution } from "../support/promiseResolution";

// WP-G08: o diálogo "Resolver" lê as escolhas ao abrir e só grava "Tirar o item", pela
// edição do pedido que já existe, no protocolo de intenção das outras ações do Gestor.

const env = installNuxtGlobals();
const session = ref<{ operator?: { id: number } }>({ operator: { id: 7 } });
vi.stubGlobal("useNuxtData", () => ({ data: session }));
vi.stubGlobal("useOrderIntention", useOrderIntention);

const READ = `/api/v1/backstage/orders/${RESOLUTION_REF}/promise-resolution/`;
const EDIT = `/api/v1/backstage/orders/${RESOLUTION_REF}/edit/`;
const conclude = (over: Partial<PromiseResolutionConclude> = {}): PromiseResolutionConclude =>
  concludeOf({ kind: "edit", label: "Tirar o item", items: EDIT_ITEMS, payload_schema: EDIT_PAYLOAD, ...over });
const refusal = (status: number, body: Record<string, unknown>) => ({ status, data: body });

beforeEach(() => {
  env.reset();
  session.value = { operator: { id: 7 } };
});

describe("usePromiseResolution: a leitura", () => {
  it("lê as escolhas do pedido ao abrir, com prazo, e só lê", async () => {
    env.fetchMock.mockResolvedValue(resolution());
    const client = usePromiseResolution();
    expect(client.state.value).toBe("idle");
    const pending = client.read(RESOLUTION_REF);
    expect(client.state.value).toBe("loading");
    await pending;
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    expect(env.fetchMock).toHaveBeenCalledWith(READ, { timeout: 8000 });
    expect(client.state.value).toBe("ready");
    expect(client.resolution.value?.choices.map((choice) => choice.kind)).toEqual(["swap", "reschedule", "remove", "cancel"]);
  });

  it("409: o pedido não está mais em risco, com a frase do servidor", async () => {
    env.fetchMock.mockRejectedValue(refusal(409, { detail: "Este pedido não tem mais promessa em risco." }));
    const client = usePromiseResolution();
    await client.read(RESOLUTION_REF);
    expect(client.state.value).toBe("gone");
    expect(client.message.value).toBe("Este pedido não tem mais promessa em risco.");
    expect(client.resolution.value).toBeNull();
  });

  it("409 sem frase não deixa a tela muda", async () => {
    env.fetchMock.mockRejectedValue(refusal(409, {}));
    const client = usePromiseResolution();
    await client.read(RESOLUTION_REF);
    expect(client.message.value).toBe("Este pedido não tem mais promessa em risco.");
  });

  it("leitura que falha ou estoura o prazo vira erro, e tentar de novo lê outra vez", async () => {
    env.fetchMock.mockRejectedValueOnce(Object.assign(new Error("timeout"), { name: "TimeoutError" }));
    const client = usePromiseResolution();
    await client.read(RESOLUTION_REF);
    expect(client.state.value).toBe("error");
    // A frase técnica do transporte nunca vai para a tela.
    expect(client.message.value).toBe("");
    env.fetchMock.mockResolvedValueOnce(resolution());
    await client.read(RESOLUTION_REF);
    expect(client.state.value).toBe("ready");
  });

  it("a recusa de permissão chega com a frase do servidor", async () => {
    env.fetchMock.mockRejectedValue(refusal(403, { detail: "Você não tem permissão para gerenciar pedidos." }));
    const client = usePromiseResolution();
    await client.read(RESOLUTION_REF);
    expect(client.state.value).toBe("error");
    expect(client.message.value).toBe("Você não tem permissão para gerenciar pedidos.");
  });

  it("a resposta que chega depois de o diálogo fechar, ou de outro pedido abrir, é descartada", async () => {
    let finish!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const client = usePromiseResolution();
    const first = client.read(RESOLUTION_REF);
    client.clear();
    finish(resolution());
    await first;
    expect(client.state.value).toBe("idle");
    expect(client.resolution.value).toBeNull();

    let finishOld!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }));
    env.fetchMock.mockResolvedValueOnce(resolution({ code: "K42" }));
    const old = client.read(RESOLUTION_REF);
    await client.read("WEB-2611-OUTRO-K42");
    finishOld(resolution({ code: "N75" }));
    await old;
    expect(client.resolution.value?.code).toBe("K42");
  });
});

describe("usePromiseResolution: tirar o item", () => {
  it("grava pela edição do pedido: a lista final e o que a rota exige, como o servidor mandou, e uma chave", async () => {
    env.fetchMock.mockResolvedValue({ outcome: "applied" });
    const client = usePromiseResolution();
    const outcome = await client.removeMissing(RESOLUTION_REF, conclude());
    expect(outcome).toEqual({ ok: true, code: "", message: "" });
    // Uma ida só: nenhuma prévia, nenhuma leitura a mais.
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    const [path, options] = env.fetchMock.mock.calls[0]!;
    expect(path).toBe(EDIT);
    expect(options.method).toBe("POST");
    expect(options.body).toEqual({ items: EDIT_ITEMS, base_revision: "edit-rev-1", expected_actor_id: 7 });
    expect(options.headers["Idempotency-Key"]).toBeTruthy();
    expect(client.busy.value).toBe(false);
  });

  it("sem a revisão que a rota exige, não grava: a leitura está velha, e a frase diz o que fazer", async () => {
    const outcome = await usePromiseResolution().removeMissing(RESOLUTION_REF, conclude({ payload_schema: {} }));
    expect(outcome).toEqual({ ok: false, code: "", message: "Atualize os dados antes de continuar." });
    expect(env.fetchMock).not.toHaveBeenCalled();
  });

  it("a assinatura do gerente vai no mesmo gesto, com a mesma chave", async () => {
    env.fetchMock
      .mockRejectedValueOnce(refusal(403, { detail: "Peça a um gerente.", error: { code: "manager_approval_required", message: "Peça a um gerente." } }))
      .mockResolvedValueOnce({ outcome: "applied" });
    const client = usePromiseResolution();
    const asked = await client.removeMissing(RESOLUTION_REF, conclude());
    expect(asked).toEqual({ ok: false, code: "manager_approval_required", message: "Peça a um gerente." });
    const signed = await client.removeMissing(RESOLUTION_REF, conclude(), { username: "ana", pin: "4321" });
    expect(signed.ok).toBe(true);
    const [first, second] = env.fetchMock.mock.calls.map((call) => call[1]);
    expect(second.body.manager_approval).toEqual({ username: "ana", pin: "4321" });
    expect(second.headers).toEqual(first.headers);
  });

  it("PIN errado volta com o código e a frase do servidor", async () => {
    env.fetchMock.mockRejectedValue(refusal(403, { detail: "Aprovação gerencial inválida.", error: { code: "manager_approval_invalid", message: "Aprovação gerencial inválida." } }));
    const outcome = await usePromiseResolution().removeMissing(RESOLUTION_REF, conclude(), { username: "ana", pin: "0000" });
    expect(outcome).toEqual({ ok: false, code: "manager_approval_invalid", message: "Aprovação gerencial inválida." });
  });

  it("a recusa da edição volta com a frase do servidor, para ficar escrita no diálogo", async () => {
    env.fetchMock.mockRejectedValue(refusal(400, { detail: "Pedido em preparo não pode ser editado.", outcome: "not_applied" }));
    const outcome = await usePromiseResolution().removeMissing(RESOLUTION_REF, conclude());
    expect(outcome).toEqual({ ok: false, code: "", message: "Pedido em preparo não pode ser editado." });
  });

  it("o pedido mudou desde a leitura: o servidor recusa pela revisão, e a frase dele fica escrita", async () => {
    env.fetchMock.mockRejectedValue(refusal(409, { detail: "O pedido mudou. Atualize antes de gravar.", outcome: "not_applied" }));
    const outcome = await usePromiseResolution().removeMissing(RESOLUTION_REF, conclude());
    expect(outcome).toEqual({ ok: false, code: "", message: "O pedido mudou. Atualize antes de gravar." });
  });

  it("sem resposta e sem recibo, a frase não afirma que o pedido ficou igual", async () => {
    env.fetchMock.mockRejectedValue(Object.assign(new Error('[POST] "/api/x": <no response> Failed to fetch'), { name: "FetchError" }));
    const outcome = await usePromiseResolution().removeMissing(RESOLUTION_REF, conclude());
    expect(outcome.ok).toBe(false);
    expect(outcome.message).toBe(
      "Não deu para confirmar se o item saiu do pedido. Atualize o pedido para ver o estado atual antes de tentar de novo.",
    );
    expect(outcome.message).not.toContain("Failed to fetch");
  });

  it("sem pessoa identificada, a frase diz o que fazer", async () => {
    session.value = {};
    const outcome = await usePromiseResolution().removeMissing(RESOLUTION_REF, conclude());
    expect(outcome).toEqual({ ok: false, code: "", message: "Identifique-se antes de continuar." });
    expect(env.fetchMock).not.toHaveBeenCalled();
  });
});
