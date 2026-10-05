import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import UiButton from "../../app/components/UiButton.vue";
import UiModal from "../../app/components/UiModal.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("primitivas estruturais Nuxt UI com identidade Shopman", () => {
  it("mantém o contrato de botão, o alvo canônico e o estado de carregamento", async () => {
    mounted = await mountSuspended(UiButton, {
      attachTo: document.body,
      props: {
        loading: true,
        text: "Salvar campanha",
      },
    });

    const button = document.body.querySelector<HTMLButtonElement>("button")!;
    expect(button).not.toBeNull();
    expect(button.disabled).toBe(true);
    expect(button.className).toContain("h-11");
    expect(button.className).toContain("bg-primary");
    expect(button.textContent).toContain("Salvar campanha");
  });

  it("usa a anatomia de modal do Nuxt UI sem deixar texto ou tema padrão escapar", async () => {
    const Host = defineComponent({
      setup() {
        const open = ref(true);
        return () =>
          h(
            UiModal,
            {
              open: open.value,
              "onUpdate:open": (value: boolean) => (open.value = value),
              title: "Revisar disparo",
              description: "Confira o público antes de continuar.",
            },
            {
              body: () => h("p", "12 clientes receberão a mensagem."),
            },
          );
      },
    });

    mounted = await mountSuspended(Host, { attachTo: document.body });
    await nextTick();

    const dialog = document.body.querySelector<HTMLElement>("[role='dialog']")!;
    expect(dialog).not.toBeNull();
    expect(dialog.textContent).toContain("Revisar disparo");
    expect(dialog.textContent).toContain("12 clientes receberão a mensagem.");
    expect(dialog.className).toContain("bg-card");
    expect(dialog.className).not.toContain("bg-white");
    expect(document.body.querySelector("[aria-label='Fechar']")).not.toBeNull();
    expect(document.body.textContent).not.toContain("Close");
  });
});
