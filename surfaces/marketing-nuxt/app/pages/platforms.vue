<script setup lang="ts">
// Plataformas — por onde a padaria consegue falar, e o que falta.
//
// ⚠️ Esta tela existe porque o estado das plataformas não tinha casa. O seletor do template
// aprovado do WhatsApp e o teste de envio moravam DENTRO de um painel de configuração
// DENTRO da tela de revisão, e o botão que os abria vivia no cabeçalho do painel — remendo
// que o dono apontou. Ver `docs/plans/MARKETING-UX-PLAN.md`.
//
// Plataforma ≠ canal: canal é por onde se VENDE, plataforma é por onde o anúncio SAI.
import { platformIcon } from "~/presentation/campaign";

const { platforms, loading } = usePlatforms();
const waTemplate = useWhatsAppTemplate();

// ⚠️ O detalhe abre em painel, não fica aberto na página. Com o WhatsApp expandido o tempo
// todo a lista já ficava estranha; com as quatro plataformas expandindo, a tela viraria um
// depósito. A lista responde "como está cada uma?" num relance; o painel responde "e o que
// eu faço?".
const opened = ref<Platform | null>(null);
const savingTemplate = ref(false);
const testRecipient = ref("");
const testSku = ref("");
const testName = ref("");

onMounted(() => { waTemplate.load(); });

async function onChooseTemplate(flowNs: string) {
  savingTemplate.value = true;
  await waTemplate.choose(flowNs);
  savingTemplate.value = false;
}

async function onSendTest() {
  if (!testRecipient.value.trim()) return;
  await waTemplate.sendTest(testRecipient.value.trim(), {
    sku: testSku.value.trim(),
    name: testName.value.trim(),
  });
}

/** Uma linha por plataforma: o resumo que responde "como está" sem abrir nada. */
function summaryFor(platform: Platform): string {
  if (!platform.ready) return platform.reason;
  if (platform.limitation) return platform.limitation;
  return kindLabel(platform.kind);
}

/** O que "entregar" quer dizer nesta plataforma — publicar e mandar mensagem não são o mesmo. */
function kindLabel(kind: string): string {
  return kind === "direct_message"
    ? "Uma mensagem por pessoa, com consentimento."
    : "Uma peça publicada na plataforma.";
}

