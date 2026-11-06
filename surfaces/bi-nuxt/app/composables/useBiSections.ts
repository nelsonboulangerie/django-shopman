// As seções do B.I., com a janela de análise na query de cada uma. A lista e os
// ícones moram na presentation (`biSections`, testada); aqui só entra a URL viva e a
// persona da antessala (`surface_role`), que decide se o Caixa aparece.
import { biSections, type BiSurfaceRole } from "~/presentation/biSections";

export function useBiSections() {
  const { windowQuery } = useBiWindow();
  const { data: session } = useNuxtData<{ surface_role?: BiSurfaceRole }>("operator-session");
  const sections = computed(() =>
    biSections(new URLSearchParams(windowQuery.value).toString(), session.value?.surface_role ?? null),
  );
  return { sections };
}
