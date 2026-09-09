import { flushPromises, mount } from "@vue/test-utils";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AnnouncementPreview from "~/components/AnnouncementPreview.vue";

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    flagMarketingSessionError: () => false,
    onBeforeUnmount,
    ref,
    watch,
  });
});

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function artifact(platform: string, body: string) {
  return {
    platform,
    body,
    hashtags: platform === "instagram" ? ["padaria"] : [],
    link: "/produto/croissant",
    image_url: "",
    provider_fields: {},
    content_version: 1,
    facts_as_of: "2026-09-09T08:00:00+00:00",
    facts_hash: "a".repeat(64),
  };
}

function batch(values: Record<string, string>) {
  return {
    sku: "CRO-1",
    sample: true,
    product_name: "Croissant",
    fields: { available_qty: "", product_name: "Croissant" },
    ai_writes: false,
    facts: {
      schema_version: 1,
      as_of: "2026-09-09T08:00:00+00:00",
      fresh_until: "2026-09-09T08:05:00+00:00",
      source_hash: "a".repeat(64),
      sku: "CRO-1",
      promotion_ref: "",
      referenced_variables: ["product_name"],
      variables: { product_name: "Croissant" },
      product: {},
      price: {},
      availability: {},
      promotion: {},
      link: {},
    },
    previews: Object.fromEntries(
      Object.entries(values).map(([platform, body]) => [
        platform,
        {
          artifact: artifact(platform, body),
          artifact_hash: (platform === "instagram" ? "b" : "c").repeat(64),
        },
      ]),
    ),
  };
}

function mountPreview(over: Record<string, unknown> = {}) {
  return mount(AnnouncementPreview, {
    props: {
      body: "Primeira versão",
      platforms: ["instagram"],
      platformLabels: {
        instagram: "Instagram",
        whatsapp: "WhatsApp",
      },
      ...over,
    },
    global: { stubs: { Icon: true } },
  });
}

describe("AnnouncementPreview — request epoch e fidelidade", () => {
  it("aborta a chamada anterior e nunca deixa sua resposta tardia vencer", async () => {
    const calls: Array<{
      resolve: (value: ReturnType<typeof batch>) => void;
      signal: AbortSignal;
    }> = [];
    vi.stubGlobal(
      "$fetch",
      vi.fn((_url, options: { signal: AbortSignal }) =>
        new Promise((resolve) => calls.push({
          resolve: resolve as (value: ReturnType<typeof batch>) => void,
          signal: options.signal,
        })),
      ),
    );
    const wrapper = mountPreview();
    await vi.advanceTimersByTimeAsync(400);
    expect(calls).toHaveLength(1);

    await wrapper.setProps({ body: "Segunda versão" });
    await nextTick();
    expect(calls[0]!.signal.aborted).toBe(true);
    expect(wrapper.text()).not.toContain("Primeira versão");
    await vi.advanceTimersByTimeAsync(400);

    calls[1]!.resolve(batch({ instagram: "Segunda versão resolvida" }));
    await flushPromises();
    calls[0]!.resolve(batch({ instagram: "Resposta antiga" }));
    await flushPromises();

    expect(wrapper.text()).toContain("Segunda versão resolvida");
    expect(wrapper.text()).not.toContain("Resposta antiga");
    wrapper.unmount();
  });

  it("envia todas as variantes uma vez e alterna o artefato exato por plataforma", async () => {
    const fetch = vi.fn().mockResolvedValue(batch({
      instagram: "Texto exclusivo do Instagram",
      whatsapp: "Texto exclusivo do WhatsApp",
    }));
    vi.stubGlobal("$fetch", fetch);
    const platformContent = {
      instagram: { body: "Texto exclusivo do Instagram" },
      whatsapp: { body: "Texto exclusivo do WhatsApp" },
    };
    const wrapper = mountPreview({
      platforms: ["instagram", "whatsapp"],
      platformContent,
    });

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]![1].body).toMatchObject({
      platforms: ["instagram", "whatsapp"],
      platform_content: platformContent,
    });
    expect(wrapper.text()).toContain("Texto exclusivo do Instagram");
    expect(wrapper.text()).not.toContain("Texto exclusivo do WhatsApp");
    expect(wrapper.text()).not.toContain("available_qty");

    await wrapper.find("[data-platform='whatsapp']").trigger("click");
    expect(wrapper.text()).toContain("Texto exclusivo do WhatsApp");
    expect(wrapper.text()).not.toContain("Texto exclusivo do Instagram");
    wrapper.unmount();
  });

  it("mostra erro estruturado no contexto e recupera sem navegação", async () => {
    const fetch = vi.fn()
      .mockRejectedValueOnce({
        data: {
          detail: "O conteúdo usa uma variável desconhecida.",
          field_errors: { body: ["Variável não reconhecida: precoo."] },
          retryable: false,
        },
      })
      .mockResolvedValueOnce(batch({ instagram: "Prévia corrigida" }));
    vi.stubGlobal("$fetch", fetch);
    const wrapper = mountPreview();

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(wrapper.get("[data-testid='preview-error']").text()).toContain(
      "Variável não reconhecida: precoo.",
    );
    await wrapper.get("[data-testid='preview-error'] button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Prévia corrigida");
    expect(fetch).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it("rotula explicitamente a amostra, o as-of e a versão verificável", async () => {
    vi.stubGlobal("$fetch", vi.fn().mockResolvedValue(batch({ instagram: "Prévia final" })));
    const wrapper = mountPreview();

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(wrapper.text()).toContain("Exemplo com Croissant");
    expect(wrapper.text()).toContain("Dados conferidos às");
    expect(wrapper.text()).toContain("Versão bbbbbbbb");
    wrapper.unmount();
  });
});
