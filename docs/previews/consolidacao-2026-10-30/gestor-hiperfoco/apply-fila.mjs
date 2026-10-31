// PRÉVIA (hiperfoco no Gestor, 31/10/2026). Aplica numa CÓPIA de surfaces/orders-nuxt;
// nunca em surfaces/. Cada troca ancora num texto exato e falha alto se não achar.
// Uso: node apply-fila.mjs <cópia>/surfaces/orders-nuxt
import fs from "node:fs";
import path from "node:path";

const root = process.argv[2];
if (!root) throw new Error("uso: node apply-fila.mjs <dir do orders-nuxt>");

function patch(rel, pairs) {
  const file = path.join(root, rel);
  let src = fs.readFileSync(file, "utf8");
  if (src.includes("PRÉVIA hiperfoco")) return console.log(`já aplicado: ${rel}`);
  for (const [from, to] of pairs) {
    const n = src.split(from).length - 1;
    if (n !== 1) throw new Error(`${rel}: âncora achada ${n}x:\n${from.slice(0, 160)}`);
    src = src.replace(from, to);
  }
  fs.writeFileSync(file, src);
  console.log(`ok: ${rel}`);
}

// 1. A fila do operador só tem o que espera o operador. O Pix que ainda não caiu
//    espera o CLIENTE: sai do "Precisa de você" e vai para "Seguem sozinhos".
//    (No produto, isto seria em `order_attention.attention_kind`, no servidor.)
patch("app/presentation/queue.ts", [
  [
    `    if (seen.has(card.ref) || (!card.attention && scope !== "all")) continue;`,
    `    if (seen.has(card.ref) || (!card.attention && scope !== "all")) continue;
    // PRÉVIA hiperfoco: o pagamento que não caiu espera o cliente, não você.
    if (scope !== "all" && waitsForCustomer(card)) continue;`,
  ],
  [
    `/** As contagens dos recortes: "Precisa de você N · Todos N · ● Atrasados N". */`,
    `/** PRÉVIA hiperfoco: o pedido parado no pagamento do cliente (Pix que não caiu). */
export function waitsForCustomer(card: OrderCardProjection): boolean {
  return card.attention === "blocked" && Boolean(card.payment_pending);
}

/** As contagens dos recortes: "Precisa de você N · Todos N · ● Atrasados N". */`,
  ],
  // "Sem estação" lia como "a cozinha não recebeu"; é o pedido sem item de cozinha.
  [`          : "Sem estação",`, `          : "Não passa pela cozinha",`],
]);

