import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useTimerTags } from "~/composables/useTimerTags";

const env = installNuxtGlobals();

describe("useTimerTags", () => {
  beforeEach(() => env.reset());

  it("lê a fileira de etiquetas do servidor", () => {
    env.fetchData.value = {
      tags: [{ ref: "estufa", label: "Estufa", minutes: 60, origin: "admin" }],
    };

    const { tags } = useTimerTags();

    expect(tags.value).toHaveLength(1);
    expect(tags.value[0]!.label).toBe("Estufa");
  });

  it("sem resposta, a fileira é vazia — e não explode", () => {
    env.fetchData.value = null;
    expect(useTimerTags().tags.value).toEqual([]);
  });

  it("createTag envia o POST, reconcilia e diz que nasceu", async () => {
    env.fetchData.value = { tags: [] };
    env.fetchMock.mockResolvedValueOnce({
      tag: { ref: "banho-maria", label: "Banho-maria", minutes: 25, origin: "operator" },
      created: true,
    });

    const result = await useTimerTags().createTag("Banho-maria", 25);

    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/timer-tags/",
      { method: "POST", body: { label: "Banho-maria", minutes: 25 } },
    );
    expect(env.refresh).toHaveBeenCalled();
    expect(result).toMatchObject({ ok: true, created: true });
    expect(result.tag?.ref).toBe("banho-maria");
  });

  it("etiqueta que já existia volta como sucesso, com created=false", async () => {
    env.fetchData.value = { tags: [] };
    env.fetchMock.mockResolvedValueOnce({
      tag: { ref: "estufa", label: "Estufa", minutes: 60, origin: "admin" },
      created: false,
    });

    const result = await useTimerTags().createTag("estufa", 5);

    expect(result).toMatchObject({ ok: true, created: false });
    // O tempo do turno não reescreve o padrão da casa: quem manda é a resposta.
    expect(result.tag?.minutes).toBe(60);
  });

  it("falha ao guardar avisa e devolve não-ok — o timer não depende disso", async () => {
    env.fetchData.value = { tags: [] };
    env.fetchMock.mockRejectedValueOnce({
      status: 400,
      data: { detail: "Dê um nome à etiqueta." },
    });

    const result = await useTimerTags().createTag("---", 10);

    expect(result.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("Dê um nome à etiqueta.");
  });

  it("403 na leitura vira `forbidden`, não tela quebrada", () => {
    env.fetchError.value = { status: 403, data: {} };
    expect(useTimerTags().forbidden.value).toBe(true);
  });
});
