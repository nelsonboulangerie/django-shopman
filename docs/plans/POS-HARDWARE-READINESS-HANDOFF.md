# POS-HARDWARE-READINESS-HANDOFF — impressora, gaveta, leitor

**Status:** 🔖 aberto (2026-08-12). Repassado pela frente de alpha (worktree
`shopman-storefront-perf`) para a frente do PDV absorver.

O ponto de partida importa: **isto não é QA à espera de aparelho.** Fui olhar o
código para responder "o que dá para testar já" e os três periféricos estão em
estágios muito diferentes — um funciona e tem defeito, dois não existem.

⚠️ **Colisão:** a frente do PDV está em `fix/pdv-stress-findings` mexendo em
política de gaveta e PIN (retirada exige PIN em qualquer valor). Este documento é
sobre o **caminho físico**, não sobre autorização. Se as duas coisas se cruzarem,
a política manda.

---

## 1. Impressora térmica — funciona, mas o `@page` está errado

**Como imprime hoje:** `window.print()` do navegador
(`surfaces/pos-nuxt/app/pages/index.vue:143`) com o recibo já no DOM
(`#pos-print-area`, `components/PosReceipt.vue`) e CSS `@media print`
(`app/assets/css/tailwind.css:238`). O driver do sistema faz o resto — qualquer
impressora serve, inclusive térmica, **sem código novo e sem ESC/POS**.

**O defeito** (`tailwind.css:250`):

```css
@page {
  margin: 6mm;
}
```

Só margem, **nenhum `size`**. Duas consequências num rolo de 80mm:

- `6mm` de cada lado come **12mm de 80mm — 15% da largura útil**. A área
  imprimível típica de uma térmica de 80mm já é ~72mm; sobra pouco.
- Sem `size`, o layout não está preso à largura do rolo: quem decide é o driver,
  então o mesmo recibo sai diferente em cada terminal.

**Correção provável:** `@page { size: 80mm auto; margin: 2mm 3mm; }` e uma
largura máxima no container do recibo. ⚠️ **Não aplicar às cegas** — o rolo da
Nelson pode ser 58mm; confirmar antes.

**Como testar SEM impressora:** emular mídia de impressão no navegador e
inspecionar/screenshotar o `#pos-print-area` na largura do rolo. Imprimir em PDF
também revela o corte. Não precisa de aparelho para achar layout quebrado —
precisa de aparelho só para confirmar a densidade e o corte do papel.

**É o item de maior valor imediato dos três:** defeito real, correção pequena,
verificável hoje.

## 2. Gaveta — não existe código

Nenhuma linha abre gaveta. As ocorrências de "gaveta" no `pos-nuxt` são **copy**
do relatório de caixa (movimentos, blind count), não comando de aparelho.

A gaveta abre por um comando ESC/POS que a **impressora** dispara
(`ESC p m t1 t2`). Impressão pelo navegador não emite ESC/POS — então, pelo
caminho atual, não há como o PDV abrir a gaveta por software.

### ❌ CORREÇÃO (2026-08-12) — o truque do driver NÃO resolve

A primeira versão deste documento sugeria: "quase todo driver de térmica tem
'abrir gaveta ao imprimir'; se tiver, custo zero". **Está errado**, e o Pablo
pegou perguntando pela sangria. Dois motivos, o segundo pior que o primeiro:

1. **Sangria e suprimento não imprimem nada.** Conferido: não há nenhuma
   impressão no fluxo de movimento de gaveta (`usePosCashSession.ts`,
   `presentation/cash.ts`, `pages/session/index.vue`). Sem impressão, o gancho do
   driver nunca dispara — e sangria é exatamente um momento em que a gaveta
   precisa abrir.

2. **O recibo da venda também não é automático.** `printReceipt()`
   (`pages/index.vue:142`) está ligado a um **botão** (`@click="printReceipt"`,
   linha 299), não ao fim da venda. Ou seja: a gaveta só abriria quando o operador
   lembrasse de clicar "imprimir" — e o momento mais comum de abrir a gaveta é a
   venda em dinheiro, para dar troco.

**Conclusão:** o gancho do driver é incidental, não mecanismo. Amarrar "a gaveta
abre" a "alguém clicou imprimir" é dependência de disciplina humana num ponto
onde a falha é silenciosa — o mesmo padrão que já nos mordeu no
[[feedback_contract_is_surface_independent]].

