import { flushPromises, mount } from "@vue/test-utils";
import { computed, ref, watch } from "vue";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import AnnouncementTemplateForm from "~/components/AnnouncementTemplateForm.vue";
import DraftRecoveryNotice from "~/components/DraftRecoveryNotice.vue";
import type {
  AnnouncementTemplate,
  MarketingFormatCapability,
  MarketingPlatformCapability,
} from "~/types/campaign";
import { installMemoryLocalStorage } from "../support/localStorage";
import { UiNativeSelectStub } from "../support/nativeUiStubs";

beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
  installMemoryLocalStorage();
});
beforeEach(() => window.localStorage.clear());

function format(
  ref: string,
  label: string,
  fields: string[] = ["publication_format"],
  required: string[] = fields,
  mediaRequired = false,
): MarketingFormatCapability {
  return {
    ref,
    label,
    provider_fields: fields,
    required_provider_fields: required,
    media_required: mediaRequired,
  };
}

const DELIVERY_CAPABILITIES: MarketingPlatformCapability[] = [
  {
    platform: "instagram",
    label: "Instagram",
    delivery_kind: "publication",
    default_format: "story",
    formats: [
      format("story", "Stories", undefined, undefined, true),
      format("feed", "Feed", undefined, undefined, true),
    ],
  },
  {
    platform: "facebook",
    label: "Facebook",
    delivery_kind: "publication",
    default_format: "feed",
    formats: [format("feed", "Feed")],
  },
  {
    platform: "google_business",
    label: "Google Meu Negócio",
    delivery_kind: "publication",
    default_format: "standard",
    formats: [
      format("standard", "Atualização", [
        "publication_format",
        "call_to_action",
      ]),
      format(
        "event",
        "Evento",
        [
          "publication_format",
          "call_to_action",
          "event_title",
          "event_start",
          "event_end",
        ],
        [
          "publication_format",
          "event_title",
          "event_start",
          "event_end",
        ],
      ),
      format("offer", "Oferta", [
        "publication_format",
        "offer_title",
        "offer_start",
        "offer_end",
        "offer_terms",
      ]),
    ],
  },
  {
    platform: "whatsapp",
    label: "WhatsApp via Meta",
    delivery_kind: "direct_message",
    default_format: "message",
    formats: [format("message", "Mensagem", ["template_name"], [])],
  },
];

function template(
  over: Partial<AnnouncementTemplate> = {},
): AnnouncementTemplate {
  return {
    pk: 3,
    name: "Lote",
    body: "{{product_name}} saiu do forno",
    platform_variants: {},
    variables: ["product_name"],
    use_ai_generation: false,
    ai_prompt: "",
    image_source: "product",
    is_active: true,
    updated_at: "2026-09-09T08:00:00-03:00",
    ...over,
  };
}

function form(
  value: AnnouncementTemplate,
  owner = "operator:7",
  deliveryCapabilities: MarketingPlatformCapability[] = DELIVERY_CAPABILITIES,
) {
  return mount(AnnouncementTemplateForm, {
    props: {
      template: value,
      variables: ["product_name", "price"],
      draftOwner: owner,
      deliveryCapabilities,
    },
    global: {
      components: { DraftRecoveryNotice, UiNativeSelect: UiNativeSelectStub },
      stubs: { Icon: true },
    },
  });
}

