// Beta 06/11 (F12): cancelar pedido pago estorna no cartão DENTRO do pedido, e o
// gerente ficava ~6 s olhando um spinner mudo no botão do PIN. Com `busyText`, a
// tela diz o que está acontecendo enquanto espera.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";

import OperatorManagerAuth from "../../app/components/OperatorManagerAuth.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

async function mount(props: Record<string, unknown>) {
  mounted = await mountSuspended(OperatorManagerAuth, {
    props: { open: true, action: "cancel_order", managers: [], ...props },
    attachTo: document.body,
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

// O primeiro mount aquece o ambiente Nuxt; o padrão de 5 s não basta numa máquina cheia.
describe("OperatorManagerAuth: a espera longa diz o que acontece", { timeout: 60_000 }, () => {
  it("ocupado com texto de andamento mostra a frase", async () => {
    await mount({ busy: true, busyText: "Cancelando e estornando no cartão. Leva alguns segundos." });
    const status = document.body.querySelector("[data-manager-auth-busy]");
    expect(status?.textContent).toContain("Cancelando e estornando no cartão.");
  });

  it("parado, a frase some", async () => {
    await mount({ busy: false, busyText: "Cancelando e estornando no cartão. Leva alguns segundos." });
    expect(document.body.querySelector("[data-manager-auth-busy]")).toBeNull();
  });

  it("o motivo do cancelamento é o que acontece com o dinheiro", async () => {
    await mount({ detail: "R$ 5,10 serão estornados no cartão do cliente." });
    expect(document.body.textContent).toContain("R$ 5,10 serão estornados no cartão do cliente.");
    expect(document.body.textContent).not.toContain("A venda já foi fechada.");
  });
});
