# Marketing: engenharia reversa por função

App: `surfaces/marketing-nuxt` (host `mkt.`, grupo `operator-office`) + `shopman/backstage/api/marketing*.py`,
`shopman/backstage/projections/marketing{,_v2,_actions}.py`, `shopman/shop/services/campaign.py` e
`shopman/shop/services/marketing_*.py` (outbox, ledger, worker, cerimônia, aprovação). Contrato factual:
`docs/reference/marketing-surface-contract.md`.

**O que o app é, em uma frase:** a padaria gera ocasiões (fornada pronta, estoque baixo, voltou ao
estoque, produto novo, relógio, decisão do gestor); o sistema transforma cada ocasião em um *anúncio*
(rascunho com texto, foto, público e plataformas); o gestor diz **sim / não / quando**; o sistema entrega
(postagem pública em Instagram/Facebook/Google, mensagem direta por WhatsApp) e conta o que aconteceu.
Todo o resto (campanhas, modelos, ofertas, plataformas) é **configuração** que existe para que esse
"sim" seja um toque.

Quem: na prática uma pessoa só (o dono/gestor) faz tudo; a separação de capacidades
(`edit_campaigns`, `approve`, `publish`, `fire`, `retry`, `reconcile`, `configure_platforms`, `freeze`…)
existe no backend, mas o operador real é um.

---

## 1. Mapa das funcionalidades

| ID | trabalho | quem | onde/dispositivo | gatilho | frequência | urgência | padrão |
|---|---|---|---|---|---|---|---|
| M01 | Ver o que pede atenção agora | gestor | escritório ou celular | abrir o app / rotina | 2-5×/dia | minutos | VIGIAR |
| M02 | Receber o aviso de anúncio para revisar e abrir a decisão | gestor | celular (push) | anúncio criado por evento | 0-10×/dia | minutos (prazo de revisão) | AVISAR → TRIAR |
| M03 | Decidir um anúncio: segue ou não segue | gestor (aprovador) | celular | M02 / M01 / M20 | 0-10×/dia | minutos (FOMO, prazo) | APROVAR |
| M04 | Ajustar texto e hashtags do anúncio antes de decidir | gestor | celular | texto do modelo não serve | 30% dos anúncios | minutos | COMPOR (micro) |
| M05 | Pedir sugestão de texto à IA e usar/desfazer/descartar | gestor | celular | texto fraco | raro (flag desligada por padrão) | minutos | COMPOR (assistido) |
| M06 | Conferir a foto que vai sair | gestor | celular | toda decisão | por anúncio | minutos | CONFERIR |
| M07 | Escolher plataformas do anúncio e o tipo/botão do post do Google | gestor | celular | toda decisão | por anúncio | minutos | COMPOR (micro) |
| M08 | Escolher quando sai: agora ou hora marcada | gestor | celular | toda decisão; silêncio 20h-8h do WhatsApp | por anúncio | minutos | PLANEJAR (micro) |
| M09 | Confirmar o disparo provando que entendeu a consequência | gestor (+ 2ª pessoa acima do limiar) | celular | "Continuar" em M03 | por anúncio aprovado | segundos | AUTORIZAR + CONFIRMAR |
| M10 | Recusar o anúncio com motivo | gestor | celular | anúncio errado/inoportuno | ocasional | minutos | APROVAR (negativo) |
| M11 | Acompanhar a entrega até assentar | gestor | celular/desktop | após M09 | por anúncio | minutos (até ~7 min; 100 pessoas ~30 min) | VIGIAR |
| M12 | Repetir somente as falhas seguras | gestor (retry) | desktop/celular | entrega com falha repetível | raro | horas | CORRIGIR |
| M13 | Consultar o resultado incerto sem reenviar | gestor (reconcile) | desktop | estado `unknown` | raro | horas | CONFERIR |
| M14 | Cancelar o que ainda não começou | gestor (publish) | celular | erro percebido após aprovar/agendar | raro | minutos | CORRIGIR |
| M15 | Mudar a hora de um anúncio já agendado | gestor | — (só API) | plano mudou | raro | horas | PLANEJAR · **sem tela** |
| M16 | Criar campanha (compositor de 5 etapas) | gestor | desktop | nova ideia/rotina | poucas/mês | dias | CONFIGURAR / COMPOR |
| M17 | Editar campanha existente | gestor | desktop | ajustar público/texto/horário | poucas/mês | dias | CONFIGURAR |
| M18 | Ligar/desligar campanha | gestor | celular ou desktop | sazonalidade, falta de produto, erro | semanal | minutos-horas | CONFIGURAR (1 toque) |
| M19 | Achar uma campanha na lista | gestor | desktop | M17/M18/M20 | semanal | — | LOCALIZAR |
| M20 | Preparar disparo manual: definir o público e ver quantos recebem | gestor (fire) | desktop/celular | decisão do gestor (promoção, aviso) | semanal | minutos | COMPOR → (M03) |
| M21 | Definir a reação automática a um evento (qual evento, qual produto/qualidade, revisão obrigatória, prazo) | gestor | desktop (+ Admin para filtro) | montar a máquina FOMO | raro | dias | CONFIGURAR |
| M22 | Programar campanha pelo relógio (uma vez / toda semana, janelas, vigência) | gestor | desktop | rotina (ex.: "pão saindo 7h") | raro | dias | PLANEJAR |
| M23 | Escrever/editar modelo de conteúdo (texto com variáveis, origem da foto, IA opcional) | gestor | desktop | nova campanha sem modelo | raro | dias | COMPOR / CONFIGURAR |
| M24 | Adaptar texto/formato por plataforma (Story×Feed, post Google Atualização/Evento/Oferta) | gestor | desktop | plataforma pede outra forma | raro | dias | COMPOR |
| M25 | Apagar modelo (com dependências visíveis) | gestor | desktop | limpeza | raro | — | CORRIGIR |
| M26 | Criar oferta automática (benefício, vigência, alcance, condições) | gestor | desktop | ação comercial | mensal | dias | CONFIGURAR |
| M27 | Criar cupom (código + regra própria + limite) | gestor | desktop | ação comercial / parceria | mensal | dias | CONFIGURAR |
| M28 | Criar campanha a partir de uma oferta | gestor | desktop | após M26 | mensal | dias | COMPOR (atalho) |
| M29 | Saber por onde a padaria consegue falar agora (catálogo de destinos, prontidão, motivo) | gestor | desktop | antes de criar/aprovar; anomalia | semanal | horas | VIGIAR / ENTENDER |
| M30 | Escolher o modelo aprovado (Meta/ManyChat) do anúncio no WhatsApp | gestor (configure) | desktop | primeira configuração / troca | raro | dias | CONFIGURAR + AUTORIZAR (TOTP) |
| M31 | Ligar cada aviso automático (pedido, pagamento, fila, fidelidade…) ao modelo aprovado | gestor (configure) | desktop | implantação / novo fluxo | raro | dias | CONFIGURAR + AUTORIZAR · **fronteira errada** |
| M32 | Verificar de novo o catálogo de modelos do WhatsApp | gestor | desktop | lista vazia/velha | raro | horas | CONFERIR |
| M33 | Enviar teste seguro a um número verificado | gestor (send_test) | desktop + celular na mão | depois de M30/M31 | raro | minutos | CONFERIR |
| M34 | Consultar o histórico (o que saiu, o que falhou, quem decidiu) | gestor | desktop | dúvida, auditoria, cliente reclamou | semanal | — | LOCALIZAR / ENTENDER |
| M35 | Dar "Visto" a um alerta / abrir a revisão pelo sino | gestor | celular/desktop | badge do sino | diário | minutos | AVISAR (ack) |
| M36 | Recuperar o rascunho local após conflito ou queda de sessão | gestor | qualquer | outra sessão mudou / reautenticou | raro | minutos | CORRIGIR |
| M37 | Congelar/descongelar todo efeito externo (botão de pânico) | dono | — (só API) | incidente, texto errado saindo | raríssimo | segundos | CORRIGIR · **sem tela** |
| M38 | Ajustar a cerimônia do disparo e o mínimo de público do WhatsApp | dono | Admin (Loja → Integrações) | calibrar risco | raríssimo | dias | CONFIGURAR · fora do app |

