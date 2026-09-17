import { mount } from "@vue/test-utils";
import { computed, defineComponent, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import MarketingCommandConfirmationDialog from "~/components/MarketingCommandConfirmationDialog.vue";

const SlotStub = defineComponent({ template: "<div><slot /></div>" });
const DialogStub = defineComponent({
  props: { open: Boolean },
  template: '<div v-if="open"><slot /></div>',
});

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    ref,
    watch,
    useNuxtData: () => ({
      data: ref({ operator: { username: "admin", name: "Admin" } }),
    }),
  });
});

describe("MarketingCommandConfirmationDialog", () => {
  it("gives the password manager an explicit username without exposing the phrase field", () => {
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: { base_version: 3, publish_mode: "now" },
          href: "/api/v1/backstage/marketing/announcements/42/approve/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "typed",
            step_up: "password",
            dual_control: false,
            typed_phrase: "PUBLICAR 12",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 12,
            platforms: ["instagram"],
            scheduled_for: null,
          },
        },
        shopTimezone: "America/Sao_Paulo",
      },
      global: {
        stubs: {
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    const username = wrapper.find("#decision-username");
    expect((username.element as HTMLInputElement).value).toBe("admin");
    expect(username.attributes("autocomplete")).toBe("username");
    expect(username.attributes("readonly")).toBeDefined();
    expect(
      wrapper.find("#decision-credential").attributes("autocomplete"),
    ).toBe("current-password");
    expect(wrapper.find("#decision-typed-confirmation").element.tagName).toBe(
      "TEXTAREA",
    );
    expect(wrapper.text()).toContain("Público geral da plataforma");
    expect(wrapper.text()).toContain("uma postagem pública por plataforma");
    expect(wrapper.text()).toContain("não envia mensagem direta por pessoa");
  });

  it("chama o efeito pelo nome, em vez de pedir para confirmar uma consequência", () => {
    // "Confirmar consequência" obrigava o gestor a traduzir jargão no exato momento
    // da decisão, e a caixa dizia "nada sai até a confirmação final" logo acima do
    // botão que ERA a confirmação final. Duas frases que não descreviam a tela.
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: { base_version: 3, publish_mode: "now" },
          href: "/api/v1/backstage/marketing/announcements/42/approve/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge-summary",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "summary",
            step_up: "none",
            dual_control: false,
            typed_phrase: "",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 1,
            platforms: ["whatsapp"],
            scheduled_for: null,
          },
        },
        shopTimezone: "America/Sao_Paulo",
      },
      global: {
        stubs: {
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    expect(wrapper.text()).toContain("Enviar agora");
    expect(wrapper.text()).not.toContain("Confirmar consequência");
    expect(wrapper.text()).toContain("Depois de confirmar, isto sai");
    // Nada de senha nem de frase: um destino não paga o preço de quinhentos.
    expect(wrapper.find("#decision-credential").exists()).toBe(false);
    expect(wrapper.find("#decision-typed-confirmation").exists()).toBe(false);
  });

  it("explica que confirmar o disparo cria revisão sem publicar", () => {
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          campaignId: 3,
          action: "fire",
          body: { base_version: 1 },
          href: "/api/v1/backstage/marketing/rules/3/fire/",
          fingerprint: "campaign-3-v1",
          idempotencyKey: "fire-key",
          productLabel: "Madeleine (MDL)",
          challenge: {
            token: "token",
            ref: "challenge",
            expires_at: "2026-09-10T11:05:00-03:00",
            mode: "typed",
            step_up: "password",
            dual_control: false,
            typed_phrase: "PREPARAR 12",
            consequence: "creates_review_announcement",
            resource_ref: "campaign:3",
            base_version: 1,
            audience_count: 12,
            platforms: ["instagram", "whatsapp"],
            scheduled_for: null,
          },
        },
        shopTimezone: "America/Sao_Paulo",
      },
      global: {
        stubs: {
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    expect(wrapper.text()).toContain("Confirmar este disparo?");
    expect(wrapper.text()).toContain("Isto cria um anúncio para revisão");
    expect(wrapper.text()).toContain("Nada é publicado nem enviado agora");
    expect(wrapper.text()).toContain("Madeleine (MDL)");
    expect(wrapper.text()).toContain("Criar para revisão");
    expect(wrapper.text()).toContain("Voltar sem criar");
    expect(wrapper.text()).toContain("Pessoas para mensagem direta");
    expect(wrapper.text()).toContain("12 pessoas");
    expect(wrapper.text()).toContain("uma postagem pública por plataforma");
    expect(wrapper.text()).toContain("WhatsApp:");
    expect(wrapper.text()).toContain("consentimento revalidado");
  });
});
