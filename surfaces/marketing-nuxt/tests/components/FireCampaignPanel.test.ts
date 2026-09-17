import { mount } from "@vue/test-utils";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAudienceCount } from "~/composables/useAudienceCount";
import FireCampaignPanel from "~/components/FireCampaignPanel.vue";
import type { AudienceCount, Campaign } from "~/types/campaign";
import { UiNativeSelectStub } from "../support/nativeUiStubs";

/** O que a contagem do servidor devolveu por último — o teste inspeciona e controla. */
let counted: AudienceCount;
/** As regras que o painel MANDOU contar. É por aqui que se prova o `match`. */
let lastCountedRules: Record<string, unknown> | null = null;
let lastCountedSku = "";

function fakeCount(over: Partial<AudienceCount> = {}): AudienceCount {
  return {
    total: 2,
    match: "any",
    match_label: "Somando as regras",
    parts: [{ label: "Faixa de preço", count: 2 }],
    vip_count: 0,
    empty_selection: false,
    alerts_pending: -1,
    alerts_notified: -1,
    excluded_by_reason: {},
    can_approve: true,
    blocked_reason: "",
    degraded_sources: [],
    ...over,
  };
}

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
//
// A contagem entra com o composable REAL — só o `$fetch` é falso. Ele carrega o debounce e
// o descarte de resposta velha, e um stub aqui deixaria justamente essa parte sem teste.
beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    flagMarketingSessionError: () => false,
    ref,
    watch,
    onBeforeUnmount,
    useAudienceCount,
    $fetch: vi.fn(
      async (_url: string, opts: { body?: Record<string, unknown> }) => {
        lastCountedRules = (opts?.body?.audience_rules ?? null) as Record<
          string,
          unknown
        > | null;
        lastCountedSku = String(opts?.body?.sku ?? "");
        return counted;
      },
    ),
  });
});

beforeEach(() => {
  counted = fakeCount();
  lastCountedRules = null;
  lastCountedSku = "";
  vi.useFakeTimers();
});

/** Passa o debounce da contagem e deixa o Vue redesenhar. */
async function settleCount(wrapper: {
  vm: { $nextTick: () => Promise<void> };
}) {
  await vi.advanceTimersByTimeAsync(400);
  await wrapper.vm.$nextTick();
}

const TIERS = [
  { value: "varejo", label: "Varejo" },
  { value: "atacado", label: "Atacado" },
];
const TAGS = [
  { value: "corredores", label: "corredores (3)" },
  { value: "sem-gluten", label: "sem glúten (1)" },
];
const SEGMENTS = [
  { value: "champion", label: "Campeão" },
  { value: "at_risk", label: "Em risco" },
];
const PRODUCTS = [
  { value: "MDL", label: "Madeleine (MDL)" },
  { value: "FOA", label: "Focaccia Alecrim (FOA)" },
];

function makeRule(over: Partial<Campaign> = {}): Campaign {
  return {
    pk: 3,
    version: 1,
    name: "Novidade da semana",
    trigger: "manual",
    trigger_label: "Disparo manual",
    platforms: ["whatsapp"],
    audience_rules: { tags: ["clientes-da-casa"] },
    requires_approval: true,
    is_active: true,
    ...over,
  } as Campaign;
}

function panel(
  rule: Campaign | null = makeRule(),
  extra: { products?: typeof PRODUCTS } = {},
) {
  return mount(FireCampaignPanel, {
    props: { rule, priceTiers: TIERS, tags: TAGS, rfmSegments: SEGMENTS, ...extra },
    global: {
      components: { UiNativeSelect: UiNativeSelectStub },
      stubs: { Icon: true },
    },
    globalProperties: {},
  });
}

