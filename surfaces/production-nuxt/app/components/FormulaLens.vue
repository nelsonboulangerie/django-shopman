<script setup lang="ts">
// A lente de uma fórmula — a mesma tela para pão e para creme; o que muda é a
// âncora e os painéis que aparecem (§1): métricas de padaria só com âncora
// `flour`; partes só quando há parte; mistura final e BOM só quando o servidor os
// devolveu. Tudo já vem formatado (ADR-014): este componente não faz conta. Os
// avisos e o "fora da faixa" são tom calmo — referência, nunca bloqueio.
import type { FormulaLensProjection } from "~/types/recipeBook";
import { toneChip, toneClass, unmatchedItems } from "~/presentation/recipeBook";

const props = defineProps<{
  lens: FormulaLensProjection | null;
  pending?: boolean;
  error?: string;
  /** Prévia do editor: painéis enxutos (sem BOM/mistura final). */
  compact?: boolean;
}>();

const unmatched = computed(() => (props.lens ? unmatchedItems(props.lens.items) : []));
const showMetrics = computed(() => !!props.lens?.is_bakery && (props.lens?.metrics.length ?? 0) > 0);
const showParts = computed(() => (props.lens?.parts.length ?? 0) > 0);
const showFinalMix = computed(
  () => !props.compact && !!props.lens?.final_mix_differs && (props.lens?.final_mix.length ?? 0) > 0,
);
const showBom = computed(
  () => !props.compact && !!props.lens?.bom_differs && (props.lens?.bom.length ?? 0) > 0,
);

function rangeLabel(metric: { low_display: string; high_display: string; max_display: string }): string {
  if (!metric.low_display && !metric.high_display) return "";
  const range = `${metric.low_display || "…"} a ${metric.high_display || "…"}`;
  return metric.max_display ? `${range} (máx ${metric.max_display})` : range;
}
</script>

