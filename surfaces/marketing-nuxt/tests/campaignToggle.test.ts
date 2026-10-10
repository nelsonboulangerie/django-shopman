import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("campaign activation switch", () => {
  // O que este teste guarda MUDOU de lugar, e de propósito: ele cravava as classes
  // do trilho DENTRO da página, e era assim que a campanha ficou com um
  // interruptor próprio, diferente do do PDV. Agora a página monta o primitivo, e
  // o alvo de 44 px é cobrado UMA vez, no kit — que é onde o conserto chega às dez
  // telas de uma vez.
  // A página monta o interruptor do Nuxt UI (`NuxtSwitch`) na célula "Ligada" da
  // tabela da suíte: nada de trilho à mão, nada de primitivo legado. O alvo de toque é
  // do tema do kit (`switch.slots.base` no app.config), cobrado uma vez lá.
  it("monta o interruptor do Nuxt UI, sem trilho próprio", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain("<NuxtSwitch");
    expect(page).not.toContain("<UiSwitch");
    expect(page).toContain(':model-value="row.original.is_active"');
    expect(page).toContain(
      ':disabled="mutatingCampaignPk !== null || !editState(row.original).enabled"',
    );
    expect(page).toContain('@update:model-value="toggle(row.original)"');
    expect(page).toContain("campaignEditAvailability(rule, actions.value)");
    // O trilho à mão não volta: nem o `role="switch"` nem as classes dele.
    expect(page).not.toContain('role="switch"');
    expect(page).not.toContain("rounded-full transition-colors");
  });

  it("a lista é a tabela da suíte, sem tabela crua", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain("<OperatorTable");
    expect(page).toContain('<OperatorTableView table-key="marketing-campaigns"');
    expect(page).toContain('view-key="marketing-campaigns"');
    expect(page).not.toMatch(/<table[\s>]/);
    expect(page).not.toMatch(/<(button|select|input)[\s>]/);
  });

  it("never opens a server-disabled manual fire action", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    const presentation = readFileSync(
      new URL("../app/presentation/campaignFire.ts", import.meta.url),
      "utf8",
    );

    expect(page).toContain(':disabled="!fireAction(row.original)?.enabled"');
    expect(page).toContain("fireActionFor(rule, actions.value)");
    expect(presentation).toContain('action.kind === "fire_campaign"');
    expect(page).toContain('"Indisponível"');
  });

  it("never opens editing when the projected Action is disabled", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    // Abrir a linha passa por `openEdit`, que recusa sem a Action; o "Editar" do ⋯
    // fica desabilitado com o motivo, e o motivo também vai escrito sob a linha.
    expect(page).toContain(':on-select="(rule: Campaign) => openEdit(rule)"');
    expect(page).toContain("if (!editState(rule).enabled) return");
    expect(page).toContain("disabled: !edit.enabled");
    expect(page).toContain("reason: edit.enabled ? undefined : edit.reason");
    expect(page).toContain("{{ editState(row.original).reason }}");
  });

  it("keeps the open editor across the authentication gate", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain('useState<boolean>("marketing-campaign-creating"');
    expect(page).toContain('"marketing-campaign-editing-pk"');
    expect(page).not.toContain("const creating = ref(false)");
    expect(page).not.toContain("const editing = ref<Campaign | null>(null)");
  });
});
