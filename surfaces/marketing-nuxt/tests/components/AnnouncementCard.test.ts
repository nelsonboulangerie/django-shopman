import { flushPromises, mount } from "@vue/test-utils";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AnnouncementCard from "~/components/AnnouncementCard.vue";
import DraftRecoveryNotice from "~/components/DraftRecoveryNotice.vue";
import type { Announcement } from "~/types/campaign";
import { installMemoryLocalStorage } from "../support/localStorage";

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    flagMarketingSessionError: () => false,
    httpErrorMessage: (_error: unknown, fallback: string) => fallback,
    onBeforeUnmount,
    onMounted,
    ref,
    watch,
  });
  installMemoryLocalStorage();
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-07-18T12:00:00Z"));
  window.localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const PLATFORMS = [
  { value: "instagram", label: "Instagram" },
  { value: "google_business", label: "Google Meu Negócio" },
  { value: "whatsapp", label: "WhatsApp" },
];

function makeAnnouncement(over: Partial<Announcement> = {}): Announcement {
  return {
    pk: 7,
    version: 1,
    status: "pending_review",
    status_label: "aguardando aprovação",
    body: "Croissant saiu do forno",
    image_url: "",
    hashtags: ["padaria"],
    link: "/p/croissant",
    platforms: ["instagram"],
    audience: { favorites_count: 12, alerts_count: 3, total: 15 },
    audience_total: 15,
    platform_results: [],
    trigger: "production_finished",
    trigger_label: "Fornada concluída",
    rule_name: "Fornada de pães",
    template_name: "Fornada",
    sku: "CRO-001",
    created_at: "2026-07-18T07:00:00-03:00",
    expires_at: "",
    expires_in_minutes: 20,
    published_at: "",
    approved_by: "",
    rejected_by: "",
    rejected_reason: "",
    scheduled_for: "",
    ai_suggestion_enabled: false,
    ...over,
  };
}

function mountCard(
  announcement: Announcement,
  draftOwner = "",
  shopTimezone = "America/Sao_Paulo",
  aiAssistAvailable = false,
  quietHoursSuspendedForLocalSimulation = false,
) {
  return mount(AnnouncementCard, {
    props: {
      announcement,
      platformOptions: PLATFORMS,
      draftOwner,
      shopTimezone,
      aiAssistAvailable,
      quietHoursSuspendedForLocalSimulation,
    },
    global: {
      components: { DraftRecoveryNotice },
      stubs: { Icon: true },
    },
  });
}

