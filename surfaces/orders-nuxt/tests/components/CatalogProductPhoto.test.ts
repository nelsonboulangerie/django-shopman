import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import CatalogProductPhoto from "../../app/components/CatalogProductPhoto.vue";

vi.stubGlobal("ref", ref);
vi.stubGlobal("httpErrorMessage", (_error: unknown, fallback: string) => fallback);

async function pick(wrapper: ReturnType<typeof mount>, size = 10) {
  const file = new File([new Uint8Array(size)], "foto.png", { type: "image/png" });
  const input = wrapper.get("[data-testid='photo-input']");
  Object.defineProperty(input.element, "files", { value: [file] });
  await input.trigger("change");
  await new Promise((resolve) => setTimeout(resolve, 20));
  await flushPromises();
}

describe("foto do produto por arquivo", () => {
  it("padroniza, guarda e entrega a URL a quem usa", async () => {
    const enhance = vi.fn(async () => "data:image/jpeg;base64,PADRAO");
    const upload = vi.fn(async () => "https://media/foto.jpg");
    const wrapper = mount(CatalogProductPhoto, { props: { enhance, upload, testid: "photo" } });
    await pick(wrapper);
    expect(enhance).toHaveBeenCalledOnce();
    await wrapper.get("[data-testid='photo-use']").trigger("click");
    await flushPromises();
    expect(upload).toHaveBeenCalledWith("data:image/jpeg;base64,PADRAO");
    expect(wrapper.emitted("stored")).toEqual([["https://media/foto.jpg"]]);
    expect(wrapper.get("[data-testid='photo-use']").text()).toContain("Foto guardada");
  });

  it("sem o ajuste, a original ainda pode ser guardada", async () => {
    const enhance = vi.fn(async () => {
      throw new Error("503");
    });
    const upload = vi.fn(async () => "https://media/original.png");
    const wrapper = mount(CatalogProductPhoto, { props: { enhance, upload, testid: "photo" } });
    await pick(wrapper);
    expect(wrapper.text()).toContain("A original ainda pode ser usada");
    await wrapper.get("[data-testid='photo-use']").trigger("click");
    await flushPromises();
    expect(upload.mock.calls[0]![0]).toMatch(/^data:image\/png;base64,/);
    expect(wrapper.emitted("stored")).toEqual([["https://media/original.png"]]);
  });

  it("recusa foto acima de 8 MB sem chamar o servidor", async () => {
    const enhance = vi.fn();
    const wrapper = mount(CatalogProductPhoto, {
      props: { enhance, upload: vi.fn(), testid: "photo" },
    });
    await pick(wrapper, 8 * 1024 * 1024 + 1);
    expect(wrapper.text()).toContain("A foto é grande demais (máximo 8 MB).");
    expect(enhance).not.toHaveBeenCalled();
  });
});