/** Bloqueio, limitação e saúde não podem parecer iguais. */
function tone(ready: boolean, limitation: string) {
  if (!ready) return { chip: "bg-destructive/10 text-destructive", icon: "lucide:circle-slash", label: "Não publica" };
  if (limitation) return { chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400", icon: "lucide:triangle-alert", label: "Alcance limitado" };
  return { chip: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400", icon: "lucide:check", label: "Pronta" };
}

useHead({ title: "Plataformas · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
    <h1 class="mb-1 text-xl font-semibold">Plataformas</h1>
    <p class="mb-4 text-sm text-muted-foreground">
      Por onde o anúncio sai. Quem vende é o canal; aqui é quem fala.
    </p>

    <div v-if="loading && !platforms.length" class="space-y-2" aria-busy="true">
      <div v-for="n in 4" :key="n" class="h-24 animate-pulse rounded-xl bg-muted"></div>
    </div>

    <ul v-else class="divide-y divide-border rounded-xl border border-border bg-card">
      <li v-for="platform in platforms" :key="platform.platform">
        <button
          type="button"
          class="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-muted"
          @click="opened = platform"
        >
          <Icon :name="platformIcon(platform.platform)" class="size-5 shrink-0 text-muted-foreground" />
          <span class="min-w-0 flex-1">
            <span class="flex flex-wrap items-center gap-2">
              <span class="font-semibold">{{ platform.label }}</span>
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
                :class="tone(platform.ready, platform.limitation).chip"
              >
                <Icon :name="tone(platform.ready, platform.limitation).icon" class="size-3" />
                {{ tone(platform.ready, platform.limitation).label }}
              </span>
              <!-- Plataforma que nenhuma campanha ativa usa não é problema: ligar
                   credencial de algo sem uso é trabalho jogado fora. -->
              <span
                v-if="!platform.in_use"
                class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                Sem uso
              </span>
            </span>
            <span class="mt-0.5 block truncate text-sm text-muted-foreground">
              {{ summaryFor(platform) }}
            </span>
          </span>
          <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
        </button>
      </li>
    </ul>

    <UiSheet :open="opened !== null" @update:open="(v) => { if (!v) opened = null }">
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>{{ opened?.label }}</UiSheetTitle>
          <UiSheetDescription>{{ opened ? kindLabel(opened.kind) : "" }}</UiSheetDescription>
        </UiSheetHeader>

        <div v-if="opened" class="flex-1 overflow-y-auto p-4">
          <div
            class="flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm"
            :class="tone(opened.ready, opened.limitation).chip"
          >
            <Icon :name="tone(opened.ready, opened.limitation).icon" class="mt-0.5 size-4 shrink-0" />
            <div class="min-w-0">
              <p class="font-semibold">{{ tone(opened.ready, opened.limitation).label }}</p>
              <p class="mt-0.5">{{ opened.reason || opened.limitation || "Nada impede a entrega." }}</p>
            </div>
          </div>

          <p v-if="opened.action" class="mt-3 text-sm">
            <span class="font-medium">O que fazer:</span> {{ opened.action }}
          </p>

          <!-- Só o WhatsApp se resolve DAQUI. As outras dependem de credencial de
               plataforma, que não se digita numa tela de operação. -->
          <template v-if="opened.platform === 'whatsapp'">
            <section class="mt-5 border-t border-border pt-4">
              <h2 class="text-sm font-semibold">Template aprovado</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Com um template aprovado, o anúncio alcança quem não conversou nas últimas 24
                horas. Sem ele, só a janela.
              </p>

              <div v-if="waTemplate.loading.value" class="mt-3 space-y-2" aria-busy="true">
                <div v-for="n in 2" :key="n" class="h-10 animate-pulse rounded-md bg-muted"></div>
              </div>

              <!-- Não conseguir perguntar à plataforma NÃO é "não há template". -->
              <div
                v-else-if="!waTemplate.canList.value"
                class="mt-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm"
              >
                <p class="font-semibold">Não foi possível consultar os templates agora</p>
                <p class="mt-1 text-muted-foreground">
                  A plataforma não respondeu. Tente de novo em instantes; nada foi alterado.
                </p>
              </div>

              <div v-else class="mt-3 space-y-1.5">
                <button
                  type="button"
                  class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
                  :class="waTemplate.current.value === '' ? 'border-primary' : 'border-border'"
                  :disabled="savingTemplate"
                  @click="onChooseTemplate('')"
                >
                  <Icon name="lucide:circle-slash" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span>
                    <span class="block text-sm font-medium">Sem template</span>
                    <span class="block text-xs text-muted-foreground">
                      Texto livre — alcança só quem conversou nas últimas 24 horas.
                    </span>
                  </span>
                </button>

                <button
                  v-for="option in waTemplate.available.value"
                  :key="option.ns"
                  type="button"
                  class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
                  :class="waTemplate.current.value === option.ns ? 'border-primary' : 'border-border'"
                  :disabled="savingTemplate"
                  @click="onChooseTemplate(option.ns)"
                >
                  <Icon name="lucide:file-check-2" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span class="min-w-0">
                    <span class="block truncate text-sm font-medium">{{ option.name }}</span>
                    <span class="block truncate font-mono text-xs text-muted-foreground">
                      {{ option.ns }}
                    </span>
                  </span>
                </button>
              </div>

              <!-- ⚠️ O que mais confunde, dito onde a decisão acontece: com template
                   escolhido, o texto que o cliente lê é o DA META, não o do Modelo. -->
              <p
                v-if="waTemplate.current.value"
                class="mt-3 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
              >
                Com template escolhido, o texto que sai no WhatsApp é o aprovado na Meta — o
                Modelo entra só com as variáveis. O texto do Modelo continua valendo para
                Instagram, Facebook e para a sua revisão.
              </p>
            </section>

            <!-- Conferir vale mais que supor: aceito pelo provedor não é o mesmo que vibrou
                 no aparelho. Um número por vez, digitado, sem lista de cliente por perto. -->
            <section class="mt-5 border-t border-border pt-4">
              <h2 class="text-sm font-semibold">Testar no meu WhatsApp</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Manda uma mensagem só para você, com as variáveis preenchidas de verdade.
              </p>

              <div class="mt-3 space-y-2">
                <div>
                  <label for="test-recipient" class="mb-1 block text-xs font-medium">
                    WhatsApp ou subscriber
                  </label>
                  <input
                    id="test-recipient"
                    v-model="testRecipient"
                    type="text"
                    placeholder="4605528796186498"
                    class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                  >
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <div>
                    <label for="test-sku" class="mb-1 block text-xs font-medium">SKU (opcional)</label>
                    <input
                      id="test-sku"
                      v-model="testSku"
                      type="text"
                      placeholder="BAGUETE"
                      class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                    >
                  </div>
                  <div>
                    <label for="test-name" class="mb-1 block text-xs font-medium">Nome (opcional)</label>
                    <input
                      id="test-name"
                      v-model="testName"
                      type="text"
                      placeholder="Pablo"
                      class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                    >
                  </div>
                </div>
                <button
                  type="button"
                  :disabled="!testRecipient.trim() || waTemplate.testing.value"
                  class="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition disabled:opacity-40"
                  @click="onSendTest"
                >
                  <Icon
                    :name="waTemplate.testing.value ? 'lucide:loader-circle' : 'lucide:send'"
                    class="size-4"
                    :class="waTemplate.testing.value ? 'animate-spin' : ''"
                  />
                  {{ waTemplate.testing.value ? "Enviando…" : "Enviar teste" }}
                </button>
              </div>

              <dl
                v-if="Object.keys(waTemplate.testFields.value).length"
                class="mt-3 space-y-1 rounded-lg bg-muted/40 p-3 text-xs"
              >
                <div
                  v-for="(value, key) in waTemplate.testFields.value"
                  :key="key"
                  class="flex gap-2"
                >
                  <dt class="shrink-0 font-mono text-muted-foreground">{{ key }}</dt>
                  <dd class="min-w-0 flex-1 truncate">
                    {{ value || "— vazio, o template renderiza sem" }}
                  </dd>
                </div>
              </dl>
            </section>
          </template>
        </div>
      </UiSheetContent>
    </UiSheet>
  </main>
</template>
