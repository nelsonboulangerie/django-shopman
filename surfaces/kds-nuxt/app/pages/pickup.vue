<script setup lang="ts">
// Customer pickup board — o display que o cliente assiste. Painel de chegadas
// (sempre DARK, leitura à distância): código GRANDE, "pronto" em verde (vá retirar)
// com chegada animada, "em preparo" neutro. Relógio ao vivo. Marca fica no storefront
// / futuro customer display do PDV — aqui é chrome neutro, copy acolhedor. Read público.
import { realtimeIndicator, splitRef } from "~/presentation/board";

const { status, realtime } = useKdsCustomerBoard();
const preparing = computed(() => status.value?.preparing ?? []);
const ready = computed(() => status.value?.ready ?? []);
// Cue de tempo-real HONESTO: "ao vivo" (verde, pulsando) só quando o SSE conectou;
// senão neutro "atualiza sozinho" (o poll de reserva carrega). Nunca mente pro cliente.
const liveCue = computed(() => realtimeIndicator(realtime.value));

// O painel CHAMA (P2-17): o número que acabou de ficar pronto fica em destaque por
// alguns segundos e a TV toca. Sem gesto o navegador barra o som; aí o cabeçalho
// oferece "Ativar o som", e um toque na TV basta.
const readyRefs = computed(() => ready.value.map((order) => order.ref));
const { isCalling, calling, soundOn, soundBlocked, activateSound } =
  usePickupCall(readyRefs);
const callingCodes = computed(() =>
  [...calling.value].map((ref) => splitRef(ref).code).join(", "),
);

// Relógio ao vivo (client-only — new Date() no SSR causaria mismatch).
const now = ref<Date | null>(null);
let clockTimer: ReturnType<typeof setInterval> | null = null;
const clockTime = computed(() =>
  now.value
    ? now.value.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "",
);
onMounted(() => {
  now.value = new Date();
  clockTimer = setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});
</script>

