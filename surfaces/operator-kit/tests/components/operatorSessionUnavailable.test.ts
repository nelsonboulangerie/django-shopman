import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorSessionUnavailable from "~/components/OperatorSessionUnavailable.vue";
import { OPERATOR_APP_NAME_STATE, operatorAppName } from "~/presentation/windowTitle";

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

  it("a página tem h1 (o nome do app) acima do aviso, que é h2", async () => {
    useState(OPERATOR_APP_NAME_STATE).value = operatorAppName("Nelson", "Gestor");
    const page = await mountSuspended(OperatorSessionUnavailable);

    expect(page.find("h1").text()).toBe("Nelson · Gestor");
    expect(page.find("h2").text()).toBe("Não foi possível conferir seu acesso");
    useState(OPERATOR_APP_NAME_STATE).value = null;
  });

  it("oferece tentar de novo, e avisa quem a montou", async () => {
    const page = await mountSuspended(OperatorSessionUnavailable);

    const botao = page.findAll("button").find(b => b.text().includes("Tentar de novo"));
    expect(botao).toBeDefined();
    await botao!.trigger("click");
    expect(page.emitted("retry")).toHaveLength(1);
  });
});