---

## 2. Fichas

### M01 · Ver o que pede atenção agora
- **Quem:** gestor. **Onde:** `/v2?area=today`; desktop hoje, mas é pergunta de celular (relance).
- **Gatilho:** abrir o app; voltar de outra tarefa. **Frequência/urgência:** 2-5×/dia, minutos. Cliente esperando: não.
- **Objetivo real:** saber se há decisão pendente que vai vencer e se alguma conexão parou.
- **Info mínima:** lista dos anúncios pendentes com prazo restante (o mais urgente primeiro) + entregas com falha/incerteza + plataforma bloqueada que afeta campanha ligada. **Sobra:** 4 cartões-contadores ("Publicações hoje", "Campanhas ligadas", "Destinos operacionais" e "Pedem revisão" duplicando a lista ao lado), título/subtítulo explicativo da "V2", contagem de "registros recentes carregados". **Falta:** prazo de cada pendente (só nome e plataformas); falhas/`unknown` de entrega (não aparecem em Hoje, só no histórico); lista completa (corta em 4, `pendingPosts.slice(0,4)`); o link "Abrir revisão" aponta para `/`, que redireciona para a própria tela (laço).
- **Entrada:** nenhuma (ler) + escolher um item. **Efeito:** nenhum. **Erro:** baixo.
- **Exceções:** board não carregou → alerta "não significa que não existam campanhas"; `freshness` não fresca → "atualize antes de decidir". Poll 60 s + SSE pessoal de invalidação.
- **Caminho hoje:** abrir → ler 4 contadores → lista de 4 → "Revisar". **Mínimo:** 1 tela que é a própria fila de decisões; 0 passos para saber, 1 toque para agir.
- **Fronteira:** recebe de Produção/Estoque/Catálogo (eventos que criam anúncios); leva a M03/M11/M29.
- **Padrão:** VIGIAR.
- **Evidência:** `app/components/MarketingV2Workspace.vue`, `app/composables/useCampaignBoard.ts`, `shopman/backstage/projections/marketing_v2.py`, `app/pages/index.vue`.

### M02 · Receber o aviso de anúncio para revisar e abrir a decisão
- **Quem:** quem tem `approve_marketing_announcements` (ou `Campaign.notify_users`). **Onde:** push no celular + sino.
- **Gatilho:** `notify_reviewers()` ao criar anúncio `pending_review` por evento ou disparo. **Frequência:** 0-10/dia; urgência = prazo de revisão da campanha (`expires_after_minutes`). Cliente esperando: indiretamente (o pão está na vitrine agora).
- **Objetivo real:** que a pessoa certa veja a ocasião antes de ela perder valor.
- **Info mínima no aviso:** produto + evento + prazo ("Croissant saiu do forno · vence em 25 min"). **Sobra:** n/d. **Falta:** decisão direto do aviso (o push só abre a tela).
- **Entrada:** tocar. **Efeito:** marca visto; deep link `/announcements/:id`. **Erro:** baixo.
- **Exceções:** anúncio já decidido/vencido/versão mudou → ação desabilitada com motivo (`announcement_no_longer_actionable`, `review_window_expired`, `source_version_changed`); notificações fechadas automaticamente quando o anúncio é decidido (`closed_review_notification_ids`).
- **Caminho hoje:** push → tela do anúncio (1 toque). **Mínimo:** 1 toque; o inevitável é abrir.
- **Fronteira:** de `shop.services.campaign` / `user_notifications`; para M03.
- **Padrão:** AVISAR → TRIAR.
- **Evidência:** `shopman/shop/services/campaign.py` (`notify_reviewers`, `_reviewers`), `shopman/shop/services/user_notifications.py`, `app/components/MarketingNotificationsBell.vue`, `app/presentation/notifications.ts`.

### M03 · Decidir um anúncio: segue ou não segue
- **Quem:** aprovador. **Onde:** `/announcements/:id` (`AnnouncementCard`); deve ser celular, uma mão, de pé no salão.
- **Gatilho:** M02, M01, ou chegada vinda do disparo manual (M20, `?dispatch=new`). **Frequência:** por anúncio; urgência minutos (selo de prazo com tons urgente/aviso/calmo). Cliente esperando: não.
- **Objetivo real:** autorizar que este conteúdo, com esta foto, saia para estas plataformas e estas pessoas, agora ou numa hora.
- **Info mínima:** foto que sai, texto que sai, onde sai (postagem pública × mensagem: quantas pessoas), quando, prazo restante, bloqueio de plataforma. **Sobra:** contexto de origem em vários chips; prévia simulada por plataforma ocupando espaço logo no card (útil, mas é conferência, não decisão); "Disparado via" como lista longa. **Falta:** nada essencial; o público aparece como resumo, e a contagem final só no M09.
- **Entrada:** confirmar (Continuar) ou recusar. **Efeito:** nenhum ainda; "Continuar" abre M09 (edições viajam junto com a aprovação num request só, para não aprovar versão anterior).
- **Exceções:** prazo vencido → "Prepare um disparo novo em Campanhas" (sem botão); silêncio do WhatsApp 20h-8h → "Imediato" indisponível, agenda sugere próximo horário; plataforma bloqueada → pílula + "Ver em Plataformas"; rascunho local em conflito com servidor → M36; 409 de versão.
- **Caminho hoje:** abrir → rolar card (foto, texto, hashtags, plataformas, prévia, público, quando) → Continuar → M09 → confirmar = 3-5 toques + rolagem. **Mínimo:** 2 toques (ver → confirmar com a consequência no mesmo lugar). Inevitável: o "sim" informado.
- **Fronteira:** de M02/M20; para M09/M10/M11. Dado: `Announcement` (content, platform_content, audience, expires_at, version).
- **Padrão:** APROVAR.
- **Evidência:** `app/pages/announcements/[id].vue`, `app/components/AnnouncementCard.vue`, `shopman/backstage/api/marketing.py` (`AnnouncementDetailView`, `AnnouncementApproveView`), `shopman/shop/services/marketing_approval.py`.

