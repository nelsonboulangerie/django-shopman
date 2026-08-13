# TikTok Developer App — Nova submissão

## Configuração do App

| Campo | Valor |
|---|---|
| **App name** | Shopman |
| **Category** | Food & Drink |
| **Platforms** | Web, Desktop |
| **Products** | Login Kit, Content Posting API |
| **Scopes** | user.info.basic, video.upload |

---

## Description (max 120 chars)

```
A commerce platform for food businesses to create and publish content to their TikTok accounts.
```

(96 caracteres — direto, enquadra como plataforma, plural "businesses" + "their accounts")

---

## Review Explanation (max 1000 chars)

```
Shopman is a commerce platform for food businesses (bakeries, cafés, restaurants).

The Content Posting API integration lives inside the Broadcast module, which lets business operators:

1. Compose visual content (photos/videos of products, behind-the-scenes, daily specials)
2. Preview how the post will appear on TikTok
3. Authorize via Login Kit (OAuth) and publish directly to TikTok

Flow demonstrated in the video:
- Operator opens the Broadcast dashboard
- Selects media from the product catalog or uploads new content
- Writes caption, adds hashtags
- Connects their TikTok account via Login Kit (OAuth redirect)
- Reviews the post preview
- Publishes via Content Posting API (Direct Post)
- Sees confirmation with post status

Each business connects their own TikTok account. The platform does not post to accounts it manages — each operator authorizes and controls their own content.
```

(~700 chars — boa margem)

---

## Pontos cruciais vs. rejeição anterior

| O que causou a rejeição | O que muda agora |
|---|---|
| App name "Nelson Boulangerie" → gritava uso interno | "Shopman" — nome de plataforma |
| "shares to **its** TikTok business account" | "businesses publish to **their** TikTok accounts" |
| App novo com histórico limpo | Sem viés de rejeição anterior |
| Demo mostrava operação Nelson-específica | Demo mostra interface genérica da plataforma |

---

## Roteiro do Demo Video (~60-90s)

### Cena 1 — Abertura (5s)
Tela: página inicial do Shopman com logo.
Narração/legenda: "Shopman — commerce platform for food businesses."

### Cena 2 — Dashboard Broadcast (10s)
Tela: marketing-nuxt dashboard (sem branding Nelson visível, ou com branding genérico).
Mostrar: lista de posts recentes, botão "New Post".

### Cena 3 — Composição do post (15s)
Tela: tela de criação de post.
Ações: selecionar foto/vídeo do catálogo, escrever caption, adicionar hashtags.
Mostrar: preview do post.

### Cena 4 — Login Kit / OAuth (15s)
Tela: clique em "Connect TikTok Account".
Ações: redirecionamento para TikTok OAuth (sandbox), autorizar, voltar ao app.
**IMPORTANTE**: usar ambiente sandbox do TikTok Developer Portal.

### Cena 5 — Publicação (10s)
Tela: botão "Publish to TikTok", loading, confirmação.
Mostrar: status do post (published/processing).

### Cena 6 — Confirmação (5s)
Tela: post aparece na lista com status "Published".
Legenda: "Content published via Content Posting API."

### Notas de produção
- **Sem áudio** — usar legendas/annotations
- **Domínio no browser deve bater com o Website URL** cadastrado no app
- **Usar sandbox** (obrigatório para primeiro review)
- **Não mostrar branding Nelson** — manter interface genérica
- **Resolução**: 1080p, formato MP4 ou MOV

---

## Checklist antes de submeter

- [ ] Criar app NOVO no TikTok Developer Portal (não editar o rejeitado)
- [ ] Definir domínio/URL da "plataforma" (ex: shopman.app, shopman.com.br, ou subdomínio)
- [ ] Website URL precisa ter Privacy Policy e Terms of Service visíveis (sem menu)
- [ ] Redirect URI deve bater com o domínio do Website URL
- [ ] Gravar demo video no sandbox
- [ ] Garantir que o marketing-nuxt não mostra branding Nelson no demo
- [ ] Revisar que todos os scopes pedidos aparecem no video

---

## Sobre o domínio

Ponto de atenção: o Website URL precisa ser um site real que pareça plataforma.
Opções:
1. **shopman.com.br** ou **shopman.app** — ideal, mas precisa registrar
2. **platform.boulangerie.com.br** — possível, mas ainda liga à Nelson
3. **Landing page simples** em qualquer domínio disponível — basta ter nome, descrição, Privacy Policy e ToS visíveis

O redirect URI do OAuth deve estar no mesmo domínio (ex: `api.shopman.app/webhooks/tiktok/callback/`).
