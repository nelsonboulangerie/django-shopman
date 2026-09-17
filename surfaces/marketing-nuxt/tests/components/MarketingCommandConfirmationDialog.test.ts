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
    // Uma linha por plataforma: diz que a postagem é por plataforma e que ela não
    // fala com ninguém em particular, sem obrigar ninguém a distribuir um "em cada".
    expect(wrapper.text()).toContain("Instagram · 1 postagem");
  });

  it("mostra O QUE vai sair antes de pedir a confirmação sem volta", () => {
    // A caixa contava PARA QUEM e ONDE, e nunca O QUÊ. O gestor autorizava um texto
    // que não estava vendo em lugar nenhum da tela — e é dele que não tem desfazer.
    // A prévia sai do corpo CONGELADO do comando, não do anúncio na tela: é o que o
    // servidor vai publicar, sem uma edição posterior que não foi selada.
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: {
            base_version: 3,
            publish_mode: "now",
            body: "Fornada saiu do forno. Reserve pelo site.",
            hashtags: ["padaria", "fornada"],
          },
          href: "/api/v1/backstage/marketing/announcements/42/approve/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge-outgoing",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "summary",
            step_up: "none",
            dual_control: false,
            typed_phrase: "",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 12,
            platforms: ["whatsapp"],
            scheduled_for: null,
          },
        },
        shopTimezone: "America/Sao_Paulo",
        imageUrl: "/media/fornada.jpg",
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

    expect(wrapper.text()).toContain("Fornada saiu do forno. Reserve pelo site.");
    expect(wrapper.text()).toContain("#padaria #fornada");
    expect(wrapper.find("img").attributes("src")).toBe("/media/fornada.jpg");
  });

  it("avisa que a postagem vai sair sem foto, antes e não depois", () => {
    // Postagem sem imagem no Instagram só se descobre publicada, quando já não tem
    // conserto. Se o disparo tem mural e o anúncio não tem foto, a caixa diz aqui.
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: { base_version: 3, publish_mode: "now", body: "Fornada." },
          href: "/api/v1/backstage/marketing/announcements/42/approve/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge-no-image",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "summary",
            step_up: "none",
            dual_control: false,
            typed_phrase: "",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 0,
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

    expect(wrapper.text()).toContain("Sem foto");
    expect(wrapper.find("img").exists()).toBe(false);
  });

  it("não inventa alarme de foto quando só vai mensagem", () => {
    // WhatsApp sem imagem é normal; o aviso é sobre mural, não sobre tudo.
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: { base_version: 3, publish_mode: "now", body: "Fornada." },
          href: "/api/v1/backstage/marketing/announcements/42/approve/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge-message-only",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "summary",
            step_up: "none",
            dual_control: false,
            typed_phrase: "",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 4,
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

    expect(wrapper.text()).not.toContain("Sem foto");
    expect(wrapper.text()).toContain("WhatsApp · 4 pessoas");
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

    // WhatsApp sozinho é envio, e o botão diz o verbo do ato. "Disparar" fica para
    // o anúncio que faz as duas coisas, onde não existe verbo específico.
    expect(wrapper.text()).toContain("Enviar agora");
    expect(wrapper.text()).not.toContain("Confirmar consequência");
    expect(wrapper.text()).toContain("Depois de confirmar, não tem desfazer");
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

    expect(wrapper.text()).toContain("Criar para revisão?");
    expect(wrapper.text()).toContain("Nada sai agora; vai para revisão");
    expect(wrapper.text()).toContain("Madeleine (MDL)");
    expect(wrapper.text()).toContain("Criar para revisão");
    expect(wrapper.text()).toContain("Voltar sem criar");
    expect(wrapper.text()).toContain("WhatsApp · 12 pessoas");
    expect(wrapper.text()).toContain("Instagram · 1 postagem");
  });
});
