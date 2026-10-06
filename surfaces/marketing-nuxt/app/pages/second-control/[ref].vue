<script setup lang="ts">
// A segunda pessoa, no celular dela (SUITE-UX §15, prévia v4 pino 7): o push "Fulano
// pede a sua confirmação" abre aqui. A tela mostra o MESMO selo (destinos, público,
// quando) e confirma com a digital do dispositivo, ou com o autenticador. Quem pediu
// não confirma o próprio pedido: o servidor recusa, e a tela nem oferece.
import { platformIcon } from "~/presentation/campaign";
import { sealConsequence, sealRows } from "~/presentation/marketingDelivery";
import { scheduleSummary } from "~/utils/marketingSchedule";

interface SecondControl {
  ref: string;
  state: "open" | "approved" | "used" | "expired";
  is_requester: boolean;
  requested_by: string;
  resource_ref: string;
  platforms: string[];
  audience_count: number;
  scheduled_for: string;
  expires_at: string;
}

const route = useRoute();
const confirmationRef = computed(() => String(route.params.ref || ""));
const { data, error, refresh, pending } = await useFetch<{ second_control: SecondControl }>(
  () => `/api/v1/backstage/marketing/security/second-control/${confirmationRef.value}/`,
  { key: () => `second-control-${confirmationRef.value}`, onResponseError: marketingSessionOnError },
);
const control = computed(() => data.value?.second_control ?? null);
const { shopTimezone } = useCampaigns();

const rows = computed(() =>
  control.value ? sealRows({ platforms: control.value.platforms, audienceCount: control.value.audience_count }) : [],
);
const consequence = computed(() => (control.value ? sealConsequence(control.value.platforms) : ""));
const when = computed(() =>
  control.value?.scheduled_for ? scheduleSummary(control.value.scheduled_for, shopTimezone.value) : "Agora, assim que quem pediu confirmar",
);

const device = useDeviceSeal();
const usingCode = ref(false);
const code = ref("");
const busy = ref(false);
const failure = ref("");

async function approve() {
  await $fetch(`/api/v1/backstage/marketing/security/second-control/${confirmationRef.value}/`, {
    method: "POST",
    credentials: "same-origin",
  });
  await refresh();
}

async function confirmWithDevice() {
  failure.value = "";
  busy.value = true;
  try {
    let outcome = await device.seal({ confirmationRef: confirmationRef.value });
    if (outcome === "needs_registration") {
      outcome = (await device.register()) ? await device.seal({ confirmationRef: confirmationRef.value }) : "cancelled";
    }
    if (outcome !== "sealed") {
      failure.value = device.error.value;
      return;
    }
    await approve();
  } catch (err) {
    flagMarketingSessionError(err);
    failure.value = httpErrorMessage(err, "Não deu para confirmar. Tente de novo.");
  } finally {
    busy.value = false;
  }
}

async function confirmWithCode() {
  if (!/^\d{6}$/.test(code.value.trim())) return;
  failure.value = "";
  busy.value = true;
  try {
    await $fetch("/api/v1/backstage/marketing/security/step-up/", {
      method: "POST",
      credentials: "same-origin",
      body: { method: "totp", credential: code.value.trim() },
    });
    await approve();
  } catch (err) {
    flagMarketingSessionError(err);
    failure.value = httpErrorMessage(err, "O código não conferiu. Tente de novo.");
  } finally {
    busy.value = false;
  }
}

useHead({ title: "Confirmação" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-second-control>
    <MarketingPageHeader title="Pedido de confirmação">
      <template #lead>
        <NuxtLink
          to="/"
          class="-ml-3 grid size-12 shrink-0 place-items-center rounded-md text-foreground hover:bg-muted md:ml-0 md:size-control md:border md:border-border"
          aria-label="Voltar às decisões"
        >
          <Icon name="lucide:arrow-left" class="size-6 md:size-5" aria-hidden="true" />
        </NuxtLink>
      </template>
    </MarketingPageHeader>

    <div class="mx-auto flex w-full max-w-lg flex-col gap-3 px-4 py-5">
      <UiSkeleton
        v-if="pending && !control"
        class="h-48 rounded-xl"
        label="Carregando segunda conferência"
      />
      <div v-else-if="error || !control" class="rounded-xl border border-dashed border-border px-5 py-8 text-center" role="alert">
        <p class="font-semibold">Este pedido não existe mais</p>
        <p class="mt-1 text-sm text-muted-foreground">Ele vence em poucos minutos. Quem pediu pode chamar de novo.</p>
      </div>
      <template v-else>
        <p class="text-[15px]">
          <b class="font-semibold">{{ control.requested_by || "Uma pessoa" }}</b>
          {{ control.is_requester ? "(você) espera outra pessoa confirmar este envio." : "pede a sua confirmação para este envio." }}
        </p>
        <ul class="rounded-xl border border-border bg-card px-3.5" aria-label="Para quem vai" data-seal-rows>
          <li v-for="row in rows" :key="row.platform" class="flex min-h-[52px] items-center gap-3 py-2 [&+&]:border-t [&+&]:border-border">
            <Icon :name="platformIcon(row.platform)" class="size-5" aria-hidden="true" />
            <span class="min-w-0 flex-1 text-[15px] leading-tight">{{ row.label }} <span v-if="row.kind" class="block text-[13px] text-muted-foreground">{{ row.kind }}</span></span>
            <span class="tnum" :class="row.strong ? 'text-[15px] font-semibold' : 'text-[14px]'">{{ row.amount }}</span>
          </li>
        </ul>
        <p class="text-[13px] text-muted-foreground">{{ when }}. {{ consequence }}</p>

        <p v-if="control.state === 'approved'" class="flex items-center gap-2 rounded-xl bg-success/10 px-4 py-3 font-semibold text-success" role="status">
          <Icon name="lucide:check" class="size-5" aria-hidden="true" /> Confirmado. Quem pediu já pode enviar.
        </p>
        <p v-else-if="control.state !== 'open'" class="rounded-xl bg-muted px-4 py-3 text-sm" role="status">
          {{ control.state === "used" ? "Este envio já saiu." : "O pedido venceu. Quem pediu pode chamar de novo." }}
        </p>
        <template v-else-if="!control.is_requester">
          <div v-if="usingCode || !device.supported.value" class="flex flex-col gap-2">
            <label for="second-control-code" class="text-xs font-medium text-muted-foreground">Código do aplicativo autenticador</label>
            <UiVerificationCodeInput id="second-control-code" v-model="code" :disabled="busy" @keydown.enter="confirmWithCode" />
            <UiButton class="h-14 rounded-xl text-[16px] font-semibold" :disabled="busy || !/^\d{6}$/.test(code.trim())" @click="confirmWithCode">
              Confirmar o envio
            </UiButton>
          </div>
          <UiButton v-else class="h-14 rounded-xl text-[16px] font-semibold" :disabled="busy" data-second-control-device @click="confirmWithDevice">
            <Icon name="lucide:fingerprint" class="size-5" aria-hidden="true" />
            Confirmar com a digital
          </UiButton>
          <p v-if="device.supported.value" class="text-center text-[13px] text-muted-foreground">
            <button type="button" class="min-h-8 font-semibold text-foreground underline underline-offset-2" @click="usingCode = !usingCode">
              {{ usingCode ? "Usar a digital do dispositivo" : "Usar o autenticador" }}
            </button>
          </p>
        </template>
        <p v-if="failure" class="text-sm text-destructive" role="alert">{{ failure }}</p>
      </template>
    </div>
  </main>
</template>
