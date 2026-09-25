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
    hint: item.hint,
  })),
);
const callToActionOptions = computed(() =>
  GOOGLE_CALL_TO_ACTIONS.map((item) => ({
    value: item.value,
    label: item.label,
    hint: item.hint,
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
  <fieldset
    class="space-y-4 rounded-lg border border-border bg-card p-4"
    data-testid="google-business-options"
  >
    <legend class="px-1 text-xs font-medium text-muted-foreground">
      Post no Google
    </legend>

    <div>
      <p class="mb-1 text-xs font-medium text-muted-foreground">
        Tipo de postagem
      </p>
      <UiRadioGroup
        :model-value="options.publication_format"
        label="Tipo de postagem no Google"
        :options="postTypeOptions"
        @update:model-value="
          update({ publication_format: $event as GoogleBusinessOptions['publication_format'] })
        "
      />
    </div>

    <div v-if="options.publication_format === 'event'" class="space-y-3">
      <div>
        <label
          :for="`${idPrefix}-event-title`"
          class="mb-1 block text-xs font-medium text-muted-foreground"
        >
          Nome do evento
        </label>
        <UiInput
          :id="`${idPrefix}-event-title`"
          :model-value="options.event_title"
          type="text"
          autocomplete="off"
          placeholder="Semana do Pão"
          @update:model-value="update({ event_title: String($event ?? '') })"
        />
      </div>
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label
            :for="`${idPrefix}-event-start`"
            class="mb-1 block text-xs font-medium text-muted-foreground"
          >
            Começa
          </label>
          <UiInput
            :id="`${idPrefix}-event-start`"
            :model-value="options.event_start"
            type="datetime-local"
            @update:model-value="update({ event_start: String($event ?? '') })"
          />
        </div>
        <div>
          <label
            :for="`${idPrefix}-event-end`"
            class="mb-1 block text-xs font-medium text-muted-foreground"
          >
            Termina
          </label>
          <UiInput
            :id="`${idPrefix}-event-end`"
            :model-value="options.event_end"
            type="datetime-local"
            @update:model-value="update({ event_end: String($event ?? '') })"
          />
        </div>
      </div>
      <p
        v-if="eventPeriodInverted"
        class="text-xs text-destructive"
        role="alert"
      >
        O evento termina antes de começar.
      </p>
      <p class="text-xs text-muted-foreground">
        Horário da loja.
      </p>
    </div>

    <div v-if="options.publication_format === 'offer'">
      <label
        :for="`${idPrefix}-offer-terms`"
        class="mb-1 block text-xs font-medium text-muted-foreground"
      >
        Condições da oferta (opcional)
      </label>
      <UiTextarea
        :id="`${idPrefix}-offer-terms`"
        :model-value="options.offer_terms"
        :rows="2"
        placeholder="Válida para pedidos pela loja on-line."
        class="resize-y"
        @update:model-value="update({ offer_terms: String($event ?? '') })"
      />
      <p class="mt-1 text-xs text-muted-foreground">
        Nome e validade vêm da promoção da campanha. Campanha sem promoção não
        publica oferta.
      </p>
    </div>

    <div v-if="choosesButton">
      <p class="mb-1 text-xs font-medium text-muted-foreground">
        Botão no post
      </p>
      <UiRadioGroup
        :model-value="options.call_to_action"
        label="Botão no post do Google"
        :options="callToActionOptions"
        class="sm:grid sm:grid-cols-2"
        @update:model-value="
          update({ call_to_action: $event as GoogleBusinessOptions['call_to_action'] })
        "
      />
      <p v-if="!hasLink" class="mt-1 text-xs text-muted-foreground">
        Este anúncio não tem link: só “Ligar agora” ou nenhum botão.
      </p>
    </div>
  </fieldset>
</template>
