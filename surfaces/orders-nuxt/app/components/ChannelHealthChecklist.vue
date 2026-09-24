<script setup lang="ts">
// O checklist vivo do canal: o que falta para ele funcionar, cada item com o gesto
// que resolve. Canal com pendência nasce ABERTO; canal pronto mostra só "Tudo certo",
// recolhido. Mora num componente próprio para entrar no card com uma linha só.
import { itemAction, orderedItems, pairUrl, previewHref, type HealthAction } from "~/presentation/channelHealth";
import type { ChannelHealthProjection } from "~/types/channelHealth";

const props = defineProps<{ health: ChannelHealthProjection | null }>();
const emit = defineEmits<{ "choose-collections": [] }>();

const runtimeConfig = useRuntimeConfig();
const bases = {
  djangoBase: String(runtimeConfig.public.djangoBaseUrl ?? ""),
  adminBase: String(runtimeConfig.public.adminBaseUrl ?? ""),
};

const expanded = ref(false);
const open = computed(() => Boolean(props.health && (!props.health.ready || expanded.value)));
const items = computed(() => (props.health ? orderedItems(props.health) : []));
const actionOf = (key: string): HealthAction | null => {
  const item = props.health?.items.find((i) => i.key === key);
  return item ? itemAction(item, bases) : null;
};

// Parear uma TV: o endereço que ela abre + o QR do mesmo endereço.
const pairing = ref(false);
const address = computed(() => (props.health ? pairUrl(props.health, bases) : ""));
const qr = ref<HTMLCanvasElement | null>(null);
const copied = ref(false);
watch([pairing, qr, address], async ([show, canvas, text]) => {
  if (!show || !canvas || !text) return;
  try {
    const { toCanvas } = await import("qrcode");
    await toCanvas(canvas, text, { width: 160, margin: 1 });
  } catch {
    // Sem QR, o endereço escrito continua servindo.
  }
}, { flush: "post" });
async function copyAddress() {
  try {
    await navigator.clipboard.writeText(address.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    copied.value = false;
  }
}

function run(action: HealthAction) {
  if (action.kind === "pair") pairing.value = !pairing.value;
  else if (action.kind === "collections") emit("choose-collections");
}
</script>

<template>
  <section v-if="health" class="space-y-2 border-t border-border pt-3" :data-channel-health="health.ref" aria-label="O que falta para este canal funcionar">
    <div class="flex items-center gap-2">
      <Icon
        :name="health.ready ? 'lucide:circle-check' : 'lucide:list-checks'"
        class="size-4" :class="health.ready ? 'text-success' : 'text-warning'"
      />
      <p class="flex-1 text-sm font-medium" data-health-summary>{{ health.summary }}</p>
      <button
        v-if="health.ready" type="button"
        class="min-h-control rounded-md px-2 text-xs text-muted-foreground underline-offset-2 hover:underline"
        :aria-expanded="expanded" @click="expanded = !expanded"
      >
        {{ expanded ? "Recolher" : "Ver o que foi conferido" }}
      </button>
    </div>

    <ul v-if="open" class="space-y-1.5" data-health-items>
      <li
        v-for="item in items" :key="item.key"
        class="flex items-start gap-2 text-sm" :data-health-item="item.key" :data-state="item.state"
      >
        <Icon
          :name="item.state === 'ok' ? 'lucide:check' : 'lucide:circle-alert'"
          class="mt-0.5 size-4 shrink-0" :class="item.state === 'ok' ? 'text-success' : 'text-warning'"
        />
        <div class="min-w-0 flex-1">
          <p :class="item.state === 'ok' ? 'text-muted-foreground' : 'text-foreground'">{{ item.label }}</p>
          <p v-if="item.hint && item.state !== 'ok'" class="text-xs text-muted-foreground">{{ item.hint }}</p>
        </div>
        <template v-if="item.state !== 'ok' && actionOf(item.key)">
          <NuxtLink
            v-if="actionOf(item.key)!.kind === 'route'"
            :to="(actionOf(item.key) as { to: string }).to"
            class="inline-flex min-h-control shrink-0 items-center rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent"
            data-health-action
          >{{ actionOf(item.key)!.label }}</NuxtLink>
          <a
            v-else-if="actionOf(item.key)!.kind === 'external'"
            :href="(actionOf(item.key) as { href: string }).href" target="_blank" rel="noopener"
            class="inline-flex min-h-control shrink-0 items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent"
            data-health-action
          >{{ actionOf(item.key)!.label }} <Icon name="lucide:external-link" class="size-3 opacity-60" /></a>
          <button
            v-else type="button"
            class="inline-flex min-h-control shrink-0 items-center rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent"
            data-health-action @click="run(actionOf(item.key)!)"
          >{{ actionOf(item.key)!.label }}</button>
        </template>
      </li>
    </ul>

    <div v-if="pairing && address" class="space-y-2 rounded-md border bg-muted/40 p-3 text-sm" data-health-pairing>
      <p class="font-medium">Parear uma TV</p>
      <ol class="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
        <li>Na TV, ou no dispositivo ligado a ela, abra o endereço abaixo (ou leia o QR com a câmera dele).</li>
        <li>Entre uma vez com um operador. A TV fica autorizada e não pede mais nada.</li>
      </ol>
      <div class="flex flex-wrap items-center gap-3">
        <canvas ref="qr" class="rounded bg-white" width="160" height="160" aria-label="QR do endereço da TV" />
        <div class="min-w-0 flex-1 space-y-1.5">
          <code class="block break-all rounded bg-background px-2 py-1 text-xs" data-health-address>{{ address }}</code>
          <button type="button" class="inline-flex min-h-control items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition hover:bg-accent" @click="copyAddress">
            <Icon :name="copied ? 'lucide:check' : 'lucide:copy'" class="size-3.5" />
            {{ copied ? "Endereço copiado" : "Copiar endereço" }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="health.preview.length" class="flex flex-wrap gap-1.5">
      <a
        v-for="link in health.preview" :key="link.path"
        :href="previewHref(link, bases)" target="_blank" rel="noopener"
        class="inline-flex min-h-control items-center gap-1 rounded-md px-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        data-health-preview
      >
        <Icon name="lucide:eye" class="size-3.5" /> {{ link.label }}
      </a>
    </div>
  </section>
</template>
