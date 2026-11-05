<script setup lang="ts">
// A lista de campanhas no celular (beta 05/11, ge:MKT-14). A tabela de seis colunas
// numa caixa de 343 px escondia "Ligada" e "Ações" atrás da rolagem horizontal: quem
// queria desligar uma campanha não via a chave. Abaixo de `md` cada campanha é um
// cartão empilhado, como em Ofertas, com a chave e o ⋯ sempre à vista. A mesa segue
// com a `OperatorTable`.
import type { OperatorMoreMenuItems } from "../../../operator-kit/app/presentation/moreMenu";
import { formatCount } from "~/presentation/campaign";
import type { Campaign } from "~/types/campaign";

interface Availability {
  enabled: boolean;
  reason: string;
}

defineProps<{
  rules: readonly Campaign[];
  platformLabels: Record<string, string>;
  createdPk: number | null;
  mutatingCampaignPk: number | null;
  editState: (rule: Campaign) => Availability;
  fireState: (rule: Campaign) => Availability;
  rowMenu: (rule: Campaign) => OperatorMoreMenuItems;
  triggerWhen: (rule: Campaign) => string;
}>();

const emit = defineEmits<{
  toggle: [rule: Campaign];
  fire: [rule: Campaign];
}>();
</script>

<template>
  <ul class="flex flex-col gap-3" data-campaigns-mobile-list>
    <li
      v-for="rule in rules"
      :key="rule.pk"
      :data-campaign-card="rule.pk"
    >
      <NuxtCard class="*:data-[slot=body]:p-3">
        <div class="flex flex-col gap-3">
          <div class="min-w-0">
            <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span
                class="break-words font-semibold"
                :class="rule.is_active ? '' : 'text-muted-foreground'"
              >{{ rule.name }}</span>
              <NuxtBadge
                v-if="!rule.requires_approval"
                color="warning"
                variant="soft"
                label="Automática"
              />
              <NuxtBadge
                v-if="rule.pk === createdPk"
                color="success"
                variant="soft"
                label="Nova"
              />
            </p>
            <p class="mt-0.5 break-words text-sm text-muted-foreground" data-campaign-card-trigger>
              {{ rule.trigger_label }}<template v-if="triggerWhen(rule)"> · {{ triggerWhen(rule) }}</template>
            </p>
            <p class="break-words text-sm text-muted-foreground" data-campaign-card-platforms>
              {{ rule.platforms.map((platform) => platformLabels[platform] ?? platform).join(", ") }}
            </p>
            <p class="text-xs text-muted-foreground">
              <template v-if="rule.sent_count">Disparou {{ formatCount(rule.sent_count) }}×</template>
              <template v-else>Ainda não disparou</template>
              <span v-if="rule.failed_count" class="text-error">
                · {{ formatCount(rule.failed_count) }}
                {{ rule.failed_count === 1 ? "falha" : "falhas" }}</span>
            </p>
          </div>

          <div class="flex items-center gap-2">
            <NuxtSwitch
              :model-value="rule.is_active"
              :label="rule.is_active ? 'Ligada' : 'Desligada'"
              :disabled="mutatingCampaignPk !== null || !editState(rule).enabled"
              :loading="mutatingCampaignPk === rule.pk"
              :aria-label="`${rule.is_active ? 'Desligar' : 'Ligar'} a campanha ${rule.name}`"
              class="flex-1 whitespace-nowrap"
              data-campaign-card-switch
              @update:model-value="emit('toggle', rule)"
            />
            <NuxtButton
              v-if="fireState(rule).enabled"
              icon="i-lucide-send"
              label="Preparar disparo"
              color="neutral"
              variant="outline"
              :aria-label="`Preparar o disparo da campanha ${rule.name}`"
              data-campaign-card-fire
              @click="emit('fire', rule)"
            />
            <OperatorMoreMenu
              :label="`Mais ações de ${rule.name}`"
              :items="rowMenu(rule)"
            />
          </div>
          <p
            v-if="!editState(rule).enabled || !fireState(rule).enabled"
            class="text-xs text-muted-foreground"
            data-campaign-card-reasons
          >
            <template v-if="!editState(rule).enabled">{{ editState(rule).reason }} </template>
            <template v-if="!fireState(rule).enabled">{{ fireState(rule).reason }}</template>
          </p>
        </div>
      </NuxtCard>
    </li>
  </ul>
</template>
