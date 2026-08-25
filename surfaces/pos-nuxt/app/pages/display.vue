<script setup lang="ts">
// TELA DO CLIENTE — a janela do segundo monitor do balcão, virada para quem
// compra (padrão de customer display de PDV). Kiosk read-only: nenhuma
// interação, fonte grande, alto contraste. Consome os snapshots que a tela de
// venda publica via BroadcastChannel (mesmo navegador da estação) e mostra ao
// cliente o que está sendo cobrado — transparência de preço em primeiro lugar.
// URL em inglês (/display); todo o texto em pt-BR.
import type { CustomerDisplayPhase } from "~/types/customerDisplay";

useHead({ title: "Tela do cliente · Shopman POS" });

const { snapshot } = useCustomerDisplayConsumer();

// O resultado fica um tempo na tela e volta às boas-vindas sozinho — o cliente
// já foi embora; a próxima venda também troca a tela no ato, quando a estação
// publicar. O timer só arma na ENTRADA da fase (a estação pode republicar o
// mesmo resultado, e cada republicação não pode esticar a espera).
const RESULT_HOLD_MS = 12000;
const resultExpired = ref(false);
let holdTimer: ReturnType<typeof setTimeout> | null = null;
function clearHold() {
  if (holdTimer) {
    clearTimeout(holdTimer);
    holdTimer = null;
  }
}
watch(snapshot, (snap, prev) => {
  if (!snap) return;
  if (snap.phase !== "result") {
    clearHold();
    resultExpired.value = false;
    return;
  }
  if (prev?.phase === "result") return; // já contando este resultado
  clearHold();
  resultExpired.value = false;
  holdTimer = setTimeout(() => {
    resultExpired.value = true;
  }, RESULT_HOLD_MS);
});
onBeforeUnmount(() => clearHold());

const phase = computed<CustomerDisplayPhase>(() => {
  const snap = snapshot.value;
  if (!snap) return "idle";
  if (snap.phase === "result" && resultExpired.value) return "idle";
  return snap.phase;
});

const shopName = computed(() => snapshot.value?.shopName || "");
const items = computed(() => snapshot.value?.items || []);
const itemCountLabel = computed(() => {
  const count = snapshot.value?.itemCount || 0;
  return count === 1 ? "1 item" : `${count} itens`;
});
</script>

<template>
  <main
    class="flex h-dvh flex-col overflow-hidden bg-background text-foreground"
    role="status"
    aria-live="polite"
  >
    <!-- BOAS-VINDAS: a loja dá o tom; nada de venda na parede. -->
    <section v-if="phase === 'idle'" class="grid flex-1 place-items-center p-10">
      <div class="grid gap-4 text-center">
        <p class="text-5xl font-semibold leading-tight tracking-tight md:text-7xl">
          {{ shopName || "Olá!" }}
        </p>
        <p class="text-3xl text-muted-foreground md:text-4xl">Que bom ter você aqui.</p>
      </div>
    </section>

    <!-- VENDA EM ANDAMENTO: os itens ao vivo e o total, sem surpresa. -->
    <section v-else-if="phase === 'sale'" class="flex min-h-0 flex-1 flex-col">
      <header class="flex shrink-0 items-baseline justify-between gap-4 border-b border-border px-8 py-5">
        <p class="truncate text-xl font-semibold tracking-tight">{{ shopName }}</p>
        <p class="shrink-0 text-xl text-muted-foreground tabular-nums">{{ itemCountLabel }}</p>
      </header>

      <!-- `justify-end` + overflow escondido: os itens mais RECENTES ficam
           sempre à vista, sem scroll (a tela não é tocável). -->
      <ul class="flex min-h-0 flex-1 flex-col justify-end gap-1 overflow-hidden px-8 py-4">
        <li
          v-for="(item, index) in items"
          :key="`${index}-${item.name}`"
          class="flex items-baseline gap-4 py-2"
        >
          <span class="w-16 shrink-0 text-right text-3xl text-muted-foreground tabular-nums md:text-4xl">{{ item.qty }}×</span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-3xl md:text-4xl">{{ item.name }}</span>
            <!-- O rótulo do desconto viaja com a linha: o preço nunca muda calado. -->
            <span v-if="item.discountLabel" class="block text-xl font-medium text-primary">{{ item.discountLabel }}</span>
          </span>
          <span class="shrink-0 text-3xl tabular-nums md:text-4xl">{{ item.totalDisplay }}</span>
        </li>
      </ul>

      <footer class="shrink-0 border-t border-border bg-card px-8 py-6">
        <div
          v-if="snapshot?.discountDisplay"
          class="mb-2 flex items-baseline justify-between text-xl text-primary"
        >
          <span>Descontos</span>
          <span class="tabular-nums">−{{ snapshot.discountDisplay }}</span>
        </div>
        <div class="flex items-baseline justify-between gap-6">
          <span class="text-3xl text-muted-foreground">Total</span>
          <span class="text-7xl font-semibold tabular-nums tracking-tight md:text-8xl">{{ snapshot?.totalDisplay }}</span>
        </div>
      </footer>
    </section>

    <!-- PAGAMENTO: o total a pagar; PIX ganha QR grande e estado honesto. -->
    <section v-else-if="phase === 'payment'" class="grid flex-1 place-items-center p-10">
      <div class="grid w-full max-w-4xl gap-8 text-center">
        <div class="grid gap-2">
          <p class="text-3xl text-muted-foreground">Total a pagar</p>
          <p class="text-7xl font-semibold tabular-nums tracking-tight md:text-8xl">{{ snapshot?.totalDisplay }}</p>
          <p v-if="snapshot?.discountDisplay" class="text-xl text-primary tabular-nums">
            Descontos −{{ snapshot.discountDisplay }}
          </p>
        </div>

        <div v-if="snapshot?.pix" class="grid justify-items-center gap-4">
          <!-- QR sempre sobre branco: leitora de celular não perdoa dark mode. -->
          <img
            v-if="snapshot.pix.qrCodeSrc"
            :src="snapshot.pix.qrCodeSrc"
            alt="QR code do pagamento PIX"
            class="size-72 rounded-2xl border border-border bg-white p-4 md:size-80"
          >
          <p v-if="snapshot.pix.status === 'waiting'" class="flex items-center gap-2 text-xl text-muted-foreground">
            <Icon name="lucide:loader-circle" class="size-6 animate-spin" />
            Aponte a câmera para pagar. Aguardando a confirmação…
          </p>
          <p v-else class="flex items-center gap-2 text-xl text-muted-foreground">
            <Icon name="lucide:clock-alert" class="size-6" />
            Confirme o pagamento com quem está atendendo, por favor.
          </p>
        </div>
      </div>
    </section>

    <!-- RESULTADO: troco enorme quando houver, e o obrigado. -->
    <section v-else class="grid flex-1 place-items-center p-10">
      <div class="grid gap-8 text-center">
        <div v-if="snapshot?.changeDisplay" class="grid gap-2">
          <p class="text-3xl text-muted-foreground">Seu troco</p>
          <p class="text-7xl font-semibold tabular-nums tracking-tight md:text-8xl">{{ snapshot.changeDisplay }}</p>
        </div>
        <div class="grid gap-3">
          <p class="text-5xl font-semibold tracking-tight md:text-7xl">
            Obrigado{{ snapshot?.customerFirstName ? `, ${snapshot.customerFirstName}` : "" }}!
          </p>
          <p class="text-3xl text-muted-foreground md:text-4xl">Volte sempre.</p>
        </div>
      </div>
    </section>
  </main>
</template>