describe("AnnouncementTemplateForm draft recovery", () => {
  it("restores text and settings after the form remounts", async () => {
    const first = form(template());
    await first
      .find("#tpl-body")
      .setValue("Texto longo que o operador acabou de revisar");
    await first
      .find("#tpl-instagram-body")
      .setValue("Versão própria para o Instagram");
    await first.find("#tpl-image").setValue("none");
    first.unmount();

    const restored = form(template());
    await flushPromises();

    expect(
      (restored.find("#tpl-body").element as HTMLTextAreaElement).value,
    ).toBe("Texto longo que o operador acabou de revisar");
    expect(
      (restored.find("#tpl-image").element as HTMLSelectElement).value,
    ).toBe("none");
    expect(
      (restored.find("#tpl-instagram-body").element as HTMLTextAreaElement)
        .value,
    ).toBe("Versão própria para o Instagram");
    expect(restored.text()).toContain("Rascunho restaurado");
  });

  it("shows the server/local diff when the same text changed concurrently", async () => {
    const first = form(template());
    await first.find("#tpl-body").setValue("Minha nova versão");
    first.unmount();

    const conflicted = form(
      template({
        body: "Versão de outra sessão",
        updated_at: "2026-09-09T08:05:00-03:00",
      }),
    );
    await flushPromises();

    expect(conflicted.text()).toContain(
      "Este conteúdo também mudou em outra sessão",
    );
    expect(conflicted.text()).toContain("Minha nova versão");
    expect(conflicted.text()).toContain("Versão de outra sessão");
  });

  it("usa Stories por padrão e só grava Feed após escolha explícita", async () => {
    const wrapper = form(template());

    const formats = wrapper.findAll('[role="radio"]');
    expect(formats[0]!.attributes("aria-checked")).toBe("true");
    expect(formats[0]!.text()).toContain("Stories");
    await formats[1]!.trigger("click");
    await wrapper.find("form").trigger("submit");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as {
      platform_variants: Record<string, Record<string, unknown>>;
    };
    expect(payload.platform_variants.instagram?.publication_format).toBe(
      "feed",
    );
    expect(payload.platform_variants.facebook?.publication_format).toBe("feed");
    expect(payload.platform_variants.google_business?.publication_format).toBe(
      "standard",
    );
  });

  it("reutiliza uma imagem fixa nos canais sem pedir redigitação", async () => {
    const wrapper = form(template());
    await wrapper.find("#tpl-image").setValue("custom");
    await wrapper
      .find("#tpl-image-url")
      .setValue("https://cdn.example.test/story.jpg");
    await wrapper.find("form").trigger("submit");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as {
      platform_variants: Record<string, Record<string, unknown>>;
    };
    for (const platform of [
      "instagram",
      "facebook",
      "google_business",
      "whatsapp",
    ]) {
      expect(payload.platform_variants[platform]?.image_url).toBe(
        "https://cdn.example.test/story.jpg",
      );
    }
  });

  it("avisa no próprio campo quando Stories ficaria sem imagem", async () => {
    const wrapper = form(template());

    expect(wrapper.text()).toContain("Usa a foto do produto, em JPEG");
    await wrapper.find("#tpl-image").setValue("none");

    expect(wrapper.text()).toContain(
      "Campanhas que incluírem Instagram ficarão bloqueadas",
    );
  });

  it("configura Evento no Google com os campos que a API exige", async () => {
    const wrapper = form(template());
    await wrapper
      .findAll('[role="radio"]')
      .find((radio) => radio.text().includes("Evento"))!
      .trigger("click");
    await wrapper.find("#tpl-google-event-title").setValue("Semana do Pão");
    await wrapper.find("#tpl-google-event-start").setValue("2026-10-01T08:00");
    await wrapper.find("#tpl-google-event-end").setValue("2026-10-04T18:00");
    await wrapper.find("form").trigger("submit");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as {
      platform_variants: Record<string, Record<string, unknown>>;
    };
    expect(payload.platform_variants.google_business).toMatchObject({
      publication_format: "event",
      event_title: "Semana do Pão",
      event_start: "2026-10-01T08:00",
      event_end: "2026-10-04T18:00",
    });
  });

  it("oferece os CTAs reais do Google e guarda a escolha", async () => {
    const wrapper = form(template({ body: "Confira: {{link}}" }));
    await wrapper
      .findAll('[role="radio"]')
      .find((radio) => radio.text().includes("Pedir on-line"))!
      .trigger("click");
    await wrapper.find("form").trigger("submit");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as {
      platform_variants: Record<string, Record<string, unknown>>;
    };
    expect(payload.platform_variants.google_business).toMatchObject({
      publication_format: "standard",
      call_to_action: "order",
    });
  });

  it("mantém a intenção comum e salva somente as adaptações explícitas por destino", async () => {
    const wrapper = form(template());
    const instagram = wrapper.get('[data-testid="composition-instagram"]');
    await instagram
      .findAll('[role="radio"]')
      .find((radio) => radio.text().includes("Feed"))!
      .trigger("click");
    await instagram
      .get("#tpl-instagram-body")
      .setValue("{{product_name}} no Feed, com mais contexto");
    await wrapper
      .get('[data-testid="composition-whatsapp"] #tpl-whatsapp-body')
      .setValue("{{product_name}} acabou de sair — responda para reservar");
    await wrapper.find("form").trigger("submit");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as {
      body: string;
      platform_variants: Record<string, Record<string, unknown>>;
    };
    expect(payload.body).toBe("{{product_name}} saiu do forno");
    expect(payload.platform_variants.instagram).toMatchObject({
      publication_format: "feed",
      body: "{{product_name}} no Feed, com mais contexto",
    });
    expect(payload.platform_variants.whatsapp).toMatchObject({
      body: "{{product_name}} acabou de sair — responda para reservar",
    });
  });

  it("não oferece nem inventa composição fora da allow-list executável", async () => {
    const instagramOnly: MarketingPlatformCapability[] = [
      {
        platform: "instagram",
        label: "Instagram",
        delivery_kind: "publication",
        default_format: "story",
        formats: [
          {
            ref: "story",
            label: "Stories",
            provider_fields: ["publication_format"],
            required_provider_fields: ["publication_format"],
            media_required: true,
          },
        ],
      },
    ];
    const wrapper = form(template(), "operator:7", instagramOnly);

    expect(wrapper.find('[data-testid="composition-instagram"]').exists()).toBe(
      true,
    );
    expect(
      wrapper.find('[data-testid="composition-google_business"]').exists(),
    ).toBe(false);
    expect(wrapper.find('[data-testid="composition-whatsapp"]').exists()).toBe(
      false,
    );
    await wrapper.find("form").trigger("submit");

    const payload = wrapper.emitted("submit")?.[0]?.[0] as {
      platform_variants: Record<string, Record<string, unknown>>;
    };
    expect(Object.keys(payload.platform_variants)).toEqual(["instagram"]);
    expect(payload.platform_variants.instagram?.publication_format).toBe(
      "story",
    );
  });

  it("falha fechado quando a allow-list executável não carregou", async () => {
    const wrapper = form(template(), "operator:7", []);

    expect(wrapper.get('[role="alert"]').text()).toContain(
      "não será salvo no escuro",
    );
    expect(wrapper.findAll('[data-testid^="composition-"]')).toHaveLength(0);
    expect(
      (wrapper.get('button[type="submit"]').element as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });
});
