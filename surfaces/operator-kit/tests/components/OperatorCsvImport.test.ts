import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import OperatorCsvImport from "../../app/components/OperatorCsvImport.vue";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("OperatorCsvImport", () => {
  it("mostra totais e erro por linha, e confirma pela revisão", async () => {
    const wrapper = await mountSuspended(OperatorCsvImport, {
      props: {
        open: true,
        columns: [{ id: "name", header: "Nome", accessorKey: "name" }],
        rowKey: (row) => String(row.name),
        totalLabels: { new: "novo", update: "atualizados", skip: "sem mudança" },
        preview: {
          rows: 4,
          totals: { new: 1, update: 2, skip: 1 },
          errors: [{ row: 7, detail: "Preço inválido." }],
          changes: [{ name: "Pão" }],
          base_revision: "revision-7",
        },
      },
    });

    expect(document.body.textContent).toContain(
      "1 novo · 2 atualizados · 1 sem mudança · 4 linhas lidas",
    );
    expect(document.body.textContent).toContain("1 linha com erro");
    expect(document.body.textContent).toContain("Linha 7: Preço inválido.");
    expect(
      document.querySelector("[data-import-apply]")?.hasAttribute("disabled"),
    ).toBe(true);

    await wrapper.setProps({
      preview: {
        rows: 1,
        totals: { new: 1, update: 0, skip: 0 },
        errors: [],
        changes: [{ name: "Pão" }],
        base_revision: "revision-8",
      },
    });
    (document.querySelector("[data-import-apply]") as HTMLElement).click();
    expect(wrapper.emitted("apply")?.at(-1)).toEqual(["revision-8"]);
    expect(document.body.textContent).toContain("1 linha lida");
    wrapper.unmount();
  });

  it("oferece um seletor em português e anuncia o arquivo escolhido", async () => {
    const readAsText = vi.fn();
    class FileReaderStub {
      result: string | ArrayBuffer | null = null;
      onload: ((event: ProgressEvent<FileReader>) => void) | null = null;

      readAsText(file: Blob, encoding?: string) {
        readAsText(file, encoding);
        this.result = "sku;nome\nP001;Pão";
        this.onload?.(new ProgressEvent("load") as ProgressEvent<FileReader>);
      }
    }
    vi.stubGlobal("FileReader", FileReaderStub);

    const wrapper = await mountSuspended(OperatorCsvImport, {
      props: {
        open: true,
        columns: [],
        rowKey: () => "row",
        preview: null,
      },
    });
    const input = document.querySelector<HTMLInputElement>('[data-import-picker] input[type="file"]')!;
    const trigger = document.querySelector<HTMLElement>('[data-import-picker] [data-slot="base"]')!;
    const state = document.querySelector<HTMLElement>("[data-import-file-state]")!;

    expect(trigger.textContent).toContain("Escolher arquivo CSV");
    expect(state.textContent?.trim()).toBe("Nenhum arquivo selecionado.");
    expect(trigger.getAttribute("role")).toBe("button");
    expect(trigger.getAttribute("tabindex")).toBe("0");
    expect(document.body.textContent).not.toMatch(/Choose File|No file chosen/);

    const file = new File(["sku;nome\nP001;Pão"], "catalogo.csv", { type: "text/csv" });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await wrapper.vm.$nextTick();

    expect(readAsText).toHaveBeenCalledWith(file, "utf-8");
    expect(wrapper.emitted("preview")?.at(-1)).toEqual(["sku;nome\nP001;Pão"]);
    expect(trigger.textContent).toContain("Trocar arquivo CSV");
    expect(state.textContent?.trim()).toBe("Arquivo selecionado: catalogo.csv");
    wrapper.unmount();
  });

  it("limpa o seletor antes de reabri-lo para aceitar o mesmo arquivo outra vez", async () => {
    const wrapper = await mountSuspended(OperatorCsvImport, {
      props: {
        open: true,
        columns: [],
        rowKey: () => "row",
        preview: null,
      },
    });
    const input = document.querySelector<HTMLInputElement>('[data-import-picker] input[type="file"]')!;
    const trigger = document.querySelector<HTMLElement>('[data-import-picker] [data-slot="base"]')!;
    const click = vi.spyOn(input, "click").mockImplementation(() => undefined);
    Object.defineProperty(input, "value", { configurable: true, writable: true, value: "catalogo.csv" });

    trigger.click();

    expect(input.value).toBe("");
    expect(click).toHaveBeenCalledOnce();
    wrapper.unmount();
  });
});
