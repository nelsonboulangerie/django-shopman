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
import { canaryText } from "~/presentation/platformReadiness";
import { receiptStateLabel } from "~/presentation/marketingResult";
import { alertActions } from "../../../../operator-kit/app/utils/alertActions";

const { platforms, loading, error, load: loadPlatforms } = usePlatforms();
const route = useRoute();
// Produtos publicáveis, para o teste de envio escolher por NOME em vez de digitar SKU.
const { products } = useCampaigns();
const waTemplate = useWhatsAppTemplate();

// O detalhe abre num workspace modal. A lista responde "como está cada uma?" num
// relance; o modal amplo responde "e o que eu faço?" sem comprimir a configuração.
const opened = ref<Platform | null>(null);

async function closePlatformWorkspace() {
  const platformRef = opened.value?.platform || "";
  opened.value = null;
  await navigateTo({ path: "/settings/platforms" }, { replace: true });
  await nextTick();
  if (platformRef) {
    document
      .querySelector<HTMLElement>(`[data-marketing-platform="${platformRef}"]`)
      ?.focus();
  }
}

watch(
  [platforms, () => route.query.platform],
  ([available, requested]) => {
    if (typeof requested !== "string" || opened.value) return;
    opened.value =
      available.find((item) => item.platform === requested) ?? null;
  },
  { immediate: true },
);
const savingTemplate = ref(false);
const pendingFlow = ref<string | null>(null);
const pendingEvent = ref("");
const selectedNotificationEvent = ref("");
const platformCommandKey = ref("");
const totp = ref("");
const testTargetRef = ref("");
const testSku = ref("");
const testEvent = ref("announcement_published");

onMounted(async () => {
  await waTemplate.load();
  selectedNotificationEvent.value =
    waTemplate.notificationTemplates.value[0]?.event || "";
  if (waTemplate.testTargets.value.length === 1) {
    testTargetRef.value = waTemplate.testTargets.value[0]?.ref || "";
  }
});

function onChooseTemplate(flowNs: string) {
  if (!waTemplate.commandAvailable.value || flowNs === waTemplate.current.value)
    return;
  pendingFlow.value = flowNs;
  pendingEvent.value = "";
  platformCommandKey.value = crypto.randomUUID();
  totp.value = "";
}

function onChooseNotificationTemplate(flowNs: string) {
  const binding = selectedNotification.value;
  if (
    !binding ||
    !binding.available ||
    !waTemplate.commandAvailable.value ||
    flowNs === binding.current
  )
    return;
  pendingFlow.value = flowNs;
  pendingEvent.value = binding.event;
  platformCommandKey.value = crypto.randomUUID();
  totp.value = "";
}

function cancelPendingTemplate() {
  pendingFlow.value = null;
  pendingEvent.value = "";
  platformCommandKey.value = "";
  totp.value = "";
}

async function onConfirmTemplate() {
  if (
    savingTemplate.value ||
    pendingFlow.value === null ||
    totp.value.length !== 6
  )
    return;
  savingTemplate.value = true;
  const changed = await waTemplate.choose(
    pendingFlow.value,
    totp.value,
    platformCommandKey.value,
    pendingEvent.value,
    pendingBindingVersion.value,
  );
  if (changed) {
    pendingFlow.value = null;
    pendingEvent.value = "";
    platformCommandKey.value = "";
    totp.value = "";
    await loadPlatforms();
    opened.value =
      platforms.value.find((item) => item.platform === "whatsapp") ??
      opened.value;
  } else if (waTemplate.lastCommandCode.value === "version_conflict") {
    // Keep the exact selected flow in view, but start a new command against the
    // freshly loaded version.  Reusing a key whose receipt is a conflict would
    // replay that conflict forever.
    platformCommandKey.value = crypto.randomUUID();
    totp.value = "";
  }
  savingTemplate.value = false;
}

async function onVerifyCatalog() {
  await waTemplate.verify();
  await loadPlatforms();
  opened.value =
    platforms.value.find((item) => item.platform === "whatsapp") ??
    opened.value;
}

