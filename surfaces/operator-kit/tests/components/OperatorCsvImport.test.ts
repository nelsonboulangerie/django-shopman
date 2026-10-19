import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import OperatorCsvImport from "../../app/components/OperatorCsvImport.vue";

describe("OperatorCsvImport", () => {
  it("mostra totais e erro por linha, e confirma pela revisão", async () => {
    const wrapper = await mountSuspended(OperatorCsvImport, {
      props: {
        open: true,
        columns: [{ id: "name", header: "Nome", accessorKey: "name" }],
        rowKey: (row) => String(row.name),
        totalLabels: { new: "novo(s)", update: "atualizado(s)", skip: "sem mudança" },
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
      "1 novo(s) · 2 atualizado(s) · 1 sem mudança",
    );
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
    wrapper.unmount();
  });
});
