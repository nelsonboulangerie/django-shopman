// Etiquetas de timer — a fileira de disparo de um toque da página /timers.
//
// A LISTA é do servidor (o gestor cura no Admin, e o que um padeiro cria vale
// para os outros); o TIMER continua sendo do aparelho (useFloorTimers). São
// dois assuntos e ficam em dois lugares: perder a rede não pode apagar um
// lembrete que já está correndo, e a lista velha em cache ainda dispara.
//
// Criar deduplica no SERVIDOR: "Pausa-café" e "pausa cafe" são a mesma coisa, e
// a resposta diz se nasceu (``created``) ou se já existia. Os dois casos são
// sucesso — o que muda é só o que a tela avisa.
import type { TimerTagLike } from "~/presentation/timers";

export interface TimerTagProjection extends TimerTagLike {
  origin: "admin" | "operator";
}

interface TimerTagsResponse {
  tags: TimerTagProjection[];
}

interface TimerTagCreateResponse {
  tag: TimerTagProjection;
  created: boolean;
}

export interface CreateTagResult {
  ok: boolean;
  tag?: TimerTagProjection;
  created?: boolean;
  message?: string;
}

const PATH = "/api/v1/backstage/production/timer-tags/";

export function useTimerTags() {
  const { data, pending, error, refresh } = useFetch<TimerTagsResponse>(PATH, {
    key: "production-timer-tags",
    server: true,
    onResponseError: operatorSessionOnError,
  });

  const tags = computed<TimerTagProjection[]>(() => data.value?.tags ?? []);
  const forbidden = computed(() => httpError(error.value).status === 403);

  // Catálogo curado no Admin: muda algumas vezes por mês, não por minuto. Um
  // poll calmo basta para o tablet que fica aberto o dia todo pegar a etiqueta
  // nova que outro turno criou.
  useAdaptivePoll(refresh, () => 300_000);

  const saving = ref(false);

  async function createTag(
    label: string,
    minutes: number,
  ): Promise<CreateTagResult> {
    if (saving.value) return { ok: false };
    saving.value = true;
    try {
      const response = await $fetch<TimerTagCreateResponse>(PATH, {
        method: "POST",
        body: { label, minutes },
      });
      await refresh();
      return { ok: true, tag: response.tag, created: response.created };
    } catch (err) {
      const message = httpErrorMessage(
        err,
        "Não foi possível guardar a etiqueta. O timer segue correndo.",
      );
      useSonner.error(message);
      return { ok: false, message };
    } finally {
      saving.value = false;
    }
  }

  return { tags, pending, error, forbidden, refresh, createTag, saving };
}
