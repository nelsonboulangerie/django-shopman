import { computed, type Ref } from "vue";
import { useGridEdit } from "../../../operator-kit/app/composables/useGridEdit";
import { csvMoneyToCents } from "../../../operator-kit/app/presentation/csv";
import { parseGrid } from "../../../operator-kit/app/presentation/gridEdit";

/** Edição e colagem na ordem visível, sem gravar antes de validar cada insumo. */
export function usePurchaseGridFields(
  inputs: Ref<Record<string, string>>,
  kind: "cost" | "minimum",
) {
  const grid = useGridEdit<string>();
  grid.draft.value = inputs.value;
  function set(sku: string, value: string) {
    grid.set(sku, value);
    inputs.value = grid.draft.value;
  }
  function undo() {
    grid.undo();
    inputs.value = grid.draft.value;
  }
  function clear(keys?: readonly string[]) {
    grid.clear(keys);
    inputs.value = grid.draft.value;
  }
  function error(value: string): string {
    if (!value.trim()) return "";
    if (kind === "cost") {
      const amount = csvMoneyToCents(value.replace(/^R\$\s*/, ""));
      return amount === null || amount <= 0
        ? "Informe um valor de compra maior que zero."
        : "";
    }
    const amount = Number(
      value.includes(",")
        ? value.trim().replace(/\./g, "").replace(",", ".")
        : value.trim(),
    );
    return !/^\d+(?:[.,]\d+)*$/.test(value.trim()) ||
      !Number.isFinite(amount) ||
      amount < 0
      ? "Informe uma quantidade válida."
      : "";
  }
  const errors = computed(() =>
    Object.fromEntries(
      Object.entries(inputs.value)
        .map(([sku, value]) => [sku, error(value)])
        .filter(([, message]) => message),
    ),
  );
  function errorsFor(rows: readonly { sku: string }[]) {
    const visible = new Set(rows.map((row) => row.sku));
    return Object.fromEntries(
      Object.entries(errors.value).filter(([sku]) => visible.has(sku)),
    );
  }
  function paste(
    event: ClipboardEvent,
    startSku: string,
    rows: { sku: string }[],
  ) {
    const text = event.clipboardData?.getData("text/plain") || "";
    // Uma coluna com vírgula decimal não é CSV com duas colunas.
    const cells = /[\t;]/.test(text)
      ? parseGrid(text)
      : text
          .trimEnd()
          .split(/\r?\n/)
          .map((value) => [value.trim().replace(/^"(.*)"$/, "$1")]);
    if (!cells.length) return;
    event.preventDefault();
    const start = rows.findIndex((row) => row.sku === startSku);
    if (start < 0) return;
    cells.forEach((row, index) => {
      const target = rows[start + index];
      if (target && row[0]?.trim()) set(target.sku, row[0]);
    });
  }
  return { set, undo, clear, paste, errors, errorsFor, canUndo: grid.canUndo };
}