### M04 · Ajustar texto e hashtags
- **Quem:** gestor (`edit_marketing_campaigns`). **Onde:** dentro de M03.
- **Gatilho:** texto do modelo não soa bem para a ocasião. **Frequência:** fração dos anúncios. **Urgência:** minutos.
- **Objetivo real:** dar o tom certo antes de sair.
- **Info mínima:** texto, limite da plataforma (Google 1.500 com hashtags, sem telefone). **Falta:** contador de limite no campo (trava só na prévia/aprovação via `field_errors`).
- **Entrada:** digitar texto. **Efeito:** rascunho local (persistido por dono de sessão) até a aprovação; vai no mesmo request. **Reversível:** sim até aprovar. **Erro:** médio (texto público).
- **Exceções:** telefone no texto do Google (`google_summary_has_phone`); corpo vazio (`body_required`).
- **Caminho:** tocar no campo, editar. **Mínimo:** idem (já é mínimo).
- **Padrão:** COMPOR (micro).
- **Evidência:** `AnnouncementCard.vue` (`edits()`, `DRAFT_LABELS`), `api/marketing.py` `_announcement_edits`.

### M05 · Pedir sugestão de texto à IA
- **Quem:** aprovador (a assistência usa `approve_marketing_announcements`). **Onde:** dentro de M03.
- **Gatilho:** modelo com `use_ai_generation`; flags `SHOPMAN_MARKETING_AI_ASSIST_V2` e política do fornecedor ligadas (padrão desligado).
- **Objetivo real:** ter uma alternativa de texto sem perder o próprio.
- **Info mínima:** "Seu texto" × "Sugestão", fatos usados, avisos. **Entrada:** escolher (Usar no rascunho / Desfazer uso / Descartar). **Efeito:** só muda o rascunho; `ai_suggestion_ref` vai como rastro; disposição registrada (`suggestions/:ref/disposition/`). Nunca publica.
- **Exceções:** sem credencial → botão não aparece.
- **Caminho:** Sugerir → ler comparação → Usar. 3 toques. **Mínimo:** 2.
- **Padrão:** COMPOR (assistido).
- **Evidência:** `AnnouncementCard.vue` (bloco sugestão), `api/marketing.py` `AnnouncementRewriteView`, `AnnouncementSuggestionDispositionView`, `shopman/shop/services/marketing_ai.py`.

### M06 · Conferir a foto que vai sair
- **Quem:** gestor. **Onde:** M03 e caixa de M09.
- **Gatilho:** toda decisão; Story exige imagem 9:16 pública; Google exige JPEG/PNG 10 KB-5 MB, ≥250 px.
- **Objetivo real:** não publicar mural sem foto ou com foto errada.
- **Info mínima:** a foto real (de `platform_content.<plataforma>.image_url`, não do campo do topo), aviso "sem foto" quando há mural. **Falta:** **trocar a foto**. A origem é decidida no modelo (`image_source`: produto/galeria/fixa/nenhuma); a API aceita `image_url` nas edições, mas o card não oferece. Se a foto está ruim, a única saída é recusar.
- **Entrada:** olhar. **Efeito:** nenhum. **Erro:** alto se passar despercebido (post público sem foto/feio).
- **Exceções:** `google_media_*` (lido por `marketing_media_probe`); caixa de confirmação avisa mural sem imagem antes.
- **Caminho:** ver. **Mínimo:** ver + (faltando) 1 gesto "trocar foto" escolhendo da galeria do produto.
- **Padrão:** CONFERIR.
- **Evidência:** `AnnouncementCard.vue` (`outgoingImage`), `app/presentation/marketingDelivery.ts` (`outgoingImageUrl`), `types/campaign.ts` (`AnnouncementEdits.image_url`), `shopman/shop/services/marketing_media_probe.py`.

### M07 · Escolher plataformas do anúncio e o post do Google
- **Quem:** gestor. **Onde:** M03.
- **Gatilho:** toda decisão (vem preenchido pela campanha).
- **Objetivo real:** tirar/pôr destino para esta ocasião; para o Google, escolher tipo (Atualização/Evento/Oferta) e botão (Nenhum, Ligar agora, Saiba mais, Pedir on-line, Comprar, Reservar, Inscrever-se).
- **Info mínima:** cada plataforma com estado e motivo (desligada/não verificada/limitada) e a grandeza (1 postagem × N mensagens). **Sobra:** comentários longos viraram tela longa; lista empilhada.
- **Entrada:** marcar de lista curta (4). **Efeito:** rascunho. **Erro:** médio (WhatsApp manda para pessoas, irreversível).
- **Exceções:** nenhuma marcada → "Escolha ao menos uma plataforma"; plataforma desligada no ambiente não bloqueia aprovação (fica `queued` "aguardando a plataforma ligar"); link sem botão não aparece no Google; Oferta do Google sela título/validade pela promoção.
- **Caminho:** marcar/desmarcar + abrir opções Google. **Mínimo:** 0 na maioria (aceitar o padrão da campanha).
- **Padrão:** COMPOR (micro).
- **Evidência:** `AnnouncementCard.vue`, `GoogleBusinessPostOptions.vue`, `app/presentation/googleBusinessPost.ts`, `app/presentation/platformReadiness.ts`, `shopman/shop/services/marketing_google_post.py`.

### M08 · Escolher quando sai
- **Quem:** gestor. **Onde:** M03 (alternador Imediato/Agendado).
- **Gatilho:** toda decisão; silêncio do WhatsApp 20:00-08:00 no fuso da loja.
- **Objetivo real:** sair na hora em que funciona (e sem acordar cliente).
- **Info mínima:** "agora" disponível ou não e por quê; hora sugerida; fuso. **Falta:** nada; já sugere próximo horário permitido e resolve horário repetido em troca de relógio.
- **Entrada:** escolher (agora/agendar) + data-hora. **Efeito:** `publish_at` na aprovação. **Erro:** médio.
- **Exceções:** `quiet_hours_active`, `scheduled_in_quiet_hours`, `delivery_wave_in_quiet_hours`, agendamento após o prazo do anúncio; acima de 2.000 mensagens agendar é obrigatório.
- **Caminho:** 1 toque (Agendado) + ajustar hora. **Mínimo:** 0 (agora) ou 1.
- **Padrão:** PLANEJAR (micro).
- **Evidência:** `AnnouncementCard.vue` (`scheduleResolution`, `useNextAllowedTime`), `app/utils/marketingSchedule.ts`, `shopman/shop/services/marketing_time.py`.

