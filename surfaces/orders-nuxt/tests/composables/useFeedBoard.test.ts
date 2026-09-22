import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useFeedBoard } from "../../app/composables/useFeedBoard";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

describe("useFeedBoard", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = { board: { catalog_channels: [], feeds: ["menu-1", "m"].map((ref) => ({ ref,
      switch: { enabled: true, disabled_reason: "", base_revision: "switch-base", expected_actor_id: 1 },
      actions: ["collections", "rotation"].map((ref) => ({ ref, enabled: true, reason: "", payload_schema: { base_revision: "fixture-base", expected_actor_id: 1 } })) })) } };
    env.fetchMock.mockResolvedValue({ outcome: "applied" });
  });

  it("deriva board da projection", () => {
    env.fetchData.value = { board: { feeds: [{ ref: "menu" }] } };
    expect(useFeedBoard().board.value).toEqual({ feeds: [{ ref: "menu" }] });
  });

  it("switchChannel/setCollections postam url + body corretos", async () => {
    const s = useFeedBoard();
    expect(await s.switchChannel("menu-1", { is_active: false, period: "1h", reason: "Loja cheia" })).toEqual({ ok: true, code: "", message: "" });
    let [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/feeds/switch/");
    expect(opts.body).toMatchObject({ ref: "menu-1", is_active: false, period: "1h", reason: "Loja cheia", base_revision: "switch-base" });

    await s.setCollections("menu-1", ["c1", "c2"]);
    [url, opts] = env.fetchMock.mock.calls[1]!;
    expect(String(url)).toBe("/api/v1/backstage/feeds/collections/");
    expect(opts.body).toMatchObject({ ref: "menu-1", collections: ["c1", "c2"] });

    await s.setRotation("menu-1", 15, 12);
    [url, opts] = env.fetchMock.mock.calls[2]!;
    expect(String(url)).toBe("/api/v1/backstage/feeds/rotation/");
    expect(opts.body).toMatchObject({ ref: "menu-1", rotate_seconds: 15, items_per_page: 12 });
  });

  it("guarda de reentrância por-ref", async () => {
    let release!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise<unknown>((r) => { release = r; }));
    const s = useFeedBoard();
    const first = s.switchChannel("m", { is_active: false, period: "1h", reason: "x" });
    expect(s.isBusy("m")).toBe(true);
    expect((await s.switchChannel("m", { is_active: false, period: "1h", reason: "x" })).ok).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release({ outcome: "applied" });
    await first;
    expect(s.isBusy("m")).toBe(false);
  });

  it("falha de coleções acende errorMsg + toast e devolve false", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Feed bloqueado" } });
    const s = useFeedBoard();
    expect(await s.setCollections("m", [], "fixture-base")).toBe(false);
    expect(s.errorMsg.value).toBe("Feed bloqueado");
    expect(env.sonner.error).toHaveBeenCalledWith("Feed bloqueado");
  });
  it("falta de gerente no toggle não vira toast: é o próximo passo do modal", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 422, data: { detail: "Ligar ou desligar um canal pede um gerente.", error: { code: "manager_approval_required" } } });
    const s = useFeedBoard();
    const outcome = await s.switchChannel("m", { is_active: false, period: "1h", reason: "x" });
    expect(outcome).toMatchObject({ ok: false, code: "manager_approval_required" });
    expect(env.sonner.error).not.toHaveBeenCalled();
  });
  it("resposta perdida consulta a mesma intenção no feed certo sem segundo POST", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
    const s = useFeedBoard();
    expect((await s.switchChannel("menu-1", { is_active: false, period: "open", reason: "Férias" })).ok).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
    const post = env.fetchMock.mock.calls[0]![1];
    const read = env.fetchMock.mock.calls[1]![1];
    expect(read.query).toEqual({ ref: "menu-1", idempotency_key: post.headers["Idempotency-Key"] });
    expect(read.method).toBeUndefined();
  });

});

it("keeps the last confirmed feed board when a later GET fails", async () => {
  const { ref, nextTick } = await import("vue");
  const data = ref<any>({ board: { feeds: [{ ref: "tv" }], all_collections: [] } });
  const error = ref<any>(null);
  const prior = globalThis.useFetch;
  vi.stubGlobal("useFetch", () => ({ data, error, pending: ref(false), refresh: env.refresh }));
  try {
    const feed = useFeedBoard();
    expect(feed.board.value?.feeds[0]?.ref).toBe("tv");
    error.value = { statusCode: 503 };
    data.value = null;
    await nextTick();
    expect(feed.board.value?.feeds[0]?.ref).toBe("tv");
    expect(feed.error.value).toBeTruthy();
  } finally {
    vi.stubGlobal("useFetch", prior);
  }
});
