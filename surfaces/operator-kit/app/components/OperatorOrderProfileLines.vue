<script setup lang="ts">
// Quem é este cliente (WP-360), as linhas (peça do `OperatorOrderDetail`): cada linha só
// aparece com o dado que o servidor de fato tem.
import { computed } from "vue";

import { profileHabits, profileHistory } from "../presentation/orderDetail";
import type { OrderDetailCustomerProfile } from "../types/orderDetail";

const props = defineProps<{ profile: OrderDetailCustomerProfile }>();
const history = computed(() => profileHistory(props.profile));
const habits = computed(() => profileHabits(props.profile));
</script>

<template>
  <p v-if="history" data-customer-history>{{ history }}</p>
  <p v-if="habits" class="text-muted-foreground" data-customer-habits>
    {{ habits }}
  </p>
  <!-- Aniversário: no dia, é gesto de casa; fora dele, é só cadastro. -->
  <p
    v-if="profile.birthday_display"
    class="flex items-center gap-1.5"
    :class="profile.is_birthday_today ? 'font-medium' : 'text-muted-foreground'"
    data-customer-birthday
  >
    <Icon name="lucide:cake" class="size-3.5 shrink-0" />
    {{
      profile.is_birthday_today
        ? "Faz aniversário hoje"
        : `Aniversário em ${profile.birthday_display}`
    }}
  </p>
  <!-- Restrição alimentar é a única linha deste bloco que pode virar incidente se
       passar batido — por isso tom de atenção, não cinza. -->
  <p
    v-if="profile.dietary_restrictions"
    class="flex items-start gap-1.5 font-medium text-warning"
    data-customer-restrictions
  >
    <Icon name="lucide:triangle-alert" class="mt-0.5 size-3.5 shrink-0" />
    <span>{{ profile.dietary_restrictions }}</span>
  </p>
  <p
    v-if="profile.notes"
    class="flex items-start gap-1.5 text-muted-foreground"
    data-customer-notes
  >
    <Icon name="lucide:sticky-note" class="mt-0.5 size-3.5 shrink-0" />
    <span>{{ profile.notes }}</span>
  </p>
</template>
