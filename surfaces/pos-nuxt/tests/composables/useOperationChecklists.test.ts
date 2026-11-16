// Rotinas no PDV (dono, 13/11/2026). A leitura e as transições da rotina, no runtime
// Nuxt do PDV: `useFetch` e `useNuxtData` simulados, as rotas do servidor registradas.
import { readBody, setResponseStatus } from "h3";
import { mockNuxtImport, registerEndpoint } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { useOperationChecklists } from "~/composables/useOperationChecklists";

const BASE = "/api/v1/backstage/operation-checklists";
const initial = {
  checklists: { business_date: "2026-10-17", can_supervise: true, templates: [] },
};

const { useFetchMock, calls, failNext } = vi.hoisted(() => ({
  useFetchMock: vi.fn(),
  calls: [] as Array<{ url: string; body: unknown }>,
  failNext: { value: null as null | Record<string, unknown> },
}));

mockNuxtImport("useNuxtData", () => () => ({ data: ref({ operator: { id: 7 } }) }));
mockNuxtImport("useFetch", () => (url: string, options: unknown) => {
  useFetchMock(url, options);
  return { data: ref(initial), pending: ref(false), error: ref(null), refresh: vi.fn() };
});

for (const path of [
  "/start/",
  "/3/tasks/9/complete/",
  "/3/tasks/10/supervise/",
  "/3/complete/",
  "/2/tasks/5/complete/",
]) {
  registerEndpoint(`${BASE}${path}`, {
    method: "POST",
    handler: async (event) => {
      calls.push({ url: `${BASE}${path}`, body: await readBody(event) });
      if (failNext.value) {
        const detail = failNext.value;
        failNext.value = null;
        setResponseStatus(event, 400);
        return detail;
      }
      return initial;
    },
  });
}

describe("useOperationChecklists", () => {
  beforeEach(() => {
    calls.length = 0;
    failNext.value = null;
    useFetchMock.mockReset();
  });

  it("lê a projeção com cache por operador", () => {
    const state = useOperationChecklists();
    expect(state.board.value).toEqual(initial.checklists);
    expect(useFetchMock).toHaveBeenCalledWith(
      `${BASE}/`,
      expect.objectContaining({ key: "pos:7:operation-checklists" }),
    );
  });

  it("inicia uma rotina com data e turno da projeção", async () => {
    const state = useOperationChecklists();
    expect(await state.start("nelson-opening", " manhã ")).toBe(true);
    expect(calls).toEqual([
      {
        url: `${BASE}/start/`,
        body: { template_ref: "nelson-opening", shift_ref: "manhã", business_date: "2026-10-17" },
      },
    ]);
  });

  it("envia evidência e usa rotas distintas para executar, conferir e fechar", async () => {
    const state = useOperationChecklists();
    await state.completeTask(3, 9, { evidence_text: "Tudo limpo", evidence_number: null });
    await state.superviseTask(3, 10);
    await state.completeRun(3);
    expect(calls.map((c) => c.url)).toEqual([
      `${BASE}/3/tasks/9/complete/`,
      `${BASE}/3/tasks/10/supervise/`,
      `${BASE}/3/complete/`,
    ]);
    expect(calls[0]!.body).toEqual({ evidence_text: "Tudo limpo", evidence_number: null });
  });

  it("expõe a mensagem do domínio quando uma transição falha", async () => {
    failNext.value = { detail: "Tarefas obrigatórias pendentes: Caixa." };
    const state = useOperationChecklists();
    expect(await state.completeRun(3)).toBe(false);
    expect(state.message.value).toBe("Tarefas obrigatórias pendentes: Caixa.");
  });

  it("a evidência que faltou fica com a tarefa, não no topo da página (GES-23)", async () => {
    failNext.value = {
      detail: "Escreva a evidência para concluir esta tarefa.",
      field: "evidence_text",
      errors: { evidence_text: ["Escreva a evidência para concluir esta tarefa."] },
    };
    const state = useOperationChecklists();
    expect(await state.completeTask(2, 5, { evidence_text: "" })).toBe(false);
    expect(state.message.value).toBe("");
    expect(state.taskErrors.value[5]).toEqual({
      field: "evidence_text",
      message: "Escreva a evidência para concluir esta tarefa.",
    });
    // A nova tentativa limpa a recusa daquela tarefa.
    await state.completeTask(2, 5, { evidence_text: "Feito" });
    expect(state.taskErrors.value[5]).toBeUndefined();
  });
});
