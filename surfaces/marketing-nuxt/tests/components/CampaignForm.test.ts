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
const PRICE_TIERS = [{ value: "atacado", label: "Atacado" }];
const TAGS = [{ value: "sem-gluten", label: "Sem glúten" }];
const RFM_SEGMENTS = [{ value: "loyal_customer", label: "Cliente fiel" }];

function form(rule: Campaign | null = null) {
  return mount(CampaignForm, {
    props: {
      rule,
      triggers: TRIGGERS,
      platformOptions: PLATFORMS,
      templates: TEMPLATES as never,
      offers: OFFERS,
      priceTiers: PRICE_TIERS,
      tags: TAGS,
      rfmSegments: RFM_SEGMENTS,
      platformLabels: { whatsapp: "WhatsApp", instagram: "Instagram" },
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
        templates: TEMPLATES as never, offers: [], platformLabels: {},
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

  it("preserva o agendamento inteiro quando ninguém o altera", async () => {
    const schedule = {
      type: "recurring" as const,
      windows: [["06:00", "07:00"], ["16:00", "18:00"]],
      weekdays: [0, 2, 4],
      starts_on: "2026-09-10",
      ends_on: "2026-12-31",
      timezone_policy: "recipient",
    };
    const wrapper = form(makeRule({ schedule }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.schedule).toEqual(schedule);
    expect(wrapper.text()).toContain("Horários adicionais preservados: 16:00–18:00");
  });

  it("edita a primeira hora sem apagar período, janelas extras ou extensão", async () => {
    const wrapper = form(makeRule({
      schedule: {
        type: "recurring",
        windows: [["06:00", "07:00"], ["16:00", "18:00"]],
        weekdays: [1, 3],
        starts_on: "2026-09-10",
        ends_on: "2026-12-31",
        timezone_policy: "recipient",
      },
    }));

    await wrapper.find("#rule-fire-at").setValue("08:15");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.schedule).toEqual({
      type: "recurring",
      windows: [["08:15", "09:15"], ["16:00", "18:00"]],
      weekdays: [1, 3],
      starts_on: "2026-09-10",
      ends_on: "2026-12-31",
      timezone_policy: "recipient",
    });
  });

  it("troca gatilho agendado por evento sem deixar um schedule incompatível", async () => {
    const wrapper = form(makeRule({
      schedule: {
        type: "once",
        at: "2026-10-10T10:00",
        provider_hint: "keep-server-extension",
      },
    }));

    await wrapper.find("#rule-trigger").setValue("production_finished");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.schedule).toEqual({
      type: "immediate",
      provider_hint: "keep-server-extension",
    });
  });
});

describe("CampaignForm — round-trip lossless da audiência", () => {
  it("salva sem alteração preservando todos os seletores públicos e futuros", async () => {
    const audienceRules = {
      favorites: true,
      alerts: true,
      bought_within_days: 45,
      vip_first_minutes: 15,
      preferred_hour_window_hours: 2,
      match: "all" as const,
      price_tiers: ["atacado"],
      tags: ["sem-gluten"],
      rfm_segments: ["loyal_customer"],
      churn_risk_min: 0.8,
      birthday_today: true,
      bought_skus: ["PAO-01"],
      bought_collections: ["cafe-da-manha"],
      future_selector: { mode: "safe" },
    };
    const wrapper = form(makeRule({
      trigger: "production_finished",
      trigger_filter: { collections: ["paes"], future_filter: true },
      audience_rules: audienceRules,
    }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.audience_rules).toEqual(audienceRules);
    expect("trigger_filter" in payload).toBe(false);
    expect(wrapper.text()).toContain("bought_skus");
    expect(wrapper.text()).toContain("future_selector");
    expect(wrapper.text()).toContain("future_filter");
  });

  it("altera critérios avançados sem apagar os seletores protegidos", async () => {
    const wrapper = form(makeRule({
      trigger: "production_finished",
      audience_rules: {
        bought_skus: ["PAO-01"],
        bought_collections: ["cafe-da-manha"],
      },
    }));

    await wrapper.findAll("button").find((button) => button.text() === "Sem glúten")!.trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Atacado")!.trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Cliente fiel")!.trigger("click");
    await wrapper.find("#rule-audience-match").setValue("all");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [Record<string, unknown>];
    expect(payload.audience_rules).toEqual({
      bought_skus: ["PAO-01"],
      bought_collections: ["cafe-da-manha"],
      tags: ["sem-gluten"],
      price_tiers: ["atacado"],
      rfm_segments: ["loyal_customer"],
      match: "all",
    });
  });
});
