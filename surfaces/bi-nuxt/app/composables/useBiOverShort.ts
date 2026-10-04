// "Sobrou ou faltou?" de um dia. O dia mora na URL (`?day=2026-10-03`, prévia
// `bi-sobra4.html`, pino 2): o link colado abre a mesma leitura, e o voltar do
// navegador volta o dia. Sem `day`, o servidor lê o último dia aberto (o "ontem" da
// casa). Leitura calma: sem poll, como o resto do B.I.
import type { BIOverShortReport } from "~/types/bi";

export function useBiOverShort() {
  const route = useRoute();
  const router = useRouter();

  const day = computed(() => (typeof route.query.day === "string" ? route.query.day : ""));

  const { data, pending, error, refresh } = useFetch<{ bi: BIOverShortReport }>("/api/v1/backstage/bi/over-short/", {
    key: "bi-over-short",
    server: true,
    query: computed(() => (day.value ? { day: day.value } : {})),
    onResponseError: operatorSessionOnError,
  });

  const report = computed(() => data.value?.bi ?? null);

  function setDay(next: string) {
    if (!next) return;
    void router.replace({ query: { ...route.query, day: next } });
  }

  return { report, pending, error, refresh, day, setDay };
}
