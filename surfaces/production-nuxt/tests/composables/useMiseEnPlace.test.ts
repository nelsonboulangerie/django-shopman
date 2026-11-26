import { readFileSync } from "node:fs";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  PREP_MARKS_PATH,
  lineItemRef,
  markAuthorLine,
  markFor,
  prepIngredientItemRef,
  useMiseEnPlace,
  usePrepMarks,
} from "~/composables/useMiseEnPlace";

const env = installNuxtGlobals();

function marksResponse(marks: Array<{ item_ref: string; quantity: string }>) {
  return {
    date: "2026-07-06",
    marks: marks.map((mark) => ({ ...mark, marked_by: "Ana", marked_at: "2026-07-06T05:40:00-03:00" })),
  };
}

describe("useMiseEnPlace", () => {
  beforeEach(() => env.reset());

  it("deriva a projeção e as linhas do dia", () => {
    env.fetchData.value = { mise_en_place: { selected_date: "2026-07-06", lines: [{ sku: "FARINHA" }, { sku: "SAL" }] } };
    const { projection, lines } = useMiseEnPlace(ref("2026-07-06"));
    expect(projection.value?.selected_date).toBe("2026-07-06");
    expect(lines.value).toHaveLength(2);
  });

  it("degrada para vazio quando o payload é nulo", () => {
    env.fetchData.value = null;
    const { projection, lines } = useMiseEnPlace(ref("2026-07-06"));
    expect(projection.value).toBeNull();
    expect(lines.value).toEqual([]);
  });
});

describe("usePrepMarks: o Separado mora no servidor", () => {
  beforeEach(() => env.reset());

  it("lê as marcas do dia pelo servidor, pela data", () => {
    env.fetchData.value = marksResponse([{ item_ref: "FARINHA", quantity: "1000 g" }]);
    const marks = usePrepMarks(ref("2026-07-06"));

    const [path, options] = env.useFetchMock.mock.calls[0]!;
    expect(path).toBe(PREP_MARKS_PATH);
    expect(options.query.value).toEqual({ date: "2026-07-06" });
    expect(marks.isMarked("FARINHA", "1000 g")).toBe(true);
  });

  it("a marca vale só na quantidade que ela guarda", () => {
    env.fetchData.value = marksResponse([{ item_ref: "FARINHA", quantity: "1000 g" }]);
    const marks = usePrepMarks(ref("2026-07-06"));
    expect(marks.isMarked("FARINHA", "1200 g")).toBe(false);
    expect(marks.isMarked("SAL", "20 g")).toBe(false);
  });

  it("marcar grava no servidor e adota a lista que ele devolve", async () => {
    env.fetchData.value = marksResponse([]);
    env.fetchMock.mockResolvedValue({
      ...marksResponse([{ item_ref: "massa/FARINHA", quantity: "900 g" }]),
      mark: null,
    });
    const marks = usePrepMarks(ref("2026-07-06"));

    const pending = marks.toggle("massa/FARINHA", "900 g", "Farinha");
    // Otimista: a caixa marca antes da resposta.
    expect(marks.isMarked("massa/FARINHA", "900 g")).toBe(true);
    await expect(pending).resolves.toBe(true);

    expect(env.fetchMock).toHaveBeenCalledWith(PREP_MARKS_PATH, {
      method: "POST",
      body: { date: "2026-07-06", item_ref: "massa/FARINHA", quantity: "900 g", checked: true },
    });
    expect(marks.isMarked("massa/FARINHA", "900 g")).toBe(true);
    expect(marks.markOf("massa/FARINHA", "900 g")?.marked_by).toBe("Ana");
  });

  it("desmarcar manda checked=false", async () => {
    env.fetchData.value = marksResponse([{ item_ref: "FARINHA", quantity: "1000 g" }]);
    env.fetchMock.mockResolvedValue({ ...marksResponse([]), mark: null });
    const marks = usePrepMarks(ref("2026-07-06"));

    await marks.toggle("FARINHA", "1000 g", "Farinha");
    expect(env.fetchMock.mock.calls[0]![1].body.checked).toBe(false);
    expect(marks.isMarked("FARINHA", "1000 g")).toBe(false);
  });

  it("servidor recusa: a marca otimista se desfaz, com aviso, e a tela relê", async () => {
    env.fetchData.value = marksResponse([]);
    env.fetchMock.mockRejectedValue({ statusCode: 409, data: { detail: "A quantidade mudou: agora são 1200 g." } });
    const onQuantityChanged = vi.fn();
    const marks = usePrepMarks(ref("2026-07-06"), onQuantityChanged);

    await expect(marks.toggle("FARINHA", "1000 g", "Farinha")).resolves.toBe(false);

    expect(marks.isMarked("FARINHA", "1000 g")).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledTimes(1);
    expect(env.sonner.error.mock.calls[0]![0]).toContain("A quantidade mudou");
    expect(onQuantityChanged).toHaveBeenCalledTimes(1);
    expect(env.refresh).toHaveBeenCalled();
  });

  it("falha sem resposta também desfaz e avisa, dizendo o item", async () => {
    env.fetchData.value = marksResponse([]);
    env.fetchMock.mockRejectedValue(new Error("network"));
    const marks = usePrepMarks(ref("2026-07-06"));

    await marks.toggle("SAL", "20 g", "Sal");
    expect(marks.isMarked("SAL", "20 g")).toBe(false);
    expect(env.sonner.error.mock.calls[0]![0]).toContain("Sal");
  });

  it("um toque por item por vez: o segundo toque em voo é ignorado", async () => {
    env.fetchData.value = marksResponse([]);
    let resolve: (value: unknown) => void = () => {};
    env.fetchMock.mockImplementation(() => new Promise((r) => (resolve = r)));
    const marks = usePrepMarks(ref("2026-07-06"));

    const first = marks.toggle("SAL", "20 g", "Sal");
    await expect(marks.toggle("SAL", "20 g", "Sal")).resolves.toBe(false);
    resolve({ ...marksResponse([{ item_ref: "SAL", quantity: "20 g" }]), mark: null });
    await first;
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
  });

  it("nenhuma marca no dispositivo: o composable não toca o localStorage", () => {
    const source = readFileSync(new URL("../../app/composables/useMiseEnPlace.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/localStorage|sessionStorage/);
    expect(source).not.toContain("preparacao:v2");
  });
});

describe("chave e autoria da marca", () => {
  it("a chave do insumo é o SKU; a do ingrediente de um preparo leva a receita", () => {
    expect(lineItemRef("FARINHA")).toBe("FARINHA");
    expect(prepIngredientItemRef("massa-brioche", "FARINHA")).toBe("massa-brioche/FARINHA");
  });

  it("markFor exige item e quantidade", () => {
    const marks = marksResponse([{ item_ref: "FARINHA", quantity: "1000 g" }]).marks;
    expect(markFor(marks, "FARINHA", "1000 g")?.item_ref).toBe("FARINHA");
    expect(markFor(marks, "FARINHA", "900 g")).toBeNull();
  });

  it("diz quem separou e quando", () => {
    const at = new Date(2026, 6, 6, 5, 40).toISOString();
    expect(markAuthorLine({ item_ref: "X", quantity: "1 g", marked_by: "Ana", marked_at: at })).toBe(
      "Separado por Ana às 5h40",
    );
    expect(markAuthorLine({ item_ref: "X", quantity: "1 g", marked_by: "", marked_at: at })).toBe(
      "Separado às 5h40",
    );
    expect(markAuthorLine(null)).toBe("");
  });
});
