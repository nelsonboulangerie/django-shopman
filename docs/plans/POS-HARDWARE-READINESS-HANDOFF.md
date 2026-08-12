# POS-HARDWARE-READINESS-HANDOFF — impressora, gaveta, leitor

**Status:** 🔖 aberto (2026-08-12). Repassado pela frente de alpha (worktree
`shopman-storefront-perf`) para a frente do PDV absorver. **Item 1 (impressora)
fechado em 2026-08-12** — os itens 2, 3 e 4 seguem abertos.

O ponto de partida importa: **isto não é QA à espera de aparelho.** Fui olhar o
código para responder "o que dá para testar já" e os três periféricos estão em
estágios muito diferentes — um funciona e tem defeito, dois não existem.

⚠️ **Colisão:** a frente do PDV está em `fix/pdv-stress-findings` mexendo em
política de gaveta e PIN (retirada exige PIN em qualquer valor). Este documento é
sobre o **caminho físico**, não sobre autorização. Se as duas coisas se cruzarem,
a política manda.

## 0. O aparelho (respondido pelo Pablo, 2026-08-12)

**Epson TM-T20, conexão USB, rolo de 80mm.**

O que isso decide:

- **ESC/POS nativo.** A TM-T20 fala ESC/POS; o kick de gaveta é
  `ESC p m t1 t2` → `1B 70 00 19 FA` (m=0, pulso 25/250ms na saída 2).
- **USB, e o driver do SO já é dono da interface** — é assim que o
  `window.print()` de hoje funciona. Isso **elimina WebUSB**: o Chrome não
  consegue reivindicar uma interface que o driver de impressão já detém, e
  brigar por ela quebraria a impressão do recibo.
- **Portanto o kick vai por trabalho RAW no spooler do sistema**, não por socket
  TCP 9100 (que seria o caminho se ela fosse de rede). Um agente local mínimo
  manda os 5 bytes como um job raw para a fila da impressora. É pequeno — dezenas
  de linhas —, mas é um processo que precisa existir na máquina do balcão.
- **80mm** confirma o `size` do `@page` da seção 1.

### ⭐ Direção do dono: isso tem que ser configurável

Pablo, no mesmo fôlego: *"idealmente, mesmo que depois, tudo isso deveria ser
configurável, ou ter pelo menos um wizard, ou algo que o valha."*

O seam **já existe** e está subaproveitado: `POSTerminal.metadata["hardware"]`
com `printer` / `cash_drawer` / `scanner` / `payment_terminal` /
`customer_display`, lido por `pos_terminal.runtime_profile` (seção 4). Hoje só
guarda o nome de um adapter. O que ele precisa passar a guardar, por terminal:

- **impressora**: fila/nome no SO, largura do rolo (80mm aqui, mas 58mm existe no
  mundo), se imprime automático ao fechar venda;
- **gaveta**: adapter (`manual` = abre com a chave, `agent` = kick pelo agente),
  endereço do agente, pulso;
- **leitor**: prefixo/sufixo do código, se o crachá identifica ou autoriza.

⚠️ Consequência prática para quem faz a seção 1: **largura de rolo é config, não
constante de CSS.** ✅ **Já feito** — o `@page` lê `--pos-roll-*` e um terminal de
58mm não exige recompilar CSS; falta só a origem do valor (o terminal declarar a
largura). Detalhe e medições na seção 1.

Uma ressalva de mecanismo: a forma sugerida aqui, `size: var(--pos-roll-width,
80mm) auto`, **não funciona** — `auto` não pode se misturar a `<length>` no
descritor `size`, e o navegador descarta a regra inteira. `var()` em si funciona;
o `auto` é que mata. Ver a tabela de medições na seção 1.

O "wizard" que ele menciona é a leitura natural disto: uma tela que configura o
terminal e **testa cada peça** (imprime página de teste, chuta a gaveta, lê um
crachá) — o que também conserta a desonestidade da seção 4, porque aí o health
passa a ser sonda de verdade, não declaração.

---

## 1. Impressora térmica — ✅ `@page` corrigido (2026-08-12)

