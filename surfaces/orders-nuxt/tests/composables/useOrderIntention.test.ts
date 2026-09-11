import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrderIntention } from "../../app/composables/useOrderIntention";
import { fixtureActions } from "../support/orderActions";

const env = installNuxtGlobals();
const session = ref<{ operator?: { id: number } }>({ operator: { id: 1 } });
vi.stubGlobal("useNuxtData", () => ({ data: session }));
const action = fixtureActions({ can_advance: true })[0]!;

beforeEach(() => { env.reset(); session.value = { operator: { id: 1 } }; });

describe("avanço — uma intenção, um resultado", () => {
  it("resposta perdida consulta recibo sem executar um segundo POST", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
    expect(await useOrderIntention().execute("ORDER", "advance", action, {})).toBe(true);
    const post = env.fetchMock.mock.calls[0]![1];
    const lookup = env.fetchMock.mock.calls[1]![1];
    expect(post.method).toBe("POST");
    expect(lookup.query.idempotency_key).toBe(post.headers["Idempotency-Key"]);
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
  });

  it("resultado desconhecido conserva chave e payload mesmo se a projeção avançar", async () => {
    const client = useOrderIntention();
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
    await expect(client.execute("ORDER", "advance", action, { change_out: "20,00" })).rejects.toThrow();
    const first = env.fetchMock.mock.calls[0]![1];
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    expect(await client.execute("ORDER", "advance", undefined, { change_out: "20,00" })).toBe(true);
    const retry = env.fetchMock.mock.calls[2]![1];
    expect(retry.headers).toEqual(first.headers);
    expect(retry.body).toEqual(first.body);
  });

  it("novo rascunho não é anunciado como salvo pelo recibo de uma nota anterior", async () => {
    const client = useOrderIntention();
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
    await expect(client.execute("ORDER", "notes", action, { notes: "Primeiro" })).rejects.toThrow();
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await expect(client.execute("ORDER", "notes", action, { notes: "Segundo" })).rejects.toThrow("novo rascunho ainda não foi salvo");
    expect(env.fetchMock.mock.calls[2]![1].method).toBeUndefined();
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    expect(await client.execute("ORDER", "notes", action, { notes: "Segundo" })).toBe(true);
    expect(env.fetchMock.mock.calls[3]![1].body.notes).toBe("Segundo");
    expect(env.fetchMock.mock.calls[3]![1].headers).not.toEqual(env.fetchMock.mock.calls[0]![1].headers);
  });

  it("troca de pessoa descarta a intenção e não aplica resposta da pessoa anterior", async () => {
    let resolve!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const client = useOrderIntention();
    const request = client.execute("ORDER", "advance", action, {});
    session.value = { operator: { id: 2 } };
    await nextTick();
    resolve({ outcome: "applied" });
    await expect(request).rejects.toThrow("identificação mudou");
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await client.execute("ORDER", "advance", action, {});
    expect(env.fetchMock.mock.calls[1]![1].headers["Idempotency-Key"]).not.toBe(env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"]);
  });
  it("assinatura é transitória e o desafio 422 conserva a mesma intenção", async () => {
    const client = useOrderIntention();
    env.fetchMock.mockRejectedValueOnce({ status: 422, data: { error: { code: "manager_approval_required" } } });
    await expect(client.execute("ORDER", "cancel", action, { reason: "Motivo" })).rejects.toBeDefined();
    const key = env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"];
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
    await expect(client.execute("ORDER", "cancel", action, { reason: "Motivo" }, { pin: "SYNTHETIC-PIN" })).rejects.toThrow();
    expect(env.fetchMock.mock.calls[1]![1].headers["Idempotency-Key"]).toBe(key);
    expect(JSON.stringify(env.states.get("orders-local-intentions")?.value)).not.toContain("SYNTHETIC-PIN");
  });

});

it("PATCH perdido recupera o recibo sem executar outra edição", async () => {
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
  const client = useOrderIntention();
  expect(await client.executePath("catalog:A:detail", "/api/v1/backstage/catalog/product/A/", { ...action, method: "PATCH" }, { patch: { name: "Meu nome" } })).toEqual({ outcome: "applied" });
  expect(env.fetchMock.mock.calls[0]![1].method).toBe("PATCH");
  expect(env.fetchMock.mock.calls[1]![1].method).toBeUndefined();
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
});

it("verificação explícita usa somente GET com a intenção pendente", async () => {
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
  const client = useOrderIntention();
  await expect(client.executePath("curation", "/catalog/reorder/", action, { ref: "manual" })).rejects.toThrow();
  const key = env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"];
  env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
  expect(await client.checkPath("curation", "/catalog/reorder/")).toEqual({ outcome: "applied" });
  expect(env.fetchMock.mock.calls[2]![1]).toEqual({ query: { idempotency_key: key, ref: "manual" } });
  await expect(client.checkPath("curation", "/catalog/reorder/")).rejects.toThrow("Não há gravação pendente");
  expect(env.fetchMock).toHaveBeenCalledTimes(3);
});

it.each(["check", "changed", "automatic"])("recibo not_applied libera nova intenção após %s, sem reenviar automaticamente", async (mode) => {
  const client = useOrderIntention();
  const refusal = { status: 409, data: { outcome: "not_applied", detail: "A nota mudou; confira o texto atual." } };
  if (mode === "automatic") {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockRejectedValueOnce(refusal);
    await expect(client.execute("ORDER", "notes", action, { notes: "Primeiro" })).rejects.toEqual(refusal);
  } else {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
    await expect(client.execute("ORDER", "notes", action, { notes: "Primeiro" })).rejects.toThrow();
    env.fetchMock.mockRejectedValueOnce(refusal);
    await expect(mode === "check" ? client.checkPath("ORDER:notes", "/api/v1/backstage/orders/ORDER/notes/") : client.execute("ORDER", "notes", action, { notes: "Segundo" })).rejects.toEqual(refusal);
  }
  const previous = env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"];
  const calls = env.fetchMock.mock.calls.length;
  expect(env.states.get("orders-local-intentions")?.value["ORDER:notes"]).toBeUndefined();
  env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
  await client.execute("ORDER", "notes", action, { notes: "Segundo" });
  expect(env.fetchMock.mock.calls[calls]![1].headers["Idempotency-Key"]).not.toBe(previous);
  expect(env.fetchMock.mock.calls[calls]![1].body.notes).toBe("Segundo");
});

it.each([401, 403, 404, 409, 502])("erro GET %s sem prova not_applied conserva intenção", async (status) => {
  const client = useOrderIntention();
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
  await expect(client.execute("ORDER", "notes", action, { notes: "Meu texto" })).rejects.toThrow();
  const previous = env.states.get("orders-local-intentions")?.value["ORDER:notes"];
  env.fetchMock.mockRejectedValueOnce({ status, data: { detail: "Indisponível" } });
  await expect(client.checkPath("ORDER:notes", "/api/v1/backstage/orders/ORDER/notes/")).rejects.toBeDefined();
  expect(env.states.get("orders-local-intentions")?.value["ORDER:notes"]).toEqual(previous);
});