describe("FireCampaignPanel — disparar agora", () => {
  it("começa no público da campanha, que é o caminho seguro", async () => {
    const wrapper = panel();
    await wrapper.find("form").trigger("submit");

    // Objeto vazio = usa o público salvo. A campanha não é alterada.
    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { audience: {}, sku: "", productLabel: "" },
    ]);
  });

  it("não deixa disparar sem escolher ninguém", async () => {
    const wrapper = panel();
    const radios = wrapper.findAll('input[name="audience-mode"]');
    await radios[1]!.setValue();

    const submit = wrapper.find('button[type="submit"]');
    expect(submit.attributes("disabled")).toBeDefined();
  });

  it("monta o público escolhido em vocabulário do backend", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();

    // "Atacado" e "Em risco" — o gestor clica em frases, não em chaves.
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "Atacado")!.trigger("click");
    await chips.find((c) => c.text() === "Em risco")!.trigger("click");
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([
      {
        audience: { price_tiers: ["atacado"], rfm_segments: ["at_risk"] },
        sku: "",
        productLabel: "",
      },
    ]);
  });

  it("traduz 'quem está sumindo' para o piso de risco que o resolvedor entende", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    await wrapper.findAll('input[type="checkbox"]')[0]!.setValue(true);
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { audience: { churn_risk_min: 0.7 }, sku: "", productLabel: "" },
    ]);
  });

  it("aniversariantes e VIP-primeiro convivem no mesmo disparo", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const boxes = wrapper.findAll('input[type="checkbox"]');
    await boxes[1]!.setValue(true); // aniversariantes
    await boxes[2]!.setValue(true); // VIP primeiro
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([
      {
        audience: { birthday_today: true, vip_first_minutes: 15 },
        sku: "",
        productLabel: "",
      },
    ]);
  });

  it("trocar de campanha zera a escolha anterior", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "Atacado")!.trigger("click");

    // Mandar mensagem para o público errado não tem desfazer.
    await wrapper.setProps({ rule: makeRule({ pk: 99, name: "Outra" }) });
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.at(-1)).toEqual([
      { audience: {}, sku: "", productLabel: "" },
    ]);
  });

  it("diz que o consentimento manda, mesmo com público escolhido", () => {
    expect(panel().text()).toContain("consentimento");
  });

  it("avisa que a escolha não altera a campanha salva", () => {
    expect(panel().text()).toContain("A campanha continua como está");
  });
});

describe("FireCampaignPanel — conteúdo sob revisão", () => {
  it("não oferece corpo livre capaz de contornar a revisão", () => {
    const wrapper = panel();

    expect(wrapper.find("textarea").exists()).toBe(false);
    expect(wrapper.text()).toContain("Texto protegido pelo fluxo de revisão");
    expect(wrapper.text()).toContain("cria um anúncio para revisão");
  });

  it("pede o produto antes da senha quando o modelo depende do catálogo", async () => {
    const wrapper = mount(FireCampaignPanel, {
      props: {
        rule: makeRule(),
        priceTiers: TIERS,
        tags: TAGS,
        rfmSegments: SEGMENTS,
        products: PRODUCTS,
        productRequired: true,
      },
      global: {
        stubs: {
          Icon: true,
          UiNativeSelect: UiNativeSelectStub,
        },
      },
    });
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Produto desta ocorrência");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();

    await wrapper.get("#fire-product").setValue("MDL");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();
    await settleCount(wrapper);
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeUndefined();
    await wrapper.find("form").trigger("submit");

    expect(lastCountedSku).toBe("MDL");
    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { audience: {}, sku: "MDL", productLabel: "Madeleine (MDL)" },
    ]);
  });

  // O painel não tem mais tela de sucesso: o disparo bem-sucedido leva o gestor à
  // revisão, e uma escala que só oferecia "Revisar anúncio agora" não pode voltar.
  it("não guarda tela de sucesso nem link para a revisão", () => {
    const wrapper = mount(FireCampaignPanel, {
      props: {
        rule: makeRule(),
        priceTiers: TIERS,
        tags: TAGS,
        rfmSegments: SEGMENTS,
      },
      global: { stubs: { Icon: true, NuxtLink: true } },
    });

    expect(wrapper.text()).not.toContain("Anúncio criado para revisão");
    expect(wrapper.text()).not.toContain("Revisar anúncio agora");
    expect(wrapper.find("form").exists()).toBe(true);
  });
});

