import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import Modal from "@nuxt/ui/components/Modal.vue";
import Slideover from "@nuxt/ui/components/Slideover.vue";
import { defineComponent, h, nextTick } from "vue";

// O X DO CABEÇALHO NÃO COBRE O TEXTO (#2806). O oficial do Nuxt UI posiciona o
// fechar em `absolute top-4 end-4` sem reservar o lugar dele, e a frase que chega à
// borda passa por baixo do X (a 375 px, no Recebimento do PDV, o X cobria a palavra
// "definem"). O tema do kit (`ui.modal` e `ui.slideover`) põe o X na linha do
// cabeçalho: o texto fica com o resto da largura e quebra antes dele. A geometria de
// verdade (caixas que não se cruzam) é medida no navegador, no PDV
// (`pos-nuxt/tests/geometry/fulfillmentHeader.spec.ts`); aqui se prova a anatomia.

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});
const settle = async () => {
  await nextTick();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
};

function host(kind: "NuxtModal" | "NuxtSlideover", props: Record<string, unknown>) {
  return defineComponent({
    setup: () => () => h(kind === "NuxtModal" ? Modal : Slideover, { open: true, ...props }, {
      body: () => h("p", "Corpo"),
    }),
  });
}

const classesOf = (selector: string) =>
  (document.body.querySelector<HTMLElement>(selector)?.className ?? "").split(/\s+/);

describe.each(["NuxtModal", "NuxtSlideover"] as const)("%s do kit: o X na linha do cabeçalho", (kind) => {
  it("o fechar não flutua por cima do texto: fica no fim da linha, no alto", async () => {
    mounted = await mountSuspended(host(kind, {
      title: "Recebimento",
      description: "Escolha como o cliente recebe o pedido.",
    }), { attachTo: document.body });
    await settle();
    const header = document.body.querySelector<HTMLElement>('[role="dialog"] [data-slot="header"]')!;
    const close = header.querySelector<HTMLElement>('[data-slot="close"]')!;
    const wrapper = header.querySelector<HTMLElement>('[data-slot="wrapper"]')!;
    expect(close).not.toBeNull();
    expect(wrapper).not.toBeNull();
    // O X é irmão do texto na mesma linha flexível, e vem depois dele.
    expect(close.parentElement).toBe(header);
    expect(wrapper.nextElementSibling).toBe(close);
    const closeClasses = classesOf('[role="dialog"] [data-slot="close"]');
    expect(closeClasses).toContain("static");
    expect(closeClasses).not.toContain("absolute");
    expect(closeClasses).toEqual(expect.arrayContaining(["shrink-0", "self-start", "ms-auto"]));
    // O texto ocupa o resto da largura e pode encolher (quebra em vez de vazar).
    expect(classesOf('[role="dialog"] [data-slot="wrapper"]')).toEqual(expect.arrayContaining(["min-w-0", "flex-1"]));
  });

  it("sem título, o X continua na ponta da direita", async () => {
    mounted = await mountSuspended(host(kind, { title: undefined, description: undefined }), { attachTo: document.body });
    await settle();
    expect(classesOf('[role="dialog"] [data-slot="close"]')).toContain("ms-auto");
  });
});
