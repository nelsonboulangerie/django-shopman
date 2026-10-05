import { flushPromises, mount } from "@vue/test-utils";
import { computed, ref, watch } from "vue";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import CampaignForm from "~/components/CampaignForm.vue";
import DraftRecoveryNotice from "~/components/DraftRecoveryNotice.vue";
import type { Campaign } from "~/types/campaign";
import { installMemoryLocalStorage } from "../support/localStorage";
import { UiNativeSelectStub } from "../support/nativeUiStubs";

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
  installMemoryLocalStorage();
});

beforeEach(() => window.localStorage.clear());

const TRIGGERS = [
  { value: "production_finished", label: "lote pronto" },
  { value: "schedule", label: "Agendado" },
];
const PLATFORMS = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "instagram", label: "Instagram" },
];
const TEMPLATES = [
  {
    pk: 1,
    name: "Relâmpago",
    body: "oi",
    platform_variants: {
      instagram: { publication_format: "feed" },
      whatsapp: {},
    },
    variables: [],
    use_ai_generation: false,
    image_source: "",
  },
];
const DELIVERY_CAPABILITIES = [
  {
    platform: "instagram",
    label: "Instagram",
    delivery_kind: "publication" as const,
    default_format: "story",
    formats: [
      {
        ref: "story",
        label: "Stories",
        provider_fields: ["publication_format"],
        required_provider_fields: ["publication_format"],
        media_required: true,
      },
      {
        ref: "feed",
        label: "Feed",
        provider_fields: ["publication_format"],
        required_provider_fields: ["publication_format"],
        media_required: true,
      },
    ],
  },
  {
    platform: "whatsapp",
    label: "WhatsApp",
    delivery_kind: "direct_message" as const,
    default_format: "message",
    formats: [
      {
        ref: "message",
        label: "Mensagem",
        provider_fields: ["template_name"],
        required_provider_fields: [],
        media_required: false,
      },
    ],
  },
];
const OFFERS = [{ value: "relampago-17h30", label: "Relâmpago das 17h30" }];
const PRICE_TIERS = [{ value: "atacado", label: "Atacado" }];
const TAGS = [{ value: "sem-gluten", label: "Sem glúten" }];
const RFM_SEGMENTS = [{ value: "loyal_customer", label: "Cliente fiel" }];

function form(rule: Campaign | null = null, draftOwner = "") {
  return mount(CampaignForm, {
    props: {
      rule,
      triggers: TRIGGERS,
      platformOptions: PLATFORMS,
      templates: TEMPLATES as never,
      deliveryCapabilities: DELIVERY_CAPABILITIES,
      offers: OFFERS,
      priceTiers: PRICE_TIERS,
      tags: TAGS,
      rfmSegments: RFM_SEGMENTS,
      platformLabels: { whatsapp: "WhatsApp", instagram: "Instagram" },
      shopTimezone: "America/Sao_Paulo",
      draftOwner,
    },
    global: {
      components: { DraftRecoveryNotice, UiNativeSelect: UiNativeSelectStub },
      stubs: { Icon: true },
    },
  });
}

function checkboxNamed(wrapper: ReturnType<typeof form>, label: string) {
  const choice = wrapper
    .findAll('[role="checkbox"]')
    .find((candidate) =>
      candidate.element
        .closest('[data-slot="item"], [data-slot="checkbox"]')
        ?.textContent?.includes(label),
    );
  if (!choice) throw new Error(`Checkbox "${label}" não encontrado.`);
  return choice;
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

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.promotion_ref).toBe("");
  });

  it("manda a oferta escolhida", async () => {
    const wrapper = form(makeRule({ trigger: "production_finished" }));

    await wrapper.find("#rule-offer").setValue("relampago-17h30");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.promotion_ref).toBe("relampago-17h30");
  });

  it("relê a oferta da regra aberta", () => {
    const wrapper = form(makeRule({ promotion_ref: "relampago-17h30" }));
    expect(
      (wrapper.find("#rule-offer").element as HTMLSelectElement).value,
    ).toBe("relampago-17h30");
  });

  it("some quando não há oferta viva — seletor vazio não ajuda ninguém", () => {
    const wrapper = mount(CampaignForm, {
      props: {
        rule: null,
        triggers: TRIGGERS,
        platformOptions: PLATFORMS,
        templates: TEMPLATES as never,
        offers: [],
        platformLabels: {},
      },
      global: { stubs: { Icon: true, UiNativeSelect: UiNativeSelectStub } },
    });
    expect(wrapper.find("#rule-offer").exists()).toBe(false);
  });
});

