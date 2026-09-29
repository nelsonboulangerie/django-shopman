<script setup lang="ts">
import type {
  AddressLocationDivergenceMode,
  LocationConsistencyStatus
} from '~/presentation/addressLocationConsistency'

const props = withDefaults(defineProps<{
  mode: AddressLocationDivergenceMode
  state?: 'idle' | 'pending' | LocationConsistencyStatus | 'failed'
  statusMessage?: string
  canReviewMap?: boolean
}>(), {
  state: 'idle',
  statusMessage: '',
  canReviewMap: true
})

const emit = defineEmits<{
  request: []
  keep: []
  'use-current': []
  'review-map': []
  dismiss: []
}>()

const visibleMismatch = computed(() => props.mode === 'visible' && props.state === 'diverged')
const neutralStatus = computed(() => {
  if (props.state === 'compatible') return props.statusMessage || 'Sua localização parece próxima do endereço escolhido.'
  if (props.state === 'inconclusive') return props.statusMessage || 'Não deu para comparar com segurança. Você pode tentar de novo ou seguir com o endereço escolhido.'
  if (props.state === 'unavailable') return props.statusMessage || 'Este endereço não tem um ponto preciso para comparar. Você pode revisá-lo no mapa.'
  if (props.state === 'failed') return props.statusMessage || 'Não foi possível conferir agora. Seu endereço continua selecionado.'
  if (props.mode === 'measure' && props.state === 'diverged') return 'Conferência concluída. Seu endereço continua selecionado.'
  return ''
})
</script>

<template>
  <section v-if="mode !== 'off'" class="shop-stack-tight" aria-label="Conferir local da entrega" data-address-location-check>
    <div v-if="state === 'idle'" class="space-y-2">
      <p class="text-sm text-muted-foreground">
        Podemos usar sua localização uma vez para conferir o ponto da entrega.
      </p>
      <UiButton
        type="button"
        variant="outline"
        size="sm"
        icon="lucide:locate-fixed"
        class="min-h-11 w-full justify-center sm:w-auto"
        data-address-location-check-request
        @click="emit('request')"
      >
        Usar minha localização
      </UiButton>
    </div>

    <p v-else-if="state === 'pending'" class="flex min-h-11 items-center gap-2 text-sm" role="status" aria-live="polite">
      <Icon name="lucide:loader-circle" class="size-4 animate-spin" aria-hidden="true" />
      Conferindo sua localização…
    </p>

    <UiAlert v-else-if="visibleMismatch" data-address-location-mismatch>
      <UiAlertTitle>Sua localização parece diferente do endereço de entrega</UiAlertTitle>
      <UiAlertDescription>
        Confira antes de continuar. Você pode manter o endereço escolhido, usar o ponto onde está ou revisar no mapa.
      </UiAlertDescription>
      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <UiButton type="button" class="min-h-11 sm:col-span-2" data-location-action="keep" @click="emit('keep')">
          Entregar neste endereço
        </UiButton>
        <UiButton type="button" variant="outline" class="min-h-11" data-location-action="use-current" @click="emit('use-current')">
          Usar minha localização
        </UiButton>
        <UiButton
          v-if="canReviewMap"
          type="button"
          variant="outline"
          class="min-h-11"
          data-location-action="review-map"
          @click="emit('review-map')"
        >
          Revisar no mapa
        </UiButton>
        <UiButton type="button" variant="ghost" class="min-h-11 sm:col-span-2" data-location-action="dismiss" @click="emit('dismiss')">
          Agora não
        </UiButton>
      </div>
    </UiAlert>

    <div v-else-if="neutralStatus" class="space-y-2" role="status" aria-live="polite" data-address-location-status>
      <p class="text-sm text-muted-foreground">{{ neutralStatus }}</p>
      <UiButton
        v-if="state !== 'compatible'"
        type="button"
        variant="ghost"
        size="sm"
        class="min-h-11"
        @click="emit('request')"
      >
        Tentar novamente
      </UiButton>
    </div>
  </section>
</template>