describe("FireCampaignPanel — postagem pública", () => {
  it("prepara um Story sem pedir ou contar destinatários diretos", async () => {
    counted = fakeCount({ total: 0, empty_selection: true });
    const wrapper = panel(
      makeRule({
        platforms: ["instagram"],
        audience_rules: {},
      }),
    );
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("1 postagem pública");
    expect(wrapper.text()).toContain("Não há seleção de contatos");
    expect(wrapper.text()).not.toContain("Para quem");
    expect(wrapper.text()).not.toContain("pessoas recebem");
    expect(lastCountedRules).toBeNull();
    const submit = wrapper.find('button[type="submit"]');
    expect(submit.text()).toContain("Revisar anúncio");
    expect(submit.attributes("disabled")).toBeUndefined();

    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { audience: {}, sku: "", productLabel: "" },
    ]);
  });

  it("mantém audiência zero bloqueada quando há também WhatsApp", async () => {
    counted = fakeCount({
      total: 0,
      parts: [{ label: "Faixa de preço", count: 0 }],
    });
    const wrapper = panel(makeRule({ platforms: ["instagram", "whatsapp"] }));
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Ninguém se encaixa neste público hoje");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();
  });
});

// ── O número, antes de enviar ────────────────────────────────────────
//
// ⚠️ Escolher público era escolher no escuro: o tamanho só aparecia depois do disparo,
// quando já não tem desfazer.

describe("FireCampaignPanel — quantas pessoas isto alcança", () => {
  it("mostra o tamanho do público enquanto se escolhe", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "Atacado")!.trigger("click");
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("pessoas recebem");
  });

  it("conta também o público salvo da campanha, que é o modo em que ela abre", async () => {
    const wrapper = panel();
    await settleCount(wrapper);

    expect(lastCountedRules).toEqual({ tags: ["clientes-da-casa"] });
  });

  it("diz que ninguém se encaixa, em vez de deixar um zero sem explicação", async () => {
    counted = fakeCount({
      total: 0,
      parts: [{ label: "Faixa de preço", count: 0 }],
    });
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    await wrapper.findAll("button[aria-pressed]")[0]!.trigger("click");
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Ninguém se encaixa neste público hoje");
  });

  it("bloqueia o disparo quando não consegue validar o público", async () => {
    const failing = vi.fn(async () => {
      throw new Error("offline");
    });
    Object.assign(globalThis, { $fetch: failing });
    const wrapper = panel();
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Não foi possível conferir o público");
    expect(wrapper.text()).toContain("O disparo está bloqueado");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();
    expect(wrapper.text()).toContain("Contar novamente");

    Object.assign(globalThis, {
      $fetch: vi.fn(
        async (_url: string, opts: { body?: Record<string, unknown> }) => {
          lastCountedRules = (opts?.body?.audience_rules ?? null) as Record<
            string,
            unknown
          > | null;
          return counted;
        },
      ),
    });
  });
});

