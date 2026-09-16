# Extração segura do #614 — L7-A e pendências factuais L1

Data: 15/09/2026. Base: `origin/main` em `8e764de70`. Escopo: leitura e código
passivo fora de produção. Nenhum deploy, expurgo, job, migration, cadastro ou
aceite contratual foi executado.

## Contraexemplo que impede o merge monolítico

O #614 afirmava que nenhum expurgo/job seria ativado, mas adicionava
`purge_consent_ip` a `MAINTENANCE_COMMANDS`. Um simples deploy faria o worker
executar `UPDATE` destrutivo em IPs de consentimento com mais de 90 dias. Isso
contraria o gate humano já registrado.

Esta extração não traz o comando, o serviço de mutação nem a entrada no worker.
O único comando novo, `data_retention`, faz inventário por contagens; `--apply`
falha antes das consultas. O #614 permanece congelado como fonte, não como
candidato de merge integral.

## Fechamento da revisão independente

A revisão adversarial encontrou e esta extração corrigiu cinco riscos antes da
publicação do branch: R01 passou a usar o timestamp do estado terminal, e não a
criação do pedido; o corte de cinco anos passou a seguir anos de calendário;
R03, R04, R09 e R13 permanecem inventários com zero candidatos enquanto faltam
marcos canônicos; R05 também permanece inventário com zero candidatos enquanto
seu relógio ainda nasce antes do encerramento; R06 preserva recibos ligados a
destinos não reconciliados; e aceite do provedor no concierge não é tratado
como entrega final. Testes de regressão cobrem cada um desses limites sem
qualquer mutação.

## L1: pacote finito por fornecedor

Pessoa jurídica canônica: **N. H. K. Panificadora LTDA — CNPJ
02.119.381/0001-58**. Para fechar L1, cada fornecedor ativo precisa de cinco
artefatos versionados: perfil/fatura da PJ; contrato/ToS e data de aceite; DPA;
subprocessadores e locais; nota `dados → finalidade → prazo → papel → mecanismo
ANPD → contato de incidente`.

| Fornecedor | Evidência ou falta concreta | Responsável pela próxima prova |
|---|---|---|
| DigitalOcean | região `nyc`; guardar billing/fatura da PJ, [DPA](https://www.digitalocean.com/legal/data-processing-agreement) e [subprocessadores](https://www.digitalocean.com/trust/subprocessors), além do mecanismo ANPD para EUA | Pablo coleta; suporte/jurídico completa mecanismo |
| Anthropic | guardar Organization/Billing da PJ, aceite/DPA, subprocessadores/locais e confirmar retenção/ZDR sem presumir | Pablo + suporte Anthropic |
| ManyChat | divergência verificada: “Nome da Empresa: Não especificado”; corrigir PJ/CNPJ somente após confirmação e guardar [DPA](https://manychat.com/legal/dpa)/[prestadores](https://manychat.com/legal/service-providers) | Pablo prepara; representante confirma alteração/aceite |
| Meta | provar Business Portfolio, PJ/CNPJ e propriedade de App/Page/WABA/IG; guardar [termos de tratamento](https://www.facebook.com/legal/terms/dataprocessing) | Pablo/representante; Meta se houver divergência |
| Google Cloud/Maps/Workspace | provar Payments/Billing da PJ, projeto/chave, Workspace corporativo, CDPA e subprocessadores | super-admin/Pablo |
| Stripe | Business details/Tax ID/fatura da PJ, [SSA/DPA](https://stripe.com/legal/dpa), prestadores e mecanismo ANPD | Pablo + Stripe/jurídico |
| Comtele | cadastro/fatura da PJ; solicitar DPA, retenção, subprocessadores e países — a [política pública](https://comtele.com.br/politicas/) não fecha esses fatos | Pablo + suporte Comtele |
| Efí | conta Empresas/CNPJ, termo API Pix/data e papéis LGPD; hoje a integração auditada está em sandbox | Pablo/representante |
| Focus NFe | emitente/contrato/fatura da PJ, terceiros/países e retenção fiscal efetiva | Pablo + contador + Focus |
| iFood | CNPJ, dono da organização/app, vínculo app↔merchant, termos/data e autorização de subprocessadores | Pablo + iFood Developer Support |
| Google Business Profile | pedido da API enviado para o projeto 528240639893; aguardar aprovação e provar branding/escopo `business.manage` sob a PJ | monitor automático; Pablo só se o Google pedir ação |

L1 não bloqueia código passivo, testes ou deploy com integrações desligadas. Ele
bloqueia novas ativações com dados pessoais, publicação de alegações jurídicas
não verificadas e afirmação ampla de conformidade. Sentry, TikTok e outros
fornecedores futuros exigem o mesmo pacote antes da primeira ativação.

Não há nova decisão pendente para L3, L4, L6 ou a política L7/R01–R15. Gates
humanos futuros são específicos: corrigir cadastro/aceitar contrato, autorizar
expurgo produtivo e ativar cada job.
