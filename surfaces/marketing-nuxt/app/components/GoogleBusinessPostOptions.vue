<script setup lang="ts">
// O post do Google na revisão: tipo de postagem, botão e os dados do evento/oferta.
//
// Apresentacional: o card é dono do estado e manda as opções junto da aprovação (um
// request só). O servidor confere tudo de novo — o que esta tela avisa antes é para
// o gestor não descobrir a recusa só depois de aprovar.
import {
  GOOGLE_CALL_TO_ACTIONS,
  GOOGLE_POST_TYPES,
  googleCallToActionNeedsLink,
} from "~/presentation/googleBusinessPost";
import type { GoogleBusinessOptions } from "~/presentation/googleBusinessPost";

const props = defineProps<{
  idPrefix: string;
  /** O anúncio tem link? Botão que leva a link não serve sem ele. */
  hasLink: boolean;
}>();

const options = defineModel<GoogleBusinessOptions>({ required: true });

function update(patch: Partial<GoogleBusinessOptions>) {
  options.value = { ...options.value, ...patch };
}

const postTypeOptions = computed(() =>
  GOOGLE_POST_TYPES.map((item) => ({
    value: item.value,
    label: item.label,
    description: item.hint,
  })),
);
const callToActionOptions = computed(() =>
  GOOGLE_CALL_TO_ACTIONS.map((item) => ({
    value: item.value,
    label: item.label,
    description: item.hint,
    disabled: googleCallToActionNeedsLink(item.value) && !props.hasLink,
  })),
);
const choosesButton = computed(
  () => options.value.publication_format !== "offer",
);
const eventPeriodInverted = computed(
  () =>
    options.value.publication_format === "event" &&
    !!options.value.event_start &&
    !!options.value.event_end &&
    options.value.event_end <= options.value.event_start,
);
</script>

<template>
  <!-- Cartão dentro de cartão (o anúncio, a composição do Google): `soft`. -->
  <NuxtCard variant="soft" data-testid="google-business-options">
    <div class="space-y-4">
      <p class="text-sm font-semibold">Post no Google</p>

      <NuxtRadioGroup
        :model-value="options.publication_format"
        legend="Tipo de postagem"
        aria-label="Tipo de postagem no Google"
        :items="postTypeOptions"
        @update:model-value="
          update({
            publication_format:
              $event as GoogleBusinessOptions['publication_format'],
          })
        "
      />

      <div v-if="options.publication_format === 'event'" class="space-y-3">
        <NuxtFormField label="Nome do evento">
          <NuxtInput
            :id="`${idPrefix}-event-title`"
            :model-value="options.event_title"
            type="text"
            autocomplete="off"
            placeholder="Semana do Pão"
            class="w-full"
            @update:model-value="update({ event_title: String($event ?? '') })"
          />
        </NuxtFormField>
        <div class="grid gap-3 sm:grid-cols-2">
          <NuxtFormField label="Começa">
            <UiDateTimeField
              :id="`${idPrefix}-event-start`"
              :model-value="options.event_start"
              label="Começo do evento"
              @update:model-value="
                update({ event_start: String($event ?? '') })
              "
            />
          </NuxtFormField>
          <NuxtFormField label="Termina">
            <UiDateTimeField
              :id="`${idPrefix}-event-end`"
              :model-value="options.event_end"
              label="Término do evento"
              @update:model-value="update({ event_end: String($event ?? '') })"
            />
          </NuxtFormField>
        </div>
        <NuxtAlert
          v-if="eventPeriodInverted"
          color="error"
          variant="subtle"
          icon="i-lucide-calendar-x"
          title="O evento termina antes de começar."
          description="Ajuste o fim para depois do começo."
        />
        <p class="text-xs text-muted-foreground">Horário da loja.</p>
      </div>

      <NuxtFormField
        v-if="options.publication_format === 'offer'"
        label="Condições da oferta (opcional)"
        help="Nome e validade vêm da promoção da campanha. Campanha sem promoção não publica oferta."
      >
        <NuxtTextarea
          :id="`${idPrefix}-offer-terms`"
          :model-value="options.offer_terms"
          :rows="2"
          autoresize
          placeholder="Válida para pedidos pela loja on-line."
          class="w-full"
          @update:model-value="update({ offer_terms: String($event ?? '') })"
        />
      </NuxtFormField>

      <div v-if="choosesButton" class="space-y-1">
        <NuxtRadioGroup
          :model-value="options.call_to_action"
          legend="Botão no post"
          aria-label="Botão no post do Google"
          :items="callToActionOptions"
          @update:model-value="
            update({
              call_to_action: $event as GoogleBusinessOptions['call_to_action'],
            })
          "
        />
        <p v-if="!hasLink" class="text-xs text-muted-foreground">
          Este anúncio não tem link: só “Ligar agora” ou nenhum botão.
        </p>
      </div>
    </div>
  </NuxtCard>
</template>
