# WhatsApp Login UX Optimization Plan

**Data:** 2026-09-25
**Status:** Proposta — aguardando aprovação
**Constraint:** Melhorias incrementais sobre a arquitetura existente (doorman + ManyChat). Não destruir e reconstruir.

---

## Diagnóstico: Por que os testadores estão perdidos?

### O fluxo atual (direto pelo site)

1. Usuário entra em `/entrar`
2. Vê um painel WhatsApp com deep link pré-montado ("envie esta mensagem para nosso número")
3. **Precisa sair do site** → abrir WhatsApp → enviar mensagem com código → esperar resposta do ManyChat → clicar no link de volta
4. Link leva a `/a?t=<token>` → troca token por sessão → redirect

**O SMS/OTP está escondido** atrás de um botão-fantasma "Não consigo usar WhatsApp" — a maioria dos usuários não percebe.

### Os 5 pontos de atrito identificados

| # | Atrito | Gravidade |
|---|--------|-----------|
| 1 | **WhatsApp é o default mesmo para quem veio pelo site** — o usuário precisa sair da página, ir ao WhatsApp, enviar mensagem, esperar resposta e clicar link de volta | Alta |
| 2 | **Falta de contexto** — ninguém explica POR QUE o WhatsApp é necessário (notificações de pedido, atendimento) | Alta |
| 3 | **"Não consigo usar WhatsApp" é ghost button** — parece link de ajuda, não alternativa real. Quem tem WhatsApp mas está no desktop não clica | Média |
| 4 | **WebView cookie isolation** — quem clica o link de volta no WhatsApp abre um WebView sem cookies do browser real, gerando handoff adicional | Média |
| 5 | **Welcome gate para nomes do ManyChat** — nomes com emojis/caracteres estranhos forçam um passo extra de confirmação | Baixa |

---

## Benchmarks e melhores práticas

### Como os grandes apps brasileiros resolvem

- **iFood / Rappi / 99**: Phone-first. Pedem o número do celular, enviam OTP via SMS ou WhatsApp como **canal de entrega** (o código chega no WhatsApp, o usuário digita no site). O usuário nunca sai do app/site.
- **Nubank / PicPay**: Phone + OTP, com device trust agressivo (biometria no retorno).
- **Magazine Luiza / Mercado Livre**: Email ou phone, OTP via SMS.

### Meta WhatsApp Business API — Authentication Templates (2026)

A Meta oferece templates de autenticação com:
- **Zero-tap**: O código é entregue direto ao app sem interação do usuário (Android)
- **One-tap**: Botão "Autofill" no WhatsApp que injeta o código no app
- **Copy code**: Botão para copiar o código no WhatsApp
- **Keyboard suggestions** (iOS 26+): Autofill nativo do OTP na notificação

**Requisito**: WhatsApp Business API direta (não ManyChat). Exige 2.000+ conversas business-initiated/dia por número.

### Padrão vencedor no Brasil

> **Phone-first → OTP via WhatsApp → Device trust no retorno**
>
> O número do celular é a identidade. O WhatsApp é o *canal de entrega* do código, não o *mecanismo* de autenticação. O usuário nunca sai do site.

---

## Plano de melhorias — 3 ondas

### Onda 1: Quick wins de UX (sem mudança de backend)

**Impacto:** Alto | **Esforço:** Baixo | **Risco:** Zero

#### 1a. Inverter a hierarquia visual em `/entrar`

**Hoje**: WhatsApp panel é hero, SMS é ghost button escondido.
**Proposta**: Phone input é hero. WhatsApp panel é opção secundária.

```
┌─────────────────────────────────┐
│  Seu número de celular          │
│  ┌───────────────────────────┐  │
│  │ +55 (__)_____-____        │  │
│  └───────────────────────────┘  │
│  [ Enviar código ]              │  ← Primary CTA
│                                 │
│  ─── ou ───                     │
│                                 │
│  [ Entrar via WhatsApp ]        │  ← Secondary, visível
│  Você receberá um link de       │
│  acesso no WhatsApp             │
└─────────────────────────────────┘
```

**Justificativa**: Quem vem pelo site espera digitar algo. O WhatsApp continua disponível mas não é imposto. Device trust (`device-check`) já existe e pula o OTP para dispositivos conhecidos.

**Arquivo**: `surfaces/storefront-nuxt/app/pages/entrar.vue` (reorganizar steps no presentation layer)

#### 1b. Adicionar copy de contexto

Antes do formulário, uma linha explicando o valor:

> "Usamos seu WhatsApp para avisar sobre seu pedido e tirar dúvidas. Rápido e prático."

Isso responde o "pra que eu tenho que fazer isso?" dos testadores. Deve ser copy de `OmotenashiCopy` (via admin), não hardcoded.

#### 1c. Promover device trust mais agressivamente

**Hoje**: Checkbox "Salvar este aparelho?" é opcional, off por default.
**Proposta**: On por default, com copy clara: "Lembrar este aparelho (não precisa do código da próxima vez)".

