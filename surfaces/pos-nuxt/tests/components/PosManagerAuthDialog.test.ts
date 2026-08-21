import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosManagerAuthDialog from "~/components/PosManagerAuthDialog.vue";

const MANAGERS = [
  { username: "marina", name: "Marina" },
  { username: "nelson", name: "Nelson" },
];

function props(overrides: Record<string, unknown> = {}) {
  return {
    open: true,
    reasonText: "Retirar dinheiro da gaveta é exceção auditada: um gerente precisa autorizar.",
    managers: MANAGERS,
    busy: false,
    error: "",
    ...overrides,
  };
}

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;

// O UiDialog TELEPORTA o conteúdo para o body, fora da árvore do wrapper. Por isso
// as buscas são no documento — e por isso a limpeza abaixo não é zelo: sem ela o
// diálogo de um teste sobrevive no body e o próximo clica no botão do anterior.
let mounted: Wrapper | null = null;

async function open(overrides: Record<string, unknown> = {}): Promise<Wrapper> {
  mounted = await mountSuspended(PosManagerAuthDialog, { props: props(overrides) });
  return mounted;
}

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

const byText = (text: string) =>
  Array.from(document.querySelectorAll("button")).find((b) => (b.textContent || "").includes(text));

async function typePin(wrapper: Wrapper, digits: string) {
  for (const digit of digits) {
    byText(digit)!.click();
    await wrapper.vm.$nextTick();
  }
}

async function confirmPin(wrapper: Wrapper) {
  document.querySelector<HTMLButtonElement>('button[aria-label="Confirmar"]')!.click();
  await wrapper.vm.$nextTick();
}

describe("PosManagerAuthDialog — quem assina vem da lista", () => {
  it("oferece os gerentes e não pede nome digitado", async () => {
    await open();

    expect(document.body.textContent).toContain("Marina");
    expect(document.body.textContent).toContain("Nelson");
    expect(document.querySelector('input[aria-label="Nome do gerente"]')).toBeNull();
  });

  it("escolher o gerente revela o pad e a autorização sai com o username dele", async () => {
    const wrapper = await open();

    byText("Marina")!.click();
    await wrapper.vm.$nextTick();
    await typePin(wrapper, "1234");
    await confirmPin(wrapper);

    // `username`, não o nome de exibição: é por ele que o servidor resolve a
    // credencial e grava a assinatura em `approved_by`.
    expect(wrapper.emitted("authorize")?.[0]).toEqual(["marina", "1234"]);
  });

  it("mostra o motivo da autorização vindo do servidor", async () => {
    await open();
    expect(document.body.textContent).toContain("exceção auditada");
  });

  // Lista vazia (leitura negada, nenhum gerente com PIN) não pode fechar a única
  // porta: o balcão ficaria travado no meio de uma sangria.
  it("cai no campo de texto quando a lista chega vazia", async () => {
    const wrapper = await open({ managers: [] });

    const input = document.querySelector<HTMLInputElement>('input[aria-label="Nome do gerente"]');
    expect(input).not.toBeNull();

    input!.value = "marina";
    input!.dispatchEvent(new Event("input"));
    await wrapper.vm.$nextTick();

    // PIN de 4 dígitos: é o mínimo do servidor (`DOORMAN.PIN_MIN_LENGTH`), e a
    // peça compartilhada passou a cobrar o mesmo. A regra antiga do diálogo
    // aceitava qualquer tamanho e mandava o gerente tomar recusa garantida.
    await typePin(wrapper, "9999");
    await confirmPin(wrapper);

    expect(wrapper.emitted("authorize")?.[0]).toEqual(["marina", "9999"]);
  });

  // PIN errado limpa o PIN e SÓ o PIN. Reescolher o próprio nome a cada erro de
  // digitação é castigo sem razão, e no balcão a fila está esperando.
  it("preserva o gerente escolhido quando o servidor recusa o PIN", async () => {
    const wrapper = await open();

    byText("Marina")!.click();
    await wrapper.vm.$nextTick();
    await typePin(wrapper, "0000");

    await wrapper.setProps({ open: false });
    await wrapper.setProps({ error: "Aprovação gerencial inválida.", open: true });

    expect(document.body.textContent).toContain("Aprovação gerencial inválida.");
    expect(document.body.textContent).toContain("Trocar gerente");

    await typePin(wrapper, "1234");
    await confirmPin(wrapper);

    expect(wrapper.emitted("authorize")?.[0]).toEqual(["marina", "1234"]);
  });

  it("permite trocar o gerente escolhido", async () => {
    const wrapper = await open();

    byText("Marina")!.click();
    await wrapper.vm.$nextTick();
    byText("Trocar gerente")!.click();
    await wrapper.vm.$nextTick();

    expect(document.body.textContent).toContain("Nelson");
    expect(document.body.textContent).not.toContain("Trocar gerente");
  });
});