<template>
  <div class="grid gap-3" data-testid="formula-lens">
    <p v-if="error" class="flex items-center gap-2 rounded-md border border-destructive/30 px-3 py-2 text-sm text-muted-foreground">
      <Icon name="lucide:cloud-off" class="size-4 shrink-0 text-destructive/70" />
      <span>{{ error }}</span>
    </p>

    <p v-else-if="!lens && pending" class="text-sm text-muted-foreground">Calculando…</p>

    <div
      v-else-if="!lens"
      class="grid place-items-center gap-1 rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground"
    >
      <Icon name="lucide:scale" class="size-6" />
      <p>Sem prévia ainda. Adicione ingredientes para a lente calcular.</p>
    </div>

    <template v-else>
      <!-- Âncora e base -->
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm" :class="pending ? 'opacity-60' : ''">
        <span>
          <span class="text-muted-foreground">Âncora</span>
          <b class="ml-1">{{ lens.anchor_label }}</b>
        </span>
        <span v-if="lens.anchor_total_display">
          <span class="text-muted-foreground">Total da âncora</span>
          <b class="ml-1 tabular-nums">{{ lens.anchor_total_display }}</b>
        </span>
        <span v-if="lens.total_mass_display">
          <span class="text-muted-foreground">Massa total</span>
          <b class="ml-1 tabular-nums">{{ lens.total_mass_display }}</b>
        </span>
        <UiBadge v-if="lens.standardized" variant="outline" class="px-1.5 py-0 text-xs">
          Padrão da casa{{ lens.basis_display ? ` · ${lens.basis_display}` : "" }}
        </UiBadge>
        <UiBadge v-else variant="outline" class="px-1.5 py-0 text-xs text-muted-foreground">Como informada</UiBadge>
      </div>

      <!-- Avisos: calmos, nunca bloqueiam -->
      <ul v-if="lens.warnings.length" class="grid gap-1" aria-label="Avisos da fórmula">
        <li
          v-for="warning in lens.warnings"
          :key="warning.code + warning.message"
          class="flex items-start gap-2 rounded-md border px-3 py-1.5 text-sm"
          :class="toneChip(warning.tone)"
        >
          <Icon name="lucide:info" class="mt-0.5 size-4 shrink-0" />
          <span>{{ warning.message }}</span>
        </li>
      </ul>

      <!-- Tabela g / % -->
      <div class="overflow-hidden rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-semibold">Ingrediente</th>
              <th class="hidden px-3 py-2 font-semibold sm:table-cell">Papel</th>
              <th class="px-3 py-2 text-right font-semibold">Quantidade</th>
              <th class="px-3 py-2 text-right font-semibold">%</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-if="!lens.items.length">
              <td colspan="4" class="px-3 py-4 text-center text-muted-foreground">Nenhum ingrediente ainda.</td>
            </tr>
            <tr
              v-for="(item, index) in lens.items"
              :key="`${item.sku || item.name}-${index}`"
              :class="item.is_anchor ? 'bg-primary/5' : ''"
            >
              <td class="px-3 py-2">
                <p class="font-medium" :class="item.is_anchor ? 'text-primary' : ''">{{ item.name || item.sku }}</p>
                <p class="text-xs text-muted-foreground">
                  <span v-if="item.sku" class="font-mono">{{ item.sku }}</span>
                  <span v-else class="text-amber-700 dark:text-amber-300">Sem insumo casado</span>
                </p>
              </td>
              <td class="hidden px-3 py-2 text-muted-foreground sm:table-cell">{{ item.role_label }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                <span>{{ item.quantity_display }}</span>
                <span v-if="item.quantity_g && item.unit !== 'g'" class="ml-1 text-xs text-muted-foreground"
                  >({{ item.quantity_g }} g)</span
                >
              </td>
              <td class="px-3 py-2 text-right tabular-nums font-semibold">{{ item.pct_display || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="unmatched.length" class="text-xs text-muted-foreground">
        {{ unmatched.length === 1 ? "1 ingrediente ainda sem insumo" : `${unmatched.length} ingredientes ainda sem insumo` }}
        — publicar exige todos casados.
      </p>

      <!-- Métricas de padaria (só âncora `flour`) -->
      <div v-if="showMetrics" class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="metric in lens.metrics"
          :key="metric.code"
          class="rounded-lg border p-3"
          :class="metric.tone === 'warning' ? 'border-amber-500/40 bg-amber-500/5' : 'bg-card'"
        >
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">{{ metric.label }}</p>
          <p class="mt-1 text-xl font-bold tabular-nums" :class="toneClass(metric.tone)">
            {{ metric.value_display || "—" }}
          </p>
          <p v-if="rangeLabel(metric)" class="text-xs text-muted-foreground">
            Referência {{ rangeLabel(metric) }}
            <span v-if="metric.tone === 'warning'" class="ml-1 text-amber-700 dark:text-amber-300">fora da faixa</span>
          </p>
          <p v-if="metric.note" class="mt-0.5 text-xs text-muted-foreground">{{ metric.note }}</p>
        </div>
      </div>

      <!-- Partes -->
      <div v-if="showParts" class="overflow-hidden rounded-lg border">
        <p class="border-b bg-muted/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Partes
        </p>
        <ul class="divide-y text-sm">
          <li
            v-for="(part, index) in lens.parts"
            :key="`${part.kind}-${part.sku}-${index}`"
            class="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2"
          >
            <span class="font-medium">{{ part.name || part.kind_label }}</span>
            <UiBadge variant="outline" class="px-1.5 py-0 text-xs">{{ part.kind_label }}</UiBadge>
            <span v-if="part.flour_pct_display" class="tabular-nums text-muted-foreground">
              {{ part.flour_pct_display }} da farinha
            </span>
            <span v-if="part.quantity_display" class="tabular-nums text-muted-foreground">{{ part.quantity_display }}</span>
            <span v-if="part.cap_pct_display" class="tabular-nums text-muted-foreground">teto {{ part.cap_pct_display }}</span>
            <span v-if="part.sku && !part.has_formula" class="text-xs text-amber-700 dark:text-amber-300">
              sem fórmula publicada
            </span>
          </li>
        </ul>
      </div>

      <!-- Mistura final (calculada, nunca digitada) -->
      <div v-if="showFinalMix" class="overflow-hidden rounded-lg border">
        <p class="border-b bg-muted/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Mistura final
        </p>
        <table class="w-full text-sm">
          <tbody class="divide-y">
            <tr v-for="(item, index) in lens.final_mix" :key="`fm-${item.sku || item.name}-${index}`">
              <td class="px-3 py-1.5">{{ item.name || item.sku }}</td>
              <td class="px-3 py-1.5 text-right tabular-nums">{{ item.quantity_display }}</td>
              <td class="px-3 py-1.5 text-right tabular-nums text-muted-foreground">{{ item.pct_display || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- BOM: o que a ficha de execução recebe -->
      <div v-if="showBom" class="overflow-hidden rounded-lg border">
        <p class="border-b bg-muted/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Ficha técnica (BOM)
        </p>
        <table class="w-full text-sm">
          <tbody class="divide-y">
            <tr v-for="(item, index) in lens.bom" :key="`bom-${item.sku || item.name}-${index}`">
              <td class="px-3 py-1.5">
                <span>{{ item.name || item.sku }}</span>
                <span v-if="item.sku" class="ml-1 font-mono text-xs text-muted-foreground">{{ item.sku }}</span>
              </td>
              <td class="px-3 py-1.5 text-right tabular-nums">{{ item.quantity_display }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
