import { beforeEach, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import Review from "../../app/components/CatalogBindingReview.vue";
for (const [key, value] of Object.entries({ computed, ref, watch })) vi.stubGlobal(key, value);
const confirm = vi.fn();
const item = () => ({ item_id: "remote-1", product_ref: "remote-product", category_ref: "category", item_context_ref: "", name: "Pão remoto", description: "Descrição original", price: "19.90", status: "AVAILABLE", external_code: "SKU", image_path: "remote/photo.jpg", notice: "Revise o vínculo", candidates: [{ sku: "SKU", name: "Produto exemplo" }], binding: null, needs_review: true, base_revision: "v1", can_bind: true, blocked_reason: "" });
const board = () => ({ items: [item()], products: [{ sku: "SKU", name: "Produto exemplo" }] });
const render = (data: any = board(), options = {}) => mount(Review, { props: { board: data, busy: false, stale: false, confirm, ...options } });
beforeEach(() => { confirm.mockReset(); });
const button = (wrapper: ReturnType<typeof render>, text: string) => wrapper.findAll("button").find(b => b.text() === text)!;

it("não seleciona a sugestão automaticamente e exige prévia antes de confirmar", async () => {
  confirm.mockResolvedValue(true);
  const wrapper = render();
  expect((wrapper.get("select").element as HTMLSelectElement).value).toBe("");
  expect(confirm).not.toHaveBeenCalled();
  await wrapper.get("select").setValue("SKU");
  expect(button(wrapper, "Confirmar vínculo local")).toBeUndefined();
  await button(wrapper, "Revisar vínculo").trigger("click");
  expect(wrapper.text()).toContain("Não copia fotos, preços ou descrições");
  await button(wrapper, "Confirmar vínculo local").trigger("click");
  await flushPromises();
  expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ item_id: "remote-1" }), "SKU", "v1");
  expect((wrapper.get("select").element as HTMLSelectElement).value).toBe("");
});

it("falha mantém a escolha e a prévia para recuperar a mesma intenção", async () => {
  confirm.mockResolvedValue(false);
  const wrapper = render();
  await wrapper.get("select").setValue("SKU");
  await button(wrapper, "Revisar vínculo").trigger("click");
  await button(wrapper, "Confirmar vínculo local").trigger("click");
  await flushPromises();
  expect((wrapper.get("select").element as HTMLSelectElement).value).toBe("SKU");
  expect(button(wrapper, "Confirmar vínculo local")).toBeDefined();
});

it("mudança concorrente exige nova revisão explícita", async () => {
  const data = board();
  const wrapper = render(data);
  await wrapper.get("select").setValue("SKU");
  await button(wrapper, "Revisar vínculo").trigger("click");
  await wrapper.setProps({ board: { ...data, items: [{ ...data.items[0], base_revision: "v2" }] } as any });
  expect(button(wrapper, "Confirmar vínculo local").attributes("disabled")).toBeDefined();
  await button(wrapper, "Revisar com os dados atuais").trigger("click");
  expect(button(wrapper, "Confirmar vínculo local")).toBeUndefined();
  await button(wrapper, "Revisar vínculo").trigger("click");
  await button(wrapper, "Confirmar vínculo local").trigger("click");
  expect(confirm).toHaveBeenCalledWith(expect.anything(), "SKU", "v2");
});

it("leitura indisponível conserva seleção mas bloqueia confirmação", async () => {
  const wrapper = render();
  await wrapper.get("select").setValue("SKU");
  await button(wrapper, "Revisar vínculo").trigger("click");
  await wrapper.setProps({ stale: true });
  expect(button(wrapper, "Confirmar vínculo local").attributes("disabled")).toBeDefined();
  expect((wrapper.get("select").element as HTMLSelectElement).value).toBe("SKU");
  expect(confirm).not.toHaveBeenCalled();
});

it("conteúdo remoto é texto e não dispara imagens ou HTML externos", () => {
  const data = board();
  data.items[0]!.description = '<img src="https://example.com/tracker" onerror="alert(1)">';
  const wrapper = render(data);
  expect(wrapper.find("img").exists()).toBe(false);
  expect(wrapper.text()).toContain('<img src="https://example.com/tracker"');
});

it("vínculo de outra captura continua pendente sem escolha automática", () => {
  const data: any = board();
  data.items[0].binding = { name: "Produto exemplo", sku: "SKU", snapshot_id: 1 };
  const wrapper = render(data);
  expect(wrapper.text()).toContain("1 pendentes de revisão");
  expect(wrapper.text()).toContain("Vínculo confirmado em outra captura");
  expect((wrapper.get("select").element as HTMLSelectElement).value).toBe("");
});
