<script setup lang="ts">
// A olhada rápida do celular (prévia `depois-marketing-bi-celular` (b), pino 7):
// deslizar para o lado troca de seção, na ordem do rail, e o pé da leitura mostra
// onde se está (os pontos) e para onde o deslizar leva ("Deslize para Caixa ›").
// Só no celular; do tablet para cima as seções estão no rail.
//
// O gesto não disputa com o que já rola de lado (a linha de chips, os gráficos
// largos): toque que começa num elemento rolável na horizontal não troca de seção.
import { swipeNeighbours } from "~/presentation/biSections";

const route = useRoute();
const router = useRouter();
const { sections } = useBiSections();
const isPhone = useMediaQuery("(max-width: 767.98px)");

const place = computed(() => swipeNeighbours(sections.value, route.path));

const SWIPE_MIN_PX = 80;
let start: { x: number; y: number } | null = null;

function scrollsSideways(target: EventTarget | null): boolean {
  let node = target instanceof HTMLElement ? target : null;
  while (node && node !== document.body) {
    if (node.closest("[data-no-swipe], input, textarea, select, [role='dialog']")) return true;
    const style = getComputedStyle(node);
    if ((style.overflowX === "auto" || style.overflowX === "scroll") && node.scrollWidth > node.clientWidth) return true;
    node = node.parentElement;
  }
  return false;
}

useEventListener(
  typeof document === "undefined" ? undefined : document,
  "touchstart",
  (event: TouchEvent) => {
    const touch = event.touches[0];
    start = isPhone.value && touch && !scrollsSideways(event.target) ? { x: touch.clientX, y: touch.clientY } : null;
  },
  { passive: true },
);
useEventListener(
  typeof document === "undefined" ? undefined : document,
  "touchend",
  (event: TouchEvent) => {
    const touch = event.changedTouches[0];
    if (!start || !touch) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    start = null;
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    const target = dx < 0 ? place.value.next : place.value.previous;
    if (target?.to) void router.push(target.to);
  },
  { passive: true },
);
</script>

<template>
  <nav
    v-if="place.index >= 0"
    class="mt-2 flex flex-col items-center gap-2 pb-1 md:hidden"
    aria-label="Seções do B.I. por deslize"
    data-bi-swipe
  >
    <ol class="flex items-center gap-1.5" aria-hidden="true">
      <li
        v-for="(section, index) in sections"
        :key="section.key"
        class="h-1.5 rounded-full transition-all"
        :class="index === place.index ? 'w-5 bg-foreground' : 'w-1.5 bg-muted-foreground/40'"
      />
    </ol>
    <NuxtLink
      v-if="place.next?.to"
      :to="place.next.to"
      class="inline-flex min-h-11 items-center gap-1 op-label text-muted-foreground"
      data-bi-swipe-next
    >
      Deslize para {{ place.next.label }}
      <Icon name="lucide:chevron-right" class="size-4" aria-hidden="true" />
    </NuxtLink>
  </nav>
</template>
