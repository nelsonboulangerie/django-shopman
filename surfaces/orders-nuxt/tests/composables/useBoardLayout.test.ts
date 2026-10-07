// A arrumação das colunas do Gestor fica lembrada por POSTO, no servidor (SUITE-UX
// §16, L7). Sem posto ou sem servidor, a tela abre com as três colunas e o que o
// operador mudar vale até recarregar.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  BOARD_LAYOUT_PATH,
  BOARD_LAYOUT_SAVE_DELAY_MS,
  useBoardLayout,
} from "../../app/composables/useBoardLayout";

const env = installNuxtGlobals();
const TITLES = { intake: "Entrada", prep: "Preparo", expedition: "Saída" };

const SAIDA = {
  intake: { open: false, weight: 1 },
  prep: { open: false, weight: 1 },
  expedition: { open: true, weight: 1 },
};

function puts() {
  return env.fetchMock.mock.calls.filter(([, options]) => options?.method === "PUT");
}

beforeEach(() => {
  env.reset();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useBoardLayout", () => {
  it("sem leitura, abre com as três colunas", async () => {
    env.fetchMock.mockRejectedValueOnce(new Error("offline"));
    const board = useBoardLayout(() => TITLES);
    await board.load();
    expect(board.allOpen.value).toBe(true);
    expect(board.gridTemplate.value).toBe("minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr)");
    expect(board.viewLabel.value).toBe("");
  });

  it("o posto Saída abre como o posto deixou", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: SAIDA });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    expect(env.fetchMock).toHaveBeenCalledWith(BOARD_LAYOUT_PATH);
    expect(board.isOpen("intake")).toBe(false);
    expect(board.viewLabel.value).toBe("Visão: Saída");
    expect(board.memoryText.value).toBe("Arrumação lembrada neste posto, no servidor.");
    expect(board.canCollapse("expedition")).toBe(false);
  });

  it("recolher grava no posto, uma vez, depois da última tecla", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: null });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    env.fetchMock.mockResolvedValue({});
    board.toggle("intake");
    board.toggle("prep");
    expect(puts()).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(puts()).toHaveLength(1);
    expect(puts()[0]![1].body).toEqual({ columns: SAIDA });
  });

  it("Mostrar as 3 colunas volta ao padrão e grava", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: SAIDA });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    env.fetchMock.mockResolvedValue({});
    board.showAll();
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(board.allOpen.value).toBe(true);
    expect(puts()).toHaveLength(1);
  });

  it("dispositivo que não é posto: muda na tela, não grava, e diz por quê", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "", columns: null });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    board.toggle("prep");
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS * 2);
    expect(board.isOpen("prep")).toBe(false);
    expect(puts()).toHaveLength(0);
    expect(board.memoryText.value).toContain("não é um posto");
  });

  it("falha ao gravar não desfaz a arrumação; avisa que vale até recarregar", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: null });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    env.fetchMock.mockRejectedValue(new Error("500"));
    board.toggle("intake");
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(board.isOpen("intake")).toBe(false);
    expect(board.saveFailed.value).toBe(true);
    expect(board.memoryText.value).toContain("Não deu para guardar");
  });

  it("gesto antes da leitura chegar vence a leitura, e vai para o posto", async () => {
    let resolve: (value: unknown) => void = () => {};
    env.fetchMock.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const board = useBoardLayout(() => TITLES);
    const loading = board.load();
    board.toggle("intake");
    env.fetchMock.mockResolvedValue({});
    resolve({ station: "passe", columns: null });
    await loading;
    expect(board.isOpen("intake")).toBe(false);
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(puts()).toHaveLength(1);
  });

  it("arrastar mostra a prévia sem gravar; soltar grava; soltar no fim recolhe", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: null });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    env.fetchMock.mockResolvedValue({});

    board.startResize("intake", 400, 400);
    board.dragResize(100);
    expect(board.layout.value.intake!.weight).toBe(1.25);
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(puts()).toHaveLength(0);
    board.endResize(100);
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(puts()).toHaveLength(1);

    board.startResize("intake", 500, 300);
    board.endResize(-450);
    expect(board.isOpen("intake")).toBe(false);
    expect(board.isOpen("prep")).toBe(true);
  });

  it("a última coluna aberta não tem alça nem recolhe", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: SAIDA });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    expect(board.nextOpen("expedition")).toBeNull();
    board.toggle("expedition");
    expect(board.isOpen("expedition")).toBe(true);
  });

  it("persiste um resize do Splitter oficial, mas ignora layouts idênticos", async () => {
    env.fetchMock.mockResolvedValueOnce({ station: "passe", columns: null });
    const board = useBoardLayout(() => TITLES);
    await board.load();
    env.fetchMock.mockResolvedValue({});

    board.applySizes([50, 25, 25]);
    expect(board.layout.value.intake!.weight).toBe(1.5);
    expect(board.layout.value.prep!.weight).toBe(0.75);
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(puts()).toHaveLength(1);

    board.applySizes([50, 25, 25]);
    await vi.advanceTimersByTimeAsync(BOARD_LAYOUT_SAVE_DELAY_MS);
    expect(puts()).toHaveLength(1);
  });
});
