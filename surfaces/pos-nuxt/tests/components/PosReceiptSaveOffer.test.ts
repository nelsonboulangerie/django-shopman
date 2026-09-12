import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h, nextTick } from "vue";
import PosReceiptSaveOffer from "~/components/PosReceiptSaveOffer.vue";
import { receiptContactOffer } from "~/presentation/receiptContact";

const EMAIL = receiptContactOffer({ field: "email", typed: "novo@example.org", customer: null });
const TAX = receiptContactOffer({ field: "tax_id", typed: "52998224725", customer: { name: "Ana", tax_id: "11144477735" } });
let wrapper: Awaited<ReturnType<typeof mountSuspended>> | null = null;
afterEach(() => { wrapper?.unmount(); wrapper = null; document.body.innerHTML = ""; });

describe("PosReceiptSaveOffer — escolha inline", () => {
  it.each([EMAIL, TAX])("digitar dado válido não abre popover nem confirmação", async (offer) => {
    wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer, checked: false },
      slots: { default: () => h("input", { "aria-label": "Dado do documento" }) }, attachTo: document.body,
    });
    const input = wrapper.find("input").element as HTMLInputElement;
    input.focus(); await nextTick();
    expect(document.querySelector('[role="dialog"], [role="alertdialog"]')).toBeNull();
    expect(document.activeElement).toBe(input);
    expect(wrapper.find('[role="switch"]').attributes("aria-checked")).toBe("false");
    expect(wrapper.emitted("update:checked")).toBeUndefined();
  });
  it("switch é a ação explícita para salvar; desmarcar continua disponível", async () => {
    wrapper = await mountSuspended(PosReceiptSaveOffer, { props: { offer: EMAIL, checked: false } });
    await wrapper.find('[role="switch"]').trigger("click");
    expect(wrapper.emitted("update:checked")?.at(-1)).toEqual([true]);
    await wrapper.setProps({ checked: true });
    await wrapper.find('[role="switch"]').trigger("click");
    expect(wrapper.emitted("update:checked")?.at(-1)).toEqual([false]);
  });
  it("trocar CPF cadastrado ainda exige reconfirmação depois de marcar", async () => {
    wrapper = await mountSuspended(PosReceiptSaveOffer, { props: { offer: TAX, checked: false } });
    expect(wrapper.find('[role="alertdialog"]').exists()).toBe(false);
    await wrapper.find('[role="switch"]').trigger("click");
    await wrapper.setProps({ checked: true });
    expect(wrapper.find('[role="alertdialog"]').text()).toContain(TAX.confirmPrompt);
    expect(wrapper.emitted("update:confirmed")).toBeUndefined();
    const confirm = wrapper.findAll("button").find((button) => button.text().includes("Sim, trocar o CPF"))!;
    await confirm.trigger("click");
    expect(wrapper.emitted("update:confirmed")?.at(-1)).toEqual([true]);
    await wrapper.setProps({ confirmed: true });
    await wrapper.setProps({ offer: { ...TAX, typed: "12345678909" } });
    expect(wrapper.emitted("update:confirmed")?.at(-1)).toEqual([false]);
  });
  it("sem oferta apenas o campo permanece", async () => {
    const offer = receiptContactOffer({ field: "email", typed: "", customer: null });
    wrapper = await mountSuspended(PosReceiptSaveOffer, { props: { offer, checked: false }, slots: { default: () => h("input") } });
    expect(wrapper.find("input").exists()).toBe(true);
    expect(wrapper.find('[role="switch"]').exists()).toBe(false);
  });
});
