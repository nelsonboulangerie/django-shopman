<script setup lang="ts">
// "Sem rede da loja · vendendo pelo 4G deste dispositivo" (v4 `pos-tablet-fluxo` 4):
// o roteador apagou e o dispositivo segue no 4G. A faixa diz isso, e "O que funciona
// agora" abre o que segue de pé e o que para (impressora, gaveta automática). Sem
// internet nenhuma o sistema não vende: isso é a faixa de conexão do kit, não esta.
const { network } = useStoreNetwork();
const open = ref(false);
const ITEMS = [
  { icon: "lucide:circle-check", tone: "text-success", title: "Vender e lançar comandas", note: "" },
  { icon: "lucide:circle-check", tone: "text-success", title: "Cartão pela maquininha", note: "ela tem bateria e 4G próprios" },
  { icon: "lucide:circle-check", tone: "text-success", title: "PIX", note: "QR na tela, confirma sozinho" },
  { icon: "lucide:triangle-alert", tone: "text-warning", title: "Dinheiro: recebe normal, a gaveta abre na chave", note: "sem a rede da loja o pulso do Balcão não chega" },
  { icon: "lucide:circle-x", tone: "text-destructive", title: "Impressora e cupom", note: "sem recibo impresso; NFC-e com CPF sai normal" },
  { icon: "lucide:triangle-alert", tone: "text-warning", title: "Cozinha: só se os tablets dela tiverem bateria ou 4G", note: "se apagaram, avise a cozinha de voz" },
] as const;
</script>

<template>
  <section v-if="network === 'cellular'" class="grid gap-2" data-pos-store-network>
    <button
      type="button"
      class="flex min-h-12 items-center gap-2.5 rounded-lg bg-secondary px-3 text-left op-label"
      :aria-expanded="open"
      @click="open = !open"
    >
      <Icon name="lucide:wifi-off" class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span class="min-w-0 flex-1"><b class="font-semibold">Sem rede da loja</b> · vendendo pelo 4G deste dispositivo</span>
      <Icon :name="open ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    </button>
    <div v-if="open" class="grid gap-2 rounded-lg border border-border bg-card p-3" data-pos-store-network-detail>
      <p class="op-label font-semibold">O que funciona agora</p>
      <ul class="grid gap-2">
        <li v-for="item in ITEMS" :key="item.title" class="flex items-start gap-2">
          <Icon :name="item.icon" class="mt-0.5 size-4 shrink-0" :class="item.tone" aria-hidden="true" />
          <span class="min-w-0">
            <span class="block op-label">{{ item.title }}</span>
            <span v-if="item.note" class="block op-micro text-muted-foreground">{{ item.note }}</span>
          </span>
        </li>
      </ul>
    </div>
  </section>
</template>