describe("CampaignForm — composer V2", () => {
  it("guia pelas cinco etapas e revisa somente as composições selecionadas", async () => {
    const wrapper = form(
      makeRule({ trigger: "production_finished", platforms: ["instagram"] }),
    );

    expect(
      wrapper.find('[role="group"][aria-label="Etapas da campanha"]').exists(),
    ).toBe(true);
    expect(wrapper.find('[aria-current="step"]').attributes("aria-label")).toBe(
      "1. Objetivo",
    );
    for (let step = 0; step < 4; step += 1) {
      await wrapper
        .findAll("button")
        .find((button) => button.text() === "Continuar")!
        .trigger("click");
    }

    expect(wrapper.find('[aria-current="step"]').attributes("aria-label")).toBe(
      "5. Revisar",
    );
    const rows = wrapper
      .find('[data-testid="campaign-compositions"]')
      .findAll("li");
    expect(rows).toHaveLength(1);
    expect(rows[0]!.text()).toContain("Instagram");
    expect(rows[0]!.text()).toContain("Publicação pública");
    expect(rows[0]!.text()).toContain("Feed");
    expect(rows[0]!.text()).not.toContain("WhatsApp");
    expect(wrapper.text()).toContain(
      "Recursos apenas catalogados para o futuro não entram nesta campanha",
    );
  });

  it("mantém o salto para uma etapa pronta mesmo usando o primitive canônico", async () => {
    const wrapper = form(
      makeRule({ trigger: "production_finished", platforms: ["instagram"] }),
    );
    const review = wrapper.find('button[aria-label="5. Revisar"]');

    expect(review.attributes("disabled")).toBeUndefined();
    await review.trigger("mousedown", { button: 0, ctrlKey: false });
    expect(wrapper.find('[aria-current="step"]').attributes("aria-label")).toBe(
      "5. Revisar",
    );
  });

  it("não avança de Destinos enquanto nenhuma plataforma foi escolhida", async () => {
    const wrapper = form(
      makeRule({ trigger: "production_finished", platforms: [] }),
    );
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Continuar")!
      .trigger("click");

    const next = wrapper
      .findAll("button")
      .find((button) => button.text() === "Continuar")!;
    expect(next.attributes("disabled")).toBeDefined();
    expect(wrapper.find('[aria-current="step"]').attributes("aria-label")).toBe(
      "2. Destinos",
    );
  });
});

