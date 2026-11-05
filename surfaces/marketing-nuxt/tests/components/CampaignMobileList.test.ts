import { mount } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import CampaignMobileList from "~/components/CampaignMobileList.vue";
import type { Campaign } from "~/types/campaign";

beforeAll(() => Object.assign(globalThis, { computed, ref }));

function campaign(over: Partial<Campaign> = {}): Campaign {
  return {
    pk: 4,
    version: 1,
    name: "Lote pronto",
    trigger: "production_finished",
    trigger_label: "Produção concluída",
    trigger_filter: {},
    template_id: 1,
    template_name: "Lote",
    platforms: ["instagram", "whatsapp"],
    audience_rules: {},
    exclusive_price_tiers: [],
    promotion_ref: "",
    schedule: {} as Campaign["schedule"],
    schedule_label: "",
    fires_on_its_own: false,
    sent_count: 0,
    reached_total: 0,
    failed_count: 0,
    last_failure: "",
    exhausted: false,
    requires_approval: true,
    expires_after_minutes: 60,
    is_active: true,
    updated_at: "2026-11-05T07:00:00-03:00",
    ...over,
  };
}

function render(fire = { enabled: false, reason: "Seu perfil não autoriza disparos manuais." }) {
  return mount(CampaignMobileList, {
    props: {
      rules: [campaign()],
      platformLabels: { instagram: "Instagram", whatsapp: "WhatsApp" },
      createdPk: null,
      mutatingCampaignPk: null,
      editState: () => ({ enabled: true, reason: "" }),
      fireState: () => fire,
      rowMenu: () => [],
      triggerWhen: () => "Quando um lote termina",
    },
    global: { stubs: { Icon: true, OperatorMoreMenu: { template: "<button data-more />" } } },
  });
}

describe("CampaignMobileList (ge:MKT-14)", () => {
  it("cada campanha é um cartão com gatilho, destinos por extenso e a chave à vista", async () => {
    const wrapper = render();
    const card = wrapper.get('[data-campaign-card="4"]');

    expect(card.get("[data-campaign-card-trigger]").text()).toBe(
      "Produção concluída · Quando um lote termina",
    );
    expect(card.get("[data-campaign-card-platforms]").text()).toBe("Instagram, WhatsApp");
    expect(card.find('[role="switch"]').exists()).toBe(true);
    expect(card.find("[data-more]").exists()).toBe(true);

    await card.get('[role="switch"]').trigger("click");
    expect(wrapper.emitted("toggle")?.[0]?.[0]).toMatchObject({ pk: 4 });
  });

  it("sem permissão de disparo, não oferece o botão e diz o porquê por extenso", () => {
    const wrapper = render();
    expect(wrapper.find("[data-campaign-card-fire]").exists()).toBe(false);
    expect(wrapper.get("[data-campaign-card-reasons]").text()).toBe(
      "Seu perfil não autoriza disparos manuais.",
    );
  });

  it("com permissão, 'Preparar disparo' abre o painel", async () => {
    const wrapper = render({ enabled: true, reason: "" });
    await wrapper.get("[data-campaign-card-fire]").trigger("click");
    expect(wrapper.emitted("fire")?.[0]?.[0]).toMatchObject({ pk: 4 });
  });

});