async function onSendTest() {
  if (!testTargetRef.value) return;
  await waTemplate.sendTest(testTargetRef.value, {
    event: testEvent.value,
    sku: testSku.value.trim(),
  });
}

/** Uma linha por plataforma: o resumo que responde "como está" sem abrir nada. */
function summaryFor(platform: Platform): string {
  if (platform.state === "unknown") return platform.reason;
  if (platform.state === "blocked") return platform.reason;
  if (typeof platform.canary_recipients === "number")
    return canaryText(platform.canary_recipients);
  if (platform.limitation) return platform.limitation;
  return kindLabel(platform.kind);
}

/** O que "entregar" quer dizer nesta plataforma — publicar e mandar mensagem não são o mesmo. */
function kindLabel(kind: string): string {
  return kind === "direct_message"
    ? "Uma mensagem por pessoa, com consentimento."
    : "Uma postagem pública na plataforma; não envia mensagem direta.";
}

/** Bloqueio, limitação e saúde não podem parecer iguais.
 *
 * ⚠️ Recebe `kind` porque o WhatsApp ENVIA mensagem e não publica nada: o carimbo do
 * mural, colado nele, fazia o gestor ler "WhatsApp · Não publica" e concluir que o
 * problema era de postagem, quando o que está parado são as MENSAGENS — a plataforma
 * cuja falha custa dinheiro e cuja mensagem não se apaga. */
type ToneColor = "info" | "neutral" | "error" | "warning" | "success";

function tone(
  platform: Pick<
    Platform,
    "state" | "source_status" | "canary_recipients" | "reason_code" | "kind"
  >,
): { color: ToneColor; icon: string; label: string } {
  if (platform.source_status === "simulated")
    return {
      color: "info",
      icon: "i-lucide-flask-conical",
      label: "Simulação local",
    };
  // Desligada pela flag do ambiente é escolha de quem opera, não defeito: não
  // pinta de vermelho como integração quebrada.
  if (platform.reason_code === "platform_switched_off")
    return { color: "neutral", icon: "i-lucide-power-off", label: "Desligada" };
  if (platform.state === "blocked")
    return {
      color: "error",
      icon: "i-lucide-circle-slash",
      label: platform.kind === "direct_message" ? "Não envia" : "Não publica",
    };
  if (platform.state === "unknown")
    return {
      color: "neutral",
      icon: "i-lucide-circle-help",
      label: "Não verificada",
    };
  if (
    platform.state === "degraded" &&
    typeof platform.canary_recipients === "number"
  )
    return {
      color: "warning",
      icon: "i-lucide-flask-conical",
      label: "Em ensaio",
    };
  if (platform.state === "degraded")
    return {
      color: "warning",
      icon: "i-lucide-triangle-alert",
      label: "Alcance limitado",
    };
  return { color: "success", icon: "i-lucide-check", label: "Pronta" };
}

/** O aviso só tem as quatro cores do conjunto: o neutro (desligada, não verificada) vira informação. */
function alertColor(color: ToneColor): "info" | "error" | "warning" | "success" {
  return color === "neutral" ? "info" : color;
}

