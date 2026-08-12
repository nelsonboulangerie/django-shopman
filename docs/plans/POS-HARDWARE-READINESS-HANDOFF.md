# POS-HARDWARE-READINESS-HANDOFF — impressora, gaveta, leitor

**Status:** 🔖 aberto (2026-08-12). Repassado pela frente de alpha (worktree
`shopman-storefront-perf`) para a frente do PDV absorver. **Itens 1
(impressora), 2 (gaveta) e 4 (health honesto da gaveta) fechados em
2026-08-12** — resta o item 3 (leitor de crachá) e o QA físico no balcão.

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
constante de CSS.** `@page { size: var(--pos-roll-width, 80mm) auto }` com o valor
vindo do perfil do terminal evita recompilar CSS por causa de um balcão com rolo
diferente. Cravar 80mm agora é aceitável; cravar sem deixar o ponto de extensão
óbvio é retrabalho garantido.

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

**Rolo confirmado com o Pablo (2026-08-12): 80mm.**

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
@page { size: 80mm 297mm; margin: 3mm 4mm; }
```

- `4mm` de margem lateral não é gosto: uma térmica de 80mm imprime ~72mm (576
  dots a 203dpi), então 4mm de cada lado são papel fora do alcance do cabeçote.
  Pedir mais largura não ganha espaço, só joga a coluna do preço para fora.
- A geometria virou variáveis CSS (`--pos-roll-*`) com **um dono só**; o recibo
  lê `.pos-receipt` e não fixa largura própria. Trocar para 58mm é mexer em um
  lugar (mais o `@page`, que repete os números porque descritores de página não
  leem custom properties — os dois lados ficam amarrados pelo teste).
- O `#pos-print-area` foi para o `body` por `Teleport`, o que permite esconder o
  app com `display: none` de verdade. Fim das páginas em branco.
- `tests/receiptPrint.test.ts` trava o contrato: largura declarada, `@page` em
  sintaxe válida (proíbe `auto`), margens iguais às vars, recibo sem largura
  própria e app escondido com `display`, não `visibility`.

**Verificado sem impressora**, renderizando o recibo com as regras reais do
`tailwind.css` via CDP `printToPDF`: página **80,1 × 297mm** (antes: Letter),
**1 página** para recibo curto (antes: 3, duas em branco) e **3 páginas** para
recibo de 60 itens — ou seja, pagina pelo conteúdo. Nada cortado na largura.

**O que ainda quer aparelho:** densidade/contraste, alinhamento lateral do rolo
(o texto agora encosta no limite da área imprimível) e o comportamento de avanço
e corte no fim do recibo, que é configuração do driver, não do CSS.

## 2. Gaveta — ✅ caminho construído (2026-08-12)

> **Fechado em software.** O agente local existe
> (`tools/pos-drawer-agent/`), a config é por terminal no Admin, e os quatro
> momentos chamam um caminho só. Falta o balcão: instalar o agente, colar o
> token, e o olho do operador confirmando que abriu.
> Ver [POS-CASH-DRAWER-PLAN](POS-CASH-DRAWER-PLAN.md) — inclusive a medição que
> destravou o desenho (HTTPS → `127.0.0.1` **passa** no Chrome 148) e a correção
> do pulso (**50/500ms**, não 25/250 — aqueles são as unidades de 2ms).

O diagnóstico abaixo permanece porque é ele que explica por que o caminho é este.

### O diagnóstico original

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
2. ~~**Gaveta**~~ — ✅ feito em 2026-08-12 (agente local + config por terminal +
   os quatro momentos). Sobra instalar no balcão e confirmar com o aparelho.
3. ~~**Rótulo honesto** no health~~ — ✅ para a gaveta: com adapter `agent` o
   servidor responde `deferred` ("verificado na estação"), porque ele não
   alcança a loopback do balcão. Os outros periféricos seguem por declaração.
4. **Leitor de crachá** — implementável e testável sem o aparelho (emulação de teclado).
5. **Comprovante impresso de sangria** — item de controle, separado de propósito:
   se ele virar o jeito de abrir a gaveta, volta o acoplamento descartado acima.

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
