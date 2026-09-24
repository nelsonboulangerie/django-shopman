# WP — Insumos sem fricção: da nota ao ingrediente

> Pedido do dono em 22/09/2026: *"Preciso deixar tudo o mais prático possível
> para tanto criar as receitas como para realizar os recebimentos no app
> Compras sem fricção"*.

## O número que explica a fricção

Medido no alpha em 22/09:

| | |
|---|---|
| Insumos cadastrados | **57** |
| Com custo de fornecedor | **5** |
| Com conversão de unidade cadastrada | **6** |
| Fornecedores | 17 |

**Cinquenta e dois insumos não têm custo e cinquenta e um não têm conversão.**
Como o recebimento exige a conversão para fechar a linha ("4 SC = 100 kg"), a
consequência é exata: quase toda linha de nota para num bloqueio pedindo
cadastro, no balcão, com o entregador esperando. A fricção não é de tela — é
de cadastro vazio.

## Onde cada fricção mora

**1. O primeiro recebimento de cada insumo é o pior.** Fornecedor novo ou
embalagem nova exige declarar a conversão na hora. O Compras já sugere o fator
lendo os dois eixos da NF-e (`qCom`/`qTrib`), mas só sugere — e sugestão que
bloqueia não tira ninguém do balcão.

**2. O de-para nota→insumo já aprende, mas só depois do primeiro acerto.**
`Supplier.metadata.purchase.invoice_product_map` guarda o par confirmado, e o
scan seguinte resolve sozinho. Ninguém semeou esse mapa com o histórico de
notas que já existe no e-mail da casa.

**3. Nomes que não se encontram.** `MANTEIGA-FR`, `FARINHA-INT`,
`SALSINHA-DESID`, `CENTEIO` (que é farinha e não está na família das
farinhas), `BATON-CHOCOLATE` e `GOTAS-CHOCOLATE` invertidos em relação ao
`CHOCOLATE-70`. Quem procura digita a família.

**4. Insumos que são a mesma coisa que um produto.** `TONICA` era a tônica que
entra na bebida **e** a garrafa que se vende; a conversa de 22/09 separou as
duas (a de insumo é Antarctica, a de prateleira é Wewi). `AGUA` é órfã: não
está em ficha nenhuma, e o nome colide com a água mineral de revenda. Cada um
desses é um estoque duplicado esperando para divergir.

**5. Ficha que aponta para o vazio.** A ficha do Vinagrete à Francesa usa
`MT`, que é o SKU de um **produto** — e de um produto que nem existe de fato.
A mostarda de insumo da casa é Beaufor Dijon, balde de 1 kg, food service.

**6. Três insumos com saldo e nenhuma ficha:** `BAUNILHA`,
`QUEIJO-COLONIAL` e a própria `AGUA`. Ou falta ficha, ou saíram de uso.

## As fatias

**F1 — cadastro que nasce pronto.** Ao criar insumo, o sistema propõe SKU na
convenção da casa (tipo na frente, sem abreviação), unidade-base e validade a
partir do nome e do que já existe. É a mesma peça que o Catálogo precisa, e
nasce compartilhada.

**F2 — semear o de-para com o histórico de notas.** As NF-e dos fornecedores
já estão no e-mail da casa. Ler as últimas de cada fornecedor e propor o
de-para nota→insumo **antes** do próximo recebimento transforma o primeiro
scan de cada fornecedor em conferência, não em cadastro.

**F3 — conversão declarada uma vez, no lugar certo.** Fechar o ciclo da
sugestão que a NF-e já dá: aceitar o fator lido vira cadastro, com
procedência ("veio da nota tal"), em vez de formulário à parte.

**F4 — a faxina de nomes e duplicatas.** As seis renomeações, a `AGUA`, a
`TONICA`, o `MT` e os três sem ficha. Renomear insumo arrasta ficha: é
migração de dado, não edição de texto.

**F5 — custo que entra sozinho.** O recebimento já grava o custo unitário no
movimento; falta ele virar custo de fornecedor quando for o primeiro, para os
52 sem custo pararem de ser 52.

## O que fica de fora, e por quê

Recebimento de **mercadoria de revenda** já foi feito (PR #964): a linha da
nota pode apontar para um produto do catálogo, e o estoque creditado é o do
SKU que o cliente leva. Este WP é sobre o outro lado — o insumo que vira pão.

⚠️ Nada aqui pede modelo novo: `Material`, `MaterialConversion`,
`SupplierMaterialCost` e o mapa de de-para já existem. O que falta é o
cadastro estar cheio antes de o entregador chegar.