### M09 · Confirmar o disparo provando que entendeu a consequência
- **Quem:** aprovador/publicador; acima do limiar, mais uma pessoa. **Onde:** `MarketingCommandConfirmationDialog` sobre M03.
- **Gatilho:** "Continuar". **Urgência:** segundos.
- **Objetivo real:** o "sim" final, proporcional ao que não se desfaz.
- **Info mínima:** o QUÊ (texto congelado do comando, com hashtags), ONDE (uma linha por destino na sua grandeza: N pessoas por WhatsApp; 1 postagem por mural), QUANDO; foto; aviso de mural sem foto. **Sobra:** pouco; é a melhor tela do app.
- **Entrada (cerimônia por consequência, ADR-031/032/033):** só postagem pública → resumo + 1 toque; qualquer mensagem direta → digitar `ENVIAR <pessoas>` sempre; acima do limiar `max(piso, min(%×base, teto÷custo))` → frase + senha; acima de `×múltiplo` → frase + TOTP + duplo controle. Botão com verbo do destino (Enviar/Publicar/Disparar/Agendar).
- **Efeito:** aprova, sela artefato imutável e público (`AudienceSnapshot`), cria outbox; recibo (`MarketingCommandReceipt`). **Reversível:** postagem sim (apagar fora do app); mensagem não. **Erro:** alto.
- **Exceções:** sessão expirada → reautenticar e voltar ao mesmo ponto; `audience_below_minimum` (mínimo WhatsApp do Admin; não vale em `canary`); quota diária 5.000 destinos; 409 versão; **duplo controle**: "Peça a outra pessoa… para abrir este mesmo anúncio e confirmar" sem nenhum mecanismo de pedir (o endpoint `security/dual-control/` não é chamado pelo Nuxt; nenhuma notificação vai para a 2ª pessoa).
- **Caminho:** ler → digitar frase → (senha/TOTP) → confirmar. **Mínimo:** postagem: 1 toque; mensagem: 1 digitação + 1 toque (o inevitável é a prova de leitura do número).
- **Fronteira:** de M03; para M11 (outbox → `maintenance-worker` → adapter → provedor).
- **Padrão:** AUTORIZAR + CONFIRMAR (rótulo novo proposto: **SELAR**, ver §3).
- **Evidência:** `app/components/MarketingCommandConfirmationDialog.vue`, `app/composables/useMarketingDecisionCommand.ts`, `shopman/shop/services/marketing_ceremony.py`, `marketing_security.py`, `marketing_commands.py`, ADRs 031-033.

### M10 · Recusar o anúncio com motivo
- **Quem:** aprovador. **Onde:** M03 → diálogo de motivo.
- **Gatilho:** conteúdo/ocasião ruim. **Objetivo real:** encerrar a ocasião e deixar registrado por quê (revela modelo de campanha errado).
- **Info mínima:** motivo curto. **Falta:** atalhos de motivo (texto livre só); ligação do motivo com "corrigir a campanha/modelo".
- **Entrada:** digitar texto + confirmar. **Efeito:** `rejected`, notificações fechadas. **Reversível:** não (precisa novo disparo). **Erro:** baixo.
- **Caminho:** Recusar → motivo → confirmar (3). **Mínimo:** 2 (escolher motivo de lista curta).
- **Padrão:** APROVAR (negativo).
- **Evidência:** `[id].vue` (`confirmingReject`, `rejectReason`), `api/marketing.py` `AnnouncementRejectView`, `campaign.reject`.

### M11 · Acompanhar a entrega até assentar
- **Quem:** gestor. **Onde:** `AnnouncementResultPanel` em `/announcements/:id`.
- **Gatilho:** após M09. **Urgência:** minutos (latência real até ~7 min por lote de 20; "enviar agora" = próxima passada do worker de 300 s).
- **Objetivo real:** saber se saiu, onde, para quantos, e se algo precisa de mão.
- **Info mínima:** por plataforma: confirmado / aceito não confirmado / na fila / aguardando plataforma ligar / falha final / falha repetível / incerto; contagens na grandeza certa. **Sobra:** explicações longas. **Falta:** SSE de marketing (poll com espera crescente que para no teto e oferece "verificar de novo").
- **Entrada:** nenhuma (ou atualizar). **Efeito:** nenhum.
- **Exceções:** flag da plataforma desligada → destinos ficam `queued`; Google `PROCESSING` fica `accepted`; `unknown` nunca repete às cegas.
- **Caminho:** ficar na tela. **Mínimo:** 0; avisar só se der problema (push de falha).
- **Fronteira:** de `marketing_outbox` → `marketing_delivery_worker` → adapters; para M12/M13/M14/M34.
- **Padrão:** VIGIAR.
- **Evidência:** `app/components/AnnouncementResultPanel.vue`, `app/presentation/marketingResult.ts` (`DELIVERY_TRACKING_POLICY`), `shopman/shop/services/marketing_delivery_{ledger,worker,aggregate,runtime}.py`.

### M12 · Repetir somente as falhas seguras
- **Quem:** `retry_failed_marketing`. **Onde:** painel de resultado e linha do histórico.
- **Gatilho:** falha repetível (`subscriber_busy`, rede antes da escrita). **Objetivo:** reentregar só a quem não recebeu, sem duplicar.
- **Info mínima:** quantos destinos, de que tipo, e o motivo. **Entrada:** confirmar (desafio com mesma cerimônia proporcional; mensagens → frase). **Efeito:** novas tentativas no ledger. **Erro:** médio (duplicata se mal classificado; o backend impede).
- **Caminho:** Repetir → caixa → confirmar. **Mínimo:** 2. Discutível: falha repetível poderia ser repetida pelo sistema sozinho (já há fila com retentativa para `subscriber_busy`).
- **Padrão:** CORRIGIR.
- **Evidência:** `app/composables/useMarketingRecovery.ts`, `api/marketing.py` `AnnouncementRetryDeliveriesView`, `shopman/shop/services/marketing_delivery_recovery.py`.

### M13 · Consultar o resultado incerto sem reenviar
- **Quem:** `reconcile_unknown_marketing`. **Onde:** painel de resultado/histórico.
- **Gatilho:** `unknown` (resposta ambígua depois de possível escrita). **Objetivo:** descobrir se saiu, consultando o provedor somente-leitura.
- **Entrada:** confirmar. **Efeito:** agenda consulta executada pela passada `--with-reconciliation`. **Erro:** baixo (só lê).
- **Caminho:** 2 toques. **Mínimo:** 0 — o sistema poderia pedir sozinho a reconciliação (é só leitura), e a tela só mostrar o resultado.
- **Padrão:** CONFERIR.
- **Evidência:** `useMarketingRecovery.ts`, `AnnouncementReconcileDeliveriesView`.

### M14 · Cancelar o que ainda não começou
- **Quem:** `publish_marketing_announcements`. **Onde:** painel de resultado.
- **Gatilho:** erro visto depois de aprovar ou agendar. **Urgência:** minutos (até a próxima passada).
- **Objetivo:** parar plataformas ainda não iniciadas; o que começou segue.
- **Entrada:** digitar motivo + confirmar. **Efeito:** outbox/destinos cancelados. **Reversível:** não. **Erro:** baixo.
- **Exceções:** entrega começou → ação desabilitada com motivo.
- **Caminho:** Cancelar → motivo → confirmar. **Mínimo:** 2.
- **Padrão:** CORRIGIR.
- **Evidência:** `AnnouncementResultPanel.vue` (`cancel_announcement`), `AnnouncementCancelView`.

### M15 · Mudar a hora de um anúncio já agendado
- **Quem:** publicador. **Onde:** não existe na UI; há `POST announcements/:id/reschedule/` e rótulo de recibo "reagendar".
- **Gatilho:** chuva, forno atrasou, promoção mudou. **Hoje:** cancelar e preparar disparo novo (passando de novo por M20→M03→M09).
- **Mínimo:** 1 campo de hora + confirmar.
- **Padrão:** PLANEJAR. **Lacuna.**
- **Evidência:** `api/marketing.py` `AnnouncementRescheduleView`; ausência em `app/` (só `presentation/marketingResult.ts` rotula o recibo).