describe("CampaignForm — natureza de cada saída", () => {
  it("não confunde postagem pública com mensagem direta", () => {
    const text = form(makeRule()).text();

    // ⚠️ O MESMO rótulo do cartão de revisão. Eram dois nomes para o mesmo conceito —
    // o cartão dizia uma coisa, o formulário outra —, e "por" ainda é ambíguo entre
    // agente e meio: "disparado por Pablo" e "disparado por Instagram" leem igual.
    expect(text).toContain("Disparado via");
    expect(text).toContain("uma postagem pública por plataforma");
    expect(text).toContain("WhatsApp envia uma mensagem por pessoa elegível");
    expect(text).toContain(
      "Mensagens diretas do Instagram ainda não fazem parte deste app",
    );
  });

  it("só pede público quando há mensagem direta por WhatsApp", () => {
    const direct = form(makeRule({ platforms: ["whatsapp"] }));
    const publicOnly = form(makeRule({ platforms: ["instagram"] }));

    expect(direct.text()).toContain("Público alvo");
    expect(direct.text()).not.toContain(
      "Estas publicações vão para o público geral",
    );
    expect(publicOnly.text()).not.toContain("Público alvo");
    expect(publicOnly.text()).toContain(
      "Estas publicações vão para o público geral",
    );
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

    await wrapper.find('input[type="time"]').setValue("17:30");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.schedule).toEqual({
      type: "recurring",
      timezone: "America/Sao_Paulo",
      windows: [["17:30", "18:30"]],
    });
  });

  it("manda só os dias marcados", async () => {
    const wrapper = form(makeRule());

    // Os dias são `UiToggleChip`: `role="checkbox"` com `aria-checked`, e não botão
    // com `aria-pressed` — marcar dia é marcar item, não apertar botão que fica
    // apertado.
    const days = wrapper
      .findAll('[role="checkbox"]')
      .filter((chip) => ["sex", "sáb"].includes(chip.text()));
    for (const day of days) await day.trigger("click");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect((payload.schedule as Record<string, unknown>).weekdays).toEqual([
      4, 5,
    ]);
  });

  it("uma vez manda o instante, não a janela", async () => {
    const wrapper = form(
      makeRule({ schedule: { type: "once", at: "2026-08-15T17:30" } }),
    );

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.schedule).toEqual({ type: "once", at: "2026-08-15T17:30" });
  });

  it("uma vez sem instante não deixa salvar", async () => {
    // ⚠️ Salvar sem a hora criaria a campanha agendada que nunca dispara — o defeito
    // que o `clean()` do model recusa. Melhor não chegar até lá.
    const wrapper = form(makeRule({ schedule: { type: "once" } }));

    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("uma vez nova envia offset e timezone sem inferir o computador", async () => {
    const wrapper = form(makeRule());
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Uma vez")!
      .trigger("click");
    await wrapper.find("#rule-once-at").setValue("2027-01-10T17:30");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.schedule).toEqual({
      type: "once",
      at: "2027-01-10T17:30:00-03:00",
      timezone: "America/Sao_Paulo",
    });
  });

  it("explica e bloqueia um horário inexistente na mudança de DST", async () => {
    const wrapper = form(makeRule(), "");
    await wrapper.setProps({ shopTimezone: "America/New_York" });
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Uma vez")!
      .trigger("click");
    await wrapper.find("#rule-once-at").setValue("2027-03-14T02:30");
    await wrapper.find("form").trigger("submit");

    expect(wrapper.text()).toContain(
      "não existe por causa da mudança do relógio",
    );
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("não manda schedule em gatilho de evento, para não apagar o do Admin", async () => {
    const wrapper = form(makeRule({ trigger: "production_finished" }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect("schedule" in payload).toBe(false);
  });

  it("relê o agendamento da regra aberta", () => {
    const wrapper = form(
      makeRule({
        schedule: {
          type: "recurring",
          windows: [["06:00", "07:00"]],
          weekdays: [0],
        },
      }),
    );

    expect(
      (wrapper.find('input[type="time"]').element as HTMLInputElement).value,
    ).toBe("06:00");
    const marked = wrapper
      .findAll('[role="checkbox"][aria-checked="true"]')
      .map((chip) => chip.text());
    expect(marked).toContain("seg");
  });

  it("preserva o agendamento inteiro quando ninguém o altera", async () => {
    const schedule = {
      type: "recurring" as const,
      windows: [
        ["06:00", "07:00"],
        ["16:00", "18:00"],
      ],
      weekdays: [0, 2, 4],
      starts_on: "2026-09-10",
      ends_on: "2026-12-31",
      timezone_policy: "recipient",
    };
    const wrapper = form(makeRule({ schedule }));

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.schedule).toEqual(schedule);
    expect(wrapper.text()).toContain(
      "Horários adicionais preservados: 16:00–18:00",
    );
  });

  it("edita a primeira hora sem apagar período, janelas extras ou extensão", async () => {
    const wrapper = form(
      makeRule({
        schedule: {
          type: "recurring",
          windows: [
            ["06:00", "07:00"],
            ["16:00", "18:00"],
          ],
          weekdays: [1, 3],
          starts_on: "2026-09-10",
          ends_on: "2026-12-31",
          timezone_policy: "recipient",
        },
      }),
    );

    await wrapper.find("#rule-fire-at").setValue("08:15");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.schedule).toEqual({
      type: "recurring",
      timezone: "America/Sao_Paulo",
      windows: [
        ["08:15", "09:15"],
        ["16:00", "18:00"],
      ],
      weekdays: [1, 3],
      starts_on: "2026-09-10",
      ends_on: "2026-12-31",
      timezone_policy: "recipient",
    });
  });

  it("troca gatilho agendado por evento sem deixar um schedule incompatível", async () => {
    const wrapper = form(
      makeRule({
        schedule: {
          type: "once",
          at: "2026-10-10T10:00",
          provider_hint: "keep-server-extension",
        },
      }),
    );

    await wrapper.find("#rule-trigger").setValue("production_finished");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
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
    const wrapper = form(
      makeRule({
        trigger: "production_finished",
        trigger_filter: { collections: ["paes"], future_filter: true },
        audience_rules: audienceRules,
      }),
    );

    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.audience_rules).toEqual(audienceRules);
    expect("trigger_filter" in payload).toBe(false);
    // O aviso conta que o que o formulário não edita continua valendo — em
    // português. Chave nova do servidor entra na conta, nunca no texto.
    expect(wrapper.text()).toContain(
      "Filtros de público já salvos (produtos comprados, coleções compradas e mais 1 critério)",
    );
    expect(wrapper.text()).toContain(
      "Os filtros do evento já salvos (coleções e mais 1 critério)",
    );
    expect(wrapper.text()).not.toMatch(
      /\b(bought_skus|future_selector|future_filter)\b/,
    );
  });

  it("altera critérios avançados sem apagar os seletores protegidos", async () => {
    const wrapper = form(
      makeRule({
        trigger: "production_finished",
        audience_rules: {
          bought_skus: ["PAO-01"],
          bought_collections: ["cafe-da-manha"],
        },
      }),
    );

    await checkboxNamed(wrapper, "Sem glúten").trigger("click");
    await checkboxNamed(wrapper, "Atacado").trigger("click");
    await checkboxNamed(wrapper, "Cliente fiel").trigger("click");
    await wrapper.find("#rule-audience-match").setValue("all");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.audience_rules).toEqual({
      bought_skus: ["PAO-01"],
      bought_collections: ["cafe-da-manha"],
      tags: ["sem-gluten"],
      price_tiers: ["atacado"],
      rfm_segments: ["loyal_customer"],
      match: "all",
    });
  });

  it("restaura nome e seleções da mesma regra para o mesmo operador", async () => {
    const rule = makeRule({
      trigger: "production_finished",
      updated_at: "2026-09-09T08:00:00-03:00",
    });
    const first = form(rule, "operator:7");
    await first.find("#rule-name").setValue("Campanha em revisão");
    await checkboxNamed(first, "Sem glúten").trigger("click");
    first.unmount();

    const restored = form(rule, "operator:7");
    await flushPromises();

    expect(
      (restored.find("#rule-name").element as HTMLInputElement).value,
    ).toBe("Campanha em revisão");
    // O chip é `role="checkbox"` com `aria-checked`, e não um botão com
    // `aria-pressed`: escolher etiqueta é marcar item, não apertar um botão que fica
    // apertado. O leitor de tela diz "marcada", que é o que a pessoa está fazendo.
    expect(
      checkboxNamed(restored, "Sem glúten").attributes("aria-checked"),
    ).toBe("true");
    expect(restored.text()).toContain("Rascunho restaurado");
  });

  it("salva a edição pendente para o operador original quando a sessão some", async () => {
    const rule = makeRule({
      trigger: "production_finished",
      updated_at: "2026-09-09T08:00:00-03:00",
    });
    const first = form(rule, "operator:7");
    await first.find("#rule-name").setValue("Não redigitar depois do login");

    // Reproduz a janela crítica: a identidade desaparece antes dos 400 ms do
    // debounce e o gate desmonta o formulário logo depois.
    await first.setProps({ draftOwner: "" });
    first.unmount();

    const restored = form(rule, "operator:7");
    await flushPromises();

    expect(
      (restored.find("#rule-name").element as HTMLInputElement).value,
    ).toBe("Não redigitar depois do login");
    expect(restored.text()).toContain("Rascunho restaurado");
  });

  it("isola o rascunho entre campanhas", async () => {
    const first = form(
      makeRule({ pk: 5, trigger: "production_finished", updated_at: "v1" }),
      "operator:7",
    );
    await first.find("#rule-name").setValue("Rascunho da cinco");
    first.unmount();

    const other = form(
      makeRule({
        pk: 6,
        name: "Campanha seis",
        trigger: "production_finished",
        updated_at: "v1",
      }),
      "operator:7",
    );
    await flushPromises();

    expect((other.find("#rule-name").element as HTMLInputElement).value).toBe(
      "Campanha seis",
    );
  });
});

