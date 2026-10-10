> Anexo do [WP-OPERADOR-NUXTUI-ONDAS](../WP-OPERADOR-NUXTUI-ONDAS.md). Leitura de código em 08/10/2026 sobre `e79ed522d` (pilha do Gestor #1528 + #1521), sem build nem navegador. Vale como mapa de arquivo:linha; o que foi visto em tela está no corpo do plano e nos PRs.

# Inventário Onda 0: marketing-nuxt (Marketing: campanhas e anúncios)

Auditoria de LEITURA. Branch `claude/operador-nuxtui-onda0-base` (pilha #1528 + #1521), worktree
`operador-nuxt-ui-migracao-16676a`. Nada foi editado, rodado ou buildado. Todo caminho é
relativo a `surfaces/marketing-nuxt/` salvo indicação. Contagens saem de `grep` sobre `app/`
(sem `node_modules`, `.nuxt`, `.output`); classe quebrada em várias linhas pode escapar das
regex de classe (dito onde importa).

Fontes lidas: `docs/plans/WP-GESTOR-CANON-LAUDO.md` (não está nesta branch; lido do commit
`2ef7e958b`, que está em `origin/main`), `docs/reference/marketing-surface-contract.md`,
o app inteiro, `operator-kit` nas peças consumidas, `surfaces-gate.yml`, os scripts de trava.

## 0. Números principais

| Medida | Valor |
|---|---|
| Rotas Nuxt reais | 9 (`/`, `/scheduled`, `/history`, `/campaigns`, `/templates`, `/offers`, `/platforms`, `/announcements/:id`, `/second-control/:ref`) + `error.vue` + 2 rotas só da matriz visual |
| Componentes locais | 20 (`app/components`), 9.159 linhas |
| `UiButton` | 82 (22 arquivos) |
| `Icon` cru | 124 |
| `UiDialog` (reka, ui-thing) | 8 diálogos + 5 `MarketingWorkspaceDialog` |
| `UiInput` / `UiTextarea` / `UiSelect` / `UiNativeSelect` | 16 / 8 / 9 / 4 |
| `UiCheckboxGroup` / `UiCheckbox` / `UiRadioGroup` / `UiRadio` / `UiSwitch` | 14 / 9 / 6 / 4 / 4 |
| Temporais do kit | `UiDateTimeField` 4, `UiDateRangeField` 2, `UiTimeRangeField` 1, `UiTimeField` 1 (8) + `UiStepper` 1 |
| `:ui=` por instância | 14 (FireCampaignPanel 4, MarketingOfferForm 5, CampaignForm 5) |
| HTML cru de controle (`<button>`, `<input>`, `<select>`, `<table>`) | 18 / 7 / 2 / 1 |
| `input type="date|time|datetime-local"` nativo | **0** |
| Valores arbitrários `[...]` | 121 (top: `[13px]` 21, `[14px]` 17, `[15px]` 11, `[16px]` 9) |
| Copy visível com travessão | 2 (`AnnouncementResultPanel.vue:486`, `:536`, placeholder de célula, que a trava permite) |
| `useSonner.*` (toast vue-sonner) | 31 chamadas em 7 arquivos |
| Baselines visuais | 82 PNG em `tests/visual/baselines` (62 chamadas `expectStableScreenshot`, algumas em laço) |
| Testes | 36 arquivos unit (265 `it/test`), 15 de componente (173), e2e 8 + a11y 3 |
| Atalhos próprios | `R` (5 telas), `N` (Campanhas); do kit: `/`, `Mod+K`, `?`, `Alt+1..n` |

## 1. Telas

Shell único: `app/app.vue`. Não usa `OperatorAppRoot` nem `OperatorSuiteShell` (o Gestor usa
os dois, `orders-nuxt/app/app.vue:87,94`). Monta à mão: `<div data-marketing-app-root
data-suite="v3">` (`app.vue:56-60`), `OfflineBanner` (:63), `MarketingNav place="rail"`
(`OperatorSuiteRail`, :70), coluna com `<component :is>` + `MarketingNav place="bar"`
(`OperatorSectionBar`, :82, some com `route.meta.fullscreen`), `MarketingInboxLive` (:85),
gate de sessão (:88-163: indisponível inline, conferindo, proibido inline, `OperatorLogin`,
`OperatorLock`), `OperatorStationSetup` (:164), `OperatorSonner` (:170), `OperatorPwaRuntime`
(:171). Foco no `h1` ao autenticar (:37-45). Cor do app em `--app-color` no `<html>` (:27-30).

| Rota | Arquivo | O que mostra | Cabeçalho (slots usados) |
|---|---|---|---|
| `/` Decisões | `pages/index.vue:8` → `components/MarketingDecisionQueue.vue` | Fila por prazo (review, retry_failed, reconcile_unknown), miniatura 60 px, falhas por plataforma, prazo em âmbar, "Revisar"; conferências automáticas; linha "+N agendados hoje" | `MarketingPageHeader` (:130) `phone-hides-actions`; `#actions` (⋯ + "Preparar disparo"), `#status` (`OperatorLiveStatus`) |
| `/scheduled` Agendados | `pages/scheduled.vue` | Aprovados com hora marcada; Reagendar e Cancelar por item | `#actions` (⋯), `#status` (live) |
| `/history` Enviados | `pages/history.vue` | Resultado por anúncio e por plataforma, contagens, paginação por cursor | `#phone-actions` (⋯), `#status`, `#actions` (⋯), `#filters` (4 chips com `<select>` invisível + Limpar) |
| `/campaigns` Ajustes › Campanhas | `pages/campaigns.vue` | Tabela (≥ lg) / lista (< lg), liga/desliga, editar, preparar disparo, paginação; 3 workspaces | `#search` (`OperatorSuiteSearch`), `#actions`, `#phone-actions`, `#filters` (3 `UiFilterChip` + chip de plataforma + Limpar) + `MarketingSettingsNav` |
| `/templates` Ajustes › Modelos | `pages/templates.vue` | Lista de modelos, novo/editar (workspace), apagar com dependências | `#actions` ("Novo modelo") + SettingsNav |
| `/offers` Ajustes › Ofertas e cupons | `pages/offers.vue` | Cartões de oferta, criar oferta/cupom (workspace), "Criar campanha com esta oferta" | `#actions`, `#phone-actions` + SettingsNav |
| `/platforms` Ajustes › Plataformas | `pages/platforms.vue` | Prontidão por plataforma; workspace por plataforma; WhatsApp: modelo aprovado, avisos automáticos, teste seguro; diálogo TOTP | `#status` (frase só ≥ lg) + SettingsNav |
| `/announcements/:id` Revisão / resultado | `pages/announcements/[id].vue` | `pending_review`: `AnnouncementCard` (foto, texto, plataformas, Google, prévia, quando, pé fixo Recusar/Continuar). Decidido: texto recusado ou `AnnouncementResultPanel` (resultado, recuperação). `definePageMeta({ fullscreen: true })` (:415) | `#lead` (voltar), `#status` (prazo ≥ md), **`#below` (:441, prazo no celular)**, `#actions` e `#phone-actions` (⋯ Revisão) |
| `/second-control/:ref` | `pages/second-control/[ref].vue` | Segunda pessoa confirma com digital (WebAuthn) ou TOTP | `#lead` (voltar) |
| erro global | `app/error.vue` | 404/426/500/503/offline com referência de suporte | sem cabeçalho do kit |
| `/__visual_error/:status`, `/__visual_board` | `app/visual/*.vue`, só com `MARKETING_VISUAL_MATRIX=1` (`nuxt.config.ts:46-66`) | Fábrica de erro e o **`MarketingBoard` legado** | `MarketingBoard.vue:184` |

Redirect de alias: `/campaign/announcements/**` → `/announcements/**` 302 (`nuxt.config.ts:72-74`).

## 2. Gestos (inventário de zero regressão)

Endpoints relativos a `/api/v1/backstage/`. "kit" = peça do operator-kit.

### 2.1 Shell e navegação
| # | Gesto | Onde | Efeito / endpoint |
|---|---|---|---|
| G1 | Tocar seção no rail (Decisões, Agendados, Enviados; Ajustes no pé) | `MarketingNav.vue:50` (kit `OperatorSuiteRail`) | `navigateTo`; seções em `useMarketingSections.ts:54-86` |
| G2 | Avisos no rail: resumo "N decisões esperam você" leva a `/` | `MarketingNav.vue:31-45` (`provideOperatorInboxAlerts`) | caixa do kit |
| G3 | Bloquear / menu do operador (rail e barra) | `MarketingNav.vue:57,65` `@lock` → `app.vue:74,82` `lock` | `useOperatorLock` |
| G4 | Barra do polegar no celular (mesmas seções + "Mais") | `MarketingNav.vue:59` (kit `OperatorSectionBar`) | |
| G5 | Segunda linha de Ajustes (Campanhas, Modelos, Ofertas e cupons, Plataformas) | `MarketingSettingsNav.vue:31-45` (NuxtLink pílula, autoscroll do ativo :16-21) | rotas |
| G6 | Sessão indisponível: "Tentar de novo" | `app.vue:103-110` | `refreshSession()` |
| G7 | Proibido: "Voltar à Central" (`<a>` com target do app instalado) | `app.vue:146-153` | `useOperatorAppLink` |
| G8 | Login / sessão expirada | `app.vue:157` kit `OperatorLogin` | `/operator/login/` |
| G9 | Destravar PIN | `app.vue:163` kit `OperatorLock` | |
| G10 | Vincular posto: concluir / dispensar | `app.vue:164-169` kit `OperatorStationSetup` | |
| G11 | Erro global: "Voltar às decisões" (`clearError`) e "Tentar de novo" | `error.vue:115-128` | |

### 2.2 Decisões (`MarketingDecisionQueue.vue`)
| G12 | ⋯ Decisões: Modelos de texto (link), Histórico de disparos (link), Atualizar (R) | :93-97, :134 | `GET marketing/decisions/` |
| G13 | Tecla R | :101-106 | refresh |
| G14 | "Preparar disparo" (`UiButton to="/campaigns"`) | :135-138 | navegação; **some no celular** (`phone-hides-actions`, sem `#phone-actions`) |
| G15 | "Revisar" por cartão (cheio no 1º, outline nos demais, `h-12`) | :259-267 | `item.href` (`#review` ou `#result`) |
| G16 | Conferência automática (linha inteira é link) | :293-308 | `check.href` |
| G17 | Linha "+N agendados hoje" | :312-324 | `/scheduled` |
| G18 | "Tentar de novo" quando a fila falha | :172-179 | refresh |
| G19 | Foto quebrada volta ao ícone | :200 (`@error`) | local |

### 2.3 Agendados (`pages/scheduled.vue`)
| G20 | ⋯ Agendados: Histórico, Atualizar (R) | :34-37, :49 | `GET marketing/decisions/` |
| G21 | Tecla R | :28-33 | |
| G22 | Título do item é link para o anúncio | :107 | `item.href` |
| G23 | "Reagendar" | :124-132 | `item.href?action=reschedule_announcement#result` |
| G24 | "Cancelar" | :133-141 | `item.href?action=cancel_announcement#result` |

⚠️ **Defeito provável pré-existente (leitura, não visto em tela):** o deep link `reschedule_announcement`
é aceito em `AnnouncementResultPanel.vue:288` e chama `startRecovery`, mas a execução passa por
`assertRecoveryAction` (`composables/useMarketingRecovery.ts:57-70`), que só conhece
`cancel_announcement`, `retry_failed_delivery`, `reconcile_unknown_delivery` (:18-22) e lança
`unsupported_marketing_recovery_action`. O backend oferece a Action
(`shopman/backstage/projections/marketing_actions.py:445`). Nenhum teste nem fixture cobre
Reagendar. A migração não pode "consertar sem querer" nem esconder isso: registrar e decidir.

Celular: Decisões e Agendados não têm `#phone-actions`; o ⋯ (e com ele "Atualizar") só existe do
tablet para cima. No celular, atualizar = R (sem teclado) ou o SSE/poll.

### 2.4 Enviados (`pages/history.vue`)
| G25 | ⋯ Enviados: Atualizar (R), no celular e no desktop | :177-179, :189-191 | `GET marketing/v2/history/` |
| G26 | Tecla R | :162-167 | |
| G27 | 4 recortes (Situação, Plataforma, Criado em, Origem da decisão): `<select>` nativo invisível sobre chip | :193-210, opções :66-115 | `setFilter` → query + refetch |
| G28 | "Limpar filtros" (cabeçalho e estado vazio) | :211-218, :277-285 | `clearFilters` |
| G29 | "Tentar de novo" (falha de leitura) | :230-238 | refresh |
| G30 | Link do item ("Ver resultado"/rótulo vindo de actions) | :402-408 | `/announcements/:id` |
| G31 | "Carregar mais resultados" e "Tentar de novo" da página seguinte | :415-428, :441-448 | cursor |

### 2.5 Campanhas (`pages/campaigns.vue`)
| G32 | Buscar (kit `OperatorSuiteSearch`, hoje botão que abre `NuxtModal`; teclas `/` e Mod+K) | :475-483 | `?q=`, debounce 250 ms (:185-194) |
| G33 | ⋯ Campanhas: Modelos, Histórico, Atualizar (R) | :450-454, :485 | `GET marketing/rules/` + `options/` |
| G34 | "Nova campanha" com `kbd N` | :486-490 | abre workspace |
| G35 | Ícone "+" Nova campanha (celular) | :493 | idem |
| G36 | Teclas R e N (N bloqueada com painel aberto) | :459-467 | |
| G37 | Chips Todas / Ligadas / Desligadas com contagem (`UiFilterChip`, `aria-pressed`) | :496-507 | `?state=` |
| G38 | Chip Plataforma (`<select>` nativo invisível) | :512-520 | `?platform=` |
| G39 | "Limpar filtros" (cabeçalho e vazio filtrado) | :521-528, :620-627 | |
| G40 | "Tentar de novo"/"Atualizar" de falha | :541, :602 | |
| G41 | "Criar a primeira" (lista vazia) | :571 | |
| G42 | "Visto" na faixa de campanha criada | :588-590 | remove `?created` |
| G43 | Editar (nome na tabela ≥ lg; linha inteira < lg), desabilitado com razão | :658-668, :746-799 | Action `edit_campaign` |
| G44 | Liga/desliga (`UiSwitch`, tabela e lista), bloqueado com PATCH em voo | :689-695, :733-743 | `PATCH marketing/rules/:pk/` com `base_updated_at`, 409 recarrega (`useCampaigns.ts:102`) |
| G45 | "Preparar disparo" (tabela outline; lista `size="xs"`) com razão por extenso | :703-712, :825-838, :845-860 | abre "Definir público" |
| G46 | Anterior / Próxima | :876-899 | `?page=` |
| G47 | Workspace Nova/Editar campanha (fechar = `close`, foco volta ao botão N) | :904-934, :264-273 | `POST/PATCH marketing/rules/`; criada → `?created=` e foco na linha |
| G48 | `?new=1&offer=<ref>` abre o composer com a oferta | :250-256 | vindo de `/offers` |
| G49 | Workspace "Definir público" | :937-961 | `FireCampaignPanel` |
| G50 | Selo do disparo (`MarketingCommandConfirmationDialog`): confirmar / cancelar | :963-970 | `POST marketing/rules/:pk/fire/`; 409 recarrega, 429 explica espera (:288-323); sucesso navega à revisão com o receipt (:325-333) |

### 2.6 Composer de campanha (`components/CampaignForm.vue`, 5 etapas)
| G51 | Rascunho: manter o meu / manter o do servidor / descartar | :784-793 → `DraftRecoveryNotice.vue:81-111` | `useMarketingDraft` (localStorage + conflito) |
| G52 | Etapas pelo `UiStepper` (clicar etapa) | :795-800 | `goToStep` |
| G53 | Nome | :808 | |
| G54 | "Quando acontecer" (`UiNativeSelect`) | :826 | |
| G55 | Modelo (`UiSelect` com busca) + link "Crie o primeiro aqui" | :844-862 | `/templates` |
| G56 | Prévia do conteúdo (`AnnouncementPreview`) | :868-877 | `POST marketing/preview/` |
| G57 | Oferta (`UiSelect`, item `value: ""` em :716) | :890-898 | |
| G58 | "Toda semana" / "Uma vez" (2 `<button aria-pressed>` artesanais) | :917-933 | |
| G59 | Dia e hora única (`UiDateTimeField`) + escolha de ocorrência ambígua (`UiRadioGroup`) | :944-952, :979-990 | sem `min`/`max` |
| G60 | Hora (`UiTimeField`), dias da semana (7 `UiToggleChip`), período (`UiDateRangeField`) | :1016-1022, :1036-1044, :1058-1063 | |
| G61 | Destinos (`UiCheckboxGroup variant="table"`) + link "Ver em Plataformas" | :1098-1117, :1133 | |
| G62 | Público WhatsApp: sinais do produto (card), "comprou nos últimos" + `<input type=number>` dias, VIP minutos, combinação (`UiNativeSelect`), etiquetas, faixa de preço, RFM, aniversariantes, risco de churn + número, janela de horário preferido | :1159-1298 | |
| G63 | Revisar antes de publicar, prazo de revisão em minutos, Campanha ligada | :1329-1359 | |
| G64 | Cancelar / Voltar / Continuar / Salvar ou Criar campanha (`type=submit`) | :1435-1463 | emit `submit` |

### 2.7 Definir público (`components/FireCampaignPanel.vue`)
| G65 | Produto da ocorrência (`UiSelect` com busca) | :317-325 | |
| G66 | Público salvo × escolher agora (`UiRadioGroup`) | :373-397 | |
| G67 | Etiquetas, faixa, RFM, outros públicos (4 `UiCheckboxGroup` com `:ui`) | :405-452 | `POST marketing/audience/count/` (`useAudienceCount.ts:56`) |
| G68 | "Qualquer uma" / "Todas" (2 `<button aria-pressed>` em cartão) | :463-487 | |
| G69 | "Tentar de novo" a contagem | :584-591 | |
| G70 | Cancelar / "Revisar anúncio" (`type=submit`) | :612-624 | emit `submit` |

### 2.8 Selo (`components/MarketingCommandConfirmationDialog.vue`, usado em 3 lugares)
| G71 | Abrir prévia em tamanho real (olho) | :348 → `AnnouncementSimulatedPreview.vue:66-77` | |
| G72 | "Pedir a confirmação de outra pessoa" / "Chamar de novo" | :386-397 | `POST security/second-control/request/`, poll 3 s em `security/second-control/:ref/` (:224-262) |
| G73 | Frase digitada (`UiTextarea`) | :420-429 | |
| G74 | Senha (`UiInput type=password`, Enter envia) ou TOTP (`UiVerificationCodeInput`, Enter envia); usuário readonly | :434-465 | `security/step-up/` |
| G75 | Voltar / Confirmar (digital WebAuthn primeiro, cadastro na 1ª vez) | :470-490, `submit` :264-291 | `security/device/register/*`, `security/device/*` |
| G76 | "Usar o meu código" / "Usar a digital" | :494, :498 | `<button>` link |
| G77 | Fechar pelo véu/Esc só sem `busy` | :296-299 | |

### 2.9 Revisão (`pages/announcements/[id].vue` + `components/AnnouncementCard.vue`)
| G78 | Voltar às decisões | `[id].vue:426-434` | `/` |
| G79 | ⋯ Revisão: Agendar para outra hora, Recusar com motivo, Ver as campanhas | `[id].vue:325-334`, :444-449 | `card.openScheduling()` / `card.askToReject()` |
| G80 | Retomar e reconfirmar / Agora não (sessão voltou) | :465-480 | `decisionCommand.resumeAfterReauthentication` |
| G81 | "Atualizar" quando o acompanhamento da entrega esgota | :519-526 | `retryWithBackoff` sobre `v2/announcements/:id/` |
| G82 | "Tentar de novo" (carga) / "Ver as decisões" | :549-565 | |
| G83 | Rascunho (manter/descartar) | `AnnouncementCard.vue:584-593` | |
| G84 | "Tirar foto" / "Tirar outra" (input file `capture="environment"`) | :613-633 | `POST announcements/:pk/photo/` (:491) |
| G85 | "Sugerir texto" (IA) | :641-656 | `POST announcements/:pk/rewrite/` (:112) |
| G86 | Texto (`UiTextarea`, contador vs limite) | :664-671 | |
| G87 | Usar no rascunho / Desfazer uso / Descartar sugestão | :719-725 | `POST .../suggestions/:ref/disposition/` (:135) |
| G88 | "Pôr hashtags" → campo | :731-748 | |
| G89 | Interruptor por plataforma (`UiSwitch`) + link Plataformas | :776-780, :796 | |
| G90 | Opções do Google (tipo, título, início/fim, termos, botão) | :805-810 → `GoogleBusinessPostOptions.vue:66-170` | 2 `UiDateTimeField` sem `min`/`max` |
| G91 | "Ver como fica em cada plataforma" (disclosure) + abas da prévia | :816-834, `AnnouncementPreview.vue:390-404` | `POST marketing/preview/` |
| G92 | "Imediato" / "Agendado" (2 `<button aria-pressed>` segmentados) | :843-862 | |
| G93 | Data e hora do disparo (`UiDateTimeField`), "Usar o próximo horário permitido", ocorrência ambígua | :880-911 | |
| G94 | Link "Prepare um disparo novo em Campanhas" (expirado) | :921 | |
| G95 | Pé fixo: Recusar / Continuar (h-14 no celular) | :932-952 | emit `reject` / `approve` |
| G96 | Diálogo "Recusar este anúncio?": motivo, Manter na fila, Recusar | `[id].vue:708-751` | `POST announcements/:pk/reject/` |
| G97 | Selo da decisão | `[id].vue:753-762` | `POST announcements/:pk/approve/` (idempotency key por impressão digital, :156-194) |
| G98 | Prazo "decide até HH:MM · faltam N min" (relógio 30 s) | `[id].vue:306-323`, :436-443 | só leitura |

### 2.10 Resultado (`components/AnnouncementResultPanel.vue`)
| G99 | Ação de recuperação por item (Cancelar outline destrutivo, Reenviar, Conferir) | :629-643 | Actions `cancel_announcement`, `retry_failed_delivery`, `reconcile_unknown_delivery` |
| G100 | Diálogo: motivo (`UiTextarea`), frase, usuário readonly, TOTP/senha (Enter confirma) | :650-815 | `announcements/:id/cancel|retry-deliveries|reconcile-deliveries/` |
| G101 | Voltar sem alterar / Conferir cancelamento / Entendi (dupla) / Confirmar / Tentar de novo | :822-870 | |
| G102 | Deep link `?action=` abre a recuperação uma vez | :283-301 | ver defeito do Reagendar |
| G103 | "Tentar de novo" o resultado | `[id].vue:680-687` | |

### 2.11 Modelos (`pages/templates.vue` + `AnnouncementTemplateForm.vue`)
| G104 | Novo modelo (cabeçalho e vazio) | :73, :137 | workspace |
| G105 | Abrir edição (linha inteira `<button>`) | :153-176 | |
| G106 | Apagar (ícone) → diálogo com dependências: Manter, Ver campanhas (NuxtLink pintado de botão), Apagar | :182-186, :220-283 | `DELETE marketing/templates/:pk/` |
| G107 | "Tentar de novo" (falha) | :97-105 | |
| G108 | Form: nome, texto, chips de variável (`<button>` insere `{{var}}`), imagem (`UiNativeSelect`), URL fixa, composição por plataforma (formato `UiRadioGroup`, texto próprio, Google), IA (checkbox + prompt), Ativo, Cancelar, Salvar | `AnnouncementTemplateForm.vue:293-476`, `PlatformCompositionEditor.vue:141-175` | `POST/PATCH marketing/templates/` |

### 2.12 Ofertas e cupons (`pages/offers.vue` + `MarketingOfferForm.vue`)
| G109 | ⋯: Criar cupom, Atualizar (R); "Criar cupom", "Criar oferta"; "+" no celular | :67-83, :91-118 | |
| G110 | Tecla R | :60-66 | `GET marketing/offers/` |
| G111 | "Criar campanha com esta oferta" | :204-211 | `/campaigns?new=1&offer=` |
| G112 | Form: código, nome, tipo (`UiNativeSelect`), valor (number), validade (`UiDateRangeField :min`, sem limpar), horário (`UiTimeRangeField`), produtos, coleções, pedido mínimo, máx. usos, canais, entrega, segmentos, só aniversariantes, ativar, Cancelar, Criar | `MarketingOfferForm.vue:168-436` | `POST marketing/offers/` |

### 2.13 Plataformas (`pages/platforms.vue`)
| G113 | Abrir plataforma (linha inteira `<button>`) / `?platform=` abre direto | :406-439, :36-44 | |
| G114 | Fechar workspace volta a `/platforms` e foca a linha | :24-34 | |
| G115 | "Tentar de novo" / "Atualizar" | :351-358, :389-396 | `GET marketing/platforms/` |
| G116 | WhatsApp: "Atualizar" a lista de modelos | :527-536 | `GET whatsapp-template/?refresh=1` |
| G117 | Modelo aprovado (`UiSelect`, item `value: ""` em :222) | :545-554 | abre diálogo TOTP |
| G118 | Aviso automático (`UiSelect`) + modelo do aviso (`UiSelect`) | :584-617 | idem |
| G119 | Teste seguro: mensagem, número verificado, produto (`UiSelect`, item `""` em :255), "Enviar teste" | :662-716 | `POST whatsapp-template/test/` |
| G120 | Diálogo "Confirmar configuração do WhatsApp": TOTP, Voltar sem alterar, Salvar configuração | :749-855 | `security/step-up/` + `POST whatsapp-template/` |

### 2.14 Segunda pessoa (`pages/second-control/[ref].vue`)
| G121 | Voltar | :100-106 | `/` |
| G122 | Confirmar com a digital | :148-151 | WebAuthn + `POST security/second-control/:ref/` |
| G123 | TOTP (Enter confirma) + "Confirmar o envio" | :143-146 | `security/step-up/` |
| G124 | Alternar digital ↔ autenticador (`<button>` link) | :153-155 | |

### 2.15 Diálogos, modais, sheets e popovers (lista fechada)
1. `MarketingWorkspaceDialog` (UiDialog tela cheia no celular, 1280×900 no desktop): campanha (`campaigns.vue:904`), definir público (:937), modelo (`templates.vue:195`), oferta/cupom (`offers.vue:229`), plataforma (`platforms.vue:447`).
2. `UiDialog` Recusar anúncio (`[id].vue:708`).
3. `UiDialog` Apagar modelo (`templates.vue:220`).
4. `UiDialog` Confirmar configuração WhatsApp (`platforms.vue:749`).
5. `UiDialog` Recuperação (`AnnouncementResultPanel.vue:650`).
6. `UiDialog` Selo, com aparência de **bottom sheet no celular** feita por classes `max-sm:*` (`MarketingCommandConfirmationDialog.vue:294-305`), 3 montagens: `campaigns.vue:963`, `[id].vue:753`, `MarketingBoard.vue:585`.
7. `UiDialog` Prévia em tamanho real (`AnnouncementSimulatedPreview.vue:65`), tela cheia, abas por formato.
8. `UiPopover` como menu ⋯ (`MarketingPageMenu.vue:30`), 9 montagens.
9. `UiDialog` Recusar do `MarketingBoard.vue:537` (só matriz).
10. Do kit: `OperatorSuiteSearch` (NuxtModal), `OperatorLogin` (NuxtModal), `OperatorLock`, `OperatorStationSetup`, `OperatorShortcutsHelp`, menus do rail.
Nenhum `UiSheet` (proibido por `tests/marketingV2CanonicalExperience.test.ts:24`).

## 3. Atalhos e SSE

**Atalhos do app** (todos `onKeyStroke`, ignoram campo de texto e modificador):
- `R` atualizar: `MarketingDecisionQueue.vue:101`, `scheduled.vue:28`, `history.vue:162`, `campaigns.vue:459`, `offers.vue:60`. Rotulado no ⋯ com `kbd` (`MarketingPageMenu.vue:47,52`).
- `N` nova campanha: `campaigns.vue:463` (`kbd` no botão :489).
- Enter confirma em TOTP/senha: `MarketingCommandConfirmationDialog.vue:449,463`, `AnnouncementResultPanel.vue:797`, `second-control/[ref].vue:143`.
- `templates.vue` e `platforms.vue` não têm `R`.
- `scripts/check_operator_shortcuts.py` só pega `addEventListener('keydown')`/`useEventListener`; `onKeyStroke` não entra no inventário de exceções.

**Do kit** (via `OperatorSuiteRail`/`OperatorSuiteSearch`, `operator-kit/app/shortcuts/suiteShortcuts.ts`): `/` e `Mod+K` busca (só existe em Campanhas), `Shift+/` ajuda, `Alt+1..n` seções.

**SSE / tempo real** (ADR-016):
- Dono único: `MarketingInboxLive.vue` no shell (`app.vue:85`). `useMarketingNotificationInbox.ts:51-87`: `EventSource` em `/sse/notifications` (kit `server/routes/sse/notifications.ts` → Django `/events/me/`), eventos `message` e `user-notification` só incrementam revisão; poll 60 s; `visibilitychange` e `online` reconciliam. Estado `connecting|live|polling` em `useState`.
- `useMarketingDecisions({ live: true })` refaz `GET marketing/decisions/` a cada revisão (`useMarketingDecisions.ts:49-55`); relógio de 30 s (`:37-46`).
- "Visto" na fila: `POST notifications/v2/seen/` (`useMarketingNotificationInbox.ts:105`).
- Sem canal de Marketing: o acompanhamento da entrega é poll com backoff (`[id].vue:183-221`).
- Selo dupla: poll 3 s (`MarketingCommandConfirmationDialog.vue:236`).
- **`OperatorLiveStatus` (3 usos):** `MarketingDecisionQueue.vue:146`, `scheduled.vue:57`, `history.vue:186`. Fonte local `presentation/liveStatus.ts` (tons `live|calm|late|off`, "Ao vivo", "Atualiza a cada 1 min", "Sem conexão") via `composables/useMarketingLiveStatus.ts`. O kit atual (`operator-kit/app/components/OperatorLiveStatus.vue:24-45`) mostra "On HH:MM"/"Off" em verde/vermelho e só põe o rótulo no `aria-label`: o contrato de `liveStatus.ts:1-3` ("a cor nunca fala sozinha") está quebrado (laudo P0-5/H2). Além disso o wrapper de Decisões e Agendados (`MarketingDecisionQueue.vue:145`, `scheduled.vue:56`) esconde abaixo de 380 px os `span:not(.live-dot)`: a classe `.live-dot` não existe mais no componente novo, então a regra esconde o conteúdo inteiro do badge, não "deixa só o ponto". `history.vue:183` usa `sr-only`, outro comportamento.

## 4. Peças do operator-kit usadas

| Peça | Usos | Onde | Nota para a migração |
|---|---|---|---|
| `OperatorPageHeader` | 1 direto (`MarketingPageHeader.vue:39`), 10 telas via wrapper | slots repassados `MarketingPageHeader.vue:40-49` | **`#below`** só em `announcements/[id].vue:441` (prazo no celular). Slot existe de novo no kit (`OperatorPageHeader.vue:188`, #1521). Também `#lead` (2), `#status` (5), `#actions` (7), `#phone-actions` (4), `#search` (1), `#filters` (2 + SettingsNav em 4 telas). O kit tem `#subtitle` e `#feedback`, que o Marketing não usa. |
| `OperatorLiveStatus` | 3 | ver §3 | quebra de contrato (P0-5) |
| `OperatorSuiteRail` | 1 | `MarketingNav.vue:50` | |
| `OperatorSectionBar` | 1 | `MarketingNav.vue:59` | laudo H8: rótulos truncam a 360 |
| `OperatorSuiteSearch` | 1 | `campaigns.vue:476` | virou modal (laudo H7): filtra a lista por trás do modal |
| `provideOperatorInboxAlerts` | 1 | `MarketingNav.vue:31` | |
| `OperatorLogin` | 1 | `app.vue:157` | `tests/components/OperatorLogin.test.ts` (3 testes) quebra: monta o SFC sem runtime Nuxt e o `<NuxtModal>` (`OperatorLogin.vue:55`) fica inerte |
| `OperatorLock`, `OperatorStationSetup`, `OperatorPwaRuntime`, `OfflineBanner` | 1 cada | `app.vue:163,164,171,63` | |
| `OperatorSonner` | 1 | `app.vue:170` | vue-sonner, `useSonner` = `toast` do vue-sonner (`nuxt.config.ts:109-113`), 31 chamadas. Gestor usa `NuxtApp` toaster + `useSonner` remapeado (`orders-nuxt/app/plugins/operator-toast.client.ts`, `utils/operatorToast.ts`). Laudo F6: o Sonner morre |
| `UiButton` (já `NuxtButton` por dentro, `UiButton.vue:106`) | 82 | 22 arquivos | variantes `default/outline/ghost/link/destructive`, `size xs/icon` (6) |
| `UiIconButton` (`<button>` cru) | 5 | `MarketingPageMenu.vue:32`, `MarketingBoard.vue:186`, `campaigns.vue:493`, `offers.vue:116`, `templates.vue:182` | → `NuxtButton square` com `aria-label` |
| `UiFilterChip` (NuxtButton+NuxtBadge) | 3 | `campaigns.vue:496,500,504` | perdeu `min-h-control` (laudo H5) |
| `UiDateTimeField` | 4 | `AnnouncementCard.vue:880`, `CampaignForm.vue:944`, `GoogleBusinessPostOptions.vue:101,115` | **nenhum passa `min`/`max`**: o defeito do `.slice(0,10)` (`UiDateTimeField.vue:58-59`) não afeta o Marketing hoje |
| `UiDateRangeField` | 2 | `CampaignForm.vue:1058`, `MarketingOfferForm.vue:287` (`:min`, `:clearable=false`, `:allow-open-ended=false`) | |
| `UiTimeRangeField` / `UiTimeField` | 1 / 1 | `MarketingOfferForm.vue:305` / `CampaignForm.vue:1016` | |
| `UiStepper` (NuxtStepper) | 1 | `CampaignForm.vue:795` | |
| `UiNativeSelect` (`<select>` cru) | 4 | `CampaignForm.vue:826,1214`, `AnnouncementTemplateForm.vue:358`, `MarketingOfferForm.vue:245` | decisão pendente do Pablo (laudo, "Lista curta") |
| `UiSelect` (NuxtSelectMenu com busca) | 9 | `CampaignForm.vue:844,890`, `FireCampaignPanel.vue:317`, `platforms.vue:545,584,605,662,678,689` | 3 com item `value: ""` |
| `UiCheckboxGroup` / `UiCheckbox` | 14 / 9 | CampaignForm, FireCampaignPanel, MarketingOfferForm, AnnouncementTemplateForm | |
| `UiRadioGroup` / `UiRadio` | 6 / 4 | AnnouncementCard, CampaignForm, FireCampaignPanel, GoogleBusinessPostOptions ×2, PlatformCompositionEditor | `UiRadio` é `<button>` cru, `UiRadioGroup` tem `<input>` |
| `UiSwitch` (NuxtSwitch) | 4 | `campaigns.vue:689,736`, `AnnouncementCard.vue:776` (+ comentário :733) | |
| `UiToggleChip` (`<button role=checkbox>` paralelo) | 1 | `CampaignForm.vue:1036` (7 dias) | laudo: "Paralela; Marketing; depois morre" |
| `UiSkeleton` (NuxtSkeleton) | 10 | DecisionQueue não; `[id].vue:533,657`, `campaigns.vue:551`, `history.vue:247`, `templates.vue:115`, `platforms.vue:369,501`, `offers.vue:146`, `second-control:111`, `MarketingBoard.vue:410` | |
| ui-thing reka: `UiDialog*` | 8 diálogos (`UiDialog` 8, `Content` 8, `Header` 8, `Title` 8, `Description` 9, `Footer` 6, `Trigger` 1, `Close` 1) | §2.15 | → `NuxtModal` |
| ui-thing: `UiPopover*` | 1 | `MarketingPageMenu.vue:30-56` | → `NuxtDropdownMenu` |
| ui-thing: `UiTabs*` | 2 | `AnnouncementPreview.vue:390`, `AnnouncementSimulatedPreview.vue:93` | → `NuxtTabs` |
| ui-thing: `UiInput` / `UiTextarea` | 16 / 8 | vários | → `NuxtInput` / `NuxtTextarea` |
| ui-thing: `UiVerificationCodeInput` (reka PinInput) | 4 | `MarketingCommandConfirmationDialog.vue:444`, `AnnouncementResultPanel.vue:791`, `platforms.vue:820`, `second-control:143` | → `NuxtPinInput` (`otp`, length 6) |
| `NuxtFormField` (já direto) | 2 | `MarketingOfferForm.vue:282,299` | único `Nuxt*` de formulário já em uso |

## 5. Componentes locais (20)

| Componente | Linhas | Papel | Destino sugerido |
|---|---:|---|---|
| `AnnouncementCard` | 958 | Revisão: foto, texto, IA, hashtags, plataformas, Google, prévia, quando, pé fixo | fica; migrar miolo |
| `AnnouncementPreview` | 629 | Prévia por plataforma (`POST preview/`), erros reparáveis | fica |
| `AnnouncementResultPanel` | 874 | Resultado por plataforma, comprovante, recuperação com step-up | fica |
| `AnnouncementSimulatedPreview` | 354 | Prévia em tamanho real que imita Story/Feed/Google/WhatsApp | fica; o HTML que imita terceiros é legítimo (não é imitação de componente nosso) |
| `AnnouncementTemplateForm` | 476 | Form de modelo | fica |
| `CampaignForm` | 1466 | Composer de 5 etapas | fica; maior risco de regressão |
| `DraftRecoveryNotice` | 118 | Conflito de rascunho local × servidor | fica como `NuxtAlert` com `actions`; candidato ao kit se outro app tiver rascunho |
| `FireCampaignPanel` | 627 | Definir público + contagem viva | fica |
| `GoogleBusinessPostOptions` | 174 | Atualização/Evento/Oferta do Google | fica |
| `MarketingBoard` | 597 | **Painel V2 legado**, só em `/__visual_board` (matriz) | **candidato a morrer**: não tem rota no app; sustenta 12 baselines (`panel__*` 7, `announcement-card__*` 5) e é lido por `tests/templatePickerReachable.test.ts`, `tests/marketingDashboardMetrics.test.ts`, `tests/marketingClient.test.ts`. Decidir antes de migrar |
| `MarketingCommandConfirmationDialog` | 503 | Selo (digital, código, segunda pessoa) | fica; casca → `NuxtModal` (ou `NuxtDrawer` no celular, hoje sheet por `max-sm:*`) |
| `MarketingDecisionQueue` | 327 | Casa do app | fica |
| `MarketingInboxLive` | 31 | Dono do SSE, sem UI | fica |
| `MarketingNav` | 67 | Rail ou barra | morre se o shell virar `OperatorSuiteShell` |
| `MarketingOfferForm` | 436 | Form de oferta/cupom | fica |
| `MarketingPageHeader` | 51 | Envelope do `OperatorPageHeader` (esconde `#actions` no celular, injeta SettingsNav em `#filters`) | encolhe ou morre |
| `MarketingPageMenu` | 58 | ⋯ feito com Popover + `role="menu"` + `<button>` cru | **morre** → `NuxtDropdownMenu` (laudo F6: "⋯ = DropdownMenu"); se o kit ganhar o ⋯, sobe |
| `MarketingSettingsNav` | 47 | Pílulas de segunda linha (NuxtLink pintado) | candidato a subir ao kit (o PDV tem o mesmo padrão em `PosSettingsTabs` no `#below`); oficial: `NuxtNavigationMenu` horizontal ou `NuxtTabs` com links |
| `MarketingWorkspaceDialog` | 34 | UiDialog tela cheia (celular) / largo (desktop) | candidato ao kit como modal de workspace, ou `NuxtModal` com `fullscreen` responsivo; a trava `marketingV2CanonicalExperience.test.ts:26-30` exige `h-dvh` e `overflow-y-auto` no arquivo |
| `PlatformCompositionEditor` | 189 | Variante por plataforma no modelo | fica |

## 6. Escapes do cânon

Componente oficial = o que o Gestor já usa (prefixo `Nuxt`).

### 6.1 Contagens
| Classe | Contagem | Observação |
|---|---:|---|
| (a) `:ui=` por instância | 14 | todos em `UiCheckboxGroup` (legend/fieldset/label) |
| (b) HTML cru que imita componente | 28 controles (`<button>` 18, `<input>` 7, `<select>` 2, `<table>` 1) | + 1 `<a>` pintado de botão (`app.vue:146`) e 4 `NuxtLink` pintados de botão |
| (c) data/hora nativa | 0 | `CampaignForm.vue:431` só cita `<input type="time">` em comentário (comentário desatualizado) |
| (c') `type="number"` | 5 `<input>` crus (`CampaignForm.vue:1173,1188,1270,1287,1343`) + 3 `UiInput` (`MarketingOfferForm.vue:263,370,377`) | → `NuxtInputNumber` |
| (d) classe que imita componente | badge ~8 (`rounded-full px-2 py-0.5`), alerta ~45 linhas (`border-*/40 bg-*/5`), cartão ~44 (`rounded-* border bg-card`), vazio 12 (`border-dashed`), controle com pele 11 (`h-12/h-14 rounded-xl text-[15/16px]` sobre UiButton) | regex de linha única: subestima |
| (e) arbitrários `[...]` | 121 (AnnouncementCard 27, Selo 20, DecisionQueue 18, scheduled 15, second-control 12) | quase tudo é tipografia em px da prévia v4; `[color-mix(...)--app-color...]` ×3 é a cor do app |
| (f) primitivas paralelas | `MarketingPageMenu`, `MarketingWorkspaceDialog`, `MarketingSettingsNav`, `UiToggleChip`, `UiIconButton`, `UiRadio`, `UiNativeSelect`, 3 segmentados `<button aria-pressed>`, 2 chips com `<select>` invisível, `kbd` cru (3), sheet por `max-sm:*` | |
| (g) travessão em copy | 2 visíveis (placeholder de valor ausente, que `guardrails.noEmDash` aceita); 133 em comentário | sem dívida de copy aqui |
| `op-*` tipografia do kit | 23 | `op-micro/label/eyebrow/body`; o Gestor não usa |
| `data-suite="v3"` | 1 (`app.vue:58`) | o Gestor proíbe (`orders-nuxt/tests/canonicalPilot.guardrails.test.ts:344`); `tests/sectionBar.test.ts:21` exige. Duas travas opostas |

### 6.2 Os 40 mais relevantes
| # | Arquivo:linha | Hoje | Oficial |
|---|---|---|---|
| 1 | `MarketingPageMenu.vue:30-56` | Popover + `role=menu` + `<button>`/NuxtLink com classe ITEM | `NuxtDropdownMenu` (itens com `to`, `kbds`) |
| 2 | `MarketingWorkspaceDialog.vue:14-33` | UiDialog com 4 valores `sm:[min(...)]` | `NuxtModal` (`fullscreen` no celular, `ui` no app.config) |
| 3 | `MarketingCommandConfirmationDialog.vue:294-305` | UiDialog virando sheet por `max-sm:top-auto ... rounded-t-[22px]` + alça desenhada (:306) | `NuxtDrawer` no celular / `NuxtModal` no desktop |
| 4 | `MarketingCommandConfirmationDialog.vue:472-489` | botões do pé com `max-sm:h-14 rounded-xl text-[15/16px]` | `NuxtButton size="xl" block` |
| 5 | `AnnouncementCard.vue:929-952` | pé fixo `fixed inset-x-0 bottom-0` + botões h-14 com pele | `NuxtButton size="xl"`; barra fixa do kit, se houver |
| 6 | `AnnouncementCard.vue:840-862` | "Imediato/Agendado" segmentado artesanal | `NuxtTabs` sem conteúdo ou `NuxtRadioGroup variant="card" orientation="horizontal"` |
| 7 | `CampaignForm.vue:917-933` | "Toda semana/Uma vez" segmentado | idem |
| 8 | `FireCampaignPanel.vue:463-487` | "Qualquer uma/Todas" cartões `<button aria-pressed>` | `NuxtRadioGroup variant="card"` |
| 9 | `history.vue:193-210` | chip `<label>` + `<select>` invisível | `NuxtSelect` (⚠️ opções com `""`) ou `NuxtDropdownMenu` |
| 10 | `campaigns.vue:512-520` | chip Plataforma com `<select>` invisível (`value=""`) | idem |
| 11 | `history.vue:211-218`, `campaigns.vue:521-528` | "Limpar filtros" `<button>` cru | `NuxtButton variant="link"` |
| 12 | `campaigns.vue:631-716` | `<table>` à mão com `thead/tbody` | `NuxtTable` (com `ui` de cabeçalho como o Gestor) |
| 13 | `campaigns.vue:658-668` | nome como `<button>` | `NuxtButton variant="link"` / `NuxtLink` |
| 14 | `campaigns.vue:746-799` | linha inteira `<button>` | `NuxtButton variant="ghost" block` ou cartão clicável do kit |
| 15 | `templates.vue:153-176` | linha inteira `<button>` | idem |
| 16 | `platforms.vue:406-439` | linha inteira `<button>` | idem |
| 17 | `AnnouncementTemplateForm.vue:334-349` | chips de variável `<button>` | `NuxtButton size="xs" variant="outline"` |
| 18 | `AnnouncementCard.vue:613-622` | botão flutuante sobre a foto `rounded-full bg-card/95` | `NuxtButton color="neutral" variant="solid"` |
| 19 | `AnnouncementCard.vue:624-633` | `<input type=file capture>` escondido | manter nativo ou `NuxtFileUpload` **preservando `capture="environment"`** |
| 20 | `AnnouncementCard.vue:731-736` | "Pôr hashtags" `<button>` sublinhado | `NuxtButton variant="link"` |
| 21 | `AnnouncementCard.vue:816-834` | disclosure "Ver como fica" `<button aria-expanded>` | `NuxtCollapsible` |
| 22 | `MarketingCommandConfirmationDialog.vue:494,498`, `second-control:153` | troca digital/código `<button>` sublinhado | `NuxtButton variant="link"` |
| 23 | `CampaignForm.vue:1173-1180,1188-1195,1270-1279,1287-1294,1343-1350` | `<input type="number" class="h-8 w-20">` | `NuxtInputNumber` |
| 24 | `MarketingOfferForm.vue:263,370,377` | `UiInput type="number"` | `NuxtInputNumber` |
| 25 | `CampaignForm.vue:1036-1044` | 7 `UiToggleChip` | `NuxtCheckboxGroup variant="card" orientation="horizontal"` (laudo) |
| 26 | `CampaignForm.vue:1098-1105` | `UiCheckboxGroup variant="table" :ui` | `NuxtCheckboxGroup variant="table"` sem `:ui` (legend no app.config) |
| 27 | `CampaignForm.vue:1164,1230,1241,1255`; `FireCampaignPanel.vue:410,425,439,450`; `MarketingOfferForm.vue:334,349,388,396,404` | `:ui` legend/fieldset repetido 13× | tema único no `app.config.ts` |
| 28 | `CampaignForm.vue:826,1214`, `AnnouncementTemplateForm.vue:358`, `MarketingOfferForm.vue:245` | `UiNativeSelect` | `NuxtSelect` ou nativo (decisão do Pablo) |
| 29 | `[id].vue:708-751`, `templates.vue:220-283`, `platforms.vue:749-855`, `AnnouncementResultPanel.vue:650-870` | `UiDialog*` | `NuxtModal` com `#footer` |
| 30 | `templates.vue:265-272` | NuxtLink pintado de botão primário | `NuxtButton to` |
| 31 | `app.vue:146-153`, `error.vue:115-121`, `[id].vue:558-564` | `<a>`/NuxtLink pintado de botão outline | `NuxtButton to variant="outline"` |
| 32 | `app.vue:88-155` | indisponível e proibido inline (`rounded-md border bg-card p-6`) | `OperatorSessionUnavailable` (kit) / `NuxtEmpty` |
| 33 | 12 vazios `border-dashed` (`MarketingDecisionQueue.vue:274`, `scheduled.vue:148`, `history.vue:257`, `campaigns.vue:561,609`, `platforms.vue:379`, `[id].vue:541`, `offers.vue:215`, `second-control:116`…) | div tracejada + ícone + texto | `NuxtEmpty` |
| 34 | ~45 alertas (`history.vue:225,300,431`, `[id].vue:455,671`, `platforms.vue:337,595,672,780`, `campaigns.vue:535,580,595`, `MarketingDecisionQueue.vue:165`, `scheduled.vue:74`, `offers.vue:132`, `AnnouncementResultPanel.vue:452,637,703,737`…) | div colorida `role=alert/status` | `NuxtAlert` (variant, color, actions) |
| 35 | badges `campaigns.vue:666,667,813`, `templates.vue:178`, `platforms.vue:420,430`, `offers.vue:177`, `PlatformCompositionEditor.vue:121` | `<span rounded-full px-2 py-0.5>` | `NuxtBadge` |
| 36 | `MarketingDecisionQueue.vue:183-269`, `scheduled.vue:84-143` | cartão `rounded-[14px]` + `ring-primary` no 1º | `NuxtCard` (variante do tema) |
| 37 | `MarketingDecisionQueue.vue:259-267`, `scheduled.vue:124-141` | "Revisar"/"Reagendar"/"Cancelar" `h-12 rounded-xl text-[15px]` | `NuxtButton size="lg"` |
| 38 | `MarketingSettingsNav.vue:31-45` | pílulas NuxtLink com `text-[13px]` e estado à mão | `NuxtNavigationMenu` horizontal (ou peça do kit) |
| 39 | `AnnouncementPreview.vue:395-403`, `AnnouncementSimulatedPreview.vue:98-109` | abas com `data-[state=active]:` à mão | `NuxtTabs` (variant pill/link) |
| 40 | `campaigns.vue:489`, `MarketingPageMenu.vue:47,52` | `<kbd>` cru | `NuxtKbd` / `OperatorKbd` |

## 7. Testes e travas que vão quebrar ou mudar

**Já vermelho por herança (antes de migrar):** `tests/components/OperatorLogin.test.ts` (3 testes;
`<NuxtModal>` inerte sem runtime). Job "Marketing · cadeia completa" vermelho no #1518/#1519, causa
Playwright não extraída (laudo §0).

**Harness de componente** (`vitest.config.ts:32-41`): projeto `component` = happy-dom +
`@vitejs/plugin-vue`, **sem runtime Nuxt**. `tests/support/uiPrimitives.ts` (550 linhas) registra
globalmente dublês escritos à mão: `NuxtSwitch`, `NuxtCheckbox`, `NuxtCheckboxGroup`,
`NuxtSelectMenu`, `NuxtFormField`, `UiButton`, `UiInput`, `UiTextarea`, `UiSkeleton`, `UiStepper`,
`UiDateField`/`UiDateTimeField`/`UiTimeField` (**como `<input type=date|datetime-local|time>`
nativo**, :314-335), `UiDateRangeField`, `UiTimeRangeField`; e monta reais `UiCheckbox*`,
`UiRadio*`, `UiSelect`, `UiSwitch`, `UiTabs*`, `UiToggleChip`. `tests/support/nativeUiStubs.ts`
dubla `UiNativeSelect`. Cada teste de diálogo traz `DialogStub`/`SlotStub` próprios (ex.:
`MarketingCommandConfirmationDialog.test.ts:81-88`). 8 dos 15 testes de componente citam
`UiButton/UiDialog/UiSelect/UiPopover/UiNativeSelect`. Trocar para `Nuxt*` direto obriga a
escolher: dublês novos (o problema T5 do laudo: o dublê decide a verdade, e foi o que deixou o
P0-1 passar) ou `mountSuspended` com runtime (como o kit).

**Travas locais que leem fonte:**
- `tests/sectionBar.test.ts:20-53`: exige `data-suite="v3"`, `<OperatorSuiteRail`, `<OperatorSectionBar`, `definePageMeta({ fullscreen: true })`, `provideOperatorInboxAlerts` no `MarketingNav`. Quebra se o shell virar `OperatorSuiteShell`.
- `tests/marketingV2CanonicalExperience.test.ts:21-39`: exige `<MarketingWorkspaceDialog` nas 4 telas, proíbe `<UiSheet`, exige `h-dvh` e `overflow-y-auto` no wrapper.
- `tests/templatePickerReachable.test.ts:17-55`: exige strings em `platforms.vue` (`UiVerificationCodeInput`, `onChooseTemplate`, "Teste seguro do WhatsApp"…) e lê `MarketingBoard.vue`.
- `tests/securityDelivery.test.ts`: fontes locais, CSP de dev só por `import.meta.dev`.
- `tests/operatorLanguage.test.ts` (333 linhas): vocabulário do Marketing (único com permissão de citar "fornada", `guardrails.vocabulary.test.ts:165`).
- `tests/suitePresentation.test.ts`: fixa o texto de `liveStatus.ts` ("Ao vivo", "Atualiza a cada 1 min").

**Travas do kit que olham o Marketing:**
- `operator-kit/tests/guardrails.appBar.test.ts:65-123`: lista `MarketingNav.vue` como shell com peças do kit.
- `operator-kit/tests/guardrails.pendingAction.test.ts:163-169`: `KNOWN_INERT` do Marketing (`MarketingBoard.confirmReject`, `[id].refreshAll`, `trackDeliveryUntilSettled`, `platforms.onVerifyCatalog`, `templates.confirmRemove`). "Só encolhe": migrar pode exigir `:loading` nesses.
- `operator-kit/tests/kitOwnership.guardrails.test.ts:146-275`: proíbe cópia local de primitivas do kit, checkbox/rádio nativos, data/hora nativa (só `<input`), Skeleton com classe solta, switch e abas à mão. Componente local novo não pode ter nome de primitiva do kit.
- `guardrails.vocabulary.test.ts:189`: Marketing exento de "lote/fornada" por bloqueio de baseline (o `mock_backend.py` tem 3 strings velhas que só mudam regerando PNG).
- `guardrails.noEmDash.test.ts:66`: `OfflineBanner.vue` exento porque aparece em `global-error__offline` do Marketing.
- `scripts/check_operator_component_ledger.py` + `docs/reference/operator-component-ledger.json` (app `marketing`, `owner WP-UX-13E`): teto `native_control_occurrences: 31` (regex `<(button|select|textarea)`; hoje 20), `local_ui_files 0`, `direct_reka_import_files 0`, `manual_overlay_files 0`; 9 superfícies `pending`. Proíbe estrutura canônica `NuxtDashboard*`/`NuxtNavigationMenu` fora do kit (é o que reprova o Gestor, laudo T6): o Marketing não pode montar layout canônico local.
- `orders-nuxt/tests/canonicalPilot.guardrails.test.ts`: proíbe `data-suite="v3"` e `suite:`; hoje só no grafo do Gestor. Se o Marketing entrar no piloto, `sectionBar.test.ts` e ela se contradizem.

**Baselines visuais** (`tests/visual/baselines`, 82 PNG): 5 announcement, 5 announcement-card, 8
campaign-form, 4 campaigns, 3 decisions, 9 fire-campaign, 5 global-error, 5 history, 7 login, 7
panel, 6 platforms, 1 scheduled, 5 settings, 6 simulated-preview, 6 templates. **Toda** troca de
componente visível muda pixels. Só regera quem tem o browser da CI (`runs-on: macos-15`, Chromium
pinado do Playwright, `surfaces-gate.yml:307-379`). 12 PNG dependem do `MarketingBoard` (só matriz).

**Job "Marketing · cadeia completa"** (`surfaces-gate.yml:307`): `npm ci` kit + app, `npm test`,
`lint`, `typecheck`, `build`, `test:e2e` (8 testes, `MARKETING_E2E_MANAGED=1`), `test:a11y` (3, com
axe, toque, reflow), `test:visual` (matriz), `test:security`. A e2e e a a11y dependem de nomes
acessíveis: "Mais: Ofertas e cupons", `menuitem` "Criar cupom", `dialog` "Nova oferta",
`combobox` "Buscar campanha", `group` "Disparado via", `checkbox` "dom", etc.
(`tests/visual/marketing-matrix.spec.ts:387-405, 630-675, 708`).

## 8. Mock visual

- **Backend hermético:** `tests/visual/mock_backend.py` (1.373 linhas, Python 3.12, porta 9011
  visual / 9012 e2e). Cenário por cookie `visual_scenario` (`marketing-matrix.spec.ts:18-31`);
  relógio fixo `2026-09-10T13:30:00Z` nos dois lados (`page.clock.setFixedTime`).
- **App:** `nuxt dev` com `MARKETING_VISUAL_CLIENT_ONLY=1` (SSR desligado, `nuxt.config.ts:23`) e
  `MARKETING_VISUAL_MATRIX=1` (rotas sintéticas), `bypassCSP: true`
  (`playwright.visual.config.ts:32`). A e2e roda SSR, sem `bypassCSP` declarado.
- **Configs:** `playwright.visual.config.ts` (via `operator-kit/visual/playwright`, `matrix: false`),
  `playwright.e2e.config.ts`, `playwright.a11y.config.ts`. `make operator-visual`/
  `scripts/run_operator_visual.py` existem no repo, não usados pelo job do Marketing.
- **Cobertura por tela** (cenários): login (7), `/` (board-pending, board-empty), `/scheduled`
  (board-pending, 390 só), `/history` (5 estados), `/campaigns` (normal, dense ×10, empty, 5 de
  disparo), `/templates` (list, empty, outage, dependency), `/offers` (board-normal ×3),
  `/platforms` (ready, blocked, outage, conflict), `/announcements/41` (403, expired, partial,
  pending, unknown), erros 404/426/500/503/offline, `/__visual_board` (normal, pending,
  all-formats, seal-dual).
- **Sem fixture / sem retrato:**
  - `/second-control/:ref`: o mock não responde `GET security/second-control/:ref/` (cai no 404
    "Fixture visual ausente", `mock_backend.py:1068`). Zero cobertura.
  - Revisão real (`/announcements/:id` pending) no **celular**: só existe a 1280
    (`announcement__pending__1280x800`). O `#below` do prazo (que sumiu no #1519) não tem retrato.
    Os retratos de cartão a 320/390/768 são do `MarketingBoard`, não da rota.
  - Reagendar/Cancelar a partir de Agendados (`?action=`): sem cenário.
  - Acompanhamento da entrega esgotado, retomar após reautenticação, foto (upload), sugestão
    de IA na rota real: sem retrato (parte coberta em teste de componente).
  - SSE: o mock responde 503 em `/api/v1/backstage/eventstream/user/` e nada em `/events/me/`;
    o "ao vivo" dos retratos é o estado `connecting→live` forçado (`useMarketingLiveStatus.ts:18`)
    ou `polling`; não há retrato de "Sem conexão".
  - Tema escuro: só `panel__normal__390x844__dark` (MarketingBoard).

## 9. Riscos específicos que a migração não pode quebrar

1. **CSP estrita (ADR-026, piloto do Marketing).** `server/middleware/00-security.ts` +
   `server/plugins/cspNonce.ts` aplicam `operator-kit/server/utils/securityHeaders.ts:28-50`:
   `script-src 'self' 'nonce-…'`, `style-src-elem 'self' 'nonce-…'` (inline só em dev),
   `connect-src 'self'`, `img-src 'self' data: https:` (sem `blob:`). Riscos: (a) peça Nuxt UI que
   cria `<style>` no cliente depois do SSR fica sem nonce em produção; (b) ícone fora do bundle
   iria a `api.iconify.design` e é recusado: `nuxt.config.ts:126-139` faz `clientBundle.scan` em
   `**/*.{vue,ts}` do app; os ícones internos do Nuxt UI (`app.config` do kit) precisam entrar no
   bundle; (c) os retratos rodam com `bypassCSP: true`, então a matriz visual **não** prova CSP:
   só a e2e (SSR) e o `securityDelivery.test.ts`. Não enfraquecer para imitar app não migrado.
2. **Publicação pública × mensagem direta** (contrato, "Responsabilidade e canais"). Instagram
   Story por padrão e Feed só por escolha; Facebook página; Google Atualização/Evento/Oferta;
   WhatsApp 1 por pessoa. Lugares onde o texto muda conforme o destino:
   `presentation/marketingDelivery.ts` (`includesDirectMessage`, `includesPublicPost`,
   `sealRows`, `sealConsequence`), `AnnouncementCard.vue:798-803`, `FireCampaignPanel.vue:336-361`,
   `CampaignForm.vue:1138-1142, 1301-1307`, selo `MarketingCommandConfirmationDialog.vue:213-221`.
   Trocar componente não pode trocar "mensagem/publicação/entrega" (vocabulário fechado do contrato).
3. **Comandos com step-up e idempotência.** Aprovar/recusar (`useMarketingDecisionCommand.ts`),
   disparar (`useCampaignFireCommand.ts`), recuperar (`useMarketingRecovery.ts`, `assertRecoveryAction`
   recusa href fora da allow-list), WhatsApp (`useWhatsAppTemplate.ts`, `Idempotency-Key`,
   `base_version`). WebAuthn (`useDeviceSeal.ts`, `utils/deviceSeal.ts`). Migrar o selo não pode
   mudar a ordem digital → código, o Enter no TOTP, nem o "fechar só sem busy" (:296-299).
4. **Segunda pessoa.** Quem pediu nunca confirma (`second-control/[ref].vue:140`); o selo chama e
   faz poll a cada 3 s. Sem retrato nem fixture: testar à mão no mock antes e depois.
5. **WhatsApp silêncio 20:00 a 08:00 e ensaio local** (`AnnouncementCard.vue:864-875`,
   `scheduleResolution` em `utils/marketingSchedule.ts`): o campo de data/hora migrado tem de
   manter o "Usar o próximo horário permitido" e a escolha de ocorrência ambígua de horário de verão.
6. **`value: ""` em seleção** (lição do P0-1 do Gestor: `SelectItem` do reka lança com valor vazio
   e derruba a página). Hoje em `<select>` nativo: `history.vue:66-115` (Situação, Plataforma,
   Origem: "Todas" = `""`), `campaigns.vue:517` (`<option value="">`). Em `UiSelect` (NuxtSelectMenu):
   `platforms.vue:222` ("Sem modelo"), `:255` (sem produto), `CampaignForm.vue:716` (sem oferta).
   Migrar para `NuxtSelect` com item vazio reproduz o P0-1; usar `placeholder` ou sentinela.
7. **Câmera:** "Tirar foto" depende de `capture="environment"` no `<input type=file>`
   (`AnnouncementCard.vue:624-633`); a aprovação só aceita foto que veio da revisão (contrato).
8. **Toast:** `useSonner` é o vue-sonner. Se o Marketing passar a `NuxtApp` (kit `OperatorAppRoot`),
   precisa do remapeamento do Gestor, senão nascem dois toasters (laudo P1-5) e as 31 chamadas
   falham em silêncio.
9. **`#below` e `fullscreen`:** a revisão some com a barra do polegar por `route.meta.fullscreen`
   (`app.vue:82`); o prazo no celular depende do `#below` (`[id].vue:441`). Sem retrato a 390.
10. **Contrato e docs:** `marketing-surface-contract.md` descreve `data-suite="v3"`,
    `MarketingPageHeader sobre OperatorPageHeader`, sino na barra de 56 px; `make marketing-docs`
    só confere rotas e probes, então a prosa deriva sem acusar. Atualizar junto.
11. **Defeitos pré-existentes a não mascarar:** Reagendar sem tratador (§2.3); `.live-dot`
    inexistente (§3); ⋯/Atualizar inacessível por toque em Decisões e Agendados no celular (§2.3);
    `MarketingBoard` vivo só na matriz.
