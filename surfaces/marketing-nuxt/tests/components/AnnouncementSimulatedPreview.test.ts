// O botão do olho e a sobreposição que ele abre.
//
// Botão só com ícone e sem nome acessível já foi defeito real deste app; aqui ele é
// medido, não prometido.
import { mount } from "@vue/test-utils";
import { computed, defineComponent, h, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import AnnouncementSimulatedPreview from "~/components/AnnouncementSimulatedPreview.vue";
import { simulatedScenes } from "~/presentation/simulatedPreview";

// O `NuxtModal` real é o DialogRoot da reka-ui, que segura o `open` e desenha o gatilho
// (slot padrão). O dublê guarda o mesmo contrato: o gatilho sempre, o corpo só aberto.
const ModalStub = defineComponent({
  props: { open: Boolean, title: String, description: String },
  emits: ["update:open"],
  setup(props, { emit, slots }) {
    return () =>
      h("div", [
        h("div", { onClick: () => emit("update:open", true) }, slots.default?.()),
        props.open
          ? h("div", { role: "dialog" }, [
              props.title ? h("h2", props.title) : null,
              props.description ? h("p", props.description) : null,
              slots.body?.(),
            ])
          : null,
      ]);
  },
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
    global: { stubs: { NuxtModal: ModalStub, Icon: true } },
  });
}

async function openPreview(scenes: ReturnType<typeof simulatedScenes>) {
  const wrapper = mountPreview(scenes);
  await wrapper.get('[data-testid="open-simulated-preview"]').trigger("click");
  return wrapper;
}

describe("AnnouncementSimulatedPreview", () => {
  it("o botão só de ícone tem nome de verdade e é quadrado, do conjunto mínimo", () => {
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
    // Botão só de ícone é `square` (conjunto mínimo da suíte), no tamanho padrão.
    expect(trigger.attributes("square")).toBeDefined();
    expect(trigger.get("[data-icon]").attributes("data-icon")).toBe("i-lucide-eye");
  });

  it("sem retrato nenhum, o olho não aparece", () => {
    const wrapper = mountPreview([]);
    expect(wrapper.find('[data-testid="open-simulated-preview"]').exists()).toBe(
      false,
    );
  });

  it("um botão por formato, e a aba diz qual está aberta", async () => {
    const shared = content();
    const wrapper = await openPreview(
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

  it("o Story avisa que o texto do rascunho não é sobreposto — sem começar pela negativa", async () => {
    const wrapper = await openPreview(
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

  it("o retrato sem foto diz o que vai acontecer, no formato certo", async () => {
    const wrapper = await openPreview(
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