describe("CampaignForm — as escolhas são peças do kit", () => {
  // ⚠️ Os sete checkboxes e o rádio desta tela eram o controle nativo do browser com
  // uma tinta do Tailwind por cima: desenho do sistema operacional no meio do desenho
  // da casa, diferente em cada dispositivo, e sem o alvo de toque de 44 px que quem
  // atende balcão precisa com uma mão só. Este teste prende a semântica que o
  // primitivo garante — `role="checkbox"` com `aria-checked` — e prova que o valor
  // marcado ainda chega ao payload.
  it("marca o público por role=checkbox, e a marca chega ao envio", async () => {
    const wrapper = form(makeRule({ trigger: "production_finished" }));

    const birthday = wrapper
      .findAll('[role="checkbox"]')
      .find(
        (box) => box.attributes("aria-label") === "Aniversariantes de hoje",
      )!;

    expect(birthday.attributes("aria-checked")).toBe("false");
    await birthday.trigger("click");
    expect(birthday.attributes("aria-checked")).toBe("true");

    await wrapper.find("form").trigger("submit");
    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(
      (payload.audience_rules as Record<string, unknown>).birthday_today,
    ).toBe(true);
  });

  it("o destino pertence ao grupo canônico, e marcar chega ao envio", async () => {
    const wrapper = form(makeRule({ platforms: [] }));

    expect(wrapper.find('input[type="checkbox"].sr-only').exists()).toBe(false);
    const destination = checkboxNamed(wrapper, "WhatsApp");
    expect(destination.attributes("aria-checked")).toBe("false");

    await destination.trigger("click");
    expect(destination.attributes("aria-checked")).toBe("true");
    await wrapper.find("form").trigger("submit");
    const [payload] = wrapper.emitted("submit")![0] as [
      Record<string, unknown>,
    ];
    expect(payload.platforms).toContain("whatsapp");
  });
});

