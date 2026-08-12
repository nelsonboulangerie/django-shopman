# CATALOG-IMAGES-OFF-GITHUB-PLAN — tirar as fotos do GitHub e do exagero

**Status:** 🔖 aberto (2026-08-11). Origem: furo #1 do smoke de alpha
([ALPHA-READINESS-AUDIT §7](ALPHA-READINESS-AUDIT.md)).

São **dois problemas independentes** que costumam ser confundidos num só. Vale
separar, porque o primeiro é quase de graça e o segundo é trabalho de conteúdo.

---

## Problema 1 — o host errado (barato de resolver)

O seed aponta as fotos para `raw.githubusercontent.com`
([seed.py:790](../../config/management/commands/seed.py)):

```python
IMG = "https://raw.githubusercontent.com/pablondrina/nb-catalog/main/img/products"
```

O `raw.githubusercontent.com` **não é CDN**. É um endpoint de conveniência para
ler arquivo de repositório: o GitHub limita hotlink e desencoraja uso como
servidor de assets. Se estrangular durante o alpha, **20 produtos ficam sem foto**
na loja — sem aviso, sem fallback além do ícone de croissant.

### A boa notícia: o CDN já existe e já está pago

O app `nb-catalog-app` na DigitalOcean (`a030e90a-…`) é um **static site servindo
o MESMO repo** `pablondrina/nb-catalog`, com `deploy_on_push: true`, publicado em
**`menu.nelsonboulangerie.com.br`**. Medido em 11/08, o mesmo arquivo:

| | `raw.githubusercontent.com` | `menu.nelsonboulangerie.com.br` |
|---|---|---|
| bytes | 1.187.232 | 1.187.232 (idêntico) |
| cache | — | `cf-cache-status: HIT`, `s-maxage=86400` |
| borda | GitHub | Cloudflare |

**Ou seja: mesmos arquivos, mesmo repo, mesmo fluxo de publicação (`git push`),
só que atrás da Cloudflare.**

### Ação 1 (uma linha)

```python
IMG = "https://menu.nelsonboulangerie.com.br/img/products"
```

Sem migração de arquivo, sem novo serviço, sem custo novo. Reseed do staging
(`seed --flush --profile qa`) e pronto. ⚠️ As fotos que o Pablo já editou no
staging pela mão precisam ser reconciliadas antes do flush — ver
[[project_cardapio_2027_menu]].

### Ação 2 — o cabeçalho de cache

O static site devolve `cache-control: public,max-age=10,s-maxage=86400`. A borda
guarda por 1 dia, mas o **navegador só por 10 segundos** — quem volta à loja
rebaixa tudo de novo. Foto de catálogo é praticamente imutável; o certo é
`max-age` longo com **nome de arquivo versionado** (`ct.v2.jpg`) para invalidar
por renomeação, que é o idioma de asset estático.

---

## Problema 2 — o peso (o que o testador sente)

Mesmo servidas por um CDN perfeito, as fotos são **grandes demais para qualquer
caixa em que a loja as desenha**. Medido em 11/08, as 19 imagens do catálogo:

**Total: 12,38 MB.** Seis passam de 1 MB cada.

| arquivo | peso | | arquivo | peso |
|---|---|---|---|---|
| `bf.jpg` (Baguette) | **1,82 MB** | | `ct.jpg` (Croissant) | **1,13 MB** |
| `pho.jpg` | **1,64 MB** | | `fe.jpg` | **1,05 MB** |
| `foa.jpg` | **1,46 MB** | | `pc.jpg` | 0,88 MB |
| `cgr.jpg` | **1,40 MB** | | `me.jpg` | 0,65 MB |

A maior tem **3208×3208 (10,3 MP)**. No cardápio ela é desenhada num quadro de
**112×112**. São 35 de 35 imagens com mais de 3× a resolução necessária.

O markup **já está correto** — `loading="lazy"` e `decoding="async"` em
[ProductListItem.vue:57](../../surfaces/storefront-nuxt/app/components/ProductListItem.vue).
Não há o que consertar em código. É a fonte.