describe("FireCampaignPanel — o zero diz qual zero é", () => {
  // ⚠️ O caso da Baguete Gergelim: o gestor favoritou o produto pelo celular, a campanha
  // "quem favoritou" contou 0 e a tela disse "ninguém se encaixa". A regra tinha achado
  // 1 pessoa; o envio a barrou por falta de confirmação de maioridade e de consentimento.
  it("mostra quem a regra achou e por que não recebe, mesmo com uma regra só", async () => {
    counted = fakeCount({
      total: 0,
      parts: [{ label: "Favoritaram o produto", count: 1 }],
      excluded_by_reason: { age_not_declared: 1 },
    });
    const wrapper = panel(makeRule({ audience_rules: { favorites: true } }), {
      products: PRODUCTS,
    });
    await wrapper.get("#fire-product").setValue("MDL");
    await settleCount(wrapper);

    const text = wrapper.text();
    expect(text).toContain("As regras acharam 1 pessoa, mas ela não pode receber");
    expect(text).toContain("Favoritaram o produto");
    expect(text).toContain("Ficam de fora");
    expect(text).toContain("1 pessoa sem confirmação de maioridade");
    expect(text).toContain("ele confirma ao entrar na loja de novo");
    expect(text).not.toContain("Ninguém se encaixa neste público hoje");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();
  });

  it("lista cada motivo quando há mais de um", async () => {
    counted = fakeCount({
      total: 0,
      parts: [{ label: "Favoritaram o produto", count: 2 }],
      excluded_by_reason: { age_not_declared: 1, missing_consent: 1 },
    });
    const wrapper = panel(makeRule({ audience_rules: { favorites: true } }), {
      products: PRODUCTS,
    });
    await wrapper.get("#fire-product").setValue("MDL");
    await settleCount(wrapper);

    const items = wrapper
      .findAll("[data-audience-exclusions] li")
      .map((li) => li.text());
    expect(items).toEqual([
      "1 pessoa sem confirmação de maioridade (feita ao entrar na loja)",
      "1 pessoa sem consentimento para receber no WhatsApp",
    ]);
    expect(wrapper.text()).toContain("As regras acharam 2 pessoas, mas nenhuma pode receber");
  });

  it("continua dizendo 'ninguém se encaixa' quando a regra não achou ninguém", async () => {
    counted = fakeCount({
      total: 0,
      parts: [{ label: "Favoritaram o produto", count: 0 }],
    });
    const wrapper = panel(makeRule({ audience_rules: { favorites: true } }), {
      products: PRODUCTS,
    });
    await wrapper.get("#fire-product").setValue("MDL");
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Ninguém se encaixa neste público hoje");
    expect(wrapper.find("[data-audience-exclusions]").exists()).toBe(false);
  });

  it("mostra quem ficou de fora também quando alguém recebe", async () => {
    counted = fakeCount({
      total: 3,
      parts: [{ label: "Etiquetas", count: 5 }],
      excluded_by_reason: { missing_consent: 2 },
    });
    const wrapper = panel();
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("pessoas recebem");
    expect(wrapper.text()).toContain("2 pessoas sem consentimento para receber no WhatsApp");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeUndefined();
  });

  it("bloqueia o disparo quando o servidor diz que o número está incompleto", async () => {
    counted = fakeCount({
      total: 7,
      can_approve: false,
      blocked_reason:
        "Não foi possível conferir todas as fontes da audiência. Aguarde a recuperação.",
      degraded_sources: ["favorites"],
    });
    const wrapper = panel();
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Não foi possível conferir todas as fontes da audiência");
    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();
  });
});

describe("FireCampaignPanel — becos sem saída", () => {
  it("campanha sem público salvo abre em 'Escolher agora' e diz por quê", async () => {
    const wrapper = panel(makeRule({ audience_rules: {} }));
    await settleCount(wrapper);

    const radios = wrapper.findAll('input[name="audience-mode"]');
    expect((radios[0]!.element as HTMLInputElement).checked).toBe(false);
    expect((radios[1]!.element as HTMLInputElement).checked).toBe(true);
    expect(wrapper.text()).toContain("Esta campanha não tem público salvo");
    expect(wrapper.text()).toContain("Escolha pelo menos um grupo acima");
  });

  it("só 'VIP primeiro' salvo não é público: continua abrindo em 'Escolher agora'", async () => {
    const wrapper = panel(
      makeRule({ audience_rules: { vip_first_minutes: 15 } }),
    );
    await settleCount(wrapper);

    const radios = wrapper.findAll('input[name="audience-mode"]');
    expect((radios[1]!.element as HTMLInputElement).checked).toBe(true);
  });

  it("com público salvo, nada disso aparece", async () => {
    const wrapper = panel();
    await settleCount(wrapper);

    expect(wrapper.text()).not.toContain("Esta campanha não tem público salvo");
    expect(wrapper.text()).not.toContain("Escolha pelo menos um grupo acima");
  });
});

