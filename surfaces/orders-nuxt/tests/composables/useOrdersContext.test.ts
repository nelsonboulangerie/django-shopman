import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrdersContext } from "../../app/composables/useOrdersContext";

const env = installNuxtGlobals();
const session = ref<{ operator?: { id: number } }>({ operator: { id: 1 } });
vi.stubGlobal("useNuxtData", () => ({ data: session }));
beforeEach(() => { env.reset(); session.value = { operator: { id: 1 } }; });

describe("contexto da fila por pessoa e sessão", () => {
  it("retoma recorte, seleção, posição e foco ao voltar do detalhe", () => {
    const board = useOrdersContext();
    board.readLocation({ person: "1", q: "PED-42", channel: "web", fulfillment: "pickup", sort: "recent", view: "table" });
    board.selected.value = new Set(["PED-42"]);
    board.state.value.scrollTop = 712;
    board.state.value.focusLabel = "Abrir pedido PED-42";
    const detail = useOrdersContext();
    expect(detail.location.value.query).toEqual({ person: "1", q: "PED-42", channel: "web", fulfillment: "pickup", sort: "recent", view: "table" });
    const resumed = useOrdersContext();
    resumed.readLocation(detail.location.value.query);
    expect(resumed.selected.value.has("PED-42")).toBe(true);
    expect(resumed.state.value.scrollTop).toBe(712);
    expect(resumed.state.value.focusLabel).toBe("Abrir pedido PED-42");
  });

  it("expiração não apaga contexto; pessoa diferente não herda seleção nem URL antiga", () => {
    const board = useOrdersContext();
    board.query.value = "Busca da pessoa A";
    board.selected.value = new Set(["A"]);
    const previous = board.location.value.query;
    session.value = {};
    expect(board.query.value).toBe("Busca da pessoa A");
    session.value = { operator: { id: 1 } };
    expect(board.selected.value.has("A")).toBe(true);
    session.value = { operator: { id: 2 } };
    expect(board.query.value).toBe("");
    expect(board.selected.value.size).toBe(0);
    board.readLocation(previous);
    expect(board.location.value.query).toEqual({ person: "2" });
    session.value = { operator: { id: 1 } };
    expect(board.selected.value.size).toBe(0);
  });

  it("URL inválida não fabrica modo, ordenação ou array de busca", () => {
    const board = useOrdersContext();
    board.readLocation({ q: ["A", "B"], view: "unknown", sort: "other", fulfillment: "express" });
    expect(board.query.value).toBe("");
    expect(board.viewMode.value).toBe("board");
    expect(board.sort.value).toBe("arrival");
    expect(board.fulfillment.value).toBe("all");
  });
});