### Onde a loja realmente desenha cada foto

Levantado nos componentes:

| Uso | Caixa | Arquivo |
|---|---|---|
| Cardápio (lista) | **112×112** (`size-28`) | `components/ProductListItem.vue` |
| Sacola (linha) | **80×80** (`size-20`) | `pages/sacola.vue` |
| Home (destaques) | 4:3 na coluna da grade | `components/ProductTile.vue` |
| Cross-sell da sacola | 4:3 no card | `components/CartUpsellRail.vue` |
| **PDP (a maior)** | 4:3, full-bleed no mobile, `lg:w-1/2` no desktop | `pages/produto/[sku].vue` |

O maior desenho real é a PDP: ~600 px de largura no desktop, ~430 px no mobile.

### Orientação de tamanho e resolução

Retina (2×) sobre o maior desenho real, com folga — **não** sobre o monitor
teórico:

| Rendição | Dimensão | Formato | Alvo de peso | Cobre |
|---|---|---|---|---|
| **única (recomendada agora)** | **1200 px no lado maior** | WebP q80 (JPEG q82 de fallback) | **≤ 180 KB** | PDP, tile, thumb, sacola |
| `thumb` (fase 2, se medir valer) | 320 px | WebP q80 | ≤ 30 KB | cardápio + sacola |
| `full` (fase 2) | 1200 px | WebP q80 | ≤ 180 KB | PDP + tile |

**Recorte:** quadrado (1:1) na origem. A loja desenha 1:1 no cardápio/sacola e
4:3 com `object-cover` na home/PDP — um quadrado atende os dois sem deformar; o
`object-cover` corta as bordas, então **o assunto tem que estar centralizado**.

**Por que 1200 e não 900:** o Unsplash já entrega `w=900` e nessas a PDP fica no
limite em telas densas. 1200 é o menor número que não deixa a PDP macia.

**Por que uma rendição só, por enquanto:** `image_url` é **um** campo da projeção
— servir tamanhos por uso exigiria mudar o contrato (`image_thumb_url`) e mexer
nos cinco componentes. Uma rendição de 1200px já derruba de 12,38 MB para
**~3 MB** (−75%) sem tocar em backend. Fase 2 só se a medição pedir.

### Ação 3 — redimensionar na origem

O trabalho é no repo `pablondrina/nb-catalog`, não neste. Receita:

```bash
# 19 arquivos em img/products/ — 1200px no lado maior, quadrado, WebP q80
for f in img/products/*.jpg; do
  magick "$f" -resize 1200x1200^ -gravity center -extent 1200x1200 \
    -quality 80 -strip "${f%.jpg}.webp"
done
```

`-strip` tira EXIF (peso morto e, em foto de celular, **geolocalização da
padaria**). Manter o `.jpg` ao lado como fallback é opcional: a Cloudflare
negocia formato sozinha quando o `Accept` do cliente pede.

---

## Ordem sugerida

1. **Ação 1** (uma linha no seed) — tira o risco de estrangulamento do GitHub. Minutos.
2. **Ação 3** (redimensionar) — o ganho de peso de verdade. É trabalho de conteúdo, feito uma vez.
3. **Ação 2** (cache header + nome versionado) — depois do 3, senão versiona duas vezes.
4. Fase 2 (rendições por uso) — **só se** medir e ainda doer.

## Como saber se funcionou

Repetir a medição do §7 do audit: recarregar `/menu` com o console e conferir
`transferido_MB` dos recursos de imagem. Hoje: **1,35 MB só no visível**. Meta
após a Ação 3: **abaixo de 400 KB**.

## Fora de escopo

As 25 fotos do **Unsplash** (`w=900&q=80`) já vêm dimensionadas e não são risco de
hotlink — o Unsplash serve isso de propósito. Ficam como estão; se um dia virarem
foto própria, entram na mesma receita.
