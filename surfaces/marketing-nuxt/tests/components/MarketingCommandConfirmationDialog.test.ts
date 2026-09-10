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
    expect(wrapper.find("#decision-credential").attributes("autocomplete")).toBe(
      "current-password",
    );
    expect(wrapper.find("#decision-typed-confirmation").element.tagName).toBe(
      "TEXTAREA",
    );
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
          challenge: {
            token: "token",
            ref: "challenge",
            expires_at: "2026-09-10T11:05:00-03:00",
            mode: "typed",
            step_up: "password",
            dual_control: false,
            typed_phrase: "PUBLICAR 12",
            consequence: "creates_review_announcement",
            resource_ref: "campaign:3",
            base_version: 1,
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

    expect(wrapper.text()).toContain("Confirmar este disparo?");
    expect(wrapper.text()).toContain("cria somente um anúncio para revisão");
    expect(wrapper.text()).toContain("nada será publicado agora");
    expect(wrapper.text()).toContain("Criar para revisão");
    expect(wrapper.text()).toContain("Voltar sem criar");
  });
});
