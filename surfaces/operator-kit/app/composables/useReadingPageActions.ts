// As ações de uma página de leitura, como DADOS para o `OperatorPageHeader`
// (`:actions` e `:actions-label`): "Copiar link desta leitura" primeiro, depois as da
// página. O período, o dia e os recortes vivem na URL, então o endereço É a leitura.
// O mesmo conteúdo do `OperatorReadingPageMenu`, que segue para quem monta o ⋯ fora
// do cabeçalho; dentro dele, a regra do celular (README "Barra do topo no celular")
// pede as ações em dados, para o kit decidir o que vira ícone e o que vai para o ⋯.
import { computed, toValue, type MaybeRefOrGetter } from "vue";

import type { OperatorHeaderAction } from "../presentation/pageHeader";
import { usePendingAction } from "./usePendingAction";

export function useReadingPageActions(items: MaybeRefOrGetter<readonly OperatorHeaderAction[]> = []) {
  const { run: copyLink } = usePendingAction(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      useSonner.success("Link copiado: quem abrir vê esta mesma leitura.");
    } catch {
      useSonner.warning("Não deu para copiar. O endereço na barra do navegador é o link desta leitura.");
    }
  });

  const actions = computed<OperatorHeaderAction[]>(() => [
    { label: "Copiar link desta leitura", icon: "i-lucide-link", onSelect: () => void copyLink() },
    ...toValue(items),
  ]);

  // O nome do ⋯ diz o que ele guarda (omotenashi-copy: rótulo que mente).
  const label = computed(() => {
    const own = toValue(items);
    return own.length
      ? `Mais: copiar link e ${own.map((item) => String(item.label ?? "").toLowerCase()).join(", ")}`
      : "Mais: copiar link desta leitura";
  });

  return { actions, label };
}
