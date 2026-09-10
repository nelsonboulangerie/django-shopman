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
  state: "ready" | "degraded" | "blocked" | "unknown";
  reason_code: string;
  version: number;
  ready: boolean;
  checked_at: string;
  facts_as_of: string | null;
  fresh_until: string | null;
  source_status: string;
  reason: string;
  action: string;
  limitation: string;
  in_use: boolean;
};

export function usePlatforms() {
  const { data, refresh, pending, error } = useFetch<{ platforms: Platform[] }>(
    "/api/v1/backstage/marketing/platforms/",
    { key: "marketing-platforms", onResponseError: operatorSessionOnError },
  );

  const platforms = computed(() => data.value?.platforms ?? []);

  /** Bloqueadas primeiro, depois limitadas, depois as saudáveis: urgência em cima. */
  const sorted = computed(() =>
    [...platforms.value].sort((a, b) => rank(a) - rank(b)),
  );

  function rank(p: Platform): number {
    if (p.state === "blocked") return 0;
    if (p.state === "unknown") return 1;
    if (p.state === "degraded") return 2;
    return 3;
  }

  return { platforms: sorted, loading: pending, error, load: refresh };
}