**Arquivo**: `surfaces/storefront-nuxt/app/pages/entrar.vue` (step de trust device)

#### 1d. Melhorar copy do fluxo WhatsApp quando escolhido

Se o usuário opta pelo WhatsApp, explicar os passos com numbered steps visuais:
1. "Toque no botão abaixo para abrir o WhatsApp"
2. "Envie a mensagem pronta (é automática)"
3. "Você receberá um link — toque nele para voltar"

**Arquivo**: `surfaces/storefront-nuxt/app/pages/entrar.vue` (WhatsappVerifyPanel)

---

### Onda 2: OTP via WhatsApp como canal (backend incremental)

**Impacto:** Alto | **Esforço:** Médio | **Risco:** Baixo

#### 2a. Usar WhatsApp como canal de entrega do OTP

**Hoje**: `VerificationCode.DeliveryMethod` já tem `WHATSAPP` no enum, mas o storefront só oferece `sms`.
**Proposta**: Adicionar opção de receber o código via WhatsApp (o código chega como mensagem, o usuário digita no site — sem sair da página).

Fluxo:
1. Usuário digita telefone
2. Escolhe "Receber por WhatsApp" ou "Receber por SMS"
3. Código de 6 dígitos chega no WhatsApp (via ManyChat automation ou API direta)
4. Usuário digita no site → verificado → sessão criada

**Benefício**: O usuário FICA no site. WhatsApp é só o carteiro do código.

**Arquivos**:
- `shopman/storefront/api/auth.py` — `RequestCodeView` já suporta `delivery_method`
- `packages/doorman/shopman/doorman/services/` — verificar se o send via WhatsApp já funciona
- ManyChat: configurar automation que recebe trigger + envia template com código (ou WhatsApp Business API direta para auth templates)

#### 2b. Auto-detect delivery method inteligente

Se o número está cadastrado no ManyChat (subscriber conhecido), default para WhatsApp. Se não, default para SMS. O usuário pode trocar.

**Arquivo**: Novo check no `RequestCodeView` ou intent layer.

#### 2c. Fallback automático SMS → WhatsApp

Se SMS falha (delivery report negativo), oferecer retry via WhatsApp automaticamente.

---

### Onda 3: Migração Meta API (futuro, não agora)

**Impacto:** Máximo | **Esforço:** Alto | **Risco:** Médio

#### 3a. WhatsApp Business API direta (substituir ManyChat)

Quando viável (memória do projeto: "intent to migrate to Meta API direct when viable"):
- Authentication templates oficiais com **one-tap autofill** (Android) e **keyboard suggestions** (iOS 26+)
- Zero-tap para apps nativos
- Custo menor que ManyChat em escala

**Requisito**: 2.000+ business-initiated conversations/dia/número.

#### 3b. Passkeys como complemento

O sistema já suporta passkeys (`PasskeyLoginView`). Promover para dispositivos que suportam:
- Após login com OTP, oferecer "Cadastrar biometria para próxima vez"
- Passkey + device trust = login em 1 toque no retorno

---

## Priorização

| # | Melhoria | Onda | Impacto | Esforço | Próximo passo |
|---|----------|------|---------|---------|---------------|
| 1 | Inverter hierarquia (phone-first) | 1 | Alto | ~2h | Reorganizar `entrar.vue` |
| 2 | Copy de contexto (por que WhatsApp) | 1 | Alto | ~30min | `OmotenashiCopy` no admin |
| 3 | Device trust on by default | 1 | Médio | ~30min | Flag no `entrar.vue` |
| 4 | Numbered steps no WhatsApp flow | 1 | Médio | ~1h | UI do `WhatsappVerifyPanel` |
| 5 | OTP via WhatsApp (canal) | 2 | Alto | ~1 dia | Verificar ManyChat automation API |
| 6 | Auto-detect delivery method | 2 | Médio | ~4h | Check subscriber ManyChat |
| 7 | Fallback SMS↔WhatsApp | 2 | Médio | ~4h | Retry logic no RequestCodeView |
| 8 | Meta API direta | 3 | Máximo | ~1 semana | Avaliar volume de conversas |
| 9 | Promoção de passkeys | 3 | Alto | ~2 dias | UX de cadastro pós-login |

---

## Decisão necessária

**Pablo, a pergunta-chave é**: na Onda 1, queremos **inverter o default** (phone-first) ou apenas **dar mais visibilidade** ao SMS mantendo WhatsApp como primary?

A inversão é o que os benchmarks brasileiros fazem (iFood, Rappi, 99). Mas muda a jornada dos usuários que já se habituaram ao fluxo WhatsApp.

Minha recomendação: **inverter**. Quem vem pelo site digita o número e recebe código. Quem vem pelo WhatsApp (link de campanha, notificação) continua entrando via bridge token sem atrito. Cada caminho otimizado para seu contexto de entrada.
