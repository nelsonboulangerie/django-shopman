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
PURCHASE_NFE_FUZZY_MATCH_MIN_SCORE=0
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
- unidade de compra sem conversao fica com `requiresConversion=true`;
- fuzzy matching fica desligado por padrao (`PURCHASE_NFE_FUZZY_MATCH_MIN_SCORE=0`).

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