function checkedAt(value: string): string {
  if (!value) return "sem verificação registrada";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

// "Sem modelo" é a primeira opção da lista, não um cartão à parte: ela é uma
// escolha como as outras, e separá-la só ensinava que não era.
const templateOptions = computed(() => [
  {
    value: "",
    label: "Sem modelo",
    description: "Texto livre: alcança só quem conversou nas últimas 24 horas.",
  },
  ...waTemplate.available.value.map((option) => ({
    value: option.ns,
    label: option.name,
    // O `ns` não aparece na linha, mas a busca o considera: é por ele que a Meta
    // chama o fluxo, e é ele que o gestor tem à mão quando o nome não bate.
    keywords: option.ns,
  })),
]);

const notificationEventOptions = computed(() =>
  waTemplate.notificationTemplates.value.map((binding) => ({
    value: binding.event,
    label: binding.label,
  })),
);

const testEventOptions = computed(() => [
  { value: "announcement_published", label: "Anúncio de novidade" },
  ...notificationEventOptions.value,
]);

const testTargetOptions = computed(() =>
  waTemplate.testTargets.value.map((target) => ({
    value: target.ref,
    label: target.label,
  })),
);

const testProductOptions = computed(() => [
  { value: "", label: "Sem produto (só o texto do modelo)" },
  ...products.value,
]);

const selectedTestBinding = computed(() =>
  testEvent.value === "announcement_published"
    ? null
    : waTemplate.notificationTemplates.value.find(
        (binding) => binding.event === testEvent.value,
      ),
);

const testEventReady = computed(
  () =>
    testEvent.value === "announcement_published" ||
    Boolean(
      selectedTestBinding.value?.available &&
      selectedTestBinding.value.current_active &&
      selectedTestBinding.value.configured,
    ),
);

const selectedNotification = computed(() =>
  waTemplate.notificationTemplates.value.find(
    (binding) => binding.event === selectedNotificationEvent.value,
  ),
);

const pendingBinding = computed(() =>
  pendingEvent.value
    ? waTemplate.notificationTemplates.value.find(
        (binding) => binding.event === pendingEvent.value,
      )
    : null,
);

const pendingBindingVersion = computed(
  () => pendingBinding.value?.version ?? waTemplate.version.value,
);

const pendingCurrentName = computed(() => {
  const binding = pendingBinding.value;
  if (binding) {
    if (binding.current_name) return binding.current_name;
    return binding.current
      ? "Fluxo configurado, mas não ativo na lista atual"
      : "Sem fluxo (janela de 24 horas)";
  }
  return (
    waTemplate.currentName.value ||
    (waTemplate.current.value
      ? "Fluxo configurado, mas não ativo na lista atual"
      : "Sem fluxo (janela de 24 horas)")
  );
});

const pendingMessageLabel = computed(
  () => pendingBinding.value?.label ?? "Anúncio de novidade",
);

const pendingFlowName = computed(() => {
  if (pendingFlow.value === "") return "Sem fluxo (janela de 24 horas)";
  return (
    waTemplate.available.value.find((item) => item.ns === pendingFlow.value)
      ?.name ?? "Fluxo selecionado"
  );
});

// As listas com busca (`NuxtSelectMenu`) trabalham com o item inteiro: a tela guarda o
// valor e entrega o item correspondente. A opção "Sem modelo" vale "" e continua sendo
// uma escolha como as outras.
type Choice = { value: string; label: string };
function optionFor<T extends Choice>(items: T[], value: string): T | undefined {
  return items.find((item) => item.value === value);
}
function choiceValue(item: unknown): string {
  const value =
    item && typeof item === "object" ? (item as Choice).value : item;
  return String(value ?? "");
}
const catalogUnavailableDescription = computed(() => {
  const base =
    "A última lista conhecida não autoriza mudança. Nada foi alterado; atualize a verificação antes de escolher.";
  return waTemplate.catalogAsOf.value
    ? `${base} Última resposta válida: ${checkedAt(waTemplate.catalogAsOf.value)}.`
    : base;
});

async function refreshAll() {
  await Promise.all([loadPlatforms(), waTemplate.load()]);
}

// "Atualizar" (tecla R) é ação do ⋯ do cabeçalho, nunca botão solto.
const headerActions = computed(() => [
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    kbds: ["R"],
    onSelect: () => void refreshAll(),
  },
]);

onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (opened.value || pendingFlow.value !== null) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']"))
    return;
  void refreshAll();
});