### M16 · Criar campanha (compositor de 5 etapas)
- **Quem:** gestor. **Onde:** `/campaigns?new=1` em workspace modal; desktop.
- **Gatilho:** ideia nova ou rotina nova. **Frequência:** poucas/mês. **Urgência:** dias.
- **Objetivo real:** guardar uma regra "quando X, diga Y, para Z, em W", para nunca mais compor isso à mão.
- **Etapas:** 1 Objetivo (nome + gatilho: produção concluída, estoque baixo, voltou ao estoque, produto novo, disparo manual, agendado) · 2 Destinos (plataformas da allow-list `delivery_capabilities` com prontidão) · 3 Conteúdo (modelo, oferta, composições por plataforma) · 4 Público e momento (favoritaram, pediram "me avise", compraram em N dias, faixa de preço, etiquetas, segmentos RFM, risco de não voltar, aniversariantes, qualquer/todos, VIP N minutos antes, janela de horário preferido; agendamento; revisar antes de publicar; prazo de revisão; ligada) · 5 Revisar.
- **Info mínima:** gatilho, modelo, plataformas, público (com contagem), revisão sim/não. **Sobra:** cards de destinos com formatos na tela pai; explicações extensas. **Falta:** **filtro do evento** (qual produto/coleção, qualidade mínima da fornada, estoque máximo restante) que decide *quando* a campanha automática dispara: só editável no Admin (`trigger_filter`), a tela apenas diz "os filtros já salvos continuam valendo"; destinatários do aviso (`notify_users`) também fora; contagem de público dentro do compositor (só existe no M20).
- **Entrada:** escolher de listas curtas + digitar nome + horários. **Efeito:** `Campaign` criada. **Reversível:** sim. **Erro:** médio (campanha automática ligada sem revisão manda sozinha).
- **Exceções:** falha da allow-list → formulário falha fechado; sem modelos → bloqueio (por isso nasceu `/templates`); `_pairing_error` (oferta incompatível); plataforma não pronta é aviso, não bloqueio.
- **Caminho hoje:** V2 Campanhas → Nova campanha → 5 etapas (~15-30 toques). **Mínimo:** 3 decisões (quando, o quê, para quem) com defaults para o resto; o inevitável é escolher o gatilho e o modelo.
- **Fronteira:** consome catálogo (produtos/coleções), Guestman (etiquetas, faixas, RFM), ofertas (M26); produz anúncios quando Produção/Estoque/relógio emitem eventos.
- **Padrão:** CONFIGURAR + COMPOR.
- **Evidência:** `app/components/CampaignForm.vue`, `app/pages/campaigns.vue`, `api/marketing.py` (`CampaignListView`, `_rule_fields`), `shopman/shop/models/campaign.py` (`Trigger`, `Campaign`), `shopman/shop/admin/campaign.py`.

### M17 · Editar campanha existente
- Igual a M16 sobre registro existente. Exige Action `edit_campaign` da versão visível; PATCH com `base_updated_at`; 409 recarrega. Rascunho local com aviso de conflito por campo legível.
- **Mínimo:** abrir na etapa do que se quer mudar (hoje sempre começa na etapa 1).
- **Padrão:** CONFIGURAR. **Evidência:** `campaigns.vue` (`openEdit`, `patch`), `app/presentation/campaignActions.ts`, `CampaignDetailView.patch`.

### M18 · Ligar/desligar campanha
- **Quem:** gestor. **Onde:** linha da lista `/campaigns` (1 toque). Faz sentido no celular ("acabou o croissant, desliga").
- **Gatilho:** falta de produto, fim de temporada, erro. **Urgência:** minutos (campanha automática pode disparar a qualquer evento).
- **Info mínima:** nome + estado. **Entrada:** 1 toque. **Efeito:** `is_active`. **Reversível:** sim. **Erro:** baixo.
- **Exceções:** sem Action → controle não existe; PATCH em voo bloqueia segundo gesto; 409 recarrega sem otimismo.
- **Caminho:** V2 Campanhas → Gerenciar todas → toque (a lista da V2 mostra estado mas não tem o interruptor). **Mínimo:** 1 toque a partir de Hoje.
- **Padrão:** CONFIGURAR (1 toque) — na prática é um **INTERRUPTOR**.
- **Evidência:** `campaigns.vue` (`toggle`, `mutatingCampaignPk`), `useCampaigns.ts`.

### M19 · Achar uma campanha
- Busca por nome/gatilho/modelo/plataforma (sem acento), filtros estado/plataforma, 12 por página, recém-criada no topo. **Padrão:** LOCALIZAR. **Evidência:** `campaigns.vue` (`filteredRules`).

### M20 · Preparar disparo manual: definir o público e ver quantos recebem
- **Quem:** `fire_marketing_campaigns`. **Onde:** `FireCampaignPanel` ("Definir público") a partir da linha da campanha.
- **Gatilho:** decisão do gestor (promoção de hoje, aviso). Vale para qualquer campanha ligada, inclusive as automáticas (força revisão).
- **Objetivo real:** escolher para quem vai esta vez, sem mudar a campanha salva.
- **Info mínima:** opções em frase (faixa, etiquetas com contagem, segmentos, reconquista, aniversariantes, VIP primeiro, somar×cruzar), **número de pessoas ao vivo** enquanto escolhe, quem ficou de fora e por quê (sem consentimento, sem data de nascimento), produto quando o modelo pede. **Sobra:** pouco. **Falta:** escolher o texto aqui (deliberadamente proibido: texto vem do modelo).
- **Entrada:** escolher de listas + produto. **Efeito:** cria anúncio `pending_review` (challenge `none` consumido automaticamente) e navega para M03. Nada é entregue. **Erro:** baixo nesta etapa.
- **Exceções:** público vazio/zero explicado; contagem falhou → botão bloqueado; 409 → recarrega e pede reconferir; 429 com hora de retorno; campanha só pública dispensa público.
- **Caminho:** linha → Preparar disparo → escolher público (+produto) → Criar → (M03 completo) → M09. ~8-12 toques. **Mínimo:** público → confirmar com consequência = 3. **Achado:** quem dispara é o mesmo que revisa; a ida à revisão é cerimônia dupla para a mesma pessoa (o backend até prevê `body` escrito = publica direto com autor como aprovador, mas a UI não usa).
- **Fronteira:** Guestman (público, consentimento) → anúncio → M03.
- **Padrão:** COMPOR → APROVAR.
- **Evidência:** `app/components/FireCampaignPanel.vue`, `app/composables/useAudienceCount.ts`, `useCampaignFireCommand.ts`, `api/marketing.py` (`CampaignFireView`, `AudienceCountView`), `shopman/shop/services/campaign.py` (`fire_now`), `marketing_fire.py`.

### M21 · Definir a reação automática a um evento
- **Quem:** gestor. **Onde:** M16 etapas 1 e 4 + Admin para o filtro.
- **Gatilho:** montar a "máquina FOMO" (fornada ótima → Story; estoque baixo → "últimas unidades"; voltou → "me avise").
- **Objetivo real:** decidir que ocasiões da produção merecem virar anúncio, e se passam por olho humano antes.
- **Info mínima:** evento, produto/coleção, qualidade mínima da fornada e parcela mínima (ADR-017), estoque máximo restante, revisar sim/não, prazo de revisão. **Falta:** os quatro filtros (só Admin). Sem filtro, "Produção concluída" casa toda fornada de todo produto.
- **Efeito:** anúncios nascem sozinhos; com `requires_approval=false` saem sem ninguém olhar. **Erro:** alto (comunicação pública automática).
- **Exceções:** correção de QC posterior torna anúncio `superseded`; prazo vencido → `expired`.
- **Mínimo:** 1 tela: evento + produto + nível + revisão.
- **Padrão:** CONFIGURAR (regra de reação).
- **Evidência:** `campaign.py` (`evaluate`, `matches_filter`, `reconcile_quality_correction`, `_expiry`), `CampaignForm.vue` (`preservedTriggerFilterKeys`).

