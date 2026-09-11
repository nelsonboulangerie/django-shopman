import { flushPromises, mount } from "@vue/test-utils";
import { computed, ref, watch } from "vue";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import AnnouncementTemplateForm from "~/components/AnnouncementTemplateForm.vue";
import DraftRecoveryNotice from "~/components/DraftRecoveryNotice.vue";
import type { AnnouncementTemplate } from "~/types/campaign";
import { installMemoryLocalStorage } from "../support/localStorage";
import { UiNativeSelectStub } from "../support/nativeUiStubs";

beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
  installMemoryLocalStorage();
});
beforeEach(() => window.localStorage.clear());

function template(
  over: Partial<AnnouncementTemplate> = {},
): AnnouncementTemplate {
  return {
    pk: 3,
    name: "Fornada",
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

function form(value: AnnouncementTemplate, owner = "operator:7") {
  return mount(AnnouncementTemplateForm, {
    props: {
      template: value,
      variables: ["product_name", "price"],
      draftOwner: owner,
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

    expect(
      (wrapper.find('input[value="story"]').element as HTMLInputElement)
        .checked,
    ).toBe(true);
    await wrapper.find('input[value="feed"]').setValue();
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

    expect(wrapper.text()).toContain("O Story usará a foto do produto");
    await wrapper.find("#tpl-image").setValue("none");

    expect(wrapper.text()).toContain(
      "Campanhas que incluírem Instagram ficarão bloqueadas",
    );
  });
});
