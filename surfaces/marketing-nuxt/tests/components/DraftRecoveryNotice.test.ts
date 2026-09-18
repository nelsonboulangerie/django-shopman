import { mount } from "@vue/test-utils";
import { computed } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import DraftRecoveryNotice from "~/components/DraftRecoveryNotice.vue";
import type { MarketingDraftConflict } from "~/utils/marketingDraft";

beforeAll(() => {
  Object.assign(globalThis, { computed });
});

function notice(
  conflicts: MarketingDraftConflict[],
  describe?: (field: string, value: unknown) => string | undefined,
) {
  return mount(DraftRecoveryNotice, {
    props: {
      state: "conflict",
      savedAt: 0,
      conflicts,
      labels: { audience_rules: "Público", platforms: "Plataformas" },
      describe,
    },
    global: { stubs: { Icon: true } },
  });
}

describe("DraftRecoveryNotice — conflito sem JSON na tela", () => {
  // ⚠️ Público e agendamento chegavam como `{"favorites":true,...}`: chave em inglês
  // e chaves na tela do gestor. Valor composto vira frase ou contagem.
  it("descreve o valor composto com a frase do dono do campo", () => {
    const text = notice(
      [
        {
          field: "audience_rules",
          base: {},
          current: { alerts: true },
          draft: { favorites: true, alerts: true },
        },
      ],
      (field, value) =>
        field === "audience_rules"
          ? Object.keys(value as object).join(" + ")
          : undefined,
    ).text();

    expect(text).toContain("Versão atual: alerts");
    expect(text).toContain("Seu rascunho: favorites + alerts");
    expect(text).not.toContain("{");
  });

  it("cai numa contagem quando ninguém descreve o campo — nunca em JSON", () => {
    const text = notice([
      {
        field: "audience_rules",
        base: {},
        current: { alerts: true },
        draft: { favorites: true, alerts: true },
      },
      {
        field: "platforms",
        base: [],
        current: ["whatsapp"],
        draft: [],
      },
    ]).text();

    expect(text).toContain("Versão atual: 1 critério");
    expect(text).toContain("Seu rascunho: 2 critérios");
    expect(text).toContain("Versão atual: 1 item");
    expect(text).toContain("Seu rascunho: nenhum");
    expect(text).not.toContain("{");
    expect(text).not.toContain("[");
    expect(text).not.toContain("whatsapp");
  });

  it("mantém as frases simples dos campos escalares", () => {
    const text = notice([
      { field: "name", base: "", current: "", draft: undefined },
      { field: "is_active", base: true, current: true, draft: false },
    ]).text();

    expect(text).toContain("Versão atual: em branco");
    expect(text).toContain("Seu rascunho: não preenchido");
    expect(text).toContain("Versão atual: sim");
    expect(text).toContain("Seu rascunho: não");
  });
});