<template>
  <div
    class="dark grid min-h-screen grid-rows-[auto_1fr] bg-background text-foreground"
  >
    <!-- header -->
    <header
      class="flex items-center justify-between gap-4 border-b px-6 py-5 md:px-10"
    >
      <div class="min-w-0">
        <p
          class="text-sm font-medium uppercase tracking-wider text-muted-foreground"
        >
          Retirada no balcão
        </p>
        <h1 class="text-3xl font-bold md:text-5xl">Seu pedido</h1>
      </div>
      <ClientOnly>
        <!-- No celular o botão desce para baixo do relógio: lado a lado, o título quebraria. -->
        <div
          class="flex shrink-0 items-center gap-4 max-md:flex-col-reverse max-md:items-end max-md:gap-3"
        >
          <NuxtButton
            v-if="soundOn && soundBlocked"
            color="neutral"
            variant="outline"
            icon="i-lucide-volume-2"
            label="Ativar o som"
            @click="activateSound"
          />
          <div v-if="now" class="flex flex-col items-end leading-none">
            <span class="text-xl font-bold tabular-nums md:text-4xl">{{
              clockTime
            }}</span>
            <span
              class="mt-1.5 flex items-center gap-1.5 whitespace-nowrap text-xs font-medium uppercase tracking-wider text-muted-foreground"
              :title="liveCue.title"
            >
              <span
                class="inline-block size-2 rounded-full"
                :class="[liveCue.dotClass, liveCue.live ? 'animate-pulse' : '']"
              />
              {{ liveCue.label }}
            </span>
          </div>
        </div>
      </ClientOnly>
    </header>

    <!-- quem lê a tela em voz alta também ouve a chamada -->
    <p class="sr-only" aria-live="polite">
      <template v-if="callingCodes"
        >Pronto para retirar: {{ callingCodes }}</template
      >
    </p>

    <!-- duas colunas: pronto (verde = vá retirar) / em preparo (neutro) -->
    <div class="grid min-h-0 gap-px overflow-hidden bg-border md:grid-cols-2">
      <!-- ready -->
      <section class="flex min-h-0 flex-col overflow-hidden bg-background">
        <h2
          class="flex items-center gap-2.5 px-6 py-5 text-xl font-bold md:px-10 md:text-3xl"
        >
          <Icon
            name="lucide:circle-check-big"
            class="size-7 shrink-0 text-success"
          />
          Pronto para retirar
          <span
            v-if="ready.length"
            class="rounded-full bg-success/15 px-2.5 py-0.5 text-base font-bold tabular-nums text-success"
            >{{ ready.length }}</span
          >
        </h2>
        <TransitionGroup
          tag="div"
          name="kds-cust"
          class="grid min-h-0 flex-1 content-start gap-3 overflow-auto px-6 pb-6 md:px-10"
        >
          <article
            v-for="order in ready"
            :key="order.ref"
            :data-calling="isCalling(order.ref) || undefined"
            class="rounded-lg border-2 px-6 py-5 shadow-sm"
            :class="
              isCalling(order.ref)
                ? 'pickup-calling border-success bg-success/25'
                : 'border-success/50 bg-success/10'
            "
          >
            <p
              class="text-xs font-bold uppercase tracking-wider text-success dark:text-lime-300"
            >
              {{ splitRef(order.ref).prefix || "Pedido" }}
            </p>
            <p
              class="break-words text-5xl font-extrabold tabular-nums leading-none md:text-7xl"
            >
              {{ splitRef(order.ref).code }}
            </p>
          </article>
          <p
            v-if="!ready.length"
            :key="'empty-ready'"
            class="rounded-lg border border-dashed p-8 text-center text-base text-muted-foreground"
          >
            Seu número aparece aqui assim que o pedido ficar pronto. ✨
          </p>
        </TransitionGroup>
      </section>

      <!-- preparing -->
      <section class="flex min-h-0 flex-col overflow-hidden bg-background">
        <h2
          class="flex items-center gap-2.5 px-6 py-5 text-xl font-bold text-muted-foreground md:px-10 md:text-3xl"
        >
          <Icon name="lucide:flame" class="size-7 shrink-0" />
          Em preparo
          <span
            v-if="preparing.length"
            class="rounded-full bg-muted px-2.5 py-0.5 text-base font-bold tabular-nums text-muted-foreground"
            >{{ preparing.length }}</span
          >
        </h2>
        <TransitionGroup
          tag="div"
          name="kds-cust"
          class="grid min-h-0 flex-1 content-start gap-3 overflow-auto px-6 pb-6 md:px-10"
        >
          <article
            v-for="order in preparing"
            :key="order.ref"
            class="rounded-lg border bg-card px-6 py-4"
          >
            <p
              class="text-xs font-bold uppercase tracking-wider text-muted-foreground"
            >
              {{ splitRef(order.ref).prefix || "Pedido" }}
            </p>
            <p
              class="break-words text-4xl font-bold tabular-nums leading-none text-muted-foreground md:text-6xl"
            >
              {{ splitRef(order.ref).code }}
            </p>
          </article>
          <p
            v-if="!preparing.length"
            :key="'empty-prep'"
            class="rounded-lg border border-dashed p-8 text-center text-base text-muted-foreground"
          >
            Nenhum pedido em preparo agora.
          </p>
        </TransitionGroup>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* Chegada/movimento dos números no painel — suave, chama atenção sem agitar. */
.kds-cust-move {
  transition: transform 0.4s cubic-bezier(0.2, 0, 0, 1);
}
.kds-cust-enter-active {
  transition:
    opacity 0.4s ease,
    transform 0.4s cubic-bezier(0.2, 0, 0, 1);
}
.kds-cust-leave-active {
  transition: opacity 0.3s ease;
}
.kds-cust-enter-from {
  opacity: 0;
  transform: translateY(-8px) scale(0.98);
}
.kds-cust-leave-to {
  opacity: 0;
}

/* A chamada: borda dupla por dentro (não vaza da coluna, não empurra a fila) e o
   fundo verde que pulsa três vezes e fica aceso enquanto dura o destaque. */
.pickup-calling {
  box-shadow: inset 0 0 0 2px var(--success);
  animation: pickup-call 1.1s ease-in-out 3;
}
@keyframes pickup-call {
  50% {
    background-color: color-mix(in oklab, var(--success) 45%, transparent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .pickup-calling {
    animation: none;
  }
  .kds-cust-move,
  .kds-cust-enter-active,
  .kds-cust-leave-active {
    transition: none;
  }
}
</style>
