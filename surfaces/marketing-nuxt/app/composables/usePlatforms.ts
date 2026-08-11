// Por onde a padaria consegue falar, e o que falta em cada lugar.
//
// Existe porque o estado das plataformas não tinha casa: vazava para o painel de revisão,
// primeiro como ação dentro de um alerta, depois como botão no cabeçalho. Ver
// `docs/plans/MARKETING-UX-PLAN.md`.
//
// ⚠️ Plataforma ≠ canal. Canal é por onde se VENDE (web, PDV, iFood); plataforma é por onde
// o anúncio SAI (Instagram, Facebook, WhatsApp). A ADR-020 §10 fixou essa distinção.
export type Platform = {
  platform: string;
  label: string;
  /** `publication` (uma peça) ou `direct_message` (uma mensagem por pessoa). */
  kind: string;
  ready: boolean;
  reason: string;
  action: string;
  limitation: string;
  in_use: boolean;
};

export function usePlatforms() {
  const { data, refresh, pending } = useFetch<{ platforms: Platform[] }>(
    "/api/v1/backstage/marketing/platforms/",
    { key: "marketing-platforms" },
  );

  const platforms = computed(() => data.value?.platforms ?? []);

  /** Bloqueadas primeiro, depois limitadas, depois as saudáveis: urgência em cima. */
  const sorted = computed(() =>
    [...platforms.value].sort((a, b) => rank(a) - rank(b)),
  );

  function rank(p: Platform): number {
    if (!p.ready) return 0;
    if (p.limitation) return 1;
    return 2;
  }

  return { platforms: sorted, loading: pending, load: refresh };
}