### M22 · Programar campanha pelo relógio
- **Quem:** gestor. **Onde:** M16 etapa 4 (só com gatilho "Agendado").
- **Info:** uma vez (data-hora com resolução de horário ambíguo) ou toda semana (hora, dias, janelas extras, vigência), fuso da loja. **Efeito:** `arm_scheduled` arma Directive na hora exata; cada ocorrência cria anúncio (com ou sem revisão).
- **Mínimo:** hora + dias.
- **Padrão:** PLANEJAR.
- **Evidência:** `CampaignForm.vue` (`buildSchedule`), `shopman/shop/services/campaign_schedule.py`, `campaign.py` (`arm_scheduled`, `create_for_occurrence`, `dispatch_due`).

### M23 · Escrever/editar modelo de conteúdo
- **Quem:** `edit_marketing_templates`. **Onde:** `/templates` (workspace modal); desktop.
- **Objetivo real:** escrever uma vez o texto que vai servir a muitas ocasiões, com lacunas preenchidas pelo sistema.
- **Info mínima:** nome, texto, chips de variáveis vindas do backend (`{{product_name}}`, `{{price}}`, `{{link}}`…), origem da foto, prévia com produto real de exemplo. Opcional: oferecer "Sugerir texto" + orientação de estilo; ativo.
- **Entrada:** digitar texto + escolher. **Efeito:** `AnnouncementTemplate`. **Erro:** médio (afeta todos os anúncios futuros).
- **Caminho:** lista → Novo/linha → formulário → salvar. **Mínimo:** nome + texto (foto padrão = do produto).
- **Padrão:** COMPOR / CONFIGURAR.
- **Evidência:** `app/pages/templates.vue`, `app/components/AnnouncementTemplateForm.vue`, `AnnouncementTemplateListView/DetailView`, `campaign.available_variables`.

### M24 · Adaptar texto/formato por plataforma
- **Quem:** gestor. **Onde:** modelo e campanha (composições "Adaptada").
- **Objetivo:** Instagram Story (padrão, exige imagem; texto não sobreposto) × Feed explícito; Google Atualização/Evento (título, início, fim)/Oferta (condições; título/validade/link selados pela promoção); WhatsApp usa o texto aprovado na Meta, não o do modelo.
- **Entrada:** escolher formato + digitar. **Efeito:** `platform_variants` / `publication_format` selado no artefato.
- **Mínimo:** 0 (um texto comum serve todos) — só abre quando precisa.
- **Padrão:** COMPOR.
- **Evidência:** `PlatformCompositionEditor.vue`, `GoogleBusinessPostOptions.vue`, `shopman/shop/services/marketing_capabilities.py`, `marketing_google_post.py`.

### M25 · Apagar modelo
- Mostra campanhas que usam o modelo e bloqueia até trocá-las ("Ver campanhas"); senão confirma. **Padrão:** CORRIGIR. **Evidência:** `templates.vue` (diálogo `removing`), `AnnouncementTemplateDetailView.delete`.

### M26 · Criar oferta automática
- **Quem:** `edit_marketing_campaigns`. **Onde:** V2 Ofertas e cupons → diálogo; desktop.
- **Objetivo real:** um benefício que o carrinho aplica sozinho dentro de uma vigência.
- **Info mínima:** nome para a equipe, tipo (percentual 1-100 / valor fixo / entrega grátis com teto), valor, começa/termina (fuso da loja), produtos/coleções (vazio = catálogo; para campanha precisa ao menos um), avançado: pedido mínimo, limite de usos, canais, entrega/retirada, segmentos.
- **Entrada:** digitar + escolher (selects múltiplos com Ctrl/⌘: hostil a toque). **Efeito:** `Promotion` em transação. **Reversível:** **não pelo app** (sem editar/desativar/excluir; "fora desta superfície"). **Erro:** alto (dinheiro em toda venda do período).
- **Caminho:** ~10 campos. **Mínimo:** tipo + valor + período + alcance.
- **Padrão:** CONFIGURAR.
- **Evidência:** `app/components/MarketingOfferForm.vue`, `useMarketingOffers.ts`, `api/marketing.py` (`MarketingOfferListView`, `_marketing_offer_fields`), `shopman/shop/models/promotion.py`, `shop/services/promotions.py`.

### M27 · Criar cupom
- Igual a M26 mais código (maiúsculas, único, sem espaço) e limite de usos; sempre nasce com `Promotion` própria (excluída das automáticas). Lista mostra código e usos. Sem desativar pelo app. **Padrão:** CONFIGURAR. **Evidência:** idem M26.

### M28 · Criar campanha a partir de uma oferta
- Link "Criar campanha com esta oferta" abre M16 com `offer` pré-selecionada (só se `available_for_campaign`). **Padrão:** COMPOR (atalho). **Evidência:** `MarketingV2Workspace.vue`, `CampaignForm.vue` (`initialPromotionRef`).

### M29 · Saber por onde a padaria consegue falar agora
- **Quem:** gestor. **Onde:** V2 Plataformas (catálogo) + `/platforms?platform=` (detalhe em modal).
- **Gatilho:** antes de montar campanha; aviso de bloqueio; "por que não saiu?".
- **Info mínima:** por plataforma: pronta / limitada / desligada neste ambiente / desconectada / desconhecida + motivo + o que fazer + "sem uso" (nenhuma campanha ativa usa). **Sobra:** formatos com estados (executável/parcial/planejado/bloqueado/não implementado), destinos "planejados" (TikTok) — inventário de engenharia, não decisão do gestor; frases como "allow-list do servidor". **Falta:** nada operacional; só WhatsApp se resolve aqui, as outras dependem de credencial/flag fora do app.
- **Entrada:** ler. **Efeito:** nenhum. **Padrão:** VIGIAR / ENTENDER.
- **Evidência:** `MarketingV2Workspace.vue` (seção platforms), `app/presentation/marketingV2.ts`, `platforms.vue`, `usePlatforms.ts`, `api/marketing.py` `PlatformsView`, `shopman/shop/services/delivery_readiness.py`, `marketing_delivery_runtime.delivery_lanes()`.

### M30 · Escolher o modelo aprovado do WhatsApp para o anúncio
- **Quem:** `configure_marketing_platforms`. **Onde:** detalhe do WhatsApp.
- **Objetivo real:** permitir alcançar quem não falou nas últimas 24 h (só com modelo aprovado pela Meta).
- **Info mínima:** modelo atual, lista buscável de fluxos do ManyChat, aviso "o texto enviado é o da Meta; o modelo entra só com variáveis". **Entrada:** escolher + TOTP (step-up). **Efeito:** `NotificationTemplate(announcement_published).whatsapp_flow_ns`, versionado, recibo; não envia nada. **Erro:** médio.
- **Exceções:** catálogo indisponível → "a última lista conhecida não autoriza mudança"; conflito de versão → reverifica.
- **Caminho:** Plataformas → WhatsApp → escolher → TOTP → confirmar. **Mínimo:** escolher + autorizar.
- **Padrão:** CONFIGURAR + AUTORIZAR.
- **Evidência:** `platforms.vue` (`onChooseTemplate`, `onConfirmTemplate`), `useWhatsAppTemplate.ts` (`configureFlowCommand`), `api/marketing.py` `WhatsAppTemplateView`.

