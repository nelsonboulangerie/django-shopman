# NCM das bebidas preparadas no balcão — revisão de 23/09/2026

> Pedido do dono: *"faça uma busca/força-tarefa e revise você os NCM das 14
> bebidas. o contador só revisa depois."*
>
> **Isto é uma revisão fundamentada, não um parecer.** O contador decide, e as
> duas linhas que têm dinheiro dentro estão marcadas como pergunta, não como
> resposta.

## O que estava errado

O catálogo do alpha declarava, na NFC-e, códigos que descrevem outra coisa —
e **cinco bebidas nem estavam na tabela do seed**, caindo no *default* de
panificação.

| o que estava lá | o que esse código realmente descreve | quantas bebidas |
|---|---|---|
| `1905.90.90` | **Produto de padaria, pastelaria ou bolachas** | 5 |
| `2101.11.10` | **Café solúvel** — o pó, não a xícara | 2 |
| `2101.12.00` | Preparação à base de extrato/essência/concentrado de café | 5 |
| `0902.40.00` | **Folha de chá preto a granel**, embalagens acima de 3 kg | 5 |

Um Caffè Latte declarado como produto de padaria não é detalhe de cadastro: é
o que sai impresso na nota.

## O raciocínio

**O capítulo 22 da NCM é o das bebidas prontas para consumo.** As posições
21.01 e 21.06 são das **preparações que servem para fazer bebida** — pó
solúvel, extrato, concentrado, xarope. É a distinção que a própria
classificação faz: preparação para elaborar bebida não entra no capítulo 22,
que é o das bebidas prontas.

O que a casa entrega no balcão é a bebida pronta. Então o endereço é o 22, e
dentro dele:

> **2202** — *"Águas, incluindo as águas minerais e as águas gaseificadas,
> adicionadas de açúcar ou de outros edulcorantes ou aromatizadas e outras
> bebidas não alcoólicas, exceto sucos (sumos) de fruta ou de produtos
> hortícolas da posição 20.09."*
>
> **2202.10.00** — águas adicionadas de açúcar/edulcorantes ou aromatizadas.
> **2202.99.00** — *"Outras"*.

Café, chá, chocolate e as bebidas com leite não são água aromatizada nem suco
da 20.09 — caem em **2202.99.00**.

## A proposta, produto a produto

Todos passam a **`2202.99.00`**, com **CEST vazio**:

| | produto | estava | o que aquele código descrevia |
|---|---|---|---|
| `SP` | Espresso | `21011110` | café solúvel |
| `COAD` | Café Coado | `21011110` | café solúvel |
| `CAP` | Cappuccino | `21011200` | preparação à base de extrato de café |
| `CAPMO` | Mochaccino | `21011200` | idem |
| `FRAP` | Frappé | `21011200` | idem |
| `VIEN` | Vienna | `21011200` | idem |
| `CE` | Coffee Float | `21011200` | idem *(sai do catálogo)* |
| `SPMC` | Espresso Macchiato | `19059090` | **padaria** |
| `CAFL` | Caffè Latte | `19059090` | **padaria** |
| `MOCHA` | Mocha | `19059090` | **padaria** |
| `CHOQ` | Chocolate Quente | `19059090` | **padaria** |
| `CHHIB` | Chá Hibisco | `19059090` | **padaria** |
| `CTFV` | Chá Tônica Frutas Vermelhas | `19059090` | **padaria** |
| `CHBLU` | Chá Bleu | `09024000` | folha de chá a granel |
| `CHCAM` | Chá Camille | `09024000` | idem |
| `CHROU` | Chá Rouge | `09024000` | idem |
| `CHSOP` | Chá Sophie | `09024000` | idem |
| `SFTCH` | Soft Chai Cítrico | `09024000` | idem |
| `SDLA` | Soda de Laranja | `22021000` | refrigerante em embalagem |
| `CV` | Cream Soda do dia | `22021000` | refrigerante em embalagem |

## Duas coisas que eu NÃO decidi

### 1. O CEST fica vazio, e isso é escolha

O `2202.99.00` tem CEST — e três deles descrevem, na letra, o que a casa
vende:

- `17.113.00` — bebidas prontas à base de mate ou chá
- `17.114.00` — bebidas prontas à base de café
- `17.115.00` — bebidas prontas à base de soja, leite ou cacau

**Mas CEST é endereço de substituição tributária**, e a ST alcança o
industrializado pronto para beber que circula na cadeia — a garrafa, a lata.
O que a casa prepara no balcão não é esse produto, e o perfil fiscal do
catálogo é `own_production` (CFOP 5102 / CSOSN 102, sem ST). Preencher um CEST
ali declararia uma ST que não existe.

**Decisão do dono (23/09):** *"se não for útil CEST nas bebidas preparadas,
deixa sem"*. Fica vazio. O contador confirma quando revisar.

### 2. As duas sodas da casa — resolvido em 23/09, e o motivo não é o que eu achava

`SDLA` (Soda de Laranja) e `CV` (Cream Soda) **passaram a `2202.99.00`**, como
as outras. O dono leu certo — *"acho que a soda cai em preparação de balcão"* —
e o argumento acabou sendo mais forte do que o dele:

