// As seções do B.I., com a janela de análise na query de cada uma. A lista e os
// ícones moram na presentation (`biSections`, testada); aqui só entra a URL viva.
import { biSections } from "~/presentation/biSections";

export function useBiSections() {
  const { windowQuery } = useBiWindow();
  const sections = computed(() => biSections(new URLSearchParams(windowQuery.value).toString()));
  return { sections };
}
