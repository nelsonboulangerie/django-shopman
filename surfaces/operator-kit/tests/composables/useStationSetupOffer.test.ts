// A oferta "Vincular este dispositivo a um posto de trabalho?" aparece ao abrir o app e,
// sem resposta, some na primeira troca de tela, só nesta abertura (KISS, dono 28/11:
// antes ela seguia no topo de toda tela, ~110 px empurrando o trabalho para baixo).
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";

import {
  useStationSetupOffer,
  useStationSetupRequest,
} from "../../app/composables/useStationSetupOffer";

async function setup() {
  let api!: ReturnType<typeof useStationSetupOffer> & {
    request: ReturnType<typeof useStationSetupRequest>;
  };
  await mountSuspended(
    defineComponent({
      setup() {
        api = {
          ...useStationSetupOffer({ canIdentify: ref(true), locked: ref(false), stationRef: ref("") }),
          request: useStationSetupRequest(),
        };
        return () => h("div");
      },
    }),
  );
  return api;
}

// O router de verdade: a oferta escuta o `afterEach` dele.
async function navigate(to: string) {
  await useRouter().push(to);
}

describe("useStationSetupOffer: a oferta não persegue o operador de tela em tela", () => {
  beforeEach(async () => {
    await useRouter().push("/");
    window.localStorage.clear();
    useStationSetupRequest().requested.value = false;
  });

  it("aparece ao abrir e some na primeira troca de tela, sem virar lembrete", async () => {
    const { offer } = await setup();
    expect(offer.value).toBe(true);

    await navigate("/plan");
    expect(offer.value).toBe(false);
    expect(window.localStorage.getItem("shopman.stationSetup.dismissed")).toBeNull();
  });

  it("trocar só a query não conta como trocar de tela", async () => {
    const { offer } = await setup();
    await navigate("/?day=amanha");
    expect(offer.value).toBe(true);
  });

  it("o pedido explícito (Vincular a um caixa do PDV) não some ao navegar", async () => {
    const { offer, request } = await setup();
    request.request();
    await navigate("/sale");
    expect(offer.value).toBe(true);
  });
});
