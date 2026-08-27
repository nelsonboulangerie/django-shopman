# Leitor de NF-e de Compras

Este runbook cobre o adapter `shopman.shop.adapters.purchase_invoice_nfe.read_invoice`,
usado pelo app Nuxt `purchase-nuxt` em `Compras > Receber`.

## Objetivo

O operador escaneia o QR Code, codigo de barras ou digita a chave de acesso da
NF-e/NFC-e. O BFF valida a chave, busca o XML da nota e devolve um rascunho de
recebimento com fornecedor, itens, quantidades, custos e conversoes provaveis.
O operador sempre confere antes de confirmar a entrada no Stockman.

## Configuracao

Variaveis principais:

```env
SHOPMAN_PURCHASE_INVOICE_READER=shopman.shop.adapters.purchase_invoice_nfe.read_invoice
PURCHASE_NFE_ENVIRONMENT=producao
PURCHASE_NFE_UF=41
PURCHASE_NFE_RECIPIENT_DOCUMENT=12345678000190
PURCHASE_NFE_CERTIFICATE_PATH=/path/nelson-a1.pfx
PURCHASE_NFE_CERTIFICATE_PASSWORD=...
```

Alternativas:

```env
PURCHASE_NFE_CERTIFICATE_PFX_BASE64=...
PURCHASE_NFE_XML_DIR=/app/private/nfe-xml
PURCHASE_NFE_AUTO_MANIFEST_CIENCIA=false
PURCHASE_NFE_FUZZY_MATCH_MIN_SCORE=87
```

`PURCHASE_NFE_XML_DIR` e util para alpha/local: se existir um arquivo
`<chave>.xml`, `NFe<chave>.xml`, `procNFe-<chave>.xml` ou qualquer `.xml`
contendo a chave, o adapter usa esse XML antes de consultar a SEFAZ.

## Mapeamento

O caminho mais seguro e declarar o mapa no fornecedor:

```json
{
  "purchase": {
    "invoice_product_map": {
      "FAR-25": {
        "materialSku": "FARINHA-T65",
        "conversionLabel": "saco 25 kg"
      }
    }
  }
}
```

Tambem e possivel declarar codigos no insumo:

```json
{
  "purchase": {
    "invoice_codes": ["FAR-25"],
    "gtins": ["7890000000000"],
    "supplier_codes": {
      "SUP-MOINHO-SP": ["FAR-25"]
    }
  }
}
```

Quando faltar mapeamento:

- fornecedor sem CNPJ cadastrado fica vazio e bloqueia a confirmacao;
- item sem insumo fica visivel como `Definir insumo`;
- unidade de compra sem conversao fica com `requiresConversion=true`, e com
  `conversionSuggestion` preenchida quando a nota responde (secao seguinte);
- matching pelo nome vira **sugestao visivel**, nunca preenchimento:
  a linha sai com `materialSku` vazio, `suggestedMaterialSku` com o insumo
  candidato e `suggestionScore` (0-100). O purchase-nuxt mostra a sugestao com
  badge e acao de aceitar/trocar, e a linha segue bloqueando a confirmacao ate
  o operador decidir. A pontuacao principal e **cobertura de tokens**: se todo
  token significativo do nome do insumo aparece na descricao da NF (exato, ou
  por prefixo para abreviacao de distribuidor: FERM~fermento), vale 100 —
  "AZEITE DE OLIVA EXTRA VIRGEM ANDORINHA VD 500ML" sugere "Azeite extra
  virgem". O WRatio do rapidfuzz fica de reforco para nomes de varios tokens.
  Limiar padrao 87 (`PURCHASE_NFE_FUZZY_MATCH_MIN_SCORE`); `0` desliga.

## Os dois eixos do item, e por que eles importam

Todo item de NF-e traz **dois pares**, por obrigacao legal:

| Par | Campos | O que e |
|---|---|---|
| comercial | `uCom` · `qCom` · `vUnCom` | como o fornecedor vendeu: "10 UN" |
| tributavel | `uTrib` · `qTrib` · `vUnTrib` | a unidade fiscal de referencia: "5 KG" |

O adapter le os dois **como blocos**: sem par comercial utilizavel (`uCom` vazio
ou `qCom` <= 0), o item inteiro passa a ser lido pelo tributavel. Nunca a
unidade de um com a quantidade do outro — foi esse cruzamento que fez uma nota
de 10 unidades de fermento entrar como 10 kg no QA de 27/08/2026.

A quantidade da linha sai assim:

- **conversao declarada** (`saco 25 kg`): fica a quantidade comercial (2 sacos);
  quem multiplica e a conversao, no recebimento;
- **unidade que a fisica alcanca** (nota em `G`, insumo em `kg`): converte na
  hora, via `shopman.utils.units`. E conversao definicional (ADR-024, tipo 1):
  nao pede tabela, nao pede autor, nao trava;
- **nem uma nem outra** ("10 UN" de insumo pesado em `kg`): fica na unidade
  comercial e a linha **trava** ate alguem declarar o fator (regra R4).

### A conversao que a nota sugere

Quando a linha trava, o adapter procura o fator na propria nota e devolve
`conversionSuggestion` — `{label, factor, kind, source, note}`:

- `source=invoice-tax-pair`: `fator = qTrib / qCom`, com o par tributavel levado
  a unidade-base. E **declaracao fiscal do emissor**, entao e a fonte primaria;
- `source=product-description`: a gramatura embutida no `xProd`
  ("FERM BIOL FRESCO MAURI 500G"). Texto livre, sinal **secundario**: so entra
  quando o par tributavel nao decide.

Ler o par tributavel **nao fere a R4**: a regra proibe inventar fator, nao
proibe ler o que o emissor declarou. Nada e gravado — a linha continua
bloqueando a confirmacao ate o operador aceitar ou declarar outra, no mesmo
molde da sugestao de insumo.

Quando a nota **discorda** de uma conversao ja escolhida (saco declarado de
25 kg, nota dizendo 20), a sugestao vem junto com a conversao e a tela mostra a
divergencia como **aviso** — nao trava, mas nao passa calada. E o alerta de
ordem de grandeza da ADR-024.

### Declarar conversao sem sair do recebimento

`POST /api/v1/backstage/purchase/conversions/`, permissao
`backstage.operate_purchase`:

```json
{
  "materialSku": "FERMENTO-BIO",
  "supplierRef": "SUP-MAURI",
  "label": "pacote 500 g",
  "factor": "0.5",
  "kind": "conventional"
}
```

`supplierRef` vazio = conversao vale para qualquer fornecedor. A resposta traz
`conversionId`, que a linha travada seleciona. A linha grava `created_by`: fator
errado muda estoque e dinheiro de toda compra seguinte, entao tem de dar para
perguntar quem declarou. Correcao e exclusao continuam no Admin.

Recusas: `conversion_factor_invalid` (fator <= 0 ou nao numerico),
`conversion_label_required`, `conversion_label_too_long`,
`conversion_kind_invalid`, `conversion_validation_failed` (rotulo ja existe no
insumo/fornecedor).

### O carimbo da conversao no lancamento

Toda entrada que atravessa uma conversao grava, no proprio `Move`:

```json
{"converted_via": {"label": "un 500 g", "factor": "0.500000", "approximate": false}}
```

As tres chaves viajam juntas: rotulo sem fator nao deixa refazer a conta, e fator
sem o `approximate` nao diz se a conta era exata. Entrada na propria unidade-base
**nao carimba nada** — nao houve ponte, e uma chave com `null` fingiria que houve.

Saldo que atravessou ponte **aproximada** volta na projection com
`stockIsApproximate: true` e aparece como `≈ 1,5 kg` na tela, com a pendencia
"Saldo estimado" no insumo (ADR-024, R3: some o `≈`, some a informacao). A janela
que decide ate quando o `≈` vale e a validade do insumo — sem ela, a janela de
consumo da politica — e erra **de proposito para o lado seguro**: marcar de menos
esconderia a incerteza.

## Operacao fiscal

A tela publica da SEFAZ/PR serve para conferencia humana e normalmente envolve
CAPTCHA. Para sistema, o caminho operacional e Distribuicao DF-e com certificado
A1/PFX do destinatario. Quando a SEFAZ retornar somente resumo da NF-e para o
destinatario, pode ser necessario registrar `Ciencia da Operacao` antes de obter
o XML completo. O adapter suporta isso com `PURCHASE_NFE_AUTO_MANIFEST_CIENCIA`,
mas o default e `false` para evitar efeito fiscal automatico sem decisao
operacional explicita.

## Smoke de alpha

Depois de configurar as credenciais no ambiente, rode:

```bash
python manage.py smoke_gateways --sandbox-only --json
```

O check `purchase_nfe/distribution_credentials` deve sair `ready`. Se ficar
`blocked_by_credentials`, faltam certificado, documento do destinatario ou o
reader `SHOPMAN_PURCHASE_INVOICE_READER`.
