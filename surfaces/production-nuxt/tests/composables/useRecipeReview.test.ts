import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeReview } from "~/composables/useRecipeReview";
import { needsReview, provenanceIcon, reviewSignature } from "~/presentation/recipeBook";

const env = installNuxtGlobals();

function queue() {
  return {
    queue: {
      items: [
        { ref: "massa-brioche", name: "Massa Brioche", version_number: 2 },
        { ref: "pain-raisins", name: "Pain aux Raisins", version_number: 1 },
      ],
      total: 2,
      confirmed_total: 5,
      recipe_total: 7,
    },
    access: { can_view: true, can_edit: true, capture_available: false },
  };
}

describe("useRecipeReview", () => {
  beforeEach(() => env.reset());

  it("lê a fila na ordem do servidor e o acesso de escrita", () => {
    env.fetchData.value = queue();
    const { items, canEdit } = useRecipeReview();
    expect(items.value.map((item) => item.ref)).toEqual(["massa-brioche", "pain-raisins"]);
    expect(canEdit.value).toBe(true);
  });

  it("registrar a conferência assina a versão e tira a receita da fila no lugar", async () => {
    env.fetchData.value = queue();
    const { items, queue: projection, confirm } = useRecipeReview();
    env.fetchMock.mockResolvedValueOnce({ ok: true });

    expect(await confirm("massa-brioche", 2)).toBe(true);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/massa-brioche/versions/2/review/",
      expect.objectContaining({ method: "POST" }),
    );
    expect(items.value.map((item) => item.ref)).toEqual(["pain-raisins"]);
    expect(projection.value?.confirmed_total).toBe(6);
  });

  it("recusa do servidor mantém a receita na fila", async () => {
    env.fetchData.value = queue();
    const { items, confirm } = useRecipeReview();
    env.fetchMock.mockRejectedValueOnce(Object.assign(new Error("409"), { statusCode: 409 }));

    expect(await confirm("massa-brioche", 2)).toBe(false);
    expect(items.value).toHaveLength(2);
  });
});

describe("apresentação da conferência", () => {
  it("só pending e changed pedem conferência", () => {
    expect(needsReview("pending")).toBe(true);
    expect(needsReview("changed")).toBe(true);
    expect(needsReview("confirmed")).toBe(false);
    expect(needsReview("")).toBe(false);
  });

  it("cada procedência tem o seu ícone", () => {
    expect(provenanceIcon("house")).toBe("i-lucide-chef-hat");
    expect(provenanceIcon("notebook")).toBe("i-lucide-notebook-pen");
    expect(provenanceIcon("agent")).toBe("i-lucide-bot");
  });

  it("assinatura diz quem e quando", () => {
    expect(reviewSignature("Maysa", "19/10/2026 14:02")).toBe("Conferida por Maysa em 19/10/2026 14:02");
    expect(reviewSignature("Maysa", "")).toBe("Conferida por Maysa");
    expect(reviewSignature("", "19/10/2026")).toBe("");
  });
});