useHead({ title: "Plataformas" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Plataformas"
      search-placeholder="Buscar campanha, modelo ou tela"
      :actions="headerActions"
      actions-label="Mais ações de Plataformas"
    >
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline"
          >Por onde o anúncio é disparado. Quem vende é o canal; aqui é quem
          fala.</span
        >
      </template>
      <template #filters-primary><MarketingSettingsNav /></template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto w-full max-w-3xl">
        <OperatorScreenState
          v-if="error && !platforms.length"
          state="error"
          what="as plataformas"
          description="Isso é uma indisponibilidade de leitura, não significa que nenhuma plataforma esteja configurada. Nenhuma configuração foi alterada."
          @retry="loadPlatforms()"
        />

        <OperatorScreenState
          v-else-if="loading && !platforms.length"
          state="loading"
          what="as plataformas"
        />

        <OperatorScreenState
          v-else-if="!platforms.length"
          state="empty"
          icon="i-lucide-share-2"
          title="Nenhuma plataforma disponível"
          description="A verificação respondeu sem opções. Atualize antes de preparar uma publicação."
        >
          <template #actions>
            <NuxtButton
              icon="i-lucide-refresh-cw"
              label="Atualizar"
              color="neutral"
              variant="outline"
              @click="loadPlatforms()"
            />
          </template>
        </OperatorScreenState>

        <NuxtCard v-else data-platform-list>
          <ul class="-my-2 divide-y divide-default">
            <li
              v-for="platform in platforms"
              :key="platform.platform"
              class="py-2"
            >
              <!-- A linha inteira abre os detalhes: alvo amplo, um toque. -->
              <NuxtButton
                :data-marketing-platform="platform.platform"
                color="neutral"
                variant="ghost"
                block
                trailing-icon="i-lucide-chevron-right"
                class="justify-start text-left"
                @click="opened = platform"
              >
                <Icon
                  :name="platformIcon(platform.platform)"
                  class="size-5 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <span class="min-w-0 flex-1">
                  <span class="flex flex-wrap items-center gap-2">
                    <span class="font-semibold">{{ platform.label }}</span>
                    <NuxtBadge
                      :color="tone(platform).color"
                      :icon="tone(platform).icon"
                      :label="tone(platform).label"
                    />
                    <!-- Plataforma que nenhuma campanha ativa usa não é problema: ligar
                         credencial de algo sem uso é trabalho jogado fora. -->
                    <NuxtBadge
                      v-if="!platform.in_use"
                      color="neutral"
                      label="Sem uso"
                    />
                  </span>
                  <!-- Em lista o texto quebra linha (o rótulo que cabe, dono
                       10/10/2026): cortado, "Uma postagem pública na plataforma; não
                       envia…" escondia justamente o que a linha explica. -->
                  <span
                    class="mt-0.5 block break-words text-sm font-normal text-muted-foreground"
                  >
                    {{ summaryFor(platform) }}
                  </span>
                </span>
              </NuxtButton>
            </li>
          </ul>
        </NuxtCard>
      </div>
    </section>

    <MarketingWorkspaceDialog
      :open="opened !== null"
      :title="opened?.label || 'Configurar plataforma'"
      :description="
        opened
          ? kindLabel(opened.kind)
          : 'Conexão, prontidão e opções disponíveis para este destino.'
      "
      @update:open="
        (v) => {
          if (!v) closePlatformWorkspace();
        }
      "
    >
      <div v-if="opened" class="mx-auto w-full max-w-5xl space-y-5">
        <div class="space-y-2">
          <NuxtAlert
            :color="alertColor(tone(opened).color)"
            variant="subtle"
            :icon="tone(opened).icon"
            :title="tone(opened).label"
            :description="
              opened.reason || opened.limitation || 'Nada impede o disparo.'
            "
          />
          <p v-if="opened.action" class="text-sm">
            <span class="font-medium">O que fazer:</span> {{ opened.action }}
          </p>
          <p class="text-xs text-muted-foreground">
            Verificado em {{ checkedAt(opened.checked_at) }}.
          </p>
        </div>

        <!-- Só o WhatsApp se resolve DAQUI. As outras dependem de credencial de
             plataforma, que não se digita numa tela de operação. -->
        <template v-if="opened.platform === 'whatsapp'">
          <section class="space-y-3 border-t border-default pt-4">
            <div>
              <h2 class="text-sm font-semibold">Modelo aprovado</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Com um modelo aprovado, o anúncio alcança quem não conversou nas
                últimas 24 horas. Sem ele, só a janela.
              </p>
            </div>

            <OperatorScreenState
              v-if="waTemplate.loading.value"
              state="loading"
              what="os modelos aprovados"
              in-card
            />

            <!-- Não conseguir perguntar à plataforma NÃO é "não há modelo". -->
            <NuxtAlert
              v-else-if="!waTemplate.canList.value"
              color="warning"
              variant="subtle"
              icon="i-lucide-cloud-off"
              title="Não foi possível consultar os modelos agora"
              :description="catalogUnavailableDescription"
              :actions="alertActions('warning', [
                {
                  label: 'Atualizar',
                  icon: 'i-lucide-refresh-cw',
                  size: 'md',
                  onClick: onVerifyCatalog,
                },
              ])"
            />

            <!-- ⚠️ Era um cartão POR modelo. A conta do ManyChat não tem teto: com
                 algumas dezenas de fluxos aprovados, escolher virava rolar a página
                 inteira. Agora é UMA linha que diz o que está valendo, e a lista só
                 abre quando alguém vai trocar, com busca, porque acima de doze opções
                 ninguém varre com o olho. -->
            <NuxtFormField
              v-else
              label="Modelo aprovado"
              help="“Sem modelo” é texto livre: alcança só quem conversou nas últimas 24 horas."
            >
              <NuxtSelectMenu
                id="whatsapp-template"
                :model-value="optionFor(templateOptions, waTemplate.current.value)"
                :items="templateOptions"
                :filter-fields="['label', 'keywords']"
                placeholder="Sem modelo"
                :search-input="{ placeholder: 'Buscar modelo aprovado' }"
                :disabled="savingTemplate || !waTemplate.commandAvailable.value"
                class="w-full"
                data-whatsapp-template-select
                @update:model-value="onChooseTemplate(choiceValue($event))"
              >
                <template #empty>Nenhum modelo com esse nome</template>
              </NuxtSelectMenu>
            </NuxtFormField>
            <p
              v-if="
                waTemplate.canList.value &&
                !waTemplate.loading.value &&
                waTemplate.available.value.length === 0
              "
              class="text-xs text-muted-foreground"
            >
              A consulta respondeu, mas não há fluxo ativo disponível. “Sem
              fluxo” continua sendo a configuração segura.
            </p>

            <!-- ⚠️ O que mais confunde, dito onde a decisão acontece: com modelo
                 escolhido, o texto que o cliente lê é o DA META, não o do Modelo. -->
            <NuxtAlert
              v-if="waTemplate.current.value"
              color="info"
              variant="subtle"
              icon="i-lucide-info"
              title="O texto enviado no WhatsApp é o aprovado na Meta."
              description="O modelo entra só com as variáveis. O texto do modelo continua valendo para Instagram, Facebook e para a sua revisão."
            />
          </section>

          <section class="space-y-3 border-t border-default pt-4">
            <div>
              <h2 class="text-sm font-semibold">Avisos automáticos</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Ligue cada aviso ao modelo aprovado correspondente. A escolha é
                versionada, exige confirmação e não envia mensagem agora.
              </p>
            </div>

            <NuxtFormField label="Mensagem">
              <NuxtSelectMenu
                id="whatsapp-notification-event"
                :model-value="
                  optionFor(notificationEventOptions, selectedNotificationEvent)
                "
                :items="notificationEventOptions"
                placeholder="Escolha o aviso"
                :search-input="{ placeholder: 'Buscar aviso' }"
                class="w-full"
                @update:model-value="
                  selectedNotificationEvent = choiceValue($event)
                "
              >
                <template #empty>Nenhum aviso encontrado</template>
              </NuxtSelectMenu>
            </NuxtFormField>

            <NuxtAlert
              v-if="selectedNotification && !selectedNotification.available"
              color="error"
              variant="subtle"
              icon="i-lucide-circle-alert"
              title="Aviso ausente neste ambiente"
              description="Aplique as migrações antes de configurar este modelo. Nada será criado com texto genérico."
            />

            <NuxtFormField
              v-else-if="selectedNotification"
              label="Modelo aprovado para este aviso"
            >
              <NuxtSelectMenu
                id="whatsapp-notification-template"
                :model-value="
                  optionFor(templateOptions, selectedNotification.current)
                "
                :items="templateOptions"
                :filter-fields="['label', 'keywords']"
                placeholder="Sem modelo"
                :search-input="{ placeholder: 'Buscar modelo aprovado' }"
                :disabled="savingTemplate || !waTemplate.commandAvailable.value"
                class="w-full"
                @update:model-value="
                  onChooseNotificationTemplate(choiceValue($event))
                "
              >
                <template #empty>Nenhum modelo com esse nome</template>
              </NuxtSelectMenu>
            </NuxtFormField>

            <NuxtAlert
              color="info"
              variant="subtle"
              icon="i-lucide-flask-conical"
              title="Teste cada modelo no ManyChat antes de ativá-lo."
              description="A lista confirma que o modelo existe; não consegue provar que os campos e o botão correspondem a este aviso."
            />
          </section>

          <!-- A ref verificada evita redigitar/errar número e não leva PII ao browser. -->
          <section
            class="space-y-3 border-t border-default pt-4"
            data-whatsapp-test
          >
            <div>
              <h2 class="text-sm font-semibold">Teste seguro do WhatsApp</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Envia uma mensagem a um número verificado. Nunca usa público de
                campanha.
              </p>
            </div>

            <!-- ⚠️ "Este papel" e "Editor habilitado" são o modelo de permissão
                 falando; quem lê quer saber se PODE e, se não, a quem pedir. -->
            <NuxtAlert
              v-if="!waTemplate.canSendTest.value"
              color="info"
              variant="subtle"
              icon="i-lucide-lock"
              title="Sua conta não pode fazer o teste."
              description="Peça a quem cuida das plataformas."
            />

            <NuxtAlert
              v-else-if="!waTemplate.testTargets.value.length"
              color="info"
              variant="subtle"
              icon="i-lucide-shield-check"
              title="Teste externo bloqueado com segurança"
              description="Nenhum dispositivo de teste verificado foi configurado. Peça ao responsável pelas plataformas; não é necessário copiar ou informar um telefone aqui."
            />

            <div v-else class="space-y-3">
              <NuxtFormField label="Mensagem a testar">
                <NuxtSelectMenu
                  id="test-event"
                  :model-value="optionFor(testEventOptions, testEvent)"
                  :items="testEventOptions"
                  placeholder="Escolha a mensagem"
                  :search-input="{ placeholder: 'Buscar mensagem' }"
                  class="w-full"
                  @update:model-value="testEvent = choiceValue($event)"
                >
                  <template #empty>Nenhuma mensagem encontrada</template>
                </NuxtSelectMenu>
              </NuxtFormField>
              <NuxtAlert
                v-if="!testEventReady"
                color="warning"
                variant="subtle"
                icon="i-lucide-triangle-alert"
                title="Este aviso precisa estar ativo e ligado a um modelo aprovado antes do teste."
                :actions="alertActions('warning', [
                  {
                    label: 'Ligar este aviso a um modelo',
                    size: 'md',
                    onClick: () => (selectedNotificationEvent = testEvent),
                  },
                ])"
              />
              <NuxtFormField label="Número verificado">
                <NuxtSelectMenu
                  id="test-target"
                  :model-value="optionFor(testTargetOptions, testTargetRef)"
                  :items="testTargetOptions"
                  placeholder="Escolha o número"
                  :search-input="{ placeholder: 'Buscar número' }"
                  class="w-full"
                  @update:model-value="testTargetRef = choiceValue($event)"
                >
                  <template #empty>Nenhum número encontrado</template>
                </NuxtSelectMenu>
              </NuxtFormField>
              <!-- ⚠️ Era "SKU (opcional)" em texto livre: o gestor não decora código
                   de produto. A lista é a mesma do disparo manual (options.products). -->
              <NuxtFormField label="Produto opcional">
                <NuxtSelectMenu
                  id="test-product"
                  :model-value="optionFor(testProductOptions, testSku)"
                  :items="testProductOptions"
                  placeholder="Sem produto (só o texto do modelo)"
                  :search-input="{ placeholder: 'Buscar produto' }"
                  class="w-full"
                  @update:model-value="testSku = choiceValue($event)"
                >
                  <template #empty>Nenhum produto encontrado</template>
                </NuxtSelectMenu>
              </NuxtFormField>
              <NuxtButton
                block
                icon="i-lucide-send"
                :loading="waTemplate.testing.value"
                :disabled="!testTargetRef || !testEventReady"
                :label="waTemplate.testing.value ? 'Enviando…' : 'Enviar teste'"
                data-whatsapp-test-send
                @click="onSendTest"
              />
            </div>

            <p
              v-if="waTemplate.testReceipt.value"
              class="break-all rounded-md bg-muted p-3 font-mono text-xs"
              data-whatsapp-test-receipt
            >
              Comprovante {{ waTemplate.testReceipt.value.receipt_ref }} ·
              {{ receiptStateLabel(waTemplate.testReceipt.value.state) }}
            </p>

            <dl
              v-if="Object.keys(waTemplate.testFields.value).length"
              class="space-y-1 rounded-md bg-muted p-3 text-xs"
            >
              <div
                v-for="(value, key) in waTemplate.testFields.value"
                :key="key"
                class="flex gap-2"
              >
                <dt class="shrink-0 font-mono text-muted-foreground">
                  {{ key }}
                </dt>
                <dd class="min-w-0 flex-1 truncate">
                  {{ value || "(vazio: o modelo renderiza sem)" }}
                </dd>
              </div>
            </dl>
          </section>
        </template>
      </div>
    </MarketingWorkspaceDialog>

    <NuxtModal
      :open="pendingFlow !== null"
      title="Confirmar configuração do WhatsApp"
      description="Esta escolha muda o alcance das próximas mensagens e fica registrada na auditoria."
      :dismissible="!savingTemplate"
      data-platform-confirm-dialog
      @update:open="
        (value) => {
          if (!value && !savingTemplate) cancelPendingTemplate();
        }
      "
    >
      <template #body>
        <div class="space-y-4">
          <NuxtAlert
            color="info"
            variant="subtle"
            icon="i-lucide-shield-check"
            title="Nenhuma mensagem será enviada agora"
            description="Só a configuração das próximas mensagens será alterada."
          />

          <dl
            class="grid grid-cols-2 overflow-hidden rounded-md border border-default text-center text-sm"
          >
            <div class="col-span-2 border-b border-default p-3">
              <dt class="text-xs text-muted-foreground">Mensagem</dt>
              <dd class="mt-1 font-semibold">{{ pendingMessageLabel }}</dd>
            </div>
            <div class="border-r border-default p-3">
              <dt class="text-xs text-muted-foreground">Configuração atual</dt>
              <dd class="mt-1 font-medium">{{ pendingCurrentName }}</dd>
            </div>
            <div class="p-3">
              <dt class="text-xs text-muted-foreground">
                Depois da confirmação
              </dt>
              <dd class="mt-1 font-medium">{{ pendingFlowName }}</dd>
            </div>
            <div class="col-span-2 border-t border-default p-3">
              <dt class="text-xs text-muted-foreground">Versão revisada</dt>
              <dd class="mt-1 font-semibold tabular-nums">
                {{ pendingBindingVersion }}
              </dd>
            </div>
          </dl>

          <NuxtFormField
            label="Código de 6 dígitos do autenticador"
            help="Use o código atual do autenticador cadastrado."
          >
            <NuxtPinInput
              id="platform-totp"
              :model-value="totp.split('')"
              :length="6"
              otp
              :disabled="savingTemplate"
              @update:model-value="totp = ($event ?? []).join('')"
            />
          </NuxtFormField>
        </div>
      </template>
      <template #footer>
        <div class="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
          <NuxtButton
            block
            color="neutral"
            variant="outline"
            label="Voltar sem alterar"
            :disabled="savingTemplate"
            @click="cancelPendingTemplate"
          />
          <NuxtButton
            block
            icon="i-lucide-shield-check"
            :loading="savingTemplate"
            :disabled="totp.length !== 6"
            :label="savingTemplate ? 'Salvando…' : 'Salvar configuração'"
            @click="onConfirmTemplate"
          />
        </div>
      </template>
    </NuxtModal>
  </main>
</template>