**Como imprime hoje:** `window.print()` do navegador
(`surfaces/pos-nuxt/app/pages/index.vue:142`) com o recibo já no DOM
(`#pos-print-area`, `components/PosReceipt.vue`) e CSS `@media print`
(`app/assets/css/tailwind.css:232`). O driver do sistema faz o resto — qualquer
impressora serve, inclusive térmica, **sem código novo e sem ESC/POS**.

**O defeito** era `@page { margin: 6mm; }` — só margem, nenhum `size`: `12mm` dos
`80mm` viravam margem (15% da largura útil) e, sem `size`, quem decidia a largura
do layout era o driver, então o mesmo recibo saía diferente em cada terminal.

**Aparelho confirmado com o Pablo (2026-08-12): Epson TM-T20, USB, rolo de 80mm.**
Isso fecha a conta da margem: a TM-T20 imprime 576 dots a 203dpi = 72,07mm, então
os 4mm de cada lado são exatamente o papel fora do alcance do cabeçote.

**A correção que este documento sugeria não funcionaria.** `size: 80mm auto` é
sintaxe inválida — o descritor `size` não aceita `<length>` misturado com `auto`,
então o navegador descarta a regra inteira e a largura continua com o driver.
Medido no Chrome (`Page.printToPDF` com `preferCSSPageSize`): com `80mm auto` a
página saía **Letter**, igual ao bug original. `size: 80mm` sozinho também não
serve — vira página **quadrada de 80×80mm**. A altura precisa ser um comprimento.

Junto apareceu um segundo defeito que ninguém tinha visto: o `#pos-print-area`
era escondido com `visibility: hidden` no `body`, que **mantém os boxes ocupando
espaço**. Toda impressão saía com **páginas em branco** depois do recibo (3
páginas para um recibo de 6 itens) e a paginação não seguia o conteúdo — recibo
longo era truncado.

**O que ficou** (`tailwind.css`, `pages/index.vue`, `components/PosReceipt.vue`):

```css
@page {
  size: 80mm 297mm; /* literal: rede para engine que rejeite var() no parse */
  size: var(--pos-roll-width, 80mm) var(--pos-roll-height, 297mm);
  margin: 3mm 4mm;
  margin: var(--pos-roll-margin-y, 3mm) var(--pos-roll-margin-x, 4mm);
}
```

- `4mm` de margem lateral não é gosto: uma térmica de 80mm imprime ~72mm (576
  dots a 203dpi), então 4mm de cada lado são papel fora do alcance do cabeçote.
  Pedir mais largura não ganha espaço, só joga a coluna do preço para fora.
- A geometria virou variáveis CSS (`--pos-roll-*`) com **um dono só**; o recibo
  lê `.pos-receipt` e não fixa largura própria.
- O `#pos-print-area` foi para o `body` por `Teleport`, o que permite esconder o
  app com `display: none` de verdade. Fim das páginas em branco.
- `tests/receiptPrint.test.ts` trava o contrato: largura declarada, `@page` em
  sintaxe válida (proíbe `auto`), literal antes da versão configurável, fallback
  obrigatório em toda `var()`, números iguais aos do `:root`, recibo sem largura
  própria e app escondido com `display`, não `visibility`.

**Verificado sem impressora**, renderizando o recibo com as regras reais do
`tailwind.css` via CDP `printToPDF`: página **80,1 × 297mm** (antes: Letter),
**1 página** para recibo curto (antes: 3, duas em branco) e **3 páginas** para
recibo de 60 itens — ou seja, pagina pelo conteúdo. Nada cortado na largura.

### ⚙️ Largura de rolo é configuração, não constante (2026-08-12)

O Pablo pediu que isso seja configurável, "mesmo que depois". A primeira versão
desta seção afirmava que **descritores de `@page` não leem custom properties** —
**está errado**, e a correção muda o desenho para melhor.

Medido no Chrome (CDP `printToPDF` + `preferCSSPageSize`), com `--w: 63mm`:

| declaração | resultado |
| --- | --- |
| `size: 63mm 211mm` (literal) | ✅ 63,2 × 211mm |
| `size: var(--w) var(--h)` | ✅ 63,2 × 211mm — **var funciona** |
| `size: var(--nao-existe, 63mm) …` | ✅ 63,2 × 211mm — fallback funciona |
| `margin: var(--my) var(--mx)` | ✅ margem por var funciona |
| `size: var(--w) auto` | ❌ Letter — o problema é o `auto`, não o `var` |
| `size: 80mm 297mm; size: var(--sem-fallback)` | ❌ **Letter** |

A última linha é a armadilha: uma `var()` que não resolve **não cai para a
declaração literal anterior** — derruba o `size` inteiro e a página volta ao
driver, silenciosamente. Por isso o `@page` ficou com o literal primeiro (rede
para engine que rejeite `var()` no parse) e a versão configurável depois, com
fallback inline em cada `var()`. O teste trava essa forma, e as quatro asserções
foram checadas por mutação (cada mutação faz o teste falhar).

**O seam está funcionando hoje.** Sobrescrevendo `--pos-roll-width: 58mm` e
`--pos-roll-margin-x: 3mm` no `:root` em runtime, medido no PDF: página **57,8mm**
com recibo de **51,9mm** e margens de 2,9/3,0mm — contra **80,1mm** e recibo de
**71,9mm** no default. Página e recibo se movem juntos, porque
`--pos-receipt-width` deriva da mesma var. Um terminal de 58mm **não exige
recompilar CSS**.

### ✅ O terminal declara a largura (2026-08-12)

A origem do valor foi ligada — as três pontas:

1. **`POSTerminal.metadata["hardware"]["printer"].roll_width_mm`** — a loja declara
   o que ela sabe: o rolo que compra. Lido por `printer_geometry()` em
   `shopman/backstage/services/pos_terminal.py`. Sem migração: o `metadata` já era
   o seam. Schema em [data-schemas.md](../reference/data-schemas.md#posterminalmetadata).
2. **A projection expõe** `terminal_roll_width_mm` e `terminal_roll_margin_mm`
   (`shopman/backstage/projections/pos.py`). Zero = terminal calado.
3. **A superfície escreve as vars no `<html>`** — `presentation/printGeometry.ts`
   (função pura) aplicada por `useHead({ htmlAttrs })` na tela que imprime.

**A margem é derivada, nunca declarada.** `ceil((rolo − imprimível) / 2)`, com a
largura imprimível vindo de tabela: 80mm→72mm, 58mm→48mm. Isso importa porque a
área imprimível **não é proporcional** — a 203dpi são 576 dots contra 384. Um rolo
de 58mm reserva **5mm** por lado, não 4. Quem fizer regra de três aqui corta a
coluna do preço. Rolo fora desses dois padrões precisa declarar `print_width_mm`;
não chutamos.

**Declaração inválida não cai calada para o default** — vira `warning` na saúde do
terminal, com o motivo. Config ignorada em silêncio é pior que config ausente: a
loja acha que configurou e o papel sai errado sem explicação.

**Quem manda no default continua sendo o CSS.** Terminal que não declara devolve
zero, a superfície não encosta no `documentElement` e o `@page` fica com o literal
de 80mm. O default tem um dono só — repetir "80mm" no Python criaria a segunda
fonte da verdade que todo este trabalho existe para evitar.

O seed passa a declarar o aparelho real da Nelson (`epson-tm-t20`, 80mm). Como
80mm já era o default, a declaração não muda o desenho: torna explícito o que era
sorte, e é o gancho para um balcão com rolo diferente.

**O que ainda quer aparelho:** densidade/contraste, alinhamento lateral do rolo
(o texto agora encosta no limite da área imprimível) e o comportamento de avanço
e corte no fim do recibo, que é configuração do driver, não do CSS.

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

**O caminho real (agora concreto, ver seção 0):** como a TM-T20 é **USB** e o
driver do SO já é dono da interface, o kick vai por **trabalho RAW no spooler** —
não por socket TCP nem por WebUSB. Um agente local mínimo manda
`1B 70 00 19 FA` como job raw para a fila da impressora. Um só caminho serve os
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

1. ~~**`@page` do recibo**~~ — ✅ feito em 2026-08-12 (rolo de 80mm confirmado
   com o Pablo). Sobra só a confirmação de densidade e corte no aparelho.
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
