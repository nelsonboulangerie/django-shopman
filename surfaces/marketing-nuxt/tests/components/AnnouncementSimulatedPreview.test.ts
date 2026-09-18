// O botão do olho e a sobreposição que ele abre.
//
// Botão só com ícone e sem nome acessível já foi defeito real deste app; aqui ele é
// medido, não prometido.
import { mount } from "@vue/test-utils";
import { computed, defineComponent, h, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import AnnouncementSimulatedPreview from "~/components/AnnouncementSimulatedPreview.vue";
import { simulatedScenes } from "~/presentation/simulatedPreview";

const SlotStub = defineComponent({ template: "<div><slot /></div>" });
// O dublê global de UiButton declara `variant` mas não `size`. Este devolve o tamanho
// pedido, para que o teste possa dizer QUAL variante foi escolhida. Os pixels são de
// `Ui/Button.vue`, onde `icon` vale `size-11` — 44px.
const SizedButtonStub = defineComponent({
  inheritAttrs: false,
  props: { size: { type: String, default: "default" } },
  setup(props, { attrs, slots }) {
    return () =>
      h(
        "button",
        { ...attrs, type: "button", "data-size": props.size },
        slots.default?.(),
      );
  },
});
// O `UiDialog` real é o DialogRoot da reka-ui, que segura o `open`. O dublê guarda o
// mesmo contrato de v-model e monta o conteúdo só quando está aberto.
const DialogStub = defineComponent({
  props: { open: Boolean },
  emits: ["update:open"],
  template: `
    <div>
      <div @click="$emit('update:open', true)"><slot name="default" /></div>
    </div>
  `,
});

beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
});

function content(over: Record<string, unknown> = {}) {
  return {
    body: "Pães de fermentação natural saíram do forno.",
    hashtags: ["#padaria"],
    imageUrl: "https://example.invalid/pao.jpg",
    link: "",
    ...over,
  } as { body: string; hashtags: string[]; imageUrl: string; link: string };
}

function mountPreview(scenes: ReturnType<typeof simulatedScenes>) {
  return mount(AnnouncementSimulatedPreview, {
    props: { scenes },
    global: {
      stubs: {
        UiButton: SizedButtonStub,
        UiDialog: DialogStub,
        UiDialogTrigger: SlotStub,
        UiDialogContent: SlotStub,
        UiDialogHeader: SlotStub,
        UiDialogTitle: SlotStub,
        UiDialogDescription: SlotStub,
        UiDialogClose: SlotStub,
        Icon: true,
      },
    },
  });
}

describe("AnnouncementSimulatedPreview", () => {
  it("o botão só de ícone tem nome de verdade e alvo de toque de 44px", () => {
    const wrapper = mountPreview(
      simulatedScenes([
        {
          platform: "instagram",
          platformLabel: "Instagram",
          publicationFormat: "story",
          content: content(),
        },
      ]),
    );

    const trigger = wrapper.get('[data-testid="open-simulated-preview"]');
    expect(trigger.attributes("aria-label")).toBe(
      "Ver a prévia em tamanho real",
    );
    // `icon` é `size-11` em `Ui/Button.vue`: 44px, o alvo de toque da casa.
    expect(trigger.attributes("data-size")).toBe("icon");
  });

  it("sem retrato nenhum, o olho não aparece", () => {
    const wrapper = mountPreview([]);
    expect(wrapper.find('[data-testid="open-simulated-preview"]').exists()).toBe(
      false,
    );
  });

  it("um botão por formato, e a aba diz qual está aberta", async () => {
    const shared = content();
    const wrapper = mountPreview(
      simulatedScenes([
        {
          platform: "instagram",
          platformLabel: "Instagram",
          publicationFormat: "story",
          content: shared,
        },
        {
          platform: "facebook",
          platformLabel: "Facebook",
          publicationFormat: "feed",
          content: shared,
        },
        {
          platform: "whatsapp",
          platformLabel: "WhatsApp",
          publicationFormat: "",
          content: shared,
        },
      ]),
    );

    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs.map((tab) => tab.text())).toEqual([
      "Story no Instagram",
      "Feed no Facebook",
      "Mensagem no WhatsApp",
    ]);
    // Duas colunas iguais; o ímpar que sobra ocupa a linha inteira em vez de ficar
    // solto na metade da tela.
    expect(tabs[2]?.classes()).toContain("col-span-2");
    expect(tabs[0]?.attributes("aria-selected")).toBe("true");
    expect(wrapper.get('[role="tabpanel"]').attributes("data-scene-kind")).toBe(
      "story",
    );

    await tabs[2]?.trigger("click");
    expect(wrapper.get('[role="tabpanel"]').attributes("data-scene-kind")).toBe(
      "whatsapp_message",
    );
    // A mensagem é retratada como mensagem: balão numa conversa, jamais um mural.
    expect(wrapper.text()).toContain(
      "A mensagem chega assim na conversa de cada pessoa elegível",
    );
  });

  it("o Story avisa que o texto do rascunho não é sobreposto — sem começar pela negativa", () => {
    const wrapper = mountPreview(
      simulatedScenes([
        {
          platform: "instagram",
          platformLabel: "Instagram",
          publicationFormat: "story",
          content: content(),
        },
      ]),
    );

    const note = wrapper.text();
    expect(note).toContain("O Story publica a imagem vertical acima");
    expect(note).toContain("sobre a imagem aparece só o que já estiver na arte");
  });

  it("o retrato sem foto diz o que vai acontecer, no formato certo", () => {
    const wrapper = mountPreview(
      simulatedScenes([
        {
          platform: "facebook",
          platformLabel: "Facebook",
          publicationFormat: "feed",
          content: content({ imageUrl: "" }),
        },
      ]),
    );

    expect(wrapper.text()).toContain("O Feed publica sem foto nesta versão.");
  });
});
