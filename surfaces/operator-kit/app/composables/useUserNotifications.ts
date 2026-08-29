// Canal PESSOAL da pessoa (`user-<id>` no Django, `/sse/notifications` no BFF).
//
// Mora na layer porque a caixa é da PESSOA, não da tela: o mesmo aviso tem de
// alcançar quem está no Gestor, no PDV ou na Produção. Uma implementação, oito apps.
//
// O push só diz "chegou algo" (ADR-016) — quem manda é o refetch do fetch canônico,
// então uma mensagem perdida custa no máximo um ciclo de poll.
export function useUserNotifications(onPush: () => void) {
  const config = useRuntimeConfig();
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let source: EventSource | null = null;

  function connect() {
    if (source) return;
    const url = ssePath("/sse/notifications", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      // Qualquer aviso do canal pessoal justifica o refetch: o painel é barato
      // e distinguir categorias aqui só criaria um segundo lugar para errar.
      ["message", "user-notification"].forEach((name) =>
        source!.addEventListener(name, () => onPush()),
      );
      source.onopen = () => {
        realtime.value = "live";
      };
      source.onerror = () => {
        realtime.value = "polling";
      };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  // Voltar para a aba (ou para a rede) é motivo de reconciliar: enquanto
  // escondida, a tela pode ter perdido pushes.
  const onVisible = () => {
    if (document.visibilityState === "visible") onPush();
  };

  onMounted(() => {
    connect();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (source) {
      source.close();
      source = null;
    }
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  return { realtime };
}
