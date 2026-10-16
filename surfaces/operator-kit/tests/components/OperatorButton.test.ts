import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";

import OperatorButton from "../../app/components/OperatorButton.vue";
import OperatorFitGroup from "../../app/components/OperatorFitGroup.vue";

describe("OperatorButton: o rótulo que cabe", () => {
  it("desenha o completo e o curto como conteúdo gerado; o texto do botão é só o completo", async () => {
    const wrapper = await mountSuspended(OperatorButton, {
      props: { label: "Enviar à cozinha", shortLabel: "Cozinha", icon: "i-lucide-chef-hat" },
    });
    const button = wrapper.find("button");
    expect(button.text()).toBe("Enviar à cozinha");
    expect(button.attributes("aria-label")).toBe("Enviar à cozinha");
    expect(button.attributes("title")).toBe("Enviar à cozinha");
    expect(button.attributes("data-op-fit")).toBe("md");
    expect(button.attributes("data-op-fit-icon")).toBe("");
    expect(button.attributes("style")).toContain("--op-fit-full");
    const short = wrapper.find('[data-op-fit-variant="short"]');
    expect(short.attributes("data-op-fit-short")).toBe("Cozinha");
    expect(short.attributes("aria-hidden")).toBe("true");
    expect(wrapper.find('[data-op-fit-variant="full"]').text()).toBe("Enviar à cozinha");
  });

  it("a tecla do atalho é a primeira a cair: some antes do rótulo completo", async () => {
    const wrapper = await mountSuspended(OperatorButton, {
      props: { label: "Enviar à cozinha", shortLabel: "Enviar", icon: "i-lucide-chef-hat", shortcut: "F9" },
    });
    const key = wrapper.find("[data-op-fit-key]");
    expect(key.text()).toBe("F9");
    expect(key.attributes("aria-hidden")).toBe("true");
    // O limite da tecla é o do completo MAIS a largura dela: cai antes do verbo.
    expect(key.attributes("style")).toContain("var(--op-fit-full, 0px)");
    expect(wrapper.find("button").attributes("aria-label")).toBe("Enviar à cozinha");
  });

  it("sem curto, um texto só que some para o ícone", async () => {
    const wrapper = await mountSuspended(OperatorButton, {
      props: { label: "Imprimir", icon: "i-lucide-printer" },
    });
    expect(wrapper.findAll(".op-fit-text")).toHaveLength(1);
    expect(wrapper.find('[data-op-fit-variant="only"]').attributes("data-op-fit-last")).toBeUndefined();
  });

  it("sem ícone o último texto quebra linha (não há degrau só ícone)", async () => {
    const wrapper = await mountSuspended(OperatorButton, {
      props: { label: "Registrar sangria", shortLabel: "Sangria" },
    });
    expect(wrapper.find('[data-op-fit-variant="short"]').attributes("data-op-fit-last")).toBe("");
    expect(wrapper.find("button").attributes("data-op-fit-icon")).toBeUndefined();
  });

  it("botão que não encolhe não ganha dica nem conta", async () => {
    const wrapper = await mountSuspended(OperatorButton, { props: { label: "Registrar sangria" } });
    const button = wrapper.find("button");
    expect(button.attributes("title")).toBeUndefined();
    expect(button.attributes("data-op-fit")).toBeUndefined();
    expect(button.text()).toBe("Registrar sangria");
  });

  it("o title de quem chama (o motivo) vence a dica", async () => {
    const wrapper = await mountSuspended(OperatorButton, {
      props: { label: "Exibir", icon: "i-lucide-eye" },
      attrs: { title: "Exibir: Já está à vista." },
    });
    expect(wrapper.find("button").attributes("title")).toBe("Exibir: Já está à vista.");
  });

  it("dentro do grupo o contêiner é o grupo: o botão não escreve a própria conta", async () => {
    const Host = defineComponent({
      setup: () => () =>
        h(
          OperatorFitGroup,
          { actions: [{ label: "Salvar comanda", shortLabel: "Salvar", icon: "i-lucide-save" }] },
          () => h(OperatorButton, { label: "Salvar comanda", shortLabel: "Salvar", icon: "i-lucide-save" }),
        ),
    });
    const wrapper = await mountSuspended(Host);
    const group = wrapper.find("[data-operator-fit-group]");
    expect(group.classes()).toContain("op-fit-scope");
    expect(group.attributes("style")).toContain("--op-fit-full");
    expect(wrapper.find("button").attributes("style") ?? "").not.toContain("--op-fit-full");
  });
});