patch("app/components/QueueView.vue", [
  [
    `  restLine,
  workingOrders,`,
    `  restLine,
  waitsForCustomer,
  workingOrders,`,
  ],
  // 1b. O "Seguem sozinhos" conta quem espera o cliente pagar.
  [
    `const rest = computed(() =>
  props.scope === "attention"
    ? restLine(progress.value, hidden.value)
    : { hidden: 0, moving: 0, text: "" },
);`,
    `// PRÉVIA hiperfoco: quem espera o cliente pagar segue sozinho, e é contado.
const waitingPay = computed(() => {
  const seen = new Set<string>();
  return props.cards.filter((card) =>
    waitsForCustomer(card) && !seen.has(card.ref) ? (seen.add(card.ref), true) : false,
  ).length;
});
const rest = computed(() => {
  if (props.scope !== "attention") return { hidden: 0, moving: 0, text: "" };
  const base = restLine(progress.value, hidden.value);
  const n = waitingPay.value;
  if (!n) return base;
  const extra = \`\${n} esperando o cliente pagar\`;
  const text = base.text.includes("Seguem sozinhos: ")
    ? base.text.replace(/(Seguem sozinhos: [^·]*[^·\\s])/, \`$1, \${extra}\`)
    : [base.text, \`Seguem sozinhos: \${extra}\`].filter(Boolean).join(" · ");
  return { ...base, moving: base.moving + n, text };
});
/** PRÉVIA hiperfoco: o relógio que decide o momento. No pedido novo, o que importa é
 *  quanto falta para o sistema agir sozinho, e perder (cancelar) não pode ter o mesmo
 *  peso de aceitar sozinho. */
function lossClock(item: QueueItem): { caption: string; value: string; danger: boolean } | null {
  const card = item.card;
  if (item.kind === "negotiation" && item.cancelsIn !== null) {
    const m = Math.floor(item.cancelsIn / 60);
    const s = String(item.cancelsIn % 60).padStart(2, "0");
    return { caption: "para o iFood decidir sozinho", value: \`\${m}:\${s}\`, danger: true };
  }
  const left = card.confirmation_deadline_iso
    ? confirmationRemainingLabel(card.confirmation_deadline_iso, props.nowMs)
    : "";
  if (!left) return null;
  if (item.kind === "ifood_accept")
    return { caption: "para o iFood cancelar", value: left, danger: true };
  if (item.kind !== "confirm") return null;
  return card.confirmation_action === "cancel"
    ? { caption: "para cancelar sozinho", value: left, danger: true }
    : { caption: "para aceitar sozinho", value: left, danger: false };
}
/** "meta 10" lia como código; a unidade vai junto. */
function goalText(item: QueueItem): string {
  return item.goalLabel.replace(/^meta (\\d+)$/, "meta $1 min");
}`,
  ],
  // 2. O relógio do canto: o prazo de perda vira o número grande do cartão.
  [
    `            <NuxtBadge
              :color="toneColor(item.tone)"
              :label="item.timeLabel"
              :data-queue-tone="item.tone"
              data-queue-time
            />
            <p class="op-micro text-muted-foreground" data-queue-goal>
              {{ item.goalLabel }}
            </p>`,
    `            <template v-if="lossClock(item)">
              <p
                class="op-title tnum leading-none"
                :class="lossClock(item)!.danger ? 'font-bold text-destructive' : 'text-muted-foreground'"
                data-hf-clock
              >
                {{ lossClock(item)!.value }}
              </p>
              <p
                class="op-micro leading-tight"
                :class="lossClock(item)!.danger ? 'text-destructive' : 'text-muted-foreground'"
                data-hf-clock-caption
              >
                {{ lossClock(item)!.caption }}
              </p>
            </template>
            <template v-else>
              <NuxtBadge
                :color="toneColor(item.tone)"
                :label="item.timeLabel"
                :data-queue-tone="item.tone"
                data-queue-time
              />
              <p class="op-micro text-muted-foreground" data-queue-goal>
                {{ goalText(item) }}
              </p>
            </template>`,
  ],
  // 3. Na retirada, o que o cliente na frente pede: se falta cobrar, e quantas sacolas.
  //    Na volta do entregador, o que deve voltar (a lista que o diálogo já tinha).
  [
    `            <p class="op-body text-foreground/85">
              {{ item.card.items_summary }}
            </p>`,
    `            <p class="op-body text-foreground/85">
              {{ item.card.items_summary }}
            </p>
            <p
              v-if="item.kind === 'handoff' && (item.card.payment_pending || item.card.volumes)"
              class="flex flex-wrap items-center gap-2"
              data-hf-handoff
            >
              <NuxtBadge
                v-if="item.card.payment_pending"
                color="warning"
                icon="i-lucide-hand-coins"
                :label="\`Falta receber \${item.card.total_display}\`"
              />
              <span v-if="item.card.volumes" class="op-body font-semibold">{{
                \`\${item.card.volumes} \${item.card.volumes === 1 ? "sacola" : "sacolas"}\`
              }}</span>
            </p>
            <div
              v-if="(item.kind === 'courier_back' || item.kind === 'settle') && item.card.courier_return_lines?.length"
              class="rounded-md bg-muted px-3 py-2"
              data-hf-return
            >
              <p class="op-micro text-muted-foreground">Deve voltar com o entregador</p>
              <p
                v-for="line in item.card.courier_return_lines"
                :key="line"
                class="op-body font-semibold"
              >
                {{ line }}
              </p>
            </div>`,
  ],
  // ... e a linha de pagamento não repete o que essas duas já dizem.
  [
    `                item.card.change_label ||
                (item.card.payment_method_label && item.kind !== 'blocked')
              "`,
    `                (item.card.change_label ||
                  (item.card.payment_method_label && item.kind !== 'blocked')) &&
                !(item.kind === 'handoff' && item.card.payment_pending) &&
                !(
                  (item.kind === 'courier_back' || item.kind === 'settle') &&
                  item.card.courier_return_lines?.length
                )
              "`,
  ],
  // 4. O prazo agora mora no relógio do canto: a frase miúda repetida sai.
  [
    `                  class="op-micro text-muted-foreground"
                  data-queue-deadline
                >
                  {{`,
    `                  class="op-micro text-muted-foreground"
                  data-queue-deadline
                  hidden
                >
                  {{`,
  ],
  [
    `                  class="op-micro text-muted-foreground"
                  data-queue-deadline
                >
                  o iFood cancela sozinho em`,
    `                  class="op-micro text-muted-foreground"
                  data-queue-deadline
                  hidden
                >
                  o iFood cancela sozinho em`,
  ],
  // 5. Botão que não se pode apertar não é botão: o bloqueio já está escrito no cartão.
  [
    `v-else-if="queueGesture(item).primary"`,
    `v-else-if="queueGesture(item).primary && !queueGesture(item).primary!.disabled"`,
  ],
  // 6. "O sistema fez" só aparece quando fez algo; a nota de rodapé do engenheiro sai.
  [`      <NuxtCard data-queue-system>`, `      <NuxtCard v-if="systemActions.length" data-queue-system>`],
  [
    `        <p class="pt-2 op-micro leading-snug text-muted-foreground">
          Aviso ao cliente só sai depois da janela de desfazer. “Marcar
          pronto” à mão continua no menu do pedido.
        </p>`,
    ``,
  ],
]);