describe("FireCampaignPanel — somar ou cruzar as regras", () => {
  /** Duas regras escolhidas: é o mínimo para a combinação querer dizer algo. */
  async function twoRulesChosen() {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "Atacado")!.trigger("click");
    await chips.find((c) => c.text() === "Em risco")!.trigger("click");
    return wrapper;
  }

  it("não oferece a escolha com uma regra só, onde ela não significaria nada", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    await wrapper.findAll("button[aria-pressed]")[0]!.trigger("click");

    expect(wrapper.text()).not.toContain("Qualquer uma");
  });

  it("oferece somar ou cruzar quando há mais de uma regra", async () => {
    const wrapper = await twoRulesChosen();

    expect(wrapper.text()).toContain("Qualquer uma");
    expect(wrapper.text()).toContain("Todas");
  });

  it("soma por padrão — o comportamento de sempre", async () => {
    const wrapper = await twoRulesChosen();
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")!.at(-1) as [
      { audience: AudienceCount },
    ];
    expect(payload.audience).not.toHaveProperty("match");
  });

  it("manda `match: all` ao escolher 'Todas' — o recorte que a união não sabe fazer", async () => {
    const wrapper = await twoRulesChosen();
    const modes = wrapper.findAll("button[aria-pressed]");
    await modes.find((m) => m.text().includes("Todas"))!.trigger("click");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")!.at(-1) as [
      {
        audience: {
          match?: string;
          groups?: string[];
          rfm_segments?: string[];
        };
      },
    ];
    expect(payload.audience.match).toBe("all");
    expect(payload.audience.price_tiers).toEqual(["atacado"]);
    expect(payload.audience.rfm_segments).toEqual(["at_risk"]);
  });

  it("trocar de campanha volta a somar, sem herdar o cruzamento anterior", async () => {
    const wrapper = await twoRulesChosen();
    const modes = wrapper.findAll("button[aria-pressed]");
    await modes.find((m) => m.text().includes("Todas"))!.trigger("click");

    await wrapper.setProps({ rule: makeRule({ pk: 77, name: "Outra" }) });
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.at(-1)).toEqual([
      { audience: {}, sku: "", productLabel: "" },
    ]);
  });
});

// ── Etiquetas: o público que o operador monta sozinho ────────────────

describe("FireCampaignPanel — etiquetas", () => {
  /** As opções só existem em "Escolher agora" — no modo salvo, quem manda é a campanha. */
  async function chooseNow() {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    return wrapper;
  }

  it("oferece as etiquetas que existem, com quantas pessoas cada uma tem", async () => {
    // A contagem no rótulo evita o erro mais comum: etiqueta criada e nunca usada.
    expect((await chooseNow()).text()).toContain("corredores (3)");
  });

  it("manda os slugs escolhidos no vocabulário do backend", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "corredores (3)")!.trigger("click");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")!.at(-1) as [
      { audience: { tags?: string[] } },
    ];
    expect(payload.audience.tags).toEqual(["corredores"]);
  });

  it("diz de quem é o trabalho de etiquetar, para o gestor não procurar aqui", async () => {
    expect((await chooseNow()).text()).toContain("Quem etiqueta é quem atende");
  });

  it("etiqueta sozinha habilita o disparo só depois da contagem segura", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "corredores (3)")!.trigger("click");

    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeDefined();
    await settleCount(wrapper);

    expect(
      wrapper.find('button[type="submit"]').attributes("disabled"),
    ).toBeUndefined();
  });

  it("etiqueta conta como regra na hora de somar ou cruzar", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "corredores (3)")!.trigger("click");
    expect(wrapper.text()).not.toContain("Qualquer uma");

    await chips.find((c) => c.text() === "Atacado")!.trigger("click");
    expect(wrapper.text()).toContain("Qualquer uma");
  });
});