> O Imposto Seletivo sobre bebida açucarada só alcança o produto em **embalagem
> primária**, entendida como *"aquela em contato direto com o produto e
> destinada ao consumidor final"* (LC 214/2025, art. 409, §1º, V).

**Soda tirada na torneira e servida no copo não tem embalagem primária.** O IS
não a alcança em NCM nenhum. Sem esse peso na balança, sobra a classificação
pura — e o que o cliente leva é a mesma bebida preparada que as outras
dezessete.

⚠️ **O que muda a conta é a embalagem, não o açúcar.** No dia em que a casa
engarrafar a soda para vender, há embalagem primária destinada ao consumidor
final: o NCM passa a ser o `2202.10.00`, e a casa vira **fabricante de bebida
açucarada** — contribuinte do Imposto Seletivo na primeira operação de
fornecimento, sem crédito a aproveitar. Servida no copo, nada disso acontece.

## O que é o Imposto Seletivo, e o que ele faz com a casa

- **Monofásico e sem crédito.** Incide **uma vez só** na cadeia, na primeira
  operação de fornecimento, e é vedado tanto aproveitar crédito de etapa
  anterior quanto gerar crédito para a seguinte (LC 214/2025, art. 410).
- **Quem paga é o fabricante ou o importador**, não o balcão. A padaria que
  **revende** Coca-Cola não calcula nem declara o IS: ele já veio dentro do
  preço de compra, como custo.
- **Para a casa, portanto, o efeito é de preço, não de obrigação.** O
  industrializado que ela revende tende a ficar mais caro, e como não há
  crédito, esse custo não se recupera — ou aperta a margem, ou vai para a
  etiqueta.
- **Começa em 2027, e não automaticamente.** As alíquotas dependem de lei
  ordinária ainda não editada, respeitadas as anterioridades anual e
  nonagesimal.
- **A finalidade é extrafiscal**: desestimular consumo, não arrecadar. É por
  isso que ele alcança o produto embalado que circula, e não a bebida que
  alguém prepara e serve na hora.

**A única porta pela qual a casa entraria nesse imposto é fabricar e embalar**
um dos produtos da lista. Enquanto a soda sai da torneira para o copo, ela está
fora.

## Fora deste escopo

- **Revenda de industrializado** (chás Kãnfa em lata e pouch, água mineral,
  geleias, queijos): o NCM vem da NF-e do fornecedor, não desta revisão.

  ⚠️ **E não há pergunta de perfil aqui — eu cheguei a levantar uma, e estava
  errado.** O eixo do `FiscalProfile` é **ST × não-ST**, não "quem fabricou":
  `own_production` é, na letra do código, *"fabricação própria **+ revenda
  comum**"*, e é a parametrização que o contador já fez (SEFA-PR). Chá seco é
  revenda comum; a ST no segmento de bebida alcança refrigerante, água e
  industrializado. Ser comprado pronto é outro eixo — é o cadastro de compra
  (`buyman.Material`) do mesmo SKU, que deixa o Compras receber a nota.

  **O chá da Kãnfa é duas coisas, e o cadastro já as separa:** a folha seca que
  se revende (12 produtos, lata e pouch, NCM 0902.20.00) e a bebida preparada
  na hora com o blend como insumo (7 produtos, com ficha apontando para
  `CHA-BLEU`, `CHA-CHAI`…, NCM 2202.99.00).
- **Mercearia da casa** (`MT`, `BK`, `TPND`, `RTAT`, `GL`, `LN`): já estavam
  marcados "validar com o contador" e continuam.

## Como aplicar

```bash
python manage.py apply_fiscal_ncm            # mostra o que mudaria
python manage.py apply_fiscal_ncm --apply    # grava
```

O `seed` nasce com os mesmos valores.

## Fontes

- [NCM 2202.99.00 — descrição oficial e CESTs associados](https://buscadorncm.com.br/ncm/22029900)
- [NCM 2202.10.00 — descrição oficial e CESTs associados](https://buscadorncm.com.br/ncm/22021000)
- [Tributação da NCM 2202.99.00 (FazComex)](https://ncm.fazcomex.com.br/22029900-outras/)
- [NCM do café para cafeteria — a xícara servida é bebida pronta](https://www.sisfood.com.br/saiba-mais/fiscal/ncm-cafe)
- [NCM 2106.90.90 e a fronteira com o capítulo 22 (preparação × bebida pronta)](https://tributodevido.com.br/portal/classificar-preparacoes-alimenticias-compostas-na-ncm-2106-90-90/)
- [Imposto Seletivo: LC 214/2025 alcança o 2202.10.00, a partir de 2027](https://www.sisfood.com.br/saiba-mais/fiscal/ncm-refrigerante)
- [Imposto Seletivo sobre bebidas açucaradas: quem paga](https://www.elscon.com.br/post/imposto-seletivo-bebidas-acucaradas)
- [LC 214/2025, art. 409 §1º V e art. 410 — incidência, embalagem primária e monofasia](https://modeloinicial.com.br/materia/direito-tributario-reforma-tributaria-lc-214-2025-imposto-seletivo)
- [Imposto Seletivo: desenho, alcance e desafios (CRCSP)](https://online.crcsp.org.br/portal/noticias/noticia.asp?c=9819)
