import { mount } from "@vue/test-utils";
import { computed, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import FireCampaignPanel from "~/components/FireCampaignPanel.vue";
import type { Campaign } from "~/types/campaign";

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
});

const GROUPS = [
  { value: "varejo", label: "Varejo" },
  { value: "corporativo", label: "Corporativo" },
];
const SEGMENTS = [
  { value: "champion", label: "campeão" },
  { value: "at_risk", label: "em risco" },
];

function makeRule(over: Partial<Campaign> = {}): Campaign {
  return {
    pk: 3,
    name: "Novidade da semana",
    trigger: "manual",
    trigger_label: "disparo manual",
    platforms: ["whatsapp"],
    audience_rules: { favorites: true },
    requires_approval: true,
    is_active: true,
    ...over,
  } as Campaign;
}

function panel(rule: Campaign | null = makeRule()) {
  return mount(FireCampaignPanel, {
    props: { rule, customerGroups: GROUPS, rfmSegments: SEGMENTS },
    global: { stubs: { Icon: true } },
    globalProperties: {},
  });
}

describe("FireCampaignPanel — disparar agora", () => {
  it("começa no público da campanha, que é o caminho seguro", async () => {
    const wrapper = panel();
    await wrapper.find("form").trigger("submit");

    // Objeto vazio = usa o público salvo. A campanha não é alterada.
    expect(wrapper.emitted("submit")?.[0]).toEqual([{}]);
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

    // "Corporativo" e "em risco" — o gestor clica em frases, não em chaves.
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "Corporativo")!.trigger("click");
    await chips.find((c) => c.text() === "em risco")!.trigger("click");
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { groups: ["corporativo"], rfm_segments: ["at_risk"] },
    ]);
  });

  it("traduz 'quem está sumindo' para o piso de risco que o resolvedor entende", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    await wrapper.findAll('input[type="checkbox"]')[0]!.setValue(true);
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([{ churn_risk_min: 0.7 }]);
  });

  it("aniversariantes e VIP-primeiro convivem no mesmo disparo", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const boxes = wrapper.findAll('input[type="checkbox"]');
    await boxes[1]!.setValue(true); // aniversariantes
    await boxes[2]!.setValue(true); // VIP primeiro
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]).toEqual([
      { birthday_today: true, vip_first_minutes: 15 },
    ]);
  });

  it("trocar de campanha zera a escolha anterior", async () => {
    const wrapper = panel();
    await wrapper.findAll('input[name="audience-mode"]')[1]!.setValue();
    const chips = wrapper.findAll("button[aria-pressed]");
    await chips.find((c) => c.text() === "Corporativo")!.trigger("click");

    // Mandar mensagem para o público errado não tem desfazer.
    await wrapper.setProps({ rule: makeRule({ pk: 99, name: "Outra" }) });
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("submit")?.at(-1)).toEqual([{}]);
  });

  it("diz que o consentimento manda, mesmo com público escolhido", () => {
    expect(panel().text()).toContain("consentimento");
  });

  it("avisa que a escolha não altera a campanha salva", () => {
    expect(panel().text()).toContain("A campanha continua como está");
  });
});
