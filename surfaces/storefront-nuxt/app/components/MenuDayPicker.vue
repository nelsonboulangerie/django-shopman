<script setup lang="ts">
// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// "Para quando?" antes da lista (OC-33 B1, variante B). Os dias são os que o
// servidor oferece (`catalog.days`): hoje apagado quando encerrado, amanhã, os
// próximos dias com expediente, e "Outro dia" no calendário (até o máximo da casa,
// sem os dias da semana fechados). Um toque escolhe; nada aqui decide se o dia vale.
import { menuDayOptions } from '~/presentation/menuDay'
import type { CatalogDaysProjection } from '~/types/shopman'
import { datepickerDisabledDates, localDateValue, parseLocalDate } from '~/utils/checkoutFlow'

const props = defineProps<{
  days: CatalogDaysProjection
  // O dia já escolhido (para marcar a opção ao trocar); '' sem escolha.
  modelValue: string
}>()

const emit = defineEmits<{ pick: [value: string] }>()

const options = computed(() => menuDayOptions(props.days))
const calendarOpen = ref(false)
const otherDate = ref<Date | null>(null)
const firstOtherDay = computed(() => parseLocalDate(props.days.next_days[0] || props.days.today))
const lastDay = computed(() => parseLocalDate(props.days.max_date))
const disabledDates = computed(() => datepickerDisabledDates([], props.days.closed_weekdays))
const isOther = computed(() => !!props.modelValue && !options.value.some(option => option.value === props.modelValue))

watch(otherDate, value => {
  if (!value) return
  calendarOpen.value = false
  emit('pick', localDateValue(value))
})
</script>

<template>
  <section class="rounded-lg border bg-card p-4 shop-stack-tight" aria-labelledby="menu-day-picker-title" data-menu-day-picker data-focus-target="menu-day">
    <h2 id="menu-day-picker-title" class="shop-heading font-display">Para quando?</h2>
    <p class="shop-muted">O cardápio mostra o que dá para pedir no dia escolhido.</p>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <UiButton
        v-for="option in options"
        :key="option.value"
        variant="outline"
        class="h-auto min-h-14 flex-col items-start justify-center gap-1 whitespace-normal bg-background px-3 py-2 text-left"
        :class="option.value === modelValue ? 'border-primary ring-1 ring-primary' : ''"
        :disabled="option.disabled"
        :aria-pressed="option.value === modelValue"
        :data-menu-day-option="option.value"
        @click="emit('pick', option.value)"
      >
        <span class="shop-body font-semibold">{{ option.title }}</span>
        <span class="shop-meta text-muted-foreground">{{ option.description }}</span>
      </UiButton>
      <UiPopover v-model:open="calendarOpen">
        <UiPopoverTrigger as-child>
          <UiButton
            variant="outline"
            class="h-auto min-h-14 flex-col items-start justify-center gap-1 whitespace-normal bg-background px-3 py-2 text-left"
            :class="isOther ? 'border-primary ring-1 ring-primary' : ''"
            data-menu-day-other
          >
            <span class="shop-body font-semibold">Outro dia</span>
            <span class="shop-meta text-muted-foreground">No calendário</span>
          </UiButton>
        </UiPopoverTrigger>
        <UiPopoverContent align="start" class="w-auto p-0">
          <UiDatepicker
            v-model="otherDate"
            is-required
            :min-date="firstOtherDay"
            :max-date="lastDay"
            :disabled-dates="disabledDates"
          />
        </UiPopoverContent>
      </UiPopover>
    </div>
  </section>
</template>
