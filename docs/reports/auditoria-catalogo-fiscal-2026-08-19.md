# Auditoria fiscal do catálogo — o que falta para ligar o porteiro (2026-08-19)

> Medição feita **no catálogo real do staging** (leitura, sem escrita), pela mesma regra
> que o porteiro de publicação e o builder de itens usam
> (`shopman.fiscalman.classification.validate_for_emission`).
> Comando equivalente: `manage.py fiscal_audit_catalog`.
>
> Existe para responder, **antes** de ligar
> `SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH`, quantos vendáveis publicados
> quebrariam. Procedimento do flip: [settings.md](../reference/settings.md), seção
> "Ligar o porteiro fiscal do catálogo".

## 1. Veredito

**Completude: 0 pendências. Dá para ligar a chave hoje sem despublicar nada.**

**Correção de perfil: 11 SKUs precisam da palavra do contador** — e isso é decisão
dele, não nossa. Não bloqueia o flip (o porteiro mede completude, não acerto), mas
bloqueia a emissão *correta*.

## 2. Completude — a medição

Universo: produtos `is_published` + `is_sellable` publicados em `ListingItem`
publicado+vendável, em vitrine ativa de canal ativo com `commerce_policy=order`.
Canais de venda ativos no staging: **`ifood`, `pdv`, `web`** (os `display` —
`google-shopping`, `meta-catalog`, `tv-cafe`, `tv-salao` — não emitem nota, logo não
têm porteiro; `whatsapp` está inativo).

| Grupo de falta | SKUs |
|---|---|
| Vendáveis publicados em canal de venda | **59** |
| Sem bloco `metadata['fiscal']` | **0** |
| Perfil fiscal desconhecido | **0** |
| NCM ausente ou fora de 8 dígitos | **0** |
| CEST faltando em perfil `resale` | **0** |
| CEST indevido em perfil `own_production` | **0** |

O catálogo inteiro (59 de 59 produtos, publicados ou não) tem bloco fiscal. Nenhum
produto é despublicado pelo flip.

## 3. Correção de perfil — o que a medição NÃO cobre

A auditoria pergunta "está preenchido?", não "está certo?". E aqui os 59 produtos
respondem a mesma coisa por construção: o seed atribui `profile: "own_production"`
a **todo** SKU, sem exceção — `fiscal_metadata_for_sku()` em
`config/management/commands/seed.py` devolve o perfil fixo, e só o NCM varia por SKU.

Ou seja: **nenhum produto foi classificado por perfil; todos herdaram o default.**
A pergunta "quais destes são revenda com ST?" nunca foi respondida.

Isso contradiz a referência canônica da casa. A
[parametrização fiscal NFC-e](../reference/fiscal-parametrizacao-nfce.md) §2 define o
perfil `resale` (CSOSN 500, CFOP 5405/6405, **CEST obrigatório**) como o de "revenda
sujeita a ST: **refrigerantes, água, industrializados**".

### 3.1 Contradição explícita com a parametrização

| SKU | Produto | NCM | Por quê |
|---|---|---|---|
| `AGUA` | Água | 22011000 (águas minerais e gaseificadas) | A parametrização §2 nomeia "água" como `resale`/ST. Está como `own_production`, sem CEST. |

### 3.2 Comprados e revendidos como vieram — precisam da decisão do contador

Estes chegam prontos de fornecedor e são vendidos na embalagem: é o desenho típico de
ST. Nenhum tem CEST, porque `own_production` não pede um.

| SKU | Produto | NCM |
|---|---|---|
| `GELEIA-MINI` | Geleia St. Dalfour (mini) | 20079990 |
| `CORNICHONS` | Cornichons | 20011000 |
| `QUEIJO-POMERODE` | Queijo Pomerode | 04061010 |
| `QUEIJO-CAMEMBERT` | Camembert | 04069020 |
| `CAFE-GRAO` | Café em Grão (250g) | 09012100 |
| `CHA-LATA` | Chá da Casa (lata) | 09022000 |
| `CHA-BLEU` | Chá Bleu | 09024000 |
| `CHA-CAMILLE` | Chá Camille | 09024000 |
| `CHA-ROUGE` | Chá Rouge | 09024000 |
| `CHA-SOPHIE` | Chá Sophie | 09024000 |

### 3.3 Fora da lista de propósito

`CREAM-SODA-DIA`, `SODA-LARANJA` e `CHA-GELADO-DIA` têm NCM de refrigerante/bebida
(2202), o que à primeira vista os colocaria em ST — mas o nome diz "do dia", isto é,
preparados na loja. Bebida preparada é `own_production` pela própria parametrização.
Mesma lógica para `BACON-CASA`, `MOSTARDA-CASA`, `PATE-RATATOUILLE`, `TAPENADE` e os
cafés/cappuccinos: preparo da casa. Ficam como estão salvo palavra em contrário.

## 4. O que precisamos do dono / contador

Para cada SKU das seções 3.1 e 3.2, duas respostas — e **só ele pode dá-las**:

1. **É `own_production` ou `resale`?** (revenda com ST ou não)
2. **Se `resale`: qual o CEST?** (7 dígitos, por produto)

⚠️ **Não preenchemos CEST nem trocamos perfil por conta própria.** Código fiscal
chutado não é zelo, é risco legal: um CEST errado numa NFC-e autorizada é erro de
documento fiscal, não bug de software. O campo fica vazio até vir a resposta.

Onde preencher, depois da resposta: **Admin → Produtos → Fiscal** (perfil + NCM;
CEST aparece na revenda). Também dá para corrigir o padrão do catálogo no seed
(`fiscal_ncm_by_sku` / `fiscal_metadata_for_sku`), que hoje assume perfil único.

Depois de preencher, `manage.py fiscal_audit_catalog --strict` volta a passar — e
aí ele passa dizendo algo, porque os `resale` novos exigirão CEST para fechar.

## 5. Como reproduzir esta medição

```bash
# No deployment (staging ou produção), leitura pura:
python manage.py fiscal_audit_catalog          # leitura humana
python manage.py fiscal_audit_catalog --json   # para script
python manage.py fiscal_audit_catalog --strict # gate: sai 1 se não estiver pronto
```
