import { mount } from "@vue/test-utils";
import { computed, defineComponent, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import MarketingCommandConfirmationDialog from "~/components/MarketingCommandConfirmationDialog.vue";

const SlotStub = defineComponent({ template: "<div><slot /></div>" });
// A prévia em tamanho real é sobreposição: aqui ela vira um dublê que só publica os
// retratos que recebeu, para que o teste possa dizer DE ONDE eles saíram.
const simulatedPreviewScenes: unknown[][] = [];
const SimulatedPreviewStub = defineComponent({
  props: { scenes: { type: Array, default: () => [] } },
  setup(props) {
    simulatedPreviewScenes.push(props.scenes);
    return () => null;
  },
});
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
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
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
            body: "O lote saiu do forno. Reserve pelo site.",
            hashtags: ["padaria", "lote"],
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
        imageUrl: "/media/lote.jpg",
      },
      global: {
        stubs: {
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    expect(wrapper.text()).toContain("O lote saiu do forno. Reserve pelo site.");
    expect(wrapper.text()).toContain("#padaria #lote");
    expect(wrapper.find("img").attributes("src")).toBe("/media/lote.jpg");
  });

  it("avisa que a postagem vai sair sem foto, antes e não depois", () => {
    // Postagem sem imagem no Instagram só se descobre publicada, quando já não tem
    // conserto. Se o disparo tem mural e o anúncio não tem foto, a caixa diz aqui.
    const wrapper = mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: { base_version: 3, publish_mode: "now", body: "Lote." },
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
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
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
          body: { base_version: 3, publish_mode: "now", body: "Lote." },
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
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
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
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
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
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
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
    expect(wrapper.text()).toContain(
      "Nada é disparado agora. O anúncio vai para revisão",
    );
    expect(wrapper.text()).toContain("Madeleine (MDL)");
    expect(wrapper.text()).toContain("Criar para revisão");
    expect(wrapper.text()).toContain("Voltar sem criar");
    expect(wrapper.text()).toContain("WhatsApp · 12 pessoas");
    expect(wrapper.text()).toContain("Instagram · 1 postagem");
  });
  // ⚠️ `dual_control` deixa o confirmar morto PARA SEMPRE nesta caixa. O texto antigo
  // explicava o desenho do gate — "a confirmação independente continua obrigatória;
  // esta sessão não substitui o segundo controle" — e deixava o gestor com um botão
  // apagado e nenhuma frase que resolvesse. Botão morto sem saída é defeito desta casa.
  it("com duas pessoas obrigatórias, diz o gesto e troca o botão morto por uma saída", () => {
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
            step_up: "none",
            dual_control: true,
            typed_phrase: "",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 4000,
            platforms: ["whatsapp"],
            scheduled_for: null,
          },
        },
        shopTimezone: "America/Sao_Paulo",
      },
      global: {
        stubs: {
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    expect(wrapper.text()).toContain("Este disparo precisa de duas pessoas.");
    expect(wrapper.text()).toContain(
      "Peça a outra pessoa com acesso ao Marketing para abrir este mesmo anúncio e confirmar.",
    );
    // A explicação do gate sai: ela não terminava em gesto nenhum.
    expect(wrapper.text()).not.toMatch(/segundo controle|volume exige/);

    const buttons = wrapper.findAll("button");
    expect(buttons.map((button) => button.text())).toContain("Entendi");
    // E o botão que nunca ligaria não fica na tela para ser tentado.
    expect(buttons.map((button) => button.text())).not.toContain("Enviar agora");
  });

  it("a prévia em tamanho real sai do corpo CONGELADO, e o formato vem do anúncio", () => {
    // ⚠️ A diferença que este teste guarda: na caixa de confirmação o retrato grande NÃO
    // pode sair do anúncio na tela. O que o servidor vai publicar é o corpo selado no
    // desafio; uma edição posterior mostraria ao gestor algo que não vai acontecer.
    // Formato e foto vêm do anúncio porque não são editáveis no card e não viajam no
    // corpo do comando.
    simulatedPreviewScenes.length = 0;
    mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "approve",
          body: {
            base_version: 3,
            publish_mode: "now",
            body: "Texto selado no comando",
            hashtags: ["padaria"],
          },
          href: "/api/v1/backstage/marketing/announcements/42/approve/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge-simulated",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "summary",
            step_up: "none",
            dual_control: false,
            typed_phrase: "",
            consequence: "publishes_now_to_eligible_audience",
            resource_ref: "announcement:42",
            base_version: 3,
            audience_count: 12,
            platforms: ["instagram", "whatsapp"],
            scheduled_for: null,
          },
        },
        shopTimezone: "America/Sao_Paulo",
        imageUrl: "/media/lote.jpg",
        platformContent: {
          instagram: {
            publication_format: "story",
            image_url: "/media/vertical.jpg",
          },
          whatsapp: {},
        },
      },
      global: {
        stubs: {
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    const scenes = simulatedPreviewScenes.at(-1) as Array<{
      kind: string;
      label: string;
      body: string;
      imageUrl: string;
    }>;
    expect(scenes.map((scene) => scene.label)).toEqual([
      "Story no Instagram",
      "Mensagem no WhatsApp",
    ]);
    expect(scenes.map((scene) => scene.body)).toEqual([
      "Texto selado no comando",
      "Texto selado no comando",
    ]);
    expect(scenes.map((scene) => scene.imageUrl)).toEqual([
      "/media/vertical.jpg",
      "/media/lote.jpg",
    ]);
  });

  it("recusar não abre prévia de um anúncio que não vai a lugar nenhum", () => {
    simulatedPreviewScenes.length = 0;
    mount(MarketingCommandConfirmationDialog, {
      props: {
        command: {
          announcementId: 42,
          action: "reject",
          body: { base_version: 3, body: "Texto recusado" },
          href: "/api/v1/backstage/marketing/announcements/42/reject/",
          ownerRef: "operator:1",
          idempotencyKey: "key",
          challenge: {
            token: "token",
            ref: "challenge-reject",
            expires_at: "2026-09-09T21:00:00-03:00",
            mode: "summary",
            step_up: "none",
            dual_control: false,
            typed_phrase: "",
            consequence: "rejects_announcement",
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
          AnnouncementSimulatedPreview: SimulatedPreviewStub,
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    expect(simulatedPreviewScenes.at(-1)).toEqual([]);
  });
});
