import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useFeedBoard } from "../../app/composables/useFeedBoard";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

describe("useFeedBoard", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = { board: { feeds: ["menu-1", "m"].map((ref) => ({ ref, actions: ["active", "collections", "rotation"].map((ref) => ({ ref, enabled: true, reason: "", payload_schema: { base_revision: "fixture-base", expected_actor_id: 1 } })) })) } };
    env.fetchMock.mockResolvedValue({ outcome: "applied" });
  });

  it("deriva board da projection", () => {
    env.fetchData.value = { board: { feeds: [{ ref: "menu" }] } };
    expect(useFeedBoard().board.value).toEqual({ feeds: [{ ref: "menu" }] });
  });

  it("setActive/setCollections postam url + body corretos", async () => {
    const s = useFeedBoard();
    await s.setActive("menu-1", true);
    let [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/feeds/active/");
    expect(opts.body).toMatchObject({ ref: "menu-1", is_active: true });

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
    const first = s.setActive("m", true);
    expect(s.isBusy("m")).toBe(true);
    expect(await s.setActive("m", false)).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release({ outcome: "applied" });
    await first;
    expect(s.isBusy("m")).toBe(false);
  });

  it("falha acende errorMsg + toast e devolve false", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Feed bloqueado" } });
    const s = useFeedBoard();
    expect(await s.setActive("m", true)).toBe(false);
    expect(s.errorMsg.value).toBe("Feed bloqueado");
    expect(env.sonner.error).toHaveBeenCalledWith("Feed bloqueado");
  });
  it("resposta perdida consulta a mesma intenção no feed certo sem segundo POST", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
    const s = useFeedBoard();
    expect(await s.setActive("menu-1", false)).toBe(true);
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
