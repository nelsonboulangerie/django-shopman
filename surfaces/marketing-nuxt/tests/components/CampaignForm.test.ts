import { mount } from "@vue/test-utils";
import { computed, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import CampaignForm from "~/components/CampaignForm.vue";
import type { Campaign } from "~/types/campaign";

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
});

const TRIGGERS = [
  { value: "production_finished", label: "fornada pronta" },
  { value: "schedule", label: "Agendado" },
];
const PLATFORMS = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "instagram", label: "Instagram" },
];
const TEMPLATES = [
  { pk: 1, name: "Relâmpago", body: "oi", variables: [], use_ai_generation: false, image_source: "" },
];
const OFFERS = [
  { value: "relampago-17h30", label: "Relâmpago das 17h30" },
];

function form(rule: Campaign | null = null) {
  return mount(CampaignForm, {
    props: {
      rule,
      triggers: TRIGGERS,
      platformOptions: PLATFORMS,
      templates: TEMPLATES as never,
      offers: OFFERS,
    },
    global: { stubs: { Icon: true } },
  });
}

function makeRule(over: Partial<Campaign> = {}): Campaign {
  return {
    pk: 5,
    name: "Relâmpago das 17h30",
    trigger: "schedule",
    trigger_label: "Agendado",
    platforms: ["whatsapp"],
    template_id: 1,
    audience_rules: {},
    requires_approval: true,
    is_active: true,
    ...over,
  } as Campaign;
}

describe("CampaignForm — a oferta anunciada", () => {
  it("deixa a campanha sem oferta por padrão", async () => {
    const wrapper = form(makeRule({ trigger: "production_finished" }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.promotion_ref).toBe("");
  });

  it("manda a oferta escolhida", async () => {
    const wrapper = form(makeRule({ trigger: "production_finished" }));

    await wrapper.find("#rule-offer").setValue("relampago-17h30");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.promotion_ref).toBe("relampago-17h30");
  });

  it("relê a oferta da regra aberta", () => {
    const wrapper = form(makeRule({ promotion_ref: "relampago-17h30" }));
    expect((wrapper.find("#rule-offer").element as HTMLSelectElement).value)
      .toBe("relampago-17h30");
  });

  it("some quando não há oferta viva — seletor vazio não ajuda ninguém", () => {
    const wrapper = mount(CampaignForm, {
      props: {
        rule: null, triggers: TRIGGERS, platformOptions: PLATFORMS,
        templates: TEMPLATES as never, offers: [],
      },
      global: { stubs: { Icon: true } },
    });
    expect(wrapper.find("#rule-offer").exists()).toBe(false);
  });
});

describe("CampaignForm — quando disparar", () => {
  it("esconde o agendamento nos gatilhos de evento", () => {
    // Nesses, a causa é o evento: perguntar a hora aqui não teria resposta.
    const wrapper = form(makeRule({ trigger: "production_finished" }));
    expect(wrapper.text()).not.toContain("Quando disparar");
  });

  it("mostra o agendamento no gatilho agendado", () => {
    expect(form(makeRule()).text()).toContain("Quando disparar");
  });

  it("monta o JSON que o serviço lê, com a semana toda implícita", async () => {
    const wrapper = form(makeRule());

    await wrapper.find("input[type=\"time\"]").setValue("17:30");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.schedule).toEqual({
      type: "recurring",
      windows: [["17:30", "18:30"]],
    });
  });

  it("manda só os dias marcados", async () => {
    const wrapper = form(makeRule());

    const days = wrapper.findAll("button[aria-pressed]").filter((b) => ["sex", "sáb"].includes(b.text()));
    for (const day of days) await day.trigger("click");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect((payload.schedule as Record<string, unknown>).weekdays).toEqual([4, 5]);
  });

  it("uma vez manda o instante, não a janela", async () => {
    const wrapper = form(makeRule({ schedule: { type: "once", at: "2026-08-15T17:30" } }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.schedule).toEqual({ type: "once", at: "2026-08-15T17:30" });
  });

  it("uma vez sem instante não deixa salvar", async () => {
    // ⚠️ Salvar sem a hora criaria a campanha agendada que nunca dispara — o defeito
    // que o `clean()` do model recusa. Melhor não chegar até lá.
    const wrapper = form(makeRule({ schedule: { type: "once" } }));

    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("não manda schedule em gatilho de evento, para não apagar o do Admin", async () => {
    const wrapper = form(makeRule({ trigger: "production_finished" }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect("schedule" in payload).toBe(false);
  });

  it("relê o agendamento da regra aberta", () => {
    const wrapper = form(
      makeRule({ schedule: { type: "recurring", windows: [["06:00", "07:00"]], weekdays: [0] } }),
    );

    expect((wrapper.find("input[type=\"time\"]").element as HTMLInputElement).value).toBe("06:00");
    const marked = wrapper.findAll("button[aria-pressed=\"true\"]").map((b) => b.text());
    expect(marked).toContain("seg");
  });
});
