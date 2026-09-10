import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrderAdvanceIntention } from "../../app/composables/useOrderAdvanceIntention";
import { fixtureActions } from "../support/orderActions";

const env = installNuxtGlobals();
const session = ref<{ operator?: { id: number } }>({ operator: { id: 1 } });
vi.stubGlobal("useNuxtData", () => ({ data: session }));
const action = fixtureActions({ can_advance: true })[0]!;

beforeEach(() => { env.reset(); session.value = { operator: { id: 1 } }; });

describe("avanço — uma intenção, um resultado", () => {
  it("resposta perdida consulta recibo sem executar um segundo POST", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
    expect(await useOrderAdvanceIntention().advance("ORDER", action, {})).toBe(true);
    const post = env.fetchMock.mock.calls[0]![1];
    const lookup = env.fetchMock.mock.calls[1]![1];
    expect(post.method).toBe("POST");
    expect(lookup.query.idempotency_key).toBe(post.headers["Idempotency-Key"]);
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
  });

  it("resultado desconhecido conserva chave e payload mesmo se a projeção avançar", async () => {
    const client = useOrderAdvanceIntention();
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "unknown" });
    await expect(client.advance("ORDER", action, { change_out: "20,00" })).rejects.toThrow();
    const first = env.fetchMock.mock.calls[0]![1];
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    expect(await client.advance("ORDER", undefined, { change_out: "30,00" })).toBe(true);
    const retry = env.fetchMock.mock.calls[2]![1];
    expect(retry.headers).toEqual(first.headers);
    expect(retry.body).toEqual(first.body);
  });

  it("troca de pessoa descarta a intenção e não aplica resposta da pessoa anterior", async () => {
    let resolve!: (value: unknown) => void;
    env.fetchMock.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const client = useOrderAdvanceIntention();
    const request = client.advance("ORDER", action, {});
    session.value = { operator: { id: 2 } };
    await nextTick();
    resolve({ outcome: "applied" });
    await expect(request).rejects.toThrow("identificação mudou");
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await client.advance("ORDER", action, {});
    expect(env.fetchMock.mock.calls[1]![1].headers["Idempotency-Key"]).not.toBe(env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"]);
  });
});
