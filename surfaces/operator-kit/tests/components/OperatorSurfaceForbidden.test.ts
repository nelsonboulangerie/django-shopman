// A recusa de app tem saída (beta 05/11, CEN-04, PDV2-15, CEN-11): a Produção, o B.I.,
// o Compras e o Gestor recusavam a Caixa sem nenhum botão, e num app instalado ela ficava
// presa ali. Uma recusa só na suíte, com "Trocar operador" e "Voltar à Central", e o nome
// do app com o artigo da identidade ("as Compras").
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import OperatorSurfaceForbidden from "../../app/components/OperatorSurfaceForbidden.vue";

const lock = vi.fn(async () => {});

vi.mock("../../app/composables/useOperatorLock", () => ({
  useOperatorLock: () => ({ operator: ref({ id: 3, name: "Fran" }), lock }),
}));

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  lock.mockClear();
});

describe("OperatorSurfaceForbidden", () => {
  it("diz o app com o artigo dele e quem está identificado", async () => {
    mounted = await mountSuspended(OperatorSurfaceForbidden, {
      props: { perm: "buyman.operate", identity: { label: "Compras", article: "as" } },
    });
    expect(mounted.find("h2").text()).toBe("Seu acesso não inclui as Compras");
    expect(mounted.text()).toContain("Você entrou como Fran.");
    expect(mounted.text()).toContain("Entrar de novo não resolve");
    expect(mounted.text()).not.toMatch(/[—–]/);
  });

  it("trocar operador trava a tela para quem tem o acesso se identificar", async () => {
    mounted = await mountSuspended(OperatorSurfaceForbidden, {
      props: { perm: "buyman.operate", identity: { label: "Compras", article: "as" } },
    });
    const swap = mounted.findAll("button").find((button) => button.text().includes("Trocar operador"));
    expect(swap).toBeDefined();
    await swap!.trigger("click");
    expect(lock).toHaveBeenCalledTimes(1);
  });

  it("cala o convite de instalar enquanto está na tela", async () => {
    const quiet = useState<boolean>("operator-pwa-quiet", () => false);
    mounted = await mountSuspended(OperatorSurfaceForbidden, {
      props: { perm: "x", identity: { label: "PDV", article: "o" } },
    });
    expect(quiet.value).toBe(true);
    mounted.unmount();
    mounted = null;
    expect(quiet.value).toBe(false);
  });
});
