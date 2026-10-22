import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";

import OperatorFormSection from "../../app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../app/components/OperatorFormShell.vue";
import OperatorConfirmDialog from "../../app/components/OperatorConfirmDialog.vue";
import { answerConfirm } from "../../app/composables/useConfirm";

// O casco canônico do cadastro: seções, aviso do que não foi salvo, ação na base
// (salvar/descartar) e a pergunta antes de descartar.

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn() as unknown as Element["scrollIntoView"];
});

afterEach(() => {
  answerConfirm(false);
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

const Host = defineComponent({
  props: {
    dirty: Boolean,
    activeSection: { type: String as () => string | null, default: "identity" },
    saveDisabled: Boolean,
    busy: Boolean,
  },
  emits: ["save", "discard", "update:open"],
  setup(props, { emit, slots }) {
    return () =>
      h("div", [
        h(
          OperatorFormShell,
          {
            open: true,
            title: "Novo produto",
            description: "Cria um produto do zero.",
            dirty: props.dirty,
            dirtyCount: 2,
            busy: props.busy,
            saveLabel: "Criar produto",
            saveDisabled: props.saveDisabled,
            saveDisabledReason: "Informe o código e o nome para salvar.",
            activeSection: props.activeSection,
            saveAttrs: { "data-testid": "create-submit" },
            onSave: () => emit("save"),
            onDiscard: () => emit("discard"),
            "onUpdate:open": (value: boolean) => emit("update:open", value),
          },
          {
            default: () =>
              h("div", [
                h(OperatorFormSection, { sectionKey: "identity", title: "Identificação" }, () =>
                  slots.identity?.(),
                ),
                h(
                  OperatorFormSection,
                  { sectionKey: "price", title: "Preço", description: "Quanto custa." },
                  () => slots.price?.(),
                ),
              ]),
            actions: () => h("button", { "data-testid": "header-action" }, "Arquivar"),
            lead: slots.lead,
          },
        ),
        h(OperatorConfirmDialog),
      ]);
  },
});

async function settle() {
  await nextTick();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
}

const box = () =>
  document.body.querySelector<HTMLElement>("[data-operator-confirm]")?.closest<HTMLElement>('[role="dialog"]') ?? null;

describe("OperatorFormShell", () => {
  it("encaminha as ações contextuais para o cabeçalho da gaveta", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body });
    await settle();
    expect(document.querySelector('[data-testid="header-action"]')?.textContent).toBe("Arquivar");
  });

  it("marca as seções como alvo do próximo foco e leva a página quando a chave muda", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body, props: { activeSection: "identity" } });
    await settle();
    const section = document.querySelector('[data-focus-target="identity"]')!;
    expect(section.getAttribute("tabindex")).toBe("-1");
    expect(document.querySelector('[data-focus-target="price"]')).not.toBeNull();

    await mounted.setProps({ activeSection: "price" });
    await settle();
    const price = document.querySelector('[data-focus-target="price"]')!;
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect((Element.prototype.scrollIntoView as unknown as ReturnType<typeof vi.fn>).mock.instances.at(-1)).toBe(price);
    expect(document.activeElement).toBe(price);
  });

  it("sem alteração, descartar fecha sem perguntar", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body, props: { dirty: false } });
    await settle();
    document.querySelector<HTMLElement>("[data-operator-action-bar-secondary]")!.click();
    await settle();
    expect(box()).toBeNull();
    const events = mounted.emitted("update:open") ?? [];
    expect(events.at(-1)).toEqual([false]);
    expect(mounted.emitted("discard")).toBeUndefined();
  });

  it("com alteração, descartar pergunta na caixa da casa e o seguro é continuar", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body, props: { dirty: true } });
    await settle();
    document.querySelector<HTMLElement>("[data-operator-action-bar-secondary]")!.click();
    await settle();
    expect(box()?.textContent).toContain("Descartar o que você preencheu?");
    expect(box()?.querySelector("[data-operator-confirm-keep]")?.textContent?.trim()).toBe("Continuar preenchendo");
    box()!.querySelector<HTMLButtonElement>("[data-operator-confirm-keep]")!.click();
    await settle();
    expect(mounted.emitted("update:open")).toBeUndefined();
    expect(mounted.emitted("discard")).toBeUndefined();

    document.querySelector<HTMLElement>("[data-operator-action-bar-secondary]")!.click();
    await settle();
    box()!.querySelector<HTMLButtonElement>("[data-operator-confirm-act]")!.click();
    await settle();
    expect(mounted.emitted("discard")).toHaveLength(1);
    expect((mounted.emitted("update:open") ?? []).at(-1)).toEqual([false]);
  });

  it("o aviso do que não foi salvo aparece na ação e na linha da mesa", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body, props: { dirty: true } });
    await settle();
    expect(document.querySelector("[data-operator-action-bar-context]")!.textContent).toContain("2 alterações não salvas");
    expect(document.querySelector("[data-form-shell]")!.getAttribute("data-form-dirty")).toBe("true");
    expect(document.querySelector("[data-form-shell-notice]")!.textContent).toContain("2 alterações não salvas");
  });

  it("quando não pode salvar, diz o motivo no lugar do salvamento", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body, props: { dirty: false, saveDisabled: true } });
    await settle();
    expect(document.querySelector("[data-form-shell-notice]")!.textContent).toContain("Informe o código e o nome para salvar.");
    const reason = document.querySelector("[data-operator-action-bar-reason]")!;
    expect(reason.textContent).toContain("Informe o código e o nome para salvar.");
  });

  it("a ação principal e a da mesa salvam pelo mesmo caminho", async () => {
    mounted = await mountSuspended(Host, { attachTo: document.body, props: { dirty: false } });
    await settle();
    const save = document.querySelectorAll<HTMLElement>('[data-testid="create-submit"]');
    expect(save.length).toBe(2);
    save[0]!.click();
    expect(mounted.emitted("save")).toHaveLength(1);
  });
});
