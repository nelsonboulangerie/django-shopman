<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): o CourierCallSheet da prévia 1 da revisão (decisão A)
// com a linha "Quem leva". Não vai ao ar.
import type { RideColor } from "~/presentation/ridePalette";

interface Option { id: string; kind: "casa" | "taon"; label: string; state: string; busy?: boolean; together: number | null }
interface Scene { id: string; options: Option[]; selected: string; note: string }

const props = defineProps<{
  scene: Scene;
  sel: Option;
  reason: string;
  quote: string[];
  primary: string;
  secondary: string;
  tone: RideColor;
  isSuggested: (o: Option) => boolean;
}>();
const emit = defineEmits<{ pick: [id: string] }>();
const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;
const chipValue = (o: Option) => (o.together === null ? "" : brl(o.together));
</script>

<template>
  <div class="mx-auto w-[460px] overflow-hidden rounded-2xl border border-default bg-default shadow-lg">
    <div class="flex items-start gap-3 border-b border-default px-5 py-4">
      <NuxtIcon name="i-lucide-bike" class="mt-0.5 size-5 text-muted" />
      <div class="min-w-0 flex-1">
        <h2 class="op-title text-highlighted">Chamar entregador</h2>
        <p class="op-micro text-muted">Pedido A47 · Pronto há 3 min · Gleba Palhano</p>
      </div>
      <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
    </div>

    <div class="flex flex-col gap-4 px-5 py-4">
      <!-- quem leva -->
      <div class="flex flex-col gap-2">
        <p class="op-label text-highlighted">Quem leva</p>
        <div class="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Quem leva">
          <button
            v-for="o in props.scene.options"
            :key="o.id"
            type="button"
            role="radio"
            :aria-checked="props.sel.id === o.id"
            class="relative flex min-h-16 flex-col items-start gap-0.5 rounded-xl border px-2.5 py-2 text-left transition"
            :class="props.sel.id === o.id ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'border-default hover:bg-elevated/60'"
            @click="emit('pick', o.id)"
          >
            <span class="flex w-full items-center gap-1">
              <span class="op-body font-semibold text-highlighted">{{ o.label }}</span>
              <NuxtIcon v-if="props.isSuggested(o)" name="i-lucide-sparkles" class="ms-auto size-3.5 text-primary" aria-label="Sugestão da casa" />
            </span>
            <span class="op-micro" :class="o.busy || o.together === null ? 'text-warning' : 'text-muted'">{{ o.state }}</span>
            <span v-if="chipValue(o)" class="op-micro tabular-nums text-toned">{{ chipValue(o) }}</span>
          </button>
        </div>
        <p class="op-micro text-muted">
          <NuxtIcon name="i-lucide-sparkles" class="me-1 inline size-3.5 align-[-2px] text-primary" />{{ props.reason }}
        </p>
        <p v-if="props.sel.busy" class="op-micro text-warning">
          {{ props.sel.label }} {{ props.sel.state.charAt(0).toLowerCase() + props.sel.state.slice(1) }}. A corrida espera por ele.
        </p>
      </div>

      <NuxtSeparator />

      <!-- quem vai junto -->
      <div class="flex flex-col gap-2">
        <p class="op-label text-highlighted">Vai junto nesta corrida?</p>
        <div class="flex flex-col gap-1.5 rounded-xl border border-primary bg-primary/5 px-3 py-2.5">
          <div class="flex items-center gap-3">
            <NuxtCheckbox :model-value="true" />
            <span class="op-body font-semibold tabular-nums text-highlighted">C03</span>
            <span class="op-micro text-muted">Gleba Palhano · 0,6 km de A47</span>
            <NuxtBadge class="ms-auto" color="primary" icon="i-lucide-sparkles" label="Sugestão da casa" />
          </div>
          <MsQuote v-if="props.quote.length" class="ps-8" size="micro" :text="props.quote" />
          <p v-else class="op-micro ps-8 text-warning">A TaOn não cotou agora. Marque C03 se quiser levar junto.</p>
          <p v-if="props.sel.kind === 'casa'" class="op-micro ps-8 text-muted">Valor da tabela da casa, combinado com {{ props.sel.label }}.</p>
        </div>
      </div>

      <NuxtSeparator />

      <!-- o que o entregador leva -->
      <div class="flex flex-col gap-2">
        <p class="op-label text-highlighted">{{ props.sel.kind === "casa" ? `${props.sel.label} leva` : "O entregador leva" }}</p>
        <div class="flex items-center justify-between op-body">
          <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />Troco do pedido A47</span>
          <span class="tabular-nums font-medium text-highlighted">R$ 50,00</span>
        </div>
        <div class="flex items-center justify-between op-body">
          <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-circle-dollar-sign" class="size-4 text-muted" />Troco do pedido C03</span>
          <span class="tabular-nums font-medium text-highlighted">R$ 20,00</span>
        </div>
        <div class="flex items-center justify-between op-body">
          <span class="flex items-center gap-2 text-toned"><NuxtIcon name="i-lucide-credit-card" class="size-4 text-muted" />Maquininha</span>
          <span class="flex items-center gap-1.5 font-medium text-highlighted"><span class="size-3 rounded-full bg-[#2563eb]" />Azul, a única livre</span>
        </div>
        <NuxtInput
          v-if="props.sel.kind === 'casa'"
          v-model="props.scene.note"
          :placeholder="`Observação para ${props.sel.label} (opcional)`"
          icon="i-lucide-message-square-text"
        />
      </div>
    </div>

    <div class="flex flex-col gap-2 border-t border-default bg-elevated/50 px-5 py-4">
      <NuxtButton block color="primary" :icon="props.sel.kind === 'casa' ? 'i-lucide-send' : 'i-lucide-bike'" :label="props.primary" />
      <NuxtButton block color="neutral" variant="outline" :label="props.secondary" />
      <p v-if="props.sel.kind === 'casa'" class="op-micro text-muted">
        Abre o WhatsApp com o link da corrida para {{ props.sel.label }}. A via impressa sai com o mesmo link em QR.
      </p>
    </div>
  </div>
</template>
