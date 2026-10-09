import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("campaign activation switch", () => {
  // O que este teste guarda MUDOU de lugar, e de propósito: ele cravava as classes
  // do trilho DENTRO da página, e era assim que a campanha ficou com um
  // interruptor próprio, diferente do do PDV. Agora a página monta o primitivo, e
  // o alvo de 44 px é cobrado UMA vez, no kit — que é onde o conserto chega às dez
  // telas de uma vez.
  it("monta o interruptor do kit, sem trilho próprio", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain("<UiSwitch");
    expect(page).toContain(':model-value="rule.is_active"');
    expect(page).toContain(
      ':disabled="mutatingCampaignPk !== null || !editState(rule).enabled"',
    );
    expect(page).toContain('@update:model-value="toggle(rule)"');
    expect(page).toContain("campaignEditAvailability(rule, actions.value)");
    // O trilho à mão não volta: nem o `role="switch"` nem as classes dele.
    expect(page).not.toContain('role="switch"');
    expect(page).not.toContain("rounded-full transition-colors");
  });

  it("o interruptor do kit usa o Nuxt UI e mantém o alvo de toque no token", () => {
    const primitive = readFileSync(
      new URL(
        "../../operator-kit/app/components/UiSwitch.vue",
        import.meta.url,
      ),
      "utf8",
    );

    expect(primitive).toContain("<NuxtSwitch");
    expect(primitive).toContain("size-control");
    expect(primitive).toContain(':model-value="modelValue"');
    expect(primitive).not.toContain('role="switch"');
    // Que o literal (`size-11`) não volte é cobrado no kit, onde a varredura tira
    // os comentários antes de medir — o cabeçalho do primitivo CITA o literal que
    // ele aposentou, e citar a dívida não é cometê-la.
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

    expect(page).toContain(':disabled="!fireAction(rule)?.enabled"');
    expect(page).toContain("fireActionFor(rule, actions.value)");
    expect(presentation).toContain('action.kind === "fire_campaign"');
    expect(page).toContain('"Indisponível"');
  });

  it("never opens editing when the projected Action is disabled", () => {
    const page = readFileSync(
      new URL("../app/pages/settings/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain(':disabled="!editState(rule).enabled"');
    expect(page).toContain("if (!editState(rule).enabled) return");
    expect(page).toContain("{{ editState(rule).reason }}");
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
