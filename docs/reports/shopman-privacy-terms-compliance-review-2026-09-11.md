# Revisão técnica de privacidade, termos e práticas do Shopman — 2026-09-11

## Conclusão executiva

Esta revisão encontrou e corrigiu inconformidades técnicas reais: política
desatualizada, identidade incompleta da loja, retenção indefinida de IP em provas
de consentimento, exportação truncada, exclusão de conta que deixava dados em
extensões, falha parcial reportada como sucesso, ausência de versão legal no
pedido e marketing direto para menores conhecidos.

O resultado reduz materialmente o risco e torna as promessas públicas
verificáveis no código. **Ele não permite afirmar que “nenhuma prática do
Shopman está fora da lei”.** Conformidade também depende de fatos que o
repositório não prova: contratos com operadores, países e mecanismos de
transferência, dados cadastrais reais, enquadramento empresarial, rotina humana
de incidentes, atendimento de cancelamentos e prática diária da equipe. Esses
itens estão registrados abaixo como gates de publicação, não como ressalva
genérica.

Não houve deploy, alteração de dados de clientes nem escrita em produção nesta
revisão.

## Escopo e método

Foram examinados o storefront e checkout, conta do cliente, exportação e
exclusão, consentimentos, audiências e entregas de Marketing, concierge com IA,
pagamentos, fiscal, autenticação, observabilidade, infraestrutura declarada e o
OAuth do Google Business Profile.

