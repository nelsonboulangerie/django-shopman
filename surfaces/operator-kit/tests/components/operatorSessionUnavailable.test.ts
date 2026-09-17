import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorSessionUnavailable from "~/components/OperatorSessionUnavailable.vue";

// A tela do "não consegui perguntar". Ela não pede credencial nenhuma — quando o
// servidor é que não respondeu, não há o que digitar.
describe("OperatorSessionUnavailable", () => {
  it("diz que a pessoa continua conectada e não pede senha", async () => {
    const page = await mountSuspended(OperatorSessionUnavailable, {
      props: { scope: "os pedidos" },
    });

    expect(page.text()).toContain("Não foi possível conferir seu acesso");
    expect(page.text()).toContain("Você continua conectado");
    expect(page.text()).toContain("os pedidos");
    expect(page.findAll("input")).toHaveLength(0);
    expect(page.text()).not.toMatch(/senha/i);
  });

  it("oferece tentar de novo, e avisa quem a montou", async () => {
    const page = await mountSuspended(OperatorSessionUnavailable);

    const botao = page.findAll("button").find(b => b.text().includes("Tentar novamente"));
    expect(botao).toBeDefined();
    await botao!.trigger("click");
    expect(page.emitted("retry")).toHaveLength(1);
  });
});
