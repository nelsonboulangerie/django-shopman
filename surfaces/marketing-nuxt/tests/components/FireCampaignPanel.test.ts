import { mount } from "@vue/test-utils";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAudienceCount } from "~/composables/useAudienceCount";
import FireCampaignPanel from "~/components/FireCampaignPanel.vue";
import type { AudienceCount, Campaign } from "~/types/campaign";

/** O que a contagem do servidor devolveu por último — o teste inspeciona e controla. */
let counted: AudienceCount;
/** As regras que o painel MANDOU contar. É por aqui que se prova o `match`. */
let lastCountedRules: Record<string, unknown> | null = null;

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
    ...over,
  };
}

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
//
// A contagem entra com o composable REAL — só o `$fetch` é falso. Ele carrega o debounce e
// o descarte de resposta velha, e um stub aqui deixaria justamente essa parte sem teste.
beforeAll(() => {
  Object.assign(globalThis, {
    computed, ref, watch, onBeforeUnmount, useAudienceCount,
    $fetch: vi.fn(async (_url: string, opts: { body?: Record<string, unknown> }) => {
      lastCountedRules = (opts?.body?.audience_rules ?? null) as Record<string, unknown> | null;
      return counted;
    }),
  });
});

beforeEach(() => {
  counted = fakeCount();
  lastCountedRules = null;
  vi.useFakeTimers();
});

/** Passa o debounce da contagem e deixa o Vue redesenhar. */
async function settleCount(wrapper: { vm: { $nextTick: () => Promise<void> } }) {
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

function makeRule(over: Partial<Campaign> = {}): Campaign {
  return {
    pk: 3,
    name: "Novidade da semana",
    trigger: "manual",
    trigger_label: "Disparo manual",
    platforms: ["whatsapp"],
    audience_rules: { favorites: true },
    requires_approval: true,
    is_active: true,
    ...over,
  } as Campaign;
}

function panel(rule: Campaign | null = makeRule()) {
  return mount(FireCampaignPanel, {
    props: { rule, priceTiers: TIERS, tags: TAGS, rfmSegments: SEGMENTS },
    global: { stubs: { Icon: true } },
    globalProperties: {},
  });
}

describe("FireCampaignPanel — disparar agora", () => {
  it("começa no público da campanha, que é o caminho seguro", async () => {
    const wrapper = panel();
    await wrapper.find("form").trigger("submit");

    // Objeto vazio = usa o público salvo. A campanha não é alterada.
    expect(wrapper.emitted("submit")?.[0]).toEqual([{ body: "", audience: {} }]);
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
      { body: "", audience: { price_tiers: ["atacado"], rfm_segments: ["at_risk"] } },
    ]);
  });

  it("traduz 'quem está sumindo' para o piso de risco que o resolvedor entende", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    await wrapper.findAll('input[type="checkbox"]')[0]!.setValue(true);
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { body: "", audience: { churn_risk_min: 0.7 } },
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
      { body: "", audience: { birthday_today: true, vip_first_minutes: 15 } },
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

    expect(wrapper.emitted("submit")?.at(-1)).toEqual([{ body: "", audience: {} }]);
  });

  it("diz que o consentimento manda, mesmo com público escolhido", () => {
    expect(panel().text()).toContain("consentimento");
  });

  it("avisa que a escolha não altera a campanha salva", () => {
    expect(panel().text()).toContain("A campanha continua como está");
  });
});

describe("FireCampaignPanel — o texto escrito na hora", () => {
  it("manda o texto que o gestor escreveu", async () => {
    const wrapper = panel();

    await wrapper.find("#fire-body").setValue("Fornada extra às 16h.");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [{ body: string }];
    expect(payload.body).toBe("Fornada extra às 16h.");
  });

  it("texto só de espaços conta como vazio", async () => {
    // ⚠️ Senão " " publicaria direto uma mensagem em branco, sem ninguém revisar.
    const wrapper = panel();

    await wrapper.find("#fire-body").setValue("   ");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")![0] as [{ body: string }];
    expect(payload.body).toBe("");
  });

  it("diz que escrever publica direto, e que em branco vai para revisão", async () => {
    const wrapper = panel();
    expect(wrapper.text()).toContain("nasce para você revisar");

    await wrapper.find("#fire-body").setValue("Fornada extra às 16h.");

    expect(wrapper.text()).toContain("Publica direto");
  });

  it("trocar de campanha zera o texto anterior", async () => {
    // Mandar o texto de uma campanha no disparo de outra não tem desfazer.
    const wrapper = panel();
    await wrapper.find("#fire-body").setValue("Texto da campanha antiga");

    await wrapper.setProps({ rule: makeRule({ pk: 99, name: "Outra" }) });
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")!.at(-1) as [{ body: string }];
    expect(payload.body).toBe("");
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

    expect(lastCountedRules).toEqual({ favorites: true });
  });

  it("diz que ninguém se encaixa, em vez de deixar um zero sem explicação", async () => {
    counted = fakeCount({ total: 0 });
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    await wrapper.findAll("button[aria-pressed]")[0]!.trigger("click");
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Ninguém se encaixa neste público hoje");
  });

  it("cala o número quando a contagem falha, em vez de mostrar um zero que mentiria", async () => {
    const failing = vi.fn(async () => { throw new Error("offline"); });
    Object.assign(globalThis, { $fetch: failing });
    const wrapper = panel();
    await settleCount(wrapper);

    expect(wrapper.text()).toContain("Não foi possível contar agora");
    expect(wrapper.text()).toContain("O disparo continua valendo");

    Object.assign(globalThis, {
      $fetch: vi.fn(async (_url: string, opts: { body?: Record<string, unknown> }) => {
        lastCountedRules = (opts?.body?.audience_rules ?? null) as Record<string, unknown> | null;
        return counted;
      }),
    });
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

    const [payload] = wrapper.emitted("submit")!.at(-1) as [{ audience: AudienceCount }];
    expect(payload.audience).not.toHaveProperty("match");
  });

  it("manda `match: all` ao escolher 'Todas' — o recorte que a união não sabe fazer", async () => {
    const wrapper = await twoRulesChosen();
    const modes = wrapper.findAll("button[aria-pressed]");
    await modes.find((m) => m.text().includes("Todas"))!.trigger("click");
    await wrapper.find("form").trigger("submit");

    const [payload] = wrapper.emitted("submit")!.at(-1) as [
      { audience: { match?: string; groups?: string[]; rfm_segments?: string[] } },
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

    expect(wrapper.emitted("submit")?.at(-1)).toEqual([{ body: "", audience: {} }]);
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

    const [payload] = wrapper.emitted("submit")!.at(-1) as [{ audience: { tags?: string[] } }];
    expect(payload.audience.tags).toEqual(["corredores"]);
  });

  it("diz de quem é o trabalho de etiquetar, para o gestor não procurar aqui", async () => {
    expect((await chooseNow()).text()).toContain("Quem etiqueta é quem atende");
  });

  it("etiqueta sozinha já habilita o disparo", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "corredores (3)")!.trigger("click");

    expect(wrapper.find('button[type="submit"]').attributes("disabled")).toBeUndefined();
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
