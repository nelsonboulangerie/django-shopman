// "Sobrou ou faltou?" de um dia. O dia e a base de comparação moram na URL
// (`?day=2026-10-03&compare=last`, prévia `bi-sobra4.html`, pinos 2 e 4): o link colado
// abre a mesma leitura, e o voltar do navegador volta o dia. Sem `day`, o servidor lê
// o último dia aberto (o "ontem" da casa); sem `compare`, o típico de 4 semanas.
// Leitura calma: sem poll, como o resto do B.I.
import type { BIOverShortReport, BIReading } from "~/types/bi";
import { COMPARE_KEYS, type CompareKey } from "~/presentation/overShort";

export function useBiOverShort() {
  const route = useRoute();
  const router = useRouter();

  const day = computed(() => (typeof route.query.day === "string" ? route.query.day : ""));
  const compare = computed<CompareKey>(() => {
    const raw = typeof route.query.compare === "string" ? route.query.compare : "";
    return (COMPARE_KEYS as readonly string[]).includes(raw) ? (raw as CompareKey) : "typical";
  });

  const { data, pending, error, refresh } = useFetch<BIReading<BIOverShortReport>>("/api/v1/backstage/bi/over-short/", {
    key: "bi-over-short",
    server: true,
    query: computed(() => ({
      ...(day.value ? { day: day.value } : {}),
      ...(compare.value !== "typical" ? { compare: compare.value } : {}),
    })),
    onResponseError: operatorSessionOnError,
  });

  const report = computed(() => data.value?.bi ?? null);
  const freshness = computed(() => ({ generated_at: data.value?.generated_at ?? null }));

  function setDay(next: string) {
    if (!next) return;
    void router.replace({ query: { ...route.query, day: next } });
  }

  function setCompare(next: string) {
    const rest = { ...route.query };
    delete rest.compare;
    void router.replace({ query: next && next !== "typical" ? { ...rest, compare: next } : rest });
  }

  return { report, freshness, pending, error, refresh, day, setDay, compare, setCompare };
}