describe("AnnouncementCard", () => {
  it("shows the generated text, the audience and the deadline", () => {
    const text = mountCard(makeAnnouncement()).text();
    expect(text).toContain("Fornada de pães");
    expect(text).toContain("12 favoritos, 3 alertas = 15 clientes");
    expect(text).toContain("Expira em 20 min");
  });

  it("pre-selects exactly the platforms the rule chose", () => {
    const wrapper = mountCard(makeAnnouncement({ platforms: ["instagram", "whatsapp"] }));
    const checked = wrapper
      .findAll("input[type=checkbox]")
      .filter((input) => (input.element as HTMLInputElement).checked);
    expect(checked).toHaveLength(2);
  });

  it("sends the edited text and platforms together with the approval", async () => {
    // Um request só: salvar e publicar em duas chamadas abriria a janela de
    // publicar a versão anterior.
    const wrapper = mountCard(makeAnnouncement());
    await wrapper.find("textarea").setValue("Texto revisado");
    await wrapper.find("input[type=text]").setValue("#paes #fornada");
    await wrapper.findAll("button")[0]!.trigger("click");

    expect(wrapper.emitted("approve")).toBeTruthy();
    const [pk, edits] = wrapper.emitted("approve")![0] as [number, Record<string, unknown>];
    expect(pk).toBe(7);
    expect(edits.body).toBe("Texto revisado");
    expect(edits.hashtags).toEqual(["paes", "fornada"]);
    expect(edits.platforms).toEqual(["instagram"]);
    expect(wrapper.emitted("approve")![0]![2]).toBe("now");
  });

  it("refuses to publish an empty announcement", async () => {
    const wrapper = mountCard(makeAnnouncement());
    await wrapper.find("textarea").setValue("   ");
    const publish = wrapper.findAll("button")[0]!;

    expect((publish.element as HTMLButtonElement).disabled).toBe(true);
    await publish.trigger("click");
    expect(wrapper.emitted("approve")).toBeFalsy();
  });

  it("refuses to publish with no platform selected", async () => {
    const wrapper = mountCard(makeAnnouncement({ platforms: [] }));
    expect((wrapper.findAll("button")[0]!.element as HTMLButtonElement).disabled).toBe(true);
    expect(wrapper.text()).toContain("Escolha ao menos uma plataforma");
  });

  it("only asks for a date after the gestor chooses to schedule", async () => {
    const wrapper = mountCard(makeAnnouncement());
    expect(wrapper.find("input[type=datetime-local]").exists()).toBe(false);

    await wrapper.findAll("button")[1]!.trigger("click");
    expect(wrapper.find("input[type=datetime-local]").exists()).toBe(true);
  });

  it("carries publish_at when scheduling", async () => {
    const wrapper = mountCard(makeAnnouncement());
    await wrapper.findAll("button")[1]!.trigger("click");
    await wrapper.find("input[type=datetime-local]").setValue("2026-07-19T07:00");
    await wrapper.find("input[type=datetime-local]").trigger("change");

    const confirm = wrapper.findAll("button").at(-1)!;
    await confirm.trigger("click");

    const [, edits] = wrapper.emitted("approve")![0] as [number, Record<string, unknown>];
    expect(edits.publish_at).toBe("2026-07-19T07:00:00-03:00");
    expect(wrapper.emitted("approve")![0]![2]).toBe("scheduled");
  });

  it("replaces a quiet-hours guess with the next permitted WhatsApp time", async () => {
    vi.setSystemTime(new Date("2026-07-18T00:30:00Z")); // 21:30 on the shop clock.
    const wrapper = mountCard(makeAnnouncement({ platforms: ["whatsapp"] }));
    const publishNow = wrapper.findAll("button").find(button => button.text().includes("Publicar agora"))!;

    expect((publishNow.element as HTMLButtonElement).disabled).toBe(true);
    expect(wrapper.text()).toContain("WhatsApp em silêncio das 20:00 às 08:00");

    await wrapper.findAll("button").find(button => button.text() === "Agendar")!.trigger("click");

    expect((wrapper.find("input[type=datetime-local]").element as HTMLInputElement).value)
      .toBe("2026-07-18T08:00");
  });

  it("allows an after-hours send only when the server marks the hermetic rehearsal", async () => {
    vi.setSystemTime(new Date("2026-07-18T00:30:00Z")); // 21:30 on the shop clock.
    const wrapper = mountCard(
      makeAnnouncement({ platforms: ["whatsapp"] }),
      "",
      "America/Sao_Paulo",
      false,
      true,
    );
    const publishNow = wrapper.findAll("button")
      .find(button => button.text().includes("Publicar agora"))!;

    expect((publishNow.element as HTMLButtonElement).disabled).toBe(false);
    expect(wrapper.text()).toContain("Ensaio local");
    expect(wrapper.text()).toContain("nenhuma mensagem sai deste computador");
    await publishNow.trigger("click");
    expect(wrapper.emitted("approve")![0]![2]).toBe("now");
  });

  it("does not allow a schedule at the exact expiry boundary", async () => {
    const wrapper = mountCard(makeAnnouncement({
      expires_at: "2026-07-19T07:00:00-03:00",
    }));
    await wrapper.findAll("button").find(button => button.text() === "Agendar")!.trigger("click");
    await wrapper.find("input[type=datetime-local]").setValue("2026-07-19T07:00");

    expect(wrapper.text()).toContain("expiraria antes desse horário");
    const confirm = wrapper.findAll("button").find(button => button.text() === "Confirmar agendamento")!;
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true);
  });

  it("waits for the operator to choose one of two DST occurrences", async () => {
    vi.setSystemTime(new Date("2026-10-31T12:00:00Z"));
    const wrapper = mountCard(makeAnnouncement(), "", "America/New_York");
    await wrapper.findAll("button").find(button => button.text() === "Agendar")!.trigger("click");
    await wrapper.find("input[type=datetime-local]").setValue("2026-11-01T01:30");

    expect(wrapper.text()).toContain("acontece duas vezes");
    const confirm = wrapper.findAll("button").find(button => button.text() === "Confirmar agendamento")!;
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true);

    await wrapper.findAll("input[type=radio]").at(-1)!.setValue();
    await confirm.trigger("click");
    const [, edits] = wrapper.emitted("approve")![0] as [number, Record<string, unknown>];
    expect(edits.publish_at).toBe("2026-11-01T01:30:00-05:00");
  });

  it("asks the parent to confirm the rejection instead of rejecting itself", async () => {
    const wrapper = mountCard(makeAnnouncement());
    const rejectButton = wrapper.findAll("button").find((b) => b.text().includes("Recusar"))!;
    await rejectButton.trigger("click");
    expect(wrapper.emitted("reject")![0]).toEqual([7]);
  });

  it("keeps the in-progress edit when the same announcement is refetched", async () => {
    // Poll/SSE não pode apagar o que o gestor está escrevendo.
    const wrapper = mountCard(makeAnnouncement());
    await wrapper.find("textarea").setValue("rascunho do gestor");

    await wrapper.setProps({ announcement: makeAnnouncement({ body: "texto do servidor" }) });

    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value).toBe(
      "rascunho do gestor",
    );
  });

  it("resets the draft when a different announcement takes its place", async () => {
    const wrapper = mountCard(makeAnnouncement());
    await wrapper.find("textarea").setValue("rascunho do announcement 7");

    await wrapper.setProps({ announcement: makeAnnouncement({ pk: 9, body: "outro announcement" }) });

    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value).toBe("outro announcement");
  });

  it("offers a placeholder when the product has no photo", () => {
    expect(mountCard(makeAnnouncement({ image_url: "" })).find("img").exists()).toBe(false);
  });

  it("keeps the operator draft untouched until a structured suggestion is accepted", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce({
        suggestion: {
          ref: "11111111-1111-4111-8111-111111111111",
          body: "Croissant acabou de sair do forno.",
          hashtags: ["Croissant", "Fornada"],
          used_fact_ids: ["product_name"],
          warnings: ["operator_should_verify_tone"],
          policy_version: "marketing-ai-v2.1",
          model_ref: "test-model",
          suggestion_hash: "a".repeat(64),
          facts_hash: "b".repeat(64),
          base_version: 1,
          facts: [{ id: "product_name", label: "Produto", value: "Croissant" }],
        },
      })
      .mockResolvedValue({ ok: true });
    vi.stubGlobal("$fetch", fetch);
    const wrapper = mountCard(
      makeAnnouncement({ ai_suggestion_enabled: true }),
      "",
      "America/Sao_Paulo",
      true,
    );
    const original = (wrapper.find("textarea").element as HTMLTextAreaElement).value;

    await wrapper.findAll("button").find(button => button.text() === "Sugerir texto")!.trigger("click");
    await flushPromises();

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/v1/backstage/marketing/announcements/7/rewrite/",
      { method: "POST", credentials: "same-origin", body: { body: original } },
    );
    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value).toBe(original);
    expect(wrapper.get("[data-testid=ai-suggestion-compare]").text()).toContain("Seu texto");
    expect(wrapper.text()).toContain("Produto: Croissant");
    expect(wrapper.text()).toContain("Nada é publicado");
    expect(wrapper.emitted("approve")).toBeFalsy();

    await wrapper.get("[data-testid=use-ai-suggestion]").trigger("click");
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/v1/backstage/marketing/announcements/7/suggestions/11111111-1111-4111-8111-111111111111/disposition/",
      { method: "POST", credentials: "same-origin", body: { action: "accept_draft" } },
    );
    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Croissant acabou de sair do forno.");
    expect(wrapper.emitted("approve")).toBeFalsy();

    await wrapper.findAll("button").find(button => button.text().includes("Publicar agora"))!
      .trigger("click");
    const [, edits] = wrapper.emitted("approve")![0] as [number, Record<string, unknown>];
    expect(edits.ai_suggestion_ref).toBe("11111111-1111-4111-8111-111111111111");
  });

  it("preserves body and hashtags when the assistant fails", async () => {
    vi.stubGlobal("$fetch", vi.fn().mockRejectedValue(new Error("timeout")));
    const wrapper = mountCard(
      makeAnnouncement({ ai_suggestion_enabled: true }),
      "",
      "America/Sao_Paulo",
      true,
    );
    await wrapper.find("textarea").setValue("Meu texto insubstituível");
    await wrapper.find("input[type=text]").setValue("#minhatag");

    await wrapper.findAll("button").find(button => button.text() === "Sugerir texto")!.trigger("click");
    await flushPromises();

    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Meu texto insubstituível");
    expect((wrapper.find("input[type=text]").element as HTMLInputElement).value).toBe("#minhatag");
    expect(wrapper.get("[data-testid=ai-assist-error]").text()).toContain("segue aqui");
  });

  it("undoes an accepted suggestion in one gesture", async () => {
    vi.stubGlobal("$fetch", vi.fn().mockResolvedValue({
      suggestion: {
        ref: "22222222-2222-4222-8222-222222222222",
        body: "Sugestão segura.", hashtags: [], used_fact_ids: [], warnings: [],
        policy_version: "marketing-ai-v2.1", model_ref: "test", suggestion_hash: "a",
        facts_hash: "b", base_version: 1, facts: [],
      },
    }));
    const wrapper = mountCard(
      makeAnnouncement({ ai_suggestion_enabled: true }), "", "America/Sao_Paulo", true,
    );

    await wrapper.findAll("button").find(button => button.text() === "Sugerir texto")!.trigger("click");
    await flushPromises();
    await wrapper.get("[data-testid=use-ai-suggestion]").trigger("click");
    await wrapper.get("[data-testid=undo-ai-suggestion]").trigger("click");

    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Croissant saiu do forno");
  });

  it("restores a draft after refresh or a failed authenticated command", async () => {
    const first = mountCard(makeAnnouncement(), "operator:7");
    await first.find("textarea").setValue("rascunho que não pode sumir");
    await first.findAll("button")[0]!.trigger("click");
    first.unmount();

    const restored = mountCard(makeAnnouncement(), "operator:7");
    await flushPromises();

    expect((restored.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("rascunho que não pode sumir");
    expect(restored.text()).toContain("Rascunho restaurado");
  });

  it("confirms the local autosave within the 400 ms feedback budget", async () => {
    vi.useFakeTimers();
    const wrapper = mountCard(makeAnnouncement(), "operator:7");
    await wrapper.find("textarea").setValue("Rascunho salvo sem outro gesto");

    await vi.advanceTimersByTimeAsync(400);

    expect(wrapper.text()).toContain("Rascunho salvo neste dispositivo");
  });

  it("flushes the last keystroke when the browser page is leaving", async () => {
    const first = mountCard(makeAnnouncement(), "operator:7");
    await first.find("textarea").setValue("Último texto antes do refresh");
    window.dispatchEvent(new Event("pagehide"));
    first.unmount();

    const restored = mountCard(makeAnnouncement(), "operator:7");
    await flushPromises();

    expect((restored.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Último texto antes do refresh");
  });

  it("never restores another operator's draft", async () => {
    const alice = mountCard(makeAnnouncement(), "operator:7");
    await alice.find("textarea").setValue("texto da Alice");
    alice.unmount();

    const bob = mountCard(makeAnnouncement(), "operator:8");
    await flushPromises();

    expect((bob.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Croissant saiu do forno");
    expect(bob.text()).not.toContain("Rascunho restaurado");
  });

  it("rebases independent changes automatically", async () => {
    const first = mountCard(makeAnnouncement(), "operator:7");
    await first.find("input[type=text]").setValue("#meu-rascunho");
    first.unmount();

    const restored = mountCard(
      makeAnnouncement({ version: 2, body: "Texto atualizado no servidor" }),
      "operator:7",
    );
    await flushPromises();

    expect((restored.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Texto atualizado no servidor");
    expect((restored.find("input[type=text]").element as HTMLInputElement).value)
      .toBe("#meu-rascunho");
    expect(restored.text()).toContain("Rascunho combinado com a versão atual");
  });

  it("shows a field diff and waits when both sides changed the same content", async () => {
    const first = mountCard(makeAnnouncement(), "operator:7");
    await first.find("textarea").setValue("Minha revisão");
    first.unmount();

    const conflicted = mountCard(
      makeAnnouncement({ version: 2, body: "Revisão de outra sessão" }),
      "operator:7",
    );
    await flushPromises();

    expect((conflicted.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Revisão de outra sessão");
    expect(conflicted.text()).toContain("Este conteúdo também mudou em outra sessão");
    expect(conflicted.text()).toContain("Minha revisão");
    expect(conflicted.text()).toContain("Revisão de outra sessão");

    await conflicted.findAll("button").find(button => button.text() === "Manter minhas mudanças")!
      .trigger("click");
    await flushPromises();
    expect((conflicted.find("textarea").element as HTMLTextAreaElement).value)
      .toBe("Minha revisão");
  });
});