describe("CampaignForm — a voz do gestor", () => {
  // ⚠️ A entidade é `Campaign` e a lista chama de "campanha"; o formulário fechava
  // com "Regra ativa", um terceiro nome para a mesma coisa.
  it("chama a campanha de campanha, nunca de regra", () => {
    const text = form(makeRule()).text();

    expect(text).toContain("Campanha ligada");
    expect(text).not.toMatch(/\bRegra\b/);
  });

  // ⚠️ O aviso de filtro preservado imprimia a CHAVE do JSON: "collections, skus",
  // "bought_skus". Chave é contrato com o servidor, não vocabulário do gestor.
  it("nomeia os filtros do evento preservados em português, sem chave JSON", () => {
    const text = form(
      makeRule({
        trigger: "production_finished",
        trigger_filter: {
          collections: ["paes"],
          skus: ["BAGUETE"],
          chave_nova_do_servidor: 1,
        },
      }),
    ).text();

    expect(text).toContain(
      "Os filtros do evento já salvos (coleções, produtos e mais 1 critério) continuam valendo.",
    );
    expect(text).not.toMatch(/\b(collections|skus|chave_nova_do_servidor)\b/);
  });

  it("nomeia os filtros de público preservados em português, sem chave JSON", () => {
    const text = form(
      makeRule({
        trigger: "production_finished",
        audience_rules: {
          bought_skus: ["BAGUETE"],
          bought_collections: ["paes"],
        },
      }),
    ).text();

    expect(text).toContain(
      "Filtros de público já salvos (produtos comprados, coleções compradas) continuam valendo",
    );
    expect(text).not.toMatch(/\bbought_(skus|collections)\b/);
  });

  // ⚠️ As quatro plataformas apareciam iguais e a recusa só chegava depois de
  // aprovar. A prontidão é pré-condição de PUBLICAR, não de configurar.
  it("mostra antes do clique onde a campanha não vai sair, sem travar o salvar", async () => {
    const wrapper = mount(CampaignForm, {
      props: {
        rule: makeRule({ platforms: ["instagram"] }),
        triggers: TRIGGERS,
        platformOptions: PLATFORMS,
        templates: TEMPLATES as never,
        offers: OFFERS,
        platformLabels: { whatsapp: "WhatsApp", instagram: "Instagram" },
        platformReadiness: [
          {
            platform: "instagram",
            state: "blocked",
            ready: false,
            reason:
              "A integração existe, mas está sem credencial neste ambiente.",
            limitation: "",
            source_status: "live",
          },
          {
            platform: "whatsapp",
            state: "unknown",
            ready: false,
            reason:
              "Não foi possível verificar o transporte do WhatsApp agora.",
            limitation: "",
            source_status: "live",
          },
        ],
      },
      global: {
        components: { DraftRecoveryNotice, UiNativeSelect: UiNativeSelectStub },
        stubs: { Icon: true, NuxtLink: true },
      },
    });
    const text = wrapper.text();

    // A pílula conta o estado das duas, escolhida ou não.
    expect(wrapper.find('[data-readiness="blocked"]').text()).toContain(
      "Instagram · não publica",
    );
    expect(wrapper.find('[data-readiness="unknown"]').text()).toContain(
      "WhatsApp · não verificada",
    );
    // A escolhida ganha a frase completa; a não escolhida não faz barulho.
    expect(text).toContain(
      "Instagram: A integração existe, mas está sem credencial neste ambiente. Nada é publicado por aqui até resolver.",
    );
    expect(text).toContain("A campanha pode ser salva assim mesmo.");
    expect(text).not.toContain("Não foi possível verificar o transporte");

    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("descreve o público em conflito como frase, não como JSON", async () => {
    const rule = makeRule({
      trigger: "production_finished",
      audience_rules: {},
      updated_at: "v1",
    });
    const first = form(rule, "operator:7");
    await checkboxNamed(first, "Sem glúten").trigger("click");
    first.unmount();

    const conflicted = form(
      makeRule({
        trigger: "production_finished",
        audience_rules: { favorites: true, alerts: true },
        updated_at: "v2",
      }),
      "operator:7",
    );
    await flushPromises();
    const text = conflicted.text();

    expect(text).toContain("Este conteúdo também mudou em outra sessão");
    expect(text).toContain("Versão atual: Favoritos, alertas");
    expect(text).toContain("Seu rascunho: Sem glúten");
    expect(text).not.toContain("{");
    expect(text).not.toMatch(/\b(favorites|alerts|tags)\b/);
  });
});
