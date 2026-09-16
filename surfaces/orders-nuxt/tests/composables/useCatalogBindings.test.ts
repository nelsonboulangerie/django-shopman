import { beforeEach, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useCatalogBindings } from "../../app/composables/useCatalogBindings";
const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));
const action = { enabled: true, reason: "", payload_schema: { base_revision: "v1", expected_actor_id: 1 } };
const item = { item_id: "remote", binding_action: action, base_revision: "v1" } as any;
beforeEach(() => {
  env.reset();
  env.fetchData.value = { board: { import_action: action, selected_snapshot: { id: 7 }, items: [item] } };
  env.fetchMock.mockResolvedValue({ outcome: "applied" });
});

it("envia apenas intenção de vínculo local com revisão e identidade", async () => {
  expect(await useCatalogBindings("ifood").bind(item, "SKU", "v1")).toBe(true);
  expect(env.fetchMock.mock.calls[0]).toEqual(["/api/v1/backstage/catalog/channels/ifood/bindings/", expect.objectContaining({ body: { expected_actor_id: 1, base_revision: "v1", snapshot_id: 7, item_id: "remote", sku: "SKU" } })]);
});

it("resposta perdida busca recibo da mesma intenção sem segundo POST", async () => {
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
  expect(await useCatalogBindings("ifood").bind(item, "SKU", "v1")).toBe(true);
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
  const post = env.fetchMock.mock.calls[0]![1];
  const lookup = env.fetchMock.mock.calls[1]![1];
  expect(lookup.query.idempotency_key).toBe(post.headers["Idempotency-Key"]);
  expect(lookup.method).toBeUndefined();
});

it("resultado desconhecido preserva payload para a próxima tentativa", async () => {
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
  const api = useCatalogBindings("ifood");
  expect(await api.bind(item, "SKU", "v1")).toBe(false);
  const first = env.fetchMock.mock.calls[0]![1];
  env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
  expect(await api.bind(item, "SKU", "v1")).toBe(true);
  expect(env.fetchMock.mock.calls[2]![1].headers).toEqual(first.headers);
  expect(env.fetchMock.mock.calls[2]![1].body).toEqual(first.body);
});


it("primeira leitura omite snapshot_id vazio", () => {
  const original = globalThis.useFetch;
  const spy = vi.fn(original);
  vi.stubGlobal("useFetch", spy);
  try {
    env.fetchData.value = { board: { import_action: action, selected_snapshot: null, items: [] } };
    useCatalogBindings("ifood");
    expect((spy.mock.calls.at(-1)![1] as any).query.value).toEqual({});
  } finally { vi.stubGlobal("useFetch", original); }
});


it("atualização de outra captura preserva a evidência selecionada", () => {
  const api = useCatalogBindings("ifood");
  const displayed = api.board.value;
  env.useFetchMock.mock.results.at(-1)!.value.data.value = { board: { import_action: action, selected_snapshot: { id: 8 }, items: [] } };
  expect(api.selected.value).toBe("7");
  expect(api.board.value).toBe(displayed);
});

it("troca explícita bloqueia gravação até chegar a captura correspondente", async () => {
  const api = useCatalogBindings("ifood");
  api.selected.value = "8";
  expect(api.stale.value).toBe(true);
  expect(await api.bind(item, "SKU", "v1")).toBe(false);
  expect(env.fetchMock).not.toHaveBeenCalled();
  env.useFetchMock.mock.results.at(-1)!.value.data.value = { board: { import_action: action, selected_snapshot: { id: 8 }, items: [item] } };
  expect(api.stale.value).toBe(false);
});
