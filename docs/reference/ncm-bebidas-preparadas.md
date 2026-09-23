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

**Pergunta ao contador:** confirma o CEST vazio para bebida preparada e servida?

### 2. As duas sodas da casa — esta tem dinheiro dentro

`SDLA` (Soda de Laranja) e `CV` (Cream Soda) seguem em **`2202.10.00`**, como
estavam. Os dois caminhos são defensáveis:

- **`2202.10.00`** descreve literalmente o que elas são: água gaseificada,
  aromatizada e adoçada. É o código do refrigerante.
- **`2202.99.00`** trataria toda bebida preparada no balcão igual, e a soda da
  casa não é um refrigerante industrializado.

O que separa os dois não é estética: **o `2202.10.00` é o único código da
posição 2202 alcançado pelo Imposto Seletivo** (LC 214/2025, Anexo XVII), com
incidência a partir de 2027. O `2202.99.00` está fora.

**Pergunta ao contador:** a soda feita na torneira da casa e servida no copo é
"bebida açucarada" para o Imposto Seletivo, ou é preparação de balcão?

## Fora deste escopo

- **Revenda de industrializado** (chás Kãnfa em lata e pouch, água mineral,
  geleias, queijos): o NCM vem da NF-e do fornecedor, não desta revisão. Fica
  de pé a pergunta que já estava no seed — se o perfil deles é `resale`, passam
  a exigir CSOSN 500, CFOP 5405/6405 e **CEST por produto**.
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
- [Imposto Seletivo sobre bebidas açucaradas](https://www.elscon.com.br/post/imposto-seletivo-bebidas-acucaradas)
