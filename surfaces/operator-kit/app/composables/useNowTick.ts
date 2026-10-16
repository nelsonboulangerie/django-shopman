// O relógio da leitura: um timer monotônico só para todos os cartões e frases de
// frescor da tela; cada projeção fornece a âncora do servidor (`server_now_iso`,
// `generated_at`). Subiu do Gestor ao kit junto do `ReadFreshness` (PR-K2).
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const tick = ref<number>(0);
let timer: ReturnType<typeof setInterval> | null = null;
let refs = 0;

export function useNowTick(serverNow?: () => string) {
  const anchor = ref<{ server: number; monotonic: number } | null>(null);
  if (serverNow)
    watch(
      serverNow,
      (value) => {
        const server = Date.parse(value);
        anchor.value = Number.isFinite(server)
          ? { server, monotonic: performance.now() }
          : null;
      },
      { immediate: true },
    );
  onMounted(() => {
    refs += 1;
    if (!timer)
      timer = setInterval(() => {
        tick.value += 1;
      }, 1000);
  });
  onBeforeUnmount(() => {
    refs = Math.max(0, refs - 1);
    if (refs === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  });
  return computed(() => {
    void tick.value;
    return anchor.value
      ? anchor.value.server +
          Math.max(0, performance.now() - anchor.value.monotonic)
      : Date.now();
  });
}
