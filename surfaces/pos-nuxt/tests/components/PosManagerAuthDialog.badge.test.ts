import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosManagerAuthDialog from "~/components/PosManagerAuthDialog.vue";

// O CRACHÁ VALE NA HORA DA SANGRIA — e é por isso que esta suíte existe.
//
// A identificação era desenhada por três componentes diferentes, e só o da tela
// de bloqueio sabia ler crachá. Sangria, pedido de troco e cancelamento de venda
// são exatamente a hora em que o gerente aparece no balcão, e era ali que o
// crachá no pescoço dele não servia para nada: ele digitava o nome à mão.
//
// Agora os três usam o `OperatorIdentify` do operator-kit. Estes testes provam
// que a peça compartilhada está de fato ligada AQUI, não só na tela de bloqueio.

const MANAGERS = [{ username: "joyce", name: "Joyce" }];
const BADGE = "4337f822b0e6"; // 12 hex: o formato que `isLikelyBadge` aceita

/** Emula um leitor HID: teclas rápidas no documento e Enter. */
function scan(token: string) {
  for (const char of token) {
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: char, bubbles: true, cancelable: true }),
    );
  }
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
  );
}

async function open(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(PosManagerAuthDialog, {
    props: { open: true, managers: MANAGERS, reasonText: "Retirar dinheiro", ...props },
  });
  await wrapper.vm.$nextTick();
  return wrapper;
}

describe("PosManagerAuthDialog — o crachá autoriza", () => {
  it("passar o crachá emite a autorização, sem escolher ninguém na lista", async () => {
    const wrapper = await open();

    scan(BADGE);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("authorizeBadge")?.[0]).toEqual([BADGE]);
  });

  it("não confunde o crachá com o PIN: nada de `authorize` no caminho do crachá", async () => {
    const wrapper = await open();

    scan(BADGE);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("authorize")).toBeUndefined();
  });

  // A regra de TEMPO (dedo × leitor) não se testa aqui: ela é pura e mora em
  // `operator-kit/tests/operatorLock.test.ts`, onde o intervalo entra como
  // número e não depende de relógio. Reproduzir aqui com relógio real dava um
  // teste que passava ou falhava conforme a máquina — instável, e provando
  // menos do que o teste puro já prova.

  it("com o diálogo fechado o leitor fica quieto", async () => {
    const wrapper = await open({ open: false });

    scan(BADGE);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("authorizeBadge")).toBeUndefined();
  });

  it("ocupado não aceita leitura: evita duas autorizações pelo mesmo gesto", async () => {
    const wrapper = await open({ busy: true });

    scan(BADGE);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("authorizeBadge")).toBeUndefined();
  });
});
