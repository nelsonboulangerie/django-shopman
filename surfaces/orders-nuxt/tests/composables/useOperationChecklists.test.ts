import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOperationChecklists } from "../../app/composables/useOperationChecklists";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 7 } }) }));

const initial = {
  checklists: {
    business_date: "2026-10-17",
    can_supervise: true,
    templates: [],
  },
};

describe("useOperationChecklists", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = initial;
    env.fetchMock.mockResolvedValue(initial);
  });

  it("lê a projeção com cache por operador", () => {
    const state = useOperationChecklists();
    expect(state.board.value).toEqual(initial.checklists);
    expect(env.useFetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operation-checklists/",
      expect.objectContaining({ key: "orders:7:operation-checklists" }),
    );
  });

  it("inicia uma rotina com data e turno da projeção", async () => {
    const state = useOperationChecklists();
    expect(await state.start("nelson-opening", " manhã ")).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operation-checklists/start/",
      expect.objectContaining({
        method: "POST",
        body: {
          template_ref: "nelson-opening",
          shift_ref: "manhã",
          business_date: "2026-10-17",
        },
      }),
    );
  });

  it("envia evidência e usa rotas distintas para executar, conferir e fechar", async () => {
    const state = useOperationChecklists();
    await state.completeTask(3, 9, {
      evidence_text: "Tudo limpo",
      evidence_number: null,
    });
    await state.superviseTask(3, 10);
    await state.completeRun(3);

    expect(env.fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/backstage/operation-checklists/3/tasks/9/complete/",
      "/api/v1/backstage/operation-checklists/3/tasks/10/supervise/",
      "/api/v1/backstage/operation-checklists/3/complete/",
    ]);
    expect(env.fetchMock.mock.calls[0]![1]).toMatchObject({
      method: "POST",
      body: { evidence_text: "Tudo limpo", evidence_number: null },
    });
  });

  it("expõe a mensagem do domínio quando uma transição falha", async () => {
    env.fetchMock.mockRejectedValueOnce({
      status: 400,
      data: { detail: "Tarefas obrigatórias pendentes: Caixa." },
    });
    const state = useOperationChecklists();
    expect(await state.completeRun(3)).toBe(false);
    expect(state.message.value).toBe("Tarefas obrigatórias pendentes: Caixa.");
  });
});