**O caminho real:** um agente local que envia o comando ESC/POS de kick
(`ESC p m t1 t2`) para a impressora (TCP 9100 ou USB). Um só caminho serve os
quatro momentos: venda em dinheiro, sangria, suprimento e "abrir sem venda".

**Independente disso, vale imprimir comprovante de sangria** — mas como
*controle*, não como mecanismo de abrir gaveta. A frente do PDV acabou de decidir
que retirada exige PIN em qualquer valor justamente por "sangria sem testemunha";
um comprovante impresso (valor, motivo, operador, hora) é a testemunha física. As
duas coisas são boas, mas são independentes: se o comprovante virar o jeito de
abrir a gaveta, volta o acoplamento de cima.

⚠️ **Pré-requisito para qualquer impressão no PDV:** modo kiosk com impressão
silenciosa (Chrome `--kiosk-printing`). Sem isso, todo `window.print()` abre
diálogo — inaceitável num balcão, e absurdo se for só para chutar a gaveta.

## 3. Leitor de crachá — não existe código, mas é testável sem o leitor

Nada de crachá no repo (as ocorrências de "badge" são componentes de UI).

**O que torna isso barato:** leitor USB de crachá é, quase sempre, **emulação de
teclado** — ele "digita" o código e dá Enter. Ou seja: basta um campo focado que
aceite a sequência. Dá para **implementar e testar sem o aparelho**, simulando as
teclas; o leitor real só confirma o formato do código e a velocidade da digitação.

O PIN já existe (`set_operator_pin`; 1234 em dev — ver a memória
`backstage_operator_pin_gate`). Crachá é uma segunda via de identificação, não um
substituto: a política de quem pode o quê continua no PIN.

## 4. ⚠️ O health de terminal é declaração, não sonda

`shopman/backstage/services/pos_terminal.py` expõe saúde de
`printer` / `cash_drawer` / `scanner` / `payment_terminal` / `customer_display`.
Mas `_component_health` só lê `terminal.metadata["hardware"][key]` e devolve:

- sem config ou `enabled: false` → `warning` "não configurado";
- `adapter: "simulated"` ou `"manual"` → **`ready`**;
- qualquer outro adapter → `warning`.

**Nunca toca em aparelho nenhum.** Serve como checklist de configuração; lido como
"hardware ok" engana — um terminal com `adapter: simulated` aparece verde sem que
exista impressora na sala. Isso é coerente com o WP-8 do `POS-FIRST-CLASS-PLAN`
("concluído sem hardware real"), mas vale um rótulo honesto na tela quando o
adapter é simulado.

---

## Ordem sugerida

1. **`@page` do recibo** — defeito real, correção pequena, verificável sem hardware.
   Confirmar a largura do rolo com o Pablo antes.
2. **Leitor de crachá** — implementável e testável sem o aparelho (emulação de teclado).
3. **Gaveta** — precisa de agente local com kick ESC/POS; o gancho do driver não
   cobre sangria nem venda (ver a correção na seção 2). Comprovante impresso de
   sangria é item separado, de controle.
4. **Rótulo honesto** no health quando o adapter é `simulated`/`manual`.

## Anexo — fotos do catálogo (outra tarefa, mesmo repasse)

Fora do PDV, mas veio no mesmo bolo. As 19 fotos do cardápio foram
redimensionadas e verificadas: **12,38 MB → 2,29 MB (−82%)**, quadrado 1200px
(nunca ampliando), WebP com qualidade adaptada a um orçamento de 180 KB, EXIF
removido. O zip foi entregue ao Pablo.

**Bloqueado no Pablo:** os arquivos vivem em `pablondrina/nb-catalog` (outro
repositório) e ninguém empurra lá sem a palavra dele.

**Sem sobrescrever nada:** os arquivos novos são `.webp` e os atuais são `.jpg`,
então nem colidem por nome (conferido: `ct.webp` devolve 404 hoje). Ainda assim o
recomendado é uma subpasta por propósito — `img/products/loja/` — porque deixa
óbvio o que serve à loja e torna a limpeza pós-go-live um `rm -rf` só.

**Quando entrarem**, falta só trocar a extensão (e a pasta, se for subpasta) no seed —
`config/management/commands/seed.py:790` já aponta para
`menu.nelsonboulangerie.com.br/img/products` (o CDN da DO, não mais o
`raw.githubusercontent.com`), então é `.jpg` → `.webp` nas 19 entradas de
`products_data`. Contexto completo em
[CATALOG-IMAGES-OFF-GITHUB-PLAN.md](CATALOG-IMAGES-OFF-GITHUB-PLAN.md).
