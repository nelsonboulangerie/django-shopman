# WP — Fotos do Instagram oficial para a Home

> Pedido do dono em 23/09/2026: *"Lance um WP separado para encontrar no nosso
> Instagram oficial fotos úteis para serem utilizadas na Home."*

Irmão do [WP-FOTOS-DA-CASA](WP-FOTOS-DA-CASA.md). A F3 de lá já tirou da Home
as imagens de banco (PR #1000, 23/09): hoje as sete fotos são da própria loja.
Este WP não refaz aquilo. Ele usa o Instagram como **acervo de onde escolher**,
para trocar ou variar as fotos que estão lá e cobrir os lugares que ainda
repetem a mesma imagem.

## O Instagram oficial

**@nelsonboulangerie**: <https://www.instagram.com/nelsonboulangerie/>. É o
link que o site declara (`config/management/commands/apply_search_presence.py`,
`sameAs` do JSON-LD). O perfil tem ~27 mil seguidores e ~372 publicações, com a
bio "Artesanal Desde 1997". Esses números vêm do índice de busca, não de uma
visita ao perfil.

## O que deu para ver do perfil (23/09/2026): quase nada

- **A grade do perfil exige login.** A leitura anônima de
  `instagram.com/nelsonboulangerie/` devolve só o cabeçalho. Não fizemos login,
  não usamos credencial e não contornamos o bloqueio. Pela regra da casa, isso
  não se faz.
- **Um post avulso às vezes abre sem login**, desde que alguém tenha o link.
  O índice de busca conhece **um único post da própria conta**:
  - <https://www.instagram.com/p/Ci0VYB6uq-u/>, de 22/09/2022, sobre os 25 anos
    da casa: a trajetória do Nelson, de veterinário a padeiro. A imagem mostra a
    loja ou a vitrine. Pela legenda é **candidato ao bloco institucional**
    (ver "slot que não existe" abaixo), mas **a foto em si não foi vista**, e as
    fotos da casa têm hoje uma vitrine diferente. Só serve se o dono, olhando,
    reconhecer a loja atual.
- Outros posts que a busca devolveu sobre "Nelson Boulangerie" **são de
  terceiros**, por exemplo o vídeo de visita do @luigi_naestrada
  (<https://www.instagram.com/p/DWv_w3kDiAz/>). Foto de cliente ou de
  influenciador **não entra** (ver direitos, abaixo).

**Conclusão:** não há lista de candidatos garimpada por máquina. Quem pode
percorrer a grade é **o dono, logado na conta dele**, com a especificação
abaixo em mãos. Este WP existe para essa garimpagem levar 15 minutos e acertar
na primeira vez.

## Os lugares da Home que levam foto (medidos no código em 23/09)

Todas moram em `surfaces/storefront-nuxt/public/img/home/` e são referenciadas
direto no código. Não passam pelo banco nem pelo catálogo.

| # | Lugar | Arquivo | Onde | Quadro que a tela recorta | Mínimo para ficar nítido | Orientação |
|---|---|---|---|---|---|---|
| H1 | Herói, "quem chega" (celular) | `facade6.webp` (900×1600) | `HomeHeroThing.vue` | quase a tela inteira em pé, ~2:3 a 9:16 | **1080×1920** | **vertical** |
| H2 | Herói, "quem chega" (≥640px) | `facade2.webp` (1600×900) | idem | faixa de ~1090×440–480, ~2,3:1 | **2200×1000** (16:9 serve se o assunto estiver no meio) | **horizontal** |
| H3 | Herói, "pedido em andamento" | `selfservice.webp` (1254² nos dois) | idem | os dois quadros acima | 1080×1920 **e** 2200×1000 | par vertical + horizontal |
| H4 | Herói, "quem já comprou" (celular) | `facade4.webp` (900×1600) | idem | vertical | 1080×1920 | vertical |
| H5 | Herói, "quem já comprou" (≥640px) | `interior.webp` (1600×900) | idem | faixa larga | 2200×1000 | horizontal |
| H6 | Herói, "feito à mão" | `baguette.webp` (1254² nos dois) | idem | os dois quadros | 1080×1920 **e** 2200×1000 | par vertical + horizontal |
| C1 | "Como funciona": pedir online | `baguette.webp` | `pages/index.vue` | 16:9, ~540 px de largura | 1280×720 | horizontal |
| C2 | "Como funciona": vir à loja | `selfservice.webp` | idem | 16:9 | 1280×720 | horizontal |
| W1 | Fundo do bloco "Fale no WhatsApp" | `facade1.webp` | idem | faixa larga, **35% de opacidade sob texto branco** | 1600×900 | horizontal |
| S1 | Cartão de compartilhamento (WhatsApp/Instagram/Facebook) | `Shop.seo_share_image_url` (Admin), vazio = 1º destaque | `index.vue` → og:image | **1200×630** | 1200×630 | horizontal |

Fora desta tabela, e de propósito: o cartão "repetir pedido" e a vitrine de
destaques usam **foto de produto** (`image_url` do catálogo, host `img.`). Essas
fotos são do WP-FOTOS-DA-CASA, porque foto de produto promete **aquela** peça.

**Onde está mais fraco hoje:**
- **H3 e H6 usam foto quadrada nos dois quadros.** No celular a foto é
  recortada em pé e perde as laterais. No computador perde o alto e o baixo.
  São os primeiros a ganhar par próprio (vertical + horizontal).
- As fotos verticais (900×1600) ficam **abaixo da nitidez** num celular de tela
  3x. O ideal é ≥1080×1920.
- `baguette` e `selfservice` aparecem duas vezes na Home (herói e "Como
  funciona"). Com fotos novas, C1 e C2 deixam de repetir o herói.
- **O slot que não existe:** a Home não tem bloco "nossa história" ou "sobre".
  O post dos 25 anos sugere um, mas criar a seção é **decisão de produto do
  dono**. Este WP não a cria. Fica anotado.

## Tema de cada lugar (o que procurar na grade)

| Lugar | Assunto | Por quê |
|---|---|---|
| H1/H2, quem chega | **fachada ou salão com luz de dia**, a casa como lugar | Primeira impressão: onde fica e como é por dentro |
| H3, pedido em andamento | **balcão/vitrine cheia** ou **mãos embalando** | "Seu pedido está sendo preparado" |
| H4/H5, quem já comprou | **interior acolhedor**: mesas, café servido | Volta de quem já conhece |
| H6, feito à mão | **forno/fornada**: pão saindo, massa sendo modelada, levain | O argumento central da casa (fermentação natural desde 1997) |
| C1, pedir online | **produto em contexto**, pronto para levar (sacola, caixa) | É o caminho da compra online |
| C2, vir à loja | **vitrine/balcão do autoatendimento** | É o caminho da visita |
| W1, WhatsApp | **ambiente com pouca informação** (textura, parede, luz) | Fica a 35% sob texto: detalhe miúdo vira ruído |
| S1, compartilhar | **a foto mais "Nelson" de todas**, legível pequena | É o que aparece no link colado no WhatsApp |

## Critérios de escolha (eliminatórios)

1. **Direito de uso da casa.** Só publicação **da própria conta** e **feita
   pela casa ou por fotógrafo contratado com cessão de uso**. Repost, foto de
   cliente, de influenciador ou de imprensa **não serve**, mesmo aparecendo no
   perfil. Na dúvida, fica de fora.
2. **Sem texto nem arte por cima:** nada de legenda gravada, selo, logo
   aplicado, moldura, "PROMO" ou data. A Home põe o próprio texto sobre a foto.
3. **Sem rosto de cliente** sem autorização escrita. Funcionário só com
   autorização. Mãos e costas trabalhando resolvem quase sempre.
4. **Retrata a casa de hoje.** Fachada, vitrine ou salão de antes de reforma
   mentem, pelo mesmo princípio de "a casa só afirma o que honra".
5. **Luz natural ou quente e foco no assunto.** Nada de flash estourado, filtro
   pesado nem sombra dura no produto.
6. **Aguenta o recorte.** Para o herói, o assunto no **terço central**: a
   mesma foto é cortada em pé no celular e em faixa no computador. Foto
   quadrada de feed raramente serve aos dois. Prefira o par.
7. **Resolução mínima da tabela acima.** Nenhuma imagem é ampliada.

## Por que não baixar do Instagram

O Instagram entrega no máximo **1080 px de largura, recomprimido**, e o feed é
quadrado ou 4:5. Isso não cobre o herói vertical nítido (1080×1920) nem a faixa
larga (2200 px). Por isso **o Instagram serve para achar a foto, não para
fornecer o arquivo**. O original vem de:

- **o celular que fotografou:** Fotos do iPhone, "Exportar original não
  modificado", ou AirDrop com "Todos os dados de Fotos" ligado. No Android,
  compartilhar o arquivo, não um print;
- **o fotógrafo:** pedir o RAW/JPEG em resolução máxima **e** confirmar por
  escrito que a casa pode usar no site;
- **o acervo da casa:** o repositório `nb-catalog` e o `cardapio.*` guardam
  originais. Vale conferir lá antes de pedir a alguém.

Em último caso (original perdido), o arquivo do Instagram serve **só** para C1,
C2 e W1, onde 1080 px basta. Nunca para o herói.

## O que depende do dono

1. **Percorrer a grade logado** e anotar, para cada lugar da tabela, 1 a 3
   links de post (`instagram.com/p/…`) com o número da foto no carrossel.
2. **Conseguir o original** de cada escolhida (celular, fotógrafo ou acervo) e
   **confirmar o direito de uso** de cada uma.
3. **Decidir se a Home ganha o bloco "nossa história"** (o post dos 25 anos é o
   gancho). Sem essa decisão, o bloco não nasce.
4. **Olhar o post dos 25 anos** (<https://www.instagram.com/p/Ci0VYB6uq-u/>)
   e dizer se a foto ainda retrata a loja de hoje.

## Integração (a parte da sessão, depois que os originais chegarem)

Segue o fluxo que a F3 do WP-FOTOS-DA-CASA já provou:

1. O dono deixa os originais numa pasta. A sessão **não sobe nada antes de ele
   ver**.
2. Tratamento, pela mesma receita do `CATALOG-IMAGES-OFF-GITHUB-PLAN`: WebP
   q80, sem EXIF (`-strip`, que também tira a localização), **nunca ampliando**.
   Vertical com 1080×1920 e horizontal com 2200 px no lado maior. Uma
   rendição por quadro, e o `<picture>` do herói já baixa só a que cabe.
3. Prévia local da Home com cada candidata no quadro real (celular e
   computador), e captura para o dono aprovar ou pedir a próxima.
4. Arquivo em `surfaces/storefront-nuxt/public/img/home/` com **nome novo**
   (`forno.v2.webp`, nunca sobrescrevendo), e referência trocada em
   `HERO_IMAGES` (`HomeHeroThing.vue`) ou em `pages/index.vue`. O `alt`
   descreve a foto nova, porque o alt velho mente sobre a imagem nova.
5. S1, cartão de compartilhamento: 1200×630 enviado ao host `img.` e a URL
   colada em **Admin → Loja → imagem de compartilhamento**. O dado vive no
   banco, e sem configurar, o link usa o primeiro destaque.
6. Commit, PR e fila. O deploy do alpha é o push no `main`.

## Fora de escopo

- Automatizar a leitura do Instagram (API Graph ou scraping). A API exige app
  aprovado e token da conta. Scraping viola os termos de uso. Para uma
  curadoria de uma dúzia de fotos, o dono logado é o caminho certo.
- Fotos de produto do catálogo: são do WP-FOTOS-DA-CASA (F1, F2 e F4).
- Imagem gerada por IA: mesma regra do WP irmão.