### M31 · Ligar cada aviso automático ao modelo aprovado
- **Quem:** `configure_marketing_platforms`. **Onde:** mesmo detalhe do WhatsApp, seletor "Mensagem".
- **Objetivo real:** que as mensagens **transacionais** da loja (pedido recebido/confirmado/pronto/saiu/entregue/cancelado, encomenda, nota fiscal, pagamento solicitado/confirmado/expirado/reembolsado, fila, fidelidade) saiam por modelo aprovado.
- **Achado:** isto não é marketing. É comunicação de pedido/pagamento; mora aqui porque o seletor de fluxo do ManyChat mora aqui. O dono de pedidos/loja não procuraria no Marketing.
- **Entrada:** escolher aviso + escolher modelo + TOTP. **Efeito:** `NotificationTemplate(event).whatsapp_flow_ns`. **Erro:** alto (cliente com pedido recebe mensagem errada/vazia).
- **Exceções:** linha do aviso ausente → "aplique as migrações"; a tela admite que não prova campos/botão, pede teste no ManyChat.
- **Padrão:** CONFIGURAR + AUTORIZAR. **Fronteira:** Pedidos/Pagamentos/Fiscal/Fidelidade.
- **Evidência:** `platforms.vue` (`onChooseNotificationTemplate`), `shopman/shop/services/marketing_platform_configuration.py` (`TRANSACTIONAL_WHATSAPP_EVENTS`, `WHATSAPP_EVENT_LABELS`).

### M32 · Verificar de novo o catálogo de modelos
- `GET whatsapp-template/?refresh=1` + recarrega prontidão. 1 toque. Poderia ser automático ao abrir o detalhe quando o catálogo não está fresco (o estado `catalog_fresh_until` já existe). **Padrão:** CONFERIR. **Evidência:** `platforms.vue` `onVerifyCatalog`, `manychat_flows.flow_catalog`.

### M33 · Enviar teste seguro
- **Quem:** `send_marketing_test`. **Onde:** detalhe do WhatsApp; o gestor com o celular de teste na mão.
- **Objetivo:** ver a mensagem real chegar antes de abrir para clientes.
- **Info mínima:** mensagem a testar (aviso), número verificado (lista por ref, sem PII), produto de exemplo; recibo e campos enviados (vazios explicitados). **Entrada:** escolher 3 de listas + Enviar. **Efeito:** 1 mensagem, `MarketingTestReceipt`, throttle. **Erro:** baixo.
- **Exceções:** sem alvos → "peça ao responsável" (alvos vivem em `SHOPMAN_MARKETING_TEST_TARGETS_JSON`, env); aviso inativo/sem modelo bloqueia.
- **Caminho:** 4 toques. **Mínimo:** 1 (testar o modelo recém-escolhido com o alvo padrão).
- **Padrão:** CONFERIR.
- **Evidência:** `platforms.vue` (`onSendTest`), `useWhatsAppTemplate.sendTest`, `WhatsAppTestSendView`, `campaign.send_test`.

### M34 · Consultar o histórico
- **Quem:** gestor. **Onde:** `/history`; desktop.
- **Gatilho:** "saiu ou não saiu?", cliente comentou, revisar recusas. **Info mínima:** assunto (evento · produto), quando, situação de entrega, quem decidiu (pessoa × automático), ações de recuperação disponíveis. Filtros: situação, plataforma, criado em, origem da decisão; cursor paginado.
- **Falta:** resultado de negócio (cliques/vendas atribuídas) — não existe; o histórico é de entrega, não de efeito.
- **Padrão:** LOCALIZAR / ENTENDER.
- **Evidência:** `app/pages/history.vue`, `useCampaignHistory.ts`, `presentation/marketingHistory.ts`, `CampaignHistoryV2View`.

### M35 · Dar "Visto" a um alerta / abrir pelo sino
- Painel do sino: alertas com estado (Novo/Visto/Resolvido/Expirado), prazo, "Revisar" (deep link validado), "Visto" (acknowledge). SSE invalida; fetch é a verdade. Resolvido automaticamente quando o anúncio é decidido. **Padrão:** AVISAR (ack). **Achado:** quase todo alerta é "anúncio para revisar", que é a mesma lista de M01; o sino duplica a fila de Hoje.
- **Evidência:** `MarketingNotificationsBell.vue`, `useMarketingNotificationInbox.ts`, `user_notifications.py`.

### M36 · Recuperar o rascunho local
- Rascunhos de anúncio, campanha e modelo persistem por dono de sessão; ao reabrir com versão do servidor diferente, `DraftRecoveryNotice` mostra conflitos campo a campo em frase (manter meu / manter servidor / descartar). Reautenticação devolve ao mesmo editor. **Padrão:** CORRIGIR. **Evidência:** `DraftRecoveryNotice.vue`, `useMarketingDraft.ts`, `utils/marketingDraft.ts`, `utils/marketingSession.ts`.

### M37 · Congelar/descongelar todo efeito externo
- **Quem:** `freeze_marketing`. **Onde:** **nenhuma tela** (Nuxt e Admin não chamam `security/freeze|unfreeze/`).
- **Gatilho:** texto errado saindo, token comprometido, incidente. **Urgência:** segundos.
- **Mínimo:** 1 interruptor com confirmação, visível de qualquer tela do app (e estado "congelado" visível).
- **Padrão:** CORRIGIR (emergência). **Lacuna.**
- **Evidência:** `api/marketing.py` (`MarketingFreezeView`, `MarketingUnfreezeView`), `shopman/shop/services/marketing_security.py`.

### M38 · Ajustar a cerimônia e o mínimo do WhatsApp
- Cinco ajustes (percentual, teto de gasto, custo por mensagem, piso, múltiplo) e o mínimo de público, em `Shop.defaults["marketing"]`, no Admin (Loja → Integrações), com a base viva ao lado. Fora do app, coerente (é política, não operação). **Padrão:** CONFIGURAR. **Evidência:** contrato §"Projeção e comandos", `marketing_ceremony.py`.

---

## 3. Padrões deste app

