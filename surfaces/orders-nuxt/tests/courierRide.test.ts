import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../operator-kit/tests/support/composableEnv";
import { useOrderIntention } from "../app/composables/useOrderIntention";
import {
  COURIER_RIDE_PATH,
  courierRideAction,
  courierRideInputs,
  courierRideResource,
} from "../app/presentation/courierRide";

// A ação `courier-ride` como a projeção a entrega: quem a tela leu e a revisão de
// cada pedido que pode entrar numa corrida.
const action = {
  enabled: true,
  reason: "",
  method: "POST",
  payload_schema: {
    expected_actor_id: 1,
    base_revisions: { "NB-A01": "rev-a", "NB-A02": "rev-b", "NB-A03": "rev-c" },
  },
};
const call = {
  refs: ["NB-A02", "NB-A01"],
  change_out: { "NB-A01": "20,00" },
  machine: "machine:1",
  ride_number: 2,
};

const env = installNuxtGlobals();
const session = ref<{ operator?: { id: number } }>({ operator: { id: 1 } });
vi.stubGlobal("useNuxtData", () => ({ data: session }));

beforeEach(() => {
  env.reset();
  session.value = { operator: { id: 1 } };
});

describe("a intenção da corrida de vários pedidos", () => {
  it("leva só as revisões dos pedidos da corrida, e quem a tela leu", () => {
    expect(courierRideAction(action, call.refs)).toEqual({
      enabled: true,
      reason: "",
      method: "POST",
      payload_schema: {
        expected_actor_id: 1,
        base_revisions: { "NB-A02": "rev-b", "NB-A01": "rev-a" },
      },
    });
  });

  it("faltou a revisão de um pedido: a ação sai desabilitada com o motivo", () => {
    const stale = courierRideAction(action, ["NB-A01", "NB-Z99"]);
    expect(stale?.enabled).toBe(false);
    expect(stale?.reason).toBe("A fila mudou. Atualize antes de chamar a corrida.");
    expect(courierRideAction(null, call.refs)).toBeUndefined();
  });

  it("os mesmos pedidos em qualquer ordem são a mesma corrida", () => {
    expect(courierRideResource(["NB-A02", "NB-A01"])).toBe(
      courierRideResource(["NB-A01", "NB-A02"]),
    );
    expect(courierRideResource(["NB-A01", "NB-A02"])).not.toBe(
      courierRideResource(["NB-A01", "NB-A03"]),
    );
  });

  it("o número que a tela mostrava vai junto, e some quando não há", () => {
    expect(courierRideInputs(call)).toEqual({
      refs: ["NB-A02", "NB-A01"],
      change_out: { "NB-A01": "20,00" },
      machine: "machine:1",
      ride_number: 2,
    });
    expect(
      courierRideInputs({ refs: ["A", "B"], change_out: {}, machine: "" }),
    ).not.toHaveProperty("ride_number");
  });
});

describe("chamar a corrida: uma intenção, uma corrida", () => {
  it("manda quem a tela leu, a revisão de cada pedido e uma chave", async () => {
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied", ride_number: 2, ride_letter: "B" });
    const result = await useOrderIntention().executeRide(action, call);
    expect(result.ride_letter).toBe("B");
    const [path, request] = env.fetchMock.mock.calls[0]!;
    expect(path).toBe(COURIER_RIDE_PATH);
    expect(request.method).toBe("POST");
    expect(request.headers["Idempotency-Key"]).toBeTruthy();
    expect(request.body).toEqual({
      expected_actor_id: 1,
      base_revisions: { "NB-A02": "rev-b", "NB-A01": "rev-a" },
      refs: ["NB-A02", "NB-A01"],
      change_out: { "NB-A01": "20,00" },
      machine: "machine:1",
      ride_number: 2,
    });
  });

  it("rede caída: o toque repetido reenvia a MESMA chave e o mesmo corpo", async () => {
    const client = useOrderIntention();
    // O POST se perde e o recibo ainda não sabe: a intenção fica guardada.
    env.fetchMock
      .mockRejectedValueOnce({ status: 502 })
      .mockResolvedValueOnce({ outcome: "unknown" });
    await expect(client.executeRide(action, call)).rejects.toThrow(
      "Não deu para confirmar se a corrida foi chamada",
    );
    const first = env.fetchMock.mock.calls[0]![1];
    expect(env.fetchMock.mock.calls[1]![0]).toBe(COURIER_RIDE_PATH);
    expect(env.fetchMock.mock.calls[1]![1].query.idempotency_key).toBe(
      first.headers["Idempotency-Key"],
    );

    // A fila releu e as revisões mudaram: mesmo assim é a mesma intenção.
    const fresher = {
      ...action,
      payload_schema: {
        expected_actor_id: 1,
        base_revisions: { "NB-A01": "x", "NB-A02": "y" },
      },
    };
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied", replayed: true, ride_letter: "B" });
    await client.executeRide(fresher, call);
    const retry = env.fetchMock.mock.calls[2]![1];
    expect(retry.headers).toEqual(first.headers);
    expect(retry.body).toEqual(first.body);
  });

  it("o pedido que mudou (409 revision_changed) libera a intenção: a próxima chamada é nova", async () => {
    const client = useOrderIntention();
    const refused = {
      status: 409,
      data: {
        code: "revision_changed",
        error: { code: "revision_changed" },
        outcome: "not_applied",
        detail: "O pedido A02 mudou depois que você abriu esta tela. Confira e chame de novo.",
      },
    };
    env.fetchMock.mockRejectedValueOnce(refused);
    await expect(client.executeRide(action, call)).rejects.toBe(refused);
    env.fetchMock.mockResolvedValueOnce({ outcome: "applied" });
    await client.executeRide(action, call);
    expect(env.fetchMock.mock.calls[1]![1].headers).not.toEqual(
      env.fetchMock.mock.calls[0]![1].headers,
    );
  });

  it("a corrida que já existia volta como feita, com a frase do servidor", async () => {
    env.fetchMock.mockResolvedValueOnce({
      outcome: "applied",
      already_called: true,
      detail: "A corrida B já tinha sido chamada.",
      ride_letter: "B",
    });
    const result = await useOrderIntention().executeRide(action, call);
    expect(result.already_called).toBe(true);
    expect(result.detail).toBe("A corrida B já tinha sido chamada.");
  });

  it("sem a ação da projeção nada é enviado", async () => {
    await expect(useOrderIntention().executeRide(undefined, call)).rejects.toThrow(
      "Atualize os dados antes de continuar.",
    );
    expect(env.fetchMock).not.toHaveBeenCalled();
  });
});