A revisão está empilhada sobre o contrato operacional do Storefront no
[PR #612](https://github.com/nelsonboulangerie/django-shopman/pull/612), que
mantém “Avise-me” ativo até pausa/cancelamento e oferece gestão da assinatura.
Isso evita duplicar ou contradizer a decisão já implementada em outra worktree.

A régua legal foi limitada à LGPD, direitos do titular e segurança; Código de
Defesa do Consumidor e comércio eletrônico; regras da ANPD para incidentes,
agentes de pequeno porte e transferência internacional; e políticas de uso de
dados do Google OAuth/API. Foram usadas fontes oficiais e o comportamento atual
do código foi verificado antes de cada alteração.[^1][^2][^3][^4][^5][^6][^7]

Não foram auditadas integralmente obrigações tributárias, trabalhistas,
sanitárias/rotulagem de alimentos, propriedade intelectual, acessibilidade ou
regulação de pagamentos. Elas exigem frentes e especialistas próprios.

## Matriz de conformidade

| Tema | Exigência | Evidência técnica | Estado |
|---|---|---|---|
| Transparência e finalidade | Informação clara sobre controlador, dados, finalidades, bases, compartilhamento, retenção e direitos (LGPD arts. 6º e 9º) | `privacy.vue` agora identifica a empresa por dados do `Shop`, enumera categorias, bases, fornecedores e direitos | **Corrigido no código; cadastro real precisa de validação humana** |
| Necessidade e minimização | Limitar tratamento ao necessário (LGPD art. 6º III) | OAuth pede apenas `business.manage`; IP bruto de consentimento passa a expirar; conteúdo da IA é delimitado | **Parcialmente atendido; inventário contratual pendente** |
| Consentimento | Prova, finalidade específica e revogação fácil (LGPD art. 8º) | `CommunicationConsent` mantém texto/hash/origem/instante; preferências permitem revogar por canal; audiência falha fechada sem opt-in | **Atendido tecnicamente para Marketing** |
| Crianças e adolescentes | Melhor interesse e requisitos próprios de consentimento/informação (LGPD art. 14) | Audiência promocional exclui idade conhecida menor que 18; política e termos informam participação do responsável | **Mitigado; falta definir age gate/fluxo do responsável para idade desconhecida** |
| Acesso, correção e eliminação | Direitos do titular (LGPD art. 18) | Autoatendimento exporta perfil, contatos, pedidos, consentimentos/histórico, preferências, loyalty, favoritos, alertas e conversas; exclusão alcança extensões e denuncia falha parcial | **Corrigido; auditoria de completude deve acompanhar novos modelos** |
| Retenção | Encerrar/eliminar ao fim do tratamento, salvo hipóteses legais (LGPD arts. 15–16) | Matriz R01–R15 aprovada; dry-run único conta candidatos sem PII; IP auxiliar é limitado a 90 dias; “Avise-me” persiste até pausa/cancelamento | **Política aprovada e observável; contrações e ativação produtiva continuam bloqueadas** |
| Segurança e privacy by design | Medidas desde a concepção (LGPD arts. 46 e 49) | Segredos no servidor, redaction do Sentry, trilhas append-only, permissões, confirmação humana e bloqueios de audiência | **Controles presentes; pentest e governança organizacional fora deste recorte** |
| Incidente | Comunicar ANPD/titulares em três dias úteis quando aplicável e guardar registro por cinco anos | Runbook corrigido com prazo, decisão e retenção; exercício L6 concluído | **Atendido no recorte técnico e operacional exercitado** |
| Contrato eletrônico | Identificação, informação prévia, resumo, correção, confirmação e contrato reproduzível (Decreto 7.962/2013) | Dados legais e links aparecem antes do envio; pedido recebe versão, URL permanente e SHA-256 | **Implementado; falta smoke externo após deploy** |
| Arrependimento/cancelamento | Direito remoto e exercício pelo mesmo meio (CDC art. 49; Decreto arts. 4º–5º) | Cancelamento automático quando seguro e solicitação eletrônica com protocolo nos demais casos | **Implementado e integrado no PR #629** |
| Cláusulas compreensíveis | Consumidor deve conhecer e compreender previamente; cláusula abusiva é nula (CDC arts. 46 e 51) | Texto reescrito em pt-BR direto e sem renúncia de direitos | **Corrigido no código; revisão jurídica final pendente** |
| Transferência internacional | Base legal + mecanismo válido e informação pública clara sobre países, finalidade, duração, agentes, segurança e direitos (Resolução ANPD 19/2024) | Política reconhece processamento internacional e canal de informação | **Bloqueante: inventário/contratos/países exatos não são prováveis pelo código** |
| Google OAuth | Homepage relevante, termos/privacidade públicos, domínio verificado, escopo mínimo e uso limitado | `/shopman-marketing`, `/privacidade`, `/termos`; refresh token protegido; `business.manage`; uso publicitário vedado na política | **Código pronto; atualizar URLs no console apenas após deploy e smoke** |

## Correções implementadas

### Documentos públicos e prova do contrato

- Rotas canônicas em pt-BR: `/privacidade` e `/termos`, preservando `/privacy` e
  `/terms` como aliases.
- Página pública `/shopman-marketing`, relevante para explicar o app OAuth sem
  expor o backstage.
- Razão social, nome fantasia, CNPJ, endereço e contato vêm da projeção real da
  loja em vez de texto fixo.
- Links legais foram adicionados à revisão do checkout e cada pedido passa a
  guardar `terms_version` e `privacy_version`.
- As páginas legais e do Marketing entram no sitemap público.

Arquivos centrais: `surfaces/storefront-nuxt/app/pages/privacy.vue`,
`surfaces/storefront-nuxt/app/pages/terms.vue`,
`surfaces/storefront-nuxt/app/pages/shopman-marketing.vue`,
`shopman/storefront/legal.py`, `shopman/storefront/api/views.py` e
`shopman/storefront/intents/checkout.py`.

### Minimização e direitos do titular

- `SHOPMAN_CONSENT_IP_RETENTION_DAYS` tem default e teto absoluto de 90 dias.
  `purge_consent_ip` remove apenas IP vencido e preserva a evidência essencial.
- A exportação deixou de cortar silenciosamente pedidos em 200 e transações de
  fidelidade em 100. Ela agora cobre contatos, identificadores, identidades
  externas, pedidos, preferências, consentimentos atuais e históricos, timeline,
  insight, conversas visíveis, audiências, loyalty, favoritos, “Avise-me”,
  dispositivos confiáveis e passkeys.
- A exclusão alcança preferências, timeline, fidelidade, tags, conversas,
  audiências e passkeys, além dos dados anteriormente tratados.
- Falhas na limpeza de PII deixaram de ser engolidas: a operação tenta todos os
  alvos, agrega erros e não devolve sucesso falso.

Arquivos centrais: `packages/guestman/shopman/guestman/contrib/consent/service.py`,
`packages/guestman/shopman/guestman/services/customer.py`,
`shopman/shop/services/account.py`, `shopman/storefront/services/account_privacy.py`
e `shopman/storefront/api/account.py`.

### Marketing de menores conhecidos

O consentimento de WhatsApp não é tratado como autorização suficiente para
marketing dirigido a menor. Antes do filtro de opt-in, a audiência exclui qualquer
cliente cuja data cadastrada indique menos de 18 anos e registra
`known_minor` no resumo sem expor PII. A idade desconhecida não é adivinhada;
ela permanece como lacuna de governança a decidir.

Arquivo central: `shopman/shop/services/audience.py`.

### Google Business Profile

O adapter passa a trocar refresh token por access token com cache curto e
falha explícita, preservando a credencial estática somente como fallback de
compatibilidade. Os dados do Google têm finalidade limitada à administração dos
perfis oficiais, em linha com a exigência de escopo mínimo e Limited Use.[^8][^9]

Arquivos centrais: `shopman/shop/adapters/marketing_delivery_google.py`,
`shopman/shop/adapters/marketing_delivery_http.py`, `config/settings.py` e
`docs/reference/marketing-surface-contract.md`.

### Evidência de verificação

- suíte integral Python: **4.357 testes aprovados**, 31 pulados pelos próprios
  marcadores, 31 desmarcados e 10 subtestes aprovados;
- frontend: **61 arquivos e 557 testes aprovados**;
- Ruff: sem achados; typecheck: aprovado; build Nuxt de produção: aprovado;
- ESLint: zero erros e cinco avisos preexistentes de ordem de atributos em um
  componente não alterado (`WhatsappVerifyPanel.vue`);
- `npm audit`: zero vulnerabilidades depois da atualização de Vitest, `js-yaml`
  e SVGO para versões corrigidas;
- Django `check`: aprovado com o aviso esperado de SQLite nas configurações de
  teste; `makemigrations --check --dry-run`: nenhuma migração ausente;
- smoke do build local: HTTP 200 e canonical correto em `/privacidade`,
  `/privacy`, `/termos`, `/terms` e `/shopman-marketing`; sitemap contém as três
  rotas canônicas.

O smoke usou apenas o build local, sem backend de produção. As páginas adotaram
o fallback público da loja como previsto; nenhuma API externa ou dado de cliente
foi acionado.

## Riscos e gates humanos ainda abertos

### Gate L1 — transferência internacional e contratos (bloqueante)

O blueprint declara hospedagem em região `nyc`, e o produto integra serviços
globais como Anthropic, Meta/ManyChat, Google, Stripe, Twilio/Comtele, iFood,
gateway fiscal, SMTP e Sentry quando habilitado. O código não demonstra:

1. qual entidade contratual efetivamente processa cada categoria;
2. todos os países de armazenamento, suporte e subprocessamento;
3. duração e critérios de retenção do fornecedor;
4. cláusulas-padrão da ANPD ou outro mecanismo válido;
5. existência e versão do DPA e subprocessadores.

A Resolução 19 exige mais do que escrever “pode haver transferência”: exige
base/mecanismo e informação pública clara, em português, sobre a operação.[^6]
Antes da publicação final, o responsável deve reunir contratos/DPAs e validar a
matriz `dado → fornecedor → país → finalidade → prazo → mecanismo → contato`.

### Gate L2 — cancelamento eletrônico pelo mesmo meio

**Implementado e integrado em 2026-09-12 pelo PR
[#629](https://github.com/nelsonboulangerie/django-shopman/pull/629).** A ação
**Solicitar cancelamento** permanece disponível quando o cancelamento automático
já não é seguro, registra protocolo imediatamente e alerta Pedidos para análise.
Ela não altera sozinha estado, pagamento ou estoque e, assim, não promete
cancelamento automático depois do início da produção/entrega.[^3]

### Gate L3 — menores e idade desconhecida

O bloqueio cobre menores conhecidos, mas data de nascimento é opcional e alertas
anônimos usam apenas telefone. O dono deve decidir se a loja:

- exige declaração de maioridade/participação do responsável no cadastro e no
  “Avise-me”; ou
- aceita público menor e implementa consentimento verificável do responsável,
  informação simples e específica e rotina de exclusão própria.

Até essa decisão, não criar campanha deliberadamente infantil nem segmentar
menores; o bloqueio técnico atual deve permanecer.

**Decisão de 2026-09-12:** marketing direto fica restrito a pessoas que declarem
ter 18 anos ou mais. A compra por menor assistido por responsável permanece
possível, mas não cria elegibilidade promocional. Um fluxo futuro de marketing
para menores exigirá participação/autorização verificável do responsável e nova
decisão. A execução técnica desta regra permanece necessária antes do release.

### Gate L4 — identidade e canal de privacidade

Confirmar no banco vivo, sem copiar PII para evidência: razão social, CNPJ,
endereço, telefone, e-mail que realmente recebe pedidos de titular e pessoa
responsável. A dispensa de encarregado para agente de pequeno porte não elimina
o dever de manter canal de comunicação e medidas de segurança.[^5]

**Confirmado em 2026-09-12:** controladora **N. H. K. Panificadora LTDA**, CNPJ
**02.119.381/0001-58**, nome fantasia **Nelson Boulangerie**, endereço **Av.
Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR, 86050-270**, telefone
**(43) 3323-1997** e canal **nelson@boulangerie.com.br**. A projeção viva ainda
tem `legal_name` vazio; o fallback público passa a manter a identificação
completa, sem autorizar escrita corretiva no banco de produção.

### Gate L5 — versão reproduzível

**Implementado nesta revisão; falta somente o smoke após deploy.** Termos e
privacidade têm cópias públicas em URL versionada; o checkout abre essas cópias
diretamente e o pedido grava versão, URL e SHA-256. O gate de CI
`check_legal_archive.py` aceita somente arquivos novos e reprova modificação ou
remoção de uma versão existente. Uma correção futura exige nova data e novo
arquivo. Depois do deploy, o fechamento operacional exige confirmar HTTP 200 e
o mesmo SHA-256 nas duas URLs externas.

### Gate L6 — incidente e operação

Nomear responsável e suplente, cadastrar contatos de fornecedores, testar o
runbook em exercício de mesa e registrar a decisão sobre notificação. A ANPD
fixou três dias úteis para comunicação de incidente com risco ou dano relevante e
cinco anos de retenção dos registros do incidente.[^4]

**Responsáveis confirmados em 2026-09-12:** Pablo Valentini responde pela
operação; Laís Kohatsu Kataoka é suplente e representante da administração.
A nomeação não usa o título de encarregado/DPO. **Exercício concluído em
2026-09-12:** o responsável confirmou congelamento das entregas, preservação de
evidências, proibição de reenvio cego, avaliação de risco em conjunto com a
suplente e desbloqueio somente após reconciliação. A evidência está em
`docs/reports/execution/privacy-incident-tabletop-20260912.md`.

### Gate L7 — tabela de retenção e descarte (bloqueante para promessa integral)

O código possui prazos explícitos para diversas trilhas de Marketing, segurança,
aparelho confiável, incidentes e IP auxiliar. Porém, expirar uma autorização não
é o mesmo que apagar o registro que contém PII. “Avise-me” é uma preferência
persistente até pausa/cancelamento; depois disso, sua prova, as conversas do
concierge e parte das demais provas de consentimento não têm hoje um job universal
de descarte por prazo. A política pública foi escrita para não prometer um limite
inexistente.

Antes de alegar conformidade integral, o controlador e o jurídico devem aprovar
uma tabela por categoria com finalidade, marco inicial, prazo, exceção por litígio
ou obrigação legal e destino final (apagar, anonimizar ou restringir). Depois, cada
prazo deve virar campo/rotina testada e monitorada. Até lá, exclusão de conta cobre
esses dados no autoatendimento, mas isso não substitui o descarte proativo exigido
quando a finalidade termina.[^1]

**Decisão concluída em 2026-09-12:** a matriz R01–R15 foi aprovada como política
operacional inicial em
`docs/governance/data-retention-schedule.md`, com marco, prazo, destino, estado
técnico e registro da aprovação. A autorização cobre implementação e testes
fora de produção. Nenhum expurgo novo foi ativado: descarte do legado produtivo
e ativação dos jobs em produção continuam sujeitos a dry-run, contagens sem PII
e gate humano separado.

**Primeira etapa técnica concluída:** `data_retention --dry-run` devolve
contagens sem PII para as 15 regras, por padrão sem mutação; `--apply` recusa
explicitamente enquanto não houver a implementação destrutiva revisada e o gate
separado. Os testes cobrem a matriz completa, a preservação de um registro
vencido no dry-run e a recusa do apply.

### Gate L8 — alertas de dependência nas demais superfícies

O manifest do Storefront ficou com `npm audit` zerado, mas o Dependabot do
repositório ainda apontava, em 11 de setembro de 2026, **36 alertas abertos no
branch padrão** (15 altos e 21 moderados). Eles repetem as mesmas famílias
`js-yaml`, SVGO e Vitest em BI, Hub, KDS, Pedidos, PDV, Produção e Compras. Cinco
desses alertas pertencem ao Storefront e são fechados por esta branch; os demais
devem ser atualizados nas branches donas de cada superfície para evitar conflito
com trabalhos já em andamento.

Os achados de Vitest e `js-yaml` estão em dependências de desenvolvimento. SVGO
aparece como runtime no inventário do GitHub, embora seja usado pela cadeia de
build; conteúdo SVG não confiável não deve entrar nessa cadeia até todas as
superfícies adotarem a versão corrigida. Este gate não prova exploração ou
ilegalidade, mas impede alegar segurança integral do repositório.

**Correção preparada no PR
[#631](https://github.com/nelsonboulangerie/django-shopman/pull/631):** 31 alertas
das sete superfícies restantes foram tratados em worktree/branch isolados; os
cinco do Storefront permanecem cobertos por este PR. A evidência local registra
sete audits zerados, 1.711 testes, typecheck e build em 7/7 superfícies. O gate
só fecha após CI remoto e nova contagem dos alertas no `main` depois de integrar
ambos os PRs.

## Gate de release proposto

1. Jurídico/dono valida o texto, dados empresariais e tratamento de perecíveis.
2. L1–L8 recebem responsável, evidência e decisão; L1, L7 e L8 impedem a
   alegação de conformidade integral.
3. CI, testes de backend, frontend, typecheck, build e `check --deploy` verdes.
4. Merge autorizado; deploy continua sendo ato separado e explícito.
5. Após deploy, smoke externo confirma 200 e canonical de `/privacidade`,
   `/termos` e `/shopman-marketing`.
6. Só então o Google OAuth troca homepage/política/termos para as URLs novas e
   passa por um consentimento real com a conta corporativa.

## Fontes

[^1]: Presidência da República, [Lei nº 13.709/2018 — LGPD compilada](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm), especialmente arts. 6º–9º, 14–18, 46, 49 e 50.
[^2]: Presidência da República, [Lei nº 8.078/1990 — Código de Defesa do Consumidor](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm), especialmente arts. 46, 49 e 51.
[^3]: Presidência da República, [Decreto nº 7.962/2013 — comércio eletrônico](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/decreto/d7962.htm), especialmente arts. 2º, 4º e 5º.
[^4]: ANPD, [Regulamento de Comunicação de Incidente de Segurança](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-aprova-o-regulamento-de-comunicacao-de-incidente-de-seguranca) e [canal oficial de comunicação](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).
[^5]: ANPD, [Resolução CD/ANPD nº 2/2022 — agentes de tratamento de pequeno porte](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-2-de-27-de-janeiro-de-2022).
[^6]: ANPD, [Resolução CD/ANPD nº 19/2024 — transferência internacional de dados](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024).
[^7]: ANPD, [Direitos dos titulares de dados](https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/direito-dos-titulares).
[^8]: Google for Developers, [OAuth 2.0 production readiness — policy compliance](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance).
[^9]: Google for Developers, [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy) e [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies).
