<script setup lang="ts">
// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// A folha "Quando" (OC-33 B1, direção E2, escolhida pelo dono em 25/11/2026). Abre no
// primeiro "+" com a casa fechada e no "Editar" da etapa feita. É a folha canônica da
// loja (BottomSheet) com a MESMA escolha de data do checkout: cartão de rádio com o
// título relativo e o dia por extenso curto, e "Outra data" no calendário. O próximo
// dia que a casa atende já vem marcado, e a ação diz o dia no verbo ("Encomendar para
// amanhã"). Trocar o dia com item que não dá: o aviso da casa, item por item, aqui
// dentro. Os dias, o "hoje já encerramos" e as recusas vêm do servidor.
import { dayActionLabel, daySheetOptions, suggestedDay, weekdayDayMonth } from '~/presentation/menuDay'
import type { CartDayChangeRefusal, CatalogDaysProjection } from '~/types/shopman'
import { datepickerDisabledDates, localDateValue, parseLocalDate } from '~/utils/checkoutFlow'

const props = defineProps<{
  open: boolean
  days: CatalogDaysProjection
  // O dia que a sacola já tem ('' sem dia): vem marcado ao reabrir pelo "Editar".
  chosen: string
  refusal?: CartDayChangeRefusal | null
  error?: string
  busy?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [value: string]
  proceedWithout: []
  keep: []
}>()

const options = computed(() => daySheetOptions(props.days))
const selected = ref('')
const calendarOpen = ref(false)
const otherDate = ref<Date | null>(null)

watch(() => props.open, open => {
  if (!open) return
  selected.value = suggestedDay(props.days, props.chosen)
  otherDate.value = null
}, { immediate: true })

const isOther = computed(() => !!selected.value && !options.value.some(option => option.value === selected.value))
const firstOtherDay = computed(() => parseLocalDate(props.days.next_days[0] || props.days.today))
const lastDay = computed(() => parseLocalDate(props.days.max_date))
const disabledDates = computed(() => datepickerDisabledDates([], props.days.closed_weekdays, props.days.today_open ? '' : props.days.today))
const description = computed(() => (props.days.today_open ? '' : 'Hoje já encerramos.'))
const actionLabel = computed(() => dayActionLabel(props.days, selected.value))

watch(otherDate, value => {
  if (!value) return
  selected.value = localDateValue(value)
  calendarOpen.value = false
})
</script>

<template>
  <BottomSheet
    :open="open"
    title="Quando"
    :description="description"
    max-width="md"
    data-menu-day-sheet
    @update:open="emit('update:open', $event)"
  >
    <div class="space-y-4 p-4">
      <!-- A sacola inteira muda de dia, ou nada muda: o que não dá no dia novo vem
           nomeado, com o gesto de seguir sem ele ou manter o dia que tinha. -->
      <UiAlert v-if="refusal" variant="warning" icon="lucide:circle-alert" role="alert" data-menu-day-refusal>
        <UiAlertTitle class="line-clamp-none">{{ refusal.title }}</UiAlertTitle>
        <UiAlertDescription>
          <ul v-if="refusal.items.length > 1" class="list-disc pl-4" data-menu-day-refusal-items>
            <li v-for="item in refusal.items" :key="item.ref || item.sku">{{ item.name }}</li>
          </ul>
          <p>{{ refusal.detail }}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <UiButton :loading="busy" data-menu-day-proceed @click="emit('proceedWithout')">
              {{ refusal.items.length > 1 ? 'Seguir sem esses itens' : 'Seguir sem esse item' }}
            </UiButton>
            <UiButton variant="outline" :disabled="busy" data-menu-day-keep @click="emit('keep')">Manter o dia que tinha</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>
      <p v-else-if="error" role="alert" class="shop-body text-destructive" data-menu-day-error>{{ error }}</p>

      <!-- A escolha de data do checkout, igual: cartão de rádio e "Outra data". -->
      <UiRadioGroup
        :model-value="isOther ? '' : selected"
        class="grid grid-cols-2 gap-2"
        aria-label="Data"
        @update:model-value="selected = String($event)"
      >
        <UiFieldLabel
          v-for="option in options"
          :key="option.value"
          :for="`menu-day-${option.value}`"
          class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary"
          :data-menu-day-option="option.value"
        >
          <UiField orientation="horizontal">
            <UiRadioGroupItem :id="`menu-day-${option.value}`" :value="option.value" :disabled="busy" />
            <UiFieldContent class="gap-1">
              <UiFieldTitle>{{ option.title }}</UiFieldTitle>
              <UiFieldDescription>{{ option.description }}</UiFieldDescription>
            </UiFieldContent>
          </UiField>
        </UiFieldLabel>

        <UiPopover v-model:open="calendarOpen">
          <UiPopoverTrigger as-child>
            <UiButton
              variant="outline"
              class="h-auto w-full items-start justify-start gap-3 whitespace-normal bg-card p-4"
              :class="isOther ? 'border-primary ring-1 ring-primary' : ''"
              :disabled="busy"
              data-menu-day-other
            >
              <Icon name="lucide:calendar-days" class="mt-0.5 size-4 shrink-0" />
              <span class="flex flex-1 flex-col items-start gap-1 text-left">
                <span class="shop-body font-semibold">Outra data</span>
                <span class="shop-muted">{{ isOther ? weekdayDayMonth(selected) : 'Escolher no calendário' }}</span>
              </span>
            </UiButton>
          </UiPopoverTrigger>
          <UiPopoverContent align="end" class="w-auto p-0">
            <UiDatepicker
              v-model="otherDate"
              is-required
              :min-date="firstOtherDay"
              :max-date="lastDay"
              :disabled-dates="disabledDates"
            />
          </UiPopoverContent>
        </UiPopover>
      </UiRadioGroup>
    </div>

    <template v-if="!refusal" #footer>
      <UiButton
        class="w-full"
        icon="lucide:shopping-bag"
        :loading="busy"
        :disabled="!selected"
        data-menu-day-confirm
        @click="emit('confirm', selected)"
      >
        {{ actionLabel }}
      </UiButton>
    </template>
  </BottomSheet>
</template>