// 7. Um trabalho, uma forma: o celular e o tablet em pé abrem na mesma fila do passe.
patch("app/pages/index.vue", [
  [
    `  () => !boardLayout.exitPost.value && !screen.belowLg.value,`,
    `  // PRÉVIA hiperfoco: a mesma fila em todo dispositivo.
  () => !boardLayout.exitPost.value,`,
  ],
]);

// 8. A Saída (posto do passe) usa o cartão do quadro: a volta do entregador ganha a mesma
//    lista do que deve voltar, e as linhas soltas de troco e maquininha saem quando ela aparece.
patch("app/components/OrderCard.vue", [
  [
    `const onRoad = computed(() => onRoadLine(props.card));`,
    `const onRoad = computed(() => onRoadLine(props.card));
// PRÉVIA hiperfoco: o que deve voltar com o entregador, já somado pelo servidor.
const returnLines = computed(() =>
  ["dispatched", "delivered"].includes(props.card.status)
    ? (props.card.courier_return_lines ?? [])
    : [],
);`,
  ],
  [
    `        <p class="op-body text-foreground/85" :title="card.items_summary">
          {{ card.items_summary }}
        </p>`,
    `        <p class="op-body text-foreground/85" :title="card.items_summary">
          {{ card.items_summary }}
        </p>
        <div v-if="returnLines.length" class="rounded-md bg-muted px-3 py-2" data-hf-return>
          <p class="op-micro text-muted-foreground">Deve voltar com o entregador</p>
          <p v-for="line in returnLines" :key="line" class="op-body font-semibold">
            {{ line }}
          </p>
        </div>`,
  ],
  [
    `          v-if="card.change_label"
          class="flex items-center gap-1.5 op-micro text-muted-foreground"`,
    `          v-if="card.change_label && !returnLines.length"
          class="flex items-center gap-1.5 op-micro text-muted-foreground"`,
  ],
  [
    `          v-if="onRoad"
          class="flex items-center gap-1.5 op-micro font-medium"`,
    `          v-if="onRoad && !returnLines.length"
          class="flex items-center gap-1.5 op-micro font-medium"`,
  ],
]);