1. **Um trabalho central, muitas portas.** M01 (Hoje), M02 (push), M35 (sino), a navegação pós-M20 e a linha do histórico levam todas à mesma coisa: *a fila de anúncios esperando o meu sim*. O app não tem essa fila como objeto (Hoje corta em 4; o board antigo `MarketingBoard` só sobrevive em teste visual; "Abrir revisão" volta para a mesma tela). Forma que a função pede: **uma fila de decisões ordenada por prazo**, que é ao mesmo tempo Hoje, sino e push.
2. **Decidir = 4 micro-escolhas + 1 selo.** M03-M08 são campos da mesma decisão (texto, foto, onde, quando); M09 é o selo. O desenho atual acerta em ter um único botão "Continuar" e verbo do destino no selo. Rótulo novo proposto: **SELAR**, a confirmação cujo atrito mede o irreversível (pessoas que recebem mensagem), e não a importância. Serve também a M12/M14/M30/M31.
3. **Disparo manual é dupla cerimônia para a mesma pessoa.** M20 → M03 → M09: quem define o público é quem revisa e quem sela. O backend já tem o caminho "autor = aprovador" (`fire_now(body=…)`), a UI não usa. Mínimo: definir público → ver o anúncio pronto → selar, numa tela só.
4. **O sistema faz o operador pedir o que é só leitura.** Reconciliar `unknown` (M13) e reverificar o catálogo (M32) são consultas sem efeito; poderiam ser automáticas, com a tela só mostrando o resultado. Repetir falha repetível (M12) já tem fila própria para `subscriber_busy`.
5. **A informação da decisão mora em outro lugar.** O filtro do evento (M21: qual produto, qual qualidade) decide se a máquina automática dispara e só existe no Admin; a troca de foto (M06) depende do modelo e a revisão não oferece; o prazo de cada pendente não aparece em Hoje; as falhas de entrega não aparecem em Hoje.
6. **Botões que existem no servidor e não existem na mão.** Reagendar (M15), congelar (M37), duplo controle (M09: "peça a outra pessoa" sem nenhum meio de pedir), editar/desativar oferta e cupom (M26/M27). O último é o mais caro: um desconto errado roda até o fim da vigência.
7. **Fronteira trocada.** M31 (avisos de pedido/pagamento/fila/fidelidade) é configuração de comunicação transacional da loja, abrigada no Marketing por acidente técnico (o seletor de fluxo do ManyChat). O mesmo trabalho que M30 com outro alvo: um único "ligar mensagem ↔ modelo aprovado", que deveria morar com quem é dono da mensagem.
8. **Configurar × operar estão no mesmo andar.** M16, M21-M27, M29-M33 são raros, de desktop, de dias; M01-M14 e M18 são diários, de celular, de minutos. A barra superior (Hoje · Campanhas · Ofertas · Plataformas) dá peso igual a uma coisa que se faz 10×/dia e a três que se fazem por mês.
9. **Tela explica o sistema em vez de servir a decisão.** Contadores ("sem somar pessoas com postagens"), estados de formato (planejado/bloqueado/não implementado), destinos planejados (TikTok), textos sobre "allow-list", "Actions", "V2", "canônicos". É linguagem de quem construiu, não de quem decide.
10. **Interruptor é um padrão próprio.** M18 (campanha), M37 (congelar), "Ativo" no modelo, aviso transacional ativo: ligar/desligar algo que age sozinho. Proposta de rótulo: **INTERRUPTOR** (CONFIGURAR de 1 toque, reversível, com efeito imediato no mundo).

---

## 4. Cobertura (telas e estados)

| Rota / estado | O que é | Dispositivo certo | Por quê |
|---|---|---|---|
| `/` | redireciona 301 para `/v2?area=today` | — | sem conteúdo |
| `/v2?area=today` | Hoje: contadores, 4 pendentes, conexões com atenção, link histórico | **celular** | é a fila de decisões; pergunta de relance |
| `/v2?area=today` erro de board / dados não frescos | alerta | celular | idem |
| `/v2?area=campaigns` | destinos ativos + 5 campanhas + Nova campanha + Modelos | desktop | configuração |
| `/v2?area=offers` | lista de ofertas/cupons, Criar oferta/cupom, criar campanha com oferta | desktop | configuração com muitos campos |
| diálogo Criar oferta / Criar cupom (`MarketingOfferForm`) | formulário com selects múltiplos | desktop | Ctrl/⌘ multi-select não funciona em toque |
| `/v2?area=platforms` | catálogo de destinos com estado e formatos, planejados | desktop | diagnóstico raro |
| `/campaigns` | lista com busca, filtros, paginação, liga/desliga, editar, preparar disparo | desktop (lista); **celular** para o interruptor | ligar/desligar é gesto de urgência no salão |
| `/campaigns?new=1` / editar → workspace modal `CampaignForm` (etapas 1-5) | compositor | desktop | 5 etapas, muitas escolhas |
| estado rascunho em conflito (`DraftRecoveryNotice`) | em campanha, modelo, anúncio | o do formulário | — |
| `FireCampaignPanel` ("Definir público") com contagem viva, exclusões, produto | disparo manual | desktop ou tablet | escolhas múltiplas com número ao vivo; celular aceitável |
| erros do disparo (409, 429, contagem falhou, zero) | estados | idem | — |
| `/templates` lista / vazio | modelos | desktop | redação |
| workspace modal `AnnouncementTemplateForm` + `PlatformCompositionEditor` + `GoogleBusinessPostOptions` + prévia | edição de modelo | desktop | escrever texto longo e conferir prévias |
| diálogo Apagar modelo (em uso / livre) | confirmação | desktop | — |
| `/announcements/:id` → `AnnouncementCard` (pendente) | revisão | **celular** | chega por push; decisão de minutos |
| idem: prévia simulada por plataforma (`AnnouncementPreview`, `AnnouncementSimulatedPreview` em tamanho real) | conferência | celular | é como o cliente vê |
| idem: bloco sugestão de IA | comparação | celular | — |
| idem: silêncio do WhatsApp / ensaio local / horário ambíguo | estados do "quando" | celular | — |
| idem: prazo vencido | sem ação ("prepare um disparo novo") | celular | — |
| diálogo Recusar (motivo) | negativo | celular | — |
| `MarketingCommandConfirmationDialog` (resumo / frase `ENVIAR N` / senha / TOTP / duplo controle / reautenticação) | selo | **celular** | último passo da decisão |
| `/announcements/:id` → faixa de resultado da decisão + `AnnouncementResultPanel` (acompanhamento com espera crescente, por plataforma) | entrega | celular (acompanhar), desktop (investigar) | — |
| diálogo de recuperação (Repetir falhas / Consultar incerto / Cancelar com motivo, com desafio) | correção | desktop | raro, exige leitura cuidadosa |
| `/announcements/:id` erro de carga / não encontrado | estado | — | — |
| `/campaign/announcements/:id` | alias que redireciona | — | links antigos de notificação |
| `/history` (filtros, lista, vazio, erro parcial, carregar mais) | histórico | desktop | consulta e auditoria |
| `/platforms` sem plataforma | redireciona para `/v2?area=platforms` | — | — |
| `/platforms?platform=whatsapp` modal: estado, modelo aprovado (busca), avisos automáticos, teste seguro, recibo e campos | configuração WhatsApp | desktop (+ celular de teste na mão) | raro, com TOTP |
| `/platforms?platform=instagram|facebook|google_business` modal | estado e motivo, sem ação | desktop | nada se resolve aqui |
| diálogo confirmar modelo (TOTP) | selo de configuração | desktop | — |
| Sino (painel) com Novo/Visto/Resolvido/Expirado, Revisar, Visto, carregar mais | alertas | **celular** | é o canal do push |
| `error.vue` | erro global | qualquer | — |
| `/health/live`, `/health/ready`, `/sse/notifications`, `/api/v1/**` (BFF) | infraestrutura | — | não é tela |
| `visual/VisualBoardPage.vue` (`MarketingBoard`) | só teste visual; board antigo da fila | — | sobra de código; a fila que ele mostrava não tem mais casa |
| (sem tela) reagendar, congelar, duplo controle solicitado, editar/desativar oferta e cupom, filtro do evento, `notify_users` | lacunas | ver fichas | — |
