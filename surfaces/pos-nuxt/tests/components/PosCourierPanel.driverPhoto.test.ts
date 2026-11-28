// A foto do entregador no painel da corrida do PDV (#3150, decisão do dono em 22/11):
// a mesma do Gestor (`photo_url` do bloco da corrida, servida pelo servidor e só
// enquanto a corrida vive). Sem foto, o ícone de sempre.
import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCourierPanel from "~/components/PosCourierPanel.vue";
import type { PreorderCourier } from "~/types/preorders";

enableAutoUnmount(afterEach);

const PHOTO = "/api/v1/backstage/deliveries/776753357/driver-photo/";

function courier(driver: PreorderCourier["driver"]): PreorderCourier {
  return {
    provider: "machine", status: "A", ride_state: "accepted", status_label: "A caminho", active: true, driver,
    tracking_url: "", confirmation_code: "", attempts_count: 0, error: null, can_dispatch: false,
    can_dispatch_again: false, can_cancel: false,
  };
}

const card = { courier_label: "A caminho", courier_tone: "neutral" };
const driver = { name: "Carlos", phone: "", vehicle_plate: "", vehicle_model: "" };

describe("PosCourierPanel: a foto do entregador", () => {
  it("com a corrida viva, mostra a foto com o nome", async () => {
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ ...driver, photo_url: PHOTO }), card, busy: false },
    });
    const block = wrapper.get("[data-pos-courier-driver-photo]");
    expect(block.text()).toContain("Carlos");
    expect(block.find("img").attributes("src")).toBe(PHOTO);
    expect(block.find("img").attributes("alt")).toBe("Carlos");
  });

  it("sem foto, o ícone de sempre", async () => {
    const wrapper = await mountSuspended(PosCourierPanel, {
      props: { courier: courier({ ...driver, photo_url: "" }), card, busy: false },
    });
    expect(wrapper.find("[data-pos-courier-driver-photo]").exists()).toBe(false);
    expect(wrapper.get("[data-pos-courier-driver]").text()).toContain("Carlos");
  });
});
