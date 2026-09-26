# WP-RELEASE-01 — Novas versões dos apps sem quebrar a operação ativa

**Estado:** aberto, pronto para execução  
**Prioridade:** P0 antes do primeiro ambiente de produção com operação real  
**Dono:** Plataforma Shopman  
**Piloto:** Marketing V2  
**Escopo:** nove surfaces Nuxt, `operator-kit`, `operator-router`, Django/BFF,
workers, migrations, imagens e promoção alpha → produção

## 1. Objetivo

Permitir que uma nova geração de qualquer app Shopman seja desenvolvida,
validada, publicada para operadores escolhidos e revertida sem interromper nem
corromper a versão estável.

O resultado não é um segundo sistema de deploy. É uma evolução da esteira que já
existe:

```text
worktree/branch
      ↓
PR + gates do componente afetado
      ↓
build único e imutável no main
      ↓
alpha automático + smoke do artefato exato
      ↓
promoção do MESMO digest para produção
      ↓
coorte interna → coorte operacional → padrão
      ↓
aposentadoria explícita da versão anterior
```

As palavras têm significados distintos neste WP:

| Termo | Significado |
| --- | --- |
| **Release ID** | Identificador de uma composição deployável, no formato `YYYYMMDD-HHMM-<shortsha>`. |
| **Build** | Imagem imutável identificada por digest e tag `<componente>-<sha>`. |
| **Versão do app** | Geração de experiência, como Marketing V1/V2. Não é uma versão semântica do monorepo. |
| **Versão da API** | Contrato público (`/api/v1/`). Só muda quando compatibilidade aditiva não resolve. |
| **Release set** | Conjunto exato de digests de `web`, `storefront-nuxt`, `operator-floor` e `operator-office` que compõe um ambiente. |

Não adotar SemVer global. O repositório tem deploy contínuo e componentes com
cadências diferentes; fingir um `2.3.1` único esconderia a composição real.

## 2. Situação atual confirmada

O Shopman já possui peças importantes e elas devem ser preservadas:

- PRs passam por Runtime Gate, Surfaces Gate e gates de Omotenashi/grupos;
- `deploy-images.yml` detecta os componentes alterados desde o último deploy de
  `main` que realmente terminou bem;
- cada build publica tag móvel e tag imutável por SHA;
- o manifesto do run registra digest por componente;
- o drift gate confronta o registry com o `main`;
- `alpha-smoke.yml` espera o deployment correspondente pelo digest, sem aprovar
  a versão anterior por engano;
- as surfaces são registradas em `surfaces/registry.json`;
- os apps de operador rodam em `operator-floor` e `operator-office`, conforme a
  ADR-030;
- schema pós-go-live segue migrations append-only e expand-contract, conforme a
  ADR-015.

O gap é de promoção e convivência segura:

1. Hoje, publicar a tag móvel é o deploy do alpha. Construir e lançar ainda são
   o mesmo gesto.
2. Não existe promoção formal do **mesmo digest já testado** para produção.
3. Não existe um release set durável dizendo exatamente o que estava ativo em
   cada ambiente e qual conjunto deve voltar num rollback.
4. Uma V2 pode nascer numa rota, mas ainda falta contrato comum para coorte,
   aderência de sessão, kill switch, métricas comparativas e data de retirada.
5. O smoke vivo cobre profundamente a loja, mas não prova uma jornada mínima de
   cada app de operador.
6. Como cinco apps compartilham `operator-floor` e três compartilham
   `operator-office`, uma mudança em um app reinicia os irmãos do grupo. A
   estratégia precisa reconhecer esse raio de explosão, não fingir isolamento.

## 3. Decisões deste WP

### D1 — construir uma vez, promover sem reconstruir

O artefato que passou no alpha é o artefato que chega à produção. Promoção deve
retaggear o manifest OCI/digest já existente; nunca rodar outro `docker build`
para “a mesma” versão.

Para cada componente publicado:

```text
<componente>-<sha>  ── digest imutável, candidato
<componente>        ── alias móvel atual do alpha, durante a transição
<componente>-prod   ── alias móvel de produção, atualizado só por promoção
```

O nome final das tags pode mudar na implementação, mas a separação
candidato/alpha/produção é obrigatória.

### D2 — `main` produz candidato; produção exige promoção explícita

- Merge em `main` continua implantando automaticamente no alpha.
- Produção não acompanha `main` automaticamente.
- Produção recebe uma promoção de release já verde no alpha, por workflow com
  GitHub Environment protegido e aprovação do responsável.
- Uma correção urgente segue o mesmo caminho, apenas com gates e janela
  proporcionais ao risco; “urgente” não autoriza rebuild diferente.

### D3 — uma V2 de interface nasce dentro da surface existente por padrão

Redesign ou fluxo novo usa o mesmo app Nuxt, os mesmos contratos canônicos e uma
rota/árvore de componentes separada enquanto estiver em prova. Isso permite
trocar V1/V2 por coorte sem duplicar infraestrutura, autenticação ou regra de
negócio.

Criar uma segunda surface/processo só é permitido quando houver incompatibilidade
técnica comprovada — por exemplo, troca de runtime que não pode coexistir — e
exige ADR, custo medido e data para apagar a duplicação.

### D4 — versão de UX não cria versão de regra de negócio

- V1 e V2 consomem Projection/Action/Intent/Mutation canônicos.
- Campo novo de API é aditivo e opcional durante a convivência.
- Nenhuma V2 replica pricing, disponibilidade, permissão, lifecycle ou side
  effect no frontend.
- `/api/v2/` não nasce só porque a tela se chama V2. Nova versão de API exige
  contrato realmente incompatível e plano de migração de consumidores.

### D5 — seleção da versão é server-side, aderente e reversível

A versão exibida é resolvida no servidor/BFF por esta precedência:

1. kill switch global;
2. ambiente;
3. loja/tenant;
4. allow-list de operador/persona;
5. percentual estável por identidade, somente quando houver população suficiente;
6. versão padrão.

O resultado fica aderente à sessão. Atualizar a página não pode alternar V1/V2.
Query string secreta, cookie editável como autorização ou `if DEBUG` não são
controle de rollout.

Para a operação atual, coortes nomeadas são melhores que “5%”:

- `internal`: autores e QA;
- `pilot`: operadores escolhidos e treinados;
- `default`: todos;
- `off`: ninguém.

O mecanismo deve reutilizar `RuleConfig`/configuração canônica quando ela
atender ao contrato. Não criar um control plane paralelo sem provar o gap.

### D6 — shadow compara leitura; escrita tem um único executor

Durante dark launch, a nova Projection pode ser calculada e comparada com a
antiga, sem ser exibida. Não duplicar mutações nem chamadas externas.

Para pagamento, estoque, impressão, notificações e publicação em plataformas:

- exatamente um caminho executa o efeito;
- idempotency key é obrigatória quando o contrato permitir retry;
- outbox/directive/receipt existente continua sendo a fonte da verdade;
- shadow registra intenção e diferença, nunca chama o provedor real;
- desligar a V2 não apaga fila, receipt ou efeito que já pode ter sido aceito.

### D7 — rollback da experiência e rollback do artefato são gestos distintos

1. **Rollback lógico:** kill switch volta a V1 sem deploy. É a primeira reação
   para regressão exclusiva da V2.
2. **Rollback de componente:** promove os digests do release set anterior, sem
   rebuild.
3. **Rollback de dados:** último recurso, seguindo ADR-015 e o runbook de
   backup/restore. Migration destrutiva nunca é “desfeita” automaticamente sob
   tráfego.

## 4. Invariantes não negociáveis

1. O checkout principal nunca é área de escrita; uma frente = worktree = branch
   = PR.
2. Produção só recebe digest que esteve ativo e verde no alpha.
3. O release manifest é condição de promoção; ausência ou digest ilegível falha
   fechado.
4. V1 continua funcionando com backend novo durante toda a janela de canário.
5. Mudança de schema segue expand → backfill → migrate → contract em releases
   distintas.
6. Contract só entra depois de provar que o release anterior não precisa mais do
   dado removido.
7. Feature flag nasce `off`, tem kill switch sem deploy, dono e data de remoção.
8. Rota V2 operacional exige autenticação e as mesmas permissões da V1. Preview
   estática não concede capacidade de escrita.
9. Service worker/cache inclui identidade de build; HTML nunca fica preso num
   precache que sobreviva ao rollback.
10. Mudança no `operator-kit` prova os oito apps; mudança no router prova os dois
    grupos.
11. Alterar um app de `operator-floor` publica o grupo inteiro e precisa provar
    reconexão de SSE e continuidade de PDV/KDS.
12. Config, secret e spec vivo não são derivados cegamente do YAML versionado;
    vale a regra atual de preservar `EV[...]` e usar `doctl apps propose` antes
    de update.
13. Não existe deploy “verde” sem provar qual digest está no ar.
14. Toda versão paralela tem prazo de retirada. V1/V2 permanente é dívida, não
    estratégia.

## 5. Matriz de risco e caminho obrigatório

| Classe de mudança | Exemplo | Caminho mínimo | Rollback primário |
| --- | --- | --- | --- |
| UI local | layout, copy, fluxo sem contrato novo | gates da surface → alpha → coorte | flag V1/V2 |
| Projection/API aditiva | campo ou Action nova | backend compatível primeiro → V2 depois | V1 continua lendo contrato antigo |
| Mutation/efeito externo | publicar, cobrar, imprimir, baixar estoque | idempotência + receipt/outbox + canário nominal | kill switch + reconciliação |
| Schema expand/backfill | campo/índice/dado novo | ADR-015 + staging com dado representativo | código anterior; coluna fica órfã |
| Schema contract | remoção/rename destrutivo | release separado, backup declarado, prova de desuso | restore; nunca rollback automático |
| Dependência/runtime | Nuxt, Vue, Python, base image | uma surface/grupo por vez, build e browser matrix | digest anterior |
| `operator-kit`/router | token, auth, BFF, segurança, roteamento | todos os consumers + boot dos dois grupos | digests dos dois grupos |
| Config/secret/topologia | env, domínio, service, tamanho | diff do spec vivo + propose + revisão humana | spec vivo anterior preservado |

## 6. Fases de execução

Cada fase é um PR próprio. Não juntar infraestrutura de promoção, roteamento de
versão e piloto funcional num PR gigante.

### Fase R0 — contrato e inventário executável

**Entregas**

- `docs/reference/release-contract.md` com nomenclatura, estados e schema do
  release manifest;
- inventário gerado a partir de `surfaces/registry.json`, grupos e componentes
  de deploy — sem segunda lista manual;
- classificação automática do risco do diff, com saída legível no PR;
- decisão documentada de onde vivem coortes/flags e quem pode alterá-las;
- ADR para build-once/promote e convivência V1/V2.

**Gate de aceite**

- O inventário enumera exatamente `web`, `storefront-nuxt`, `operator-floor` e
  `operator-office`, além das surfaces contidas em cada grupo.
- Um teste quebra se registry, grupos e deploy divergirem.
- O PR declara os componentes e a classe de risco afetados.

### Fase R1 — identidade observável da release

**Entregas**

- `SHOPMAN_RELEASE_ID` e `SHOPMAN_BUILD_SHA` injetados no build, nunca secretos;
- endpoint barato de versão em Django e em cada Nitro, separado de liveness e
  readiness;
- header/diagnóstico de release que permita ao suporte identificar o artefato
  servido sem abrir o painel da nuvem;
- release manifest com, no mínimo:

```json
{
  "release_id": "20260926-1803-6682bbe",
  "git_sha": "6682bbe...",
  "source_run": 36260743089,
  "components": {
    "web": {"digest": "sha256:...", "immutable_tag": "web-6682bbe..."},
    "storefront-nuxt": {"digest": "sha256:..."},
    "operator-floor": {"digest": "sha256:..."},
    "operator-office": {"digest": "sha256:..."}
  },
  "migration_graph_hash": "..."
}
```

- todo valor da resposta vem do build/env; nenhum endpoint consulta GitHub ou
  DigitalOcean em request de usuário.

**Gate de aceite**

- Um smoke prova SHA/release esperados, não apenas HTTP 200.
- O manifest referencia somente digests imutáveis existentes no registry.
- Não há segredo, nome de token ou configuração sensível na resposta.

### Fase R2 — separar candidato, alpha e produção

**Entregas**

- evoluir `deploy-images.yml` para sempre produzir candidato imutável e o
  manifesto completo do release set;
- manter alpha contínuo com os mecanismos atuais de digest, drift e smoke;
- criar workflow `promote-release.yml`, manual e protegido, que:
  1. recebe um Release ID verde;
  2. valida ancestralidade e presença dos digests;
  3. retaggeia os mesmos manifests para as tags de produção;
  4. registra GitHub Deployment/Release;
  5. espera o deployment correto pelo digest;
  6. roda smoke de produção;
- produção usa tags próprias e nunca `deploy_on_push` das tags do alpha;
- o spec vivo é migrado com `propose`, preservando secrets, antes de habilitar
  qualquer tag nova.

**Gate de aceite**

- Digest no alpha = digest promovido para produção.
- Rebuild no workflow de promoção é tecnicamente impossível.
- Promoção com manifest ausente, componente faltando ou smoke vermelho para.
- Push comum em `main` não altera produção.

### Fase R3 — release set e rollback reproduzível

**Entregas**

- armazenamento durável do manifest de cada promoção de produção;
- workflow `rollback-release.yml` recebe Release ID anterior e reaponta todas as
  tags/componentes afetados para os digests registrados;
- dry-run obrigatório mostra exatamente o que mudará;
- proteção contra rollback de código incompatível com migration contract já
  aplicada;
- atualização de `docs/runbooks/rollback-de-deploy.md` com três níveis:
  flag, componente e dados.

**Gate de aceite**

- Drill em alpha reverte para o release anterior sem build.
- Depois do rollback, endpoint de versão e registry exibem os digests esperados.
- Recovery time medido e registrado: meta ≤ 2 min para flag e ≤ 10 min para
  rollback de componente, sem contar restore de banco.

### Fase R4 — framework comum de convivência V1/V2

**Entregas**

- resolver server-side de variante, reutilizável por todas as surfaces;
- coortes `off/internal/pilot/default`, aderência de sessão e kill switch;
- telemetria com `app`, `variant`, `release_id`, rota e resultado, sem PII;
- contrato de cache/PWA que elimina HTML velho depois de promoção/rollback;
- helper de navegação que preserva a variante sem expô-la como autorização;
- guardrail: toda flag de versão exige dono, justificativa e
  `remove_after=YYYY-MM-DD`.

**Gate de aceite**

- Mesmo operador permanece na mesma variante durante a sessão.
- Operador fora da allow-list não abre V2 por URL direta.
- Kill switch volta todos à V1 sem rebuild nem deploy.
- Expiração vencida reprova a CI, para evitar V1 eterna.

### Fase R5 — smoke e observabilidade por app/grupo

**Entregas**

- smoke autenticado mínimo para cada app de operador;
- para `operator-floor`: login, shell de cada filho, SSE conecta/reconecta e uma
  leitura crítica de PDV/KDS/Pedidos/Produção;
- para `operator-office`: Marketing, B.I. e Compras renderizam e alcançam seus
  BFFs;
- dashboards/alertas por release e variante: taxa de erro, p95, 5xx do BFF,
  restart, backlog de directives, falha de SSE e invariantes de negócio;
- promotion gate com orçamento explícito, não “parece saudável”.

**Critérios iniciais de promoção**

- zero falha de health/readiness/smoke;
- nenhuma regressão estatisticamente relevante de 5xx ou p95;
- nenhum aumento de backlog stuck ou efeito externo `unknown`;
- zero restart inesperado dos grupos;
- uma jornada crítica concluída por app afetado;
- soak mínimo: 24 h no alpha e, para apps do chão, pelo menos um pico operacional
  representativo.

### Fase R6 — piloto Marketing V2

O Marketing V2 valida o mecanismo antes de espalhá-lo para o PDV ou KDS, porque
permite começar sem afetar venda, produção ou pagamento.

**Etapas**

1. Converter a prévia atual em rota autenticada real, usando tokens e
   componentes canônicos do Shopman.
2. V1 permanece padrão; V2 fica `internal` e inicialmente read-only.
3. Ligar shadow somente para projections/capabilities e registrar diferenças.
4. Habilitar um operador piloto.
5. Liberar uma plataforma de baixo risco por vez; escrita usa o pipeline de
   comando/receipt/idempotência já definido pelo Marketing.
6. Acompanhar uma semana operacional ou volume mínimo acordado.
7. Tornar V2 padrão, manter kill switch e V1 por uma janela curta.
8. Remover V1, rota temporária e flag no prazo registrado.

**Gate de aceite**

- Alternar V1/V2 não duplica campanha, publicação ou receipt.
- V2 não amplia allow-list executável de provedor por consequência visual.
- Desligar V2 preserva comandos em voo e reconciliação.
- A versão no ar é identificável pelo Release ID no diagnóstico.
- Retirada da V1 tem PR/data definidos antes de V2 virar padrão.

### Fase R7 — expansão gradual para os demais apps

Ordem recomendada, aumentando a consequência operacional:

1. B.I. e Compras;
2. Gestor de Pedidos e Central;
3. Produção e KDS;
4. PDV;
5. Storefront.

A ordem pode mudar por demanda, mas cada adoção registra:

- jornada crítica;
- coorte piloto;
- efeito externo possível;
- métrica de sucesso;
- rollback lógico;
- release set anterior;
- data de remoção da versão velha.

## 7. Arquivos previstos — não editar todos no primeiro PR

| Área | Arquivos prováveis |
| --- | --- |
| Contrato | `docs/reference/release-contract.md`, nova ADR, este WP |
| Build/deploy | `.github/workflows/deploy-images.yml`, `alpha-smoke.yml`, novos `promote-release.yml` e `rollback-release.yml` |
| Automação | `scripts/release_manifest.py`, `scripts/promote_release.py`, `scripts/check_release_compatibility.py` |
| Registro | `surfaces/registry.json`, `scripts/deploy_components.py` sem listas paralelas |
| Runtime | endpoint de versão no Django, `operator-kit` e storefront |
| Rollout | config canônica + helper de variante nas surfaces |
| Operação | `docs/runbooks/rollback-de-deploy.md`, novo runbook de promoção |
| Piloto | `surfaces/marketing-nuxt/` e contratos já existentes do Marketing |

Esses nomes são direção, não autorização para um executor atravessar todas as
áreas. Cada fase assume somente seus arquivos e repete a checagem de
sobreposição com PRs/worktrees ativos.

## 8. Testes e drills obrigatórios

1. Manifest criado a partir de build seletivo e de build completo.
2. Run intermediário cancelado não perde componente no release seguinte.
3. Promoção retaggeia o mesmo digest e não executa Docker build.
4. Deployment anterior não pode satisfazer o smoke do atual.
5. Rollback recompõe o release set anterior, inclusive os dois grupos.
6. V1 funciona contra backend já expandido para V2.
7. V2 indisponível para identidade fora da coorte.
8. Kill switch funciona durante sessão ativa.
9. SSE reconecta após troca de `operator-floor`.
10. Service worker não restaura HTML da release quebrada.
11. Side effect não duplica em retry, troca de variante ou rollback.
12. Migration contract bloqueia rollback incompatível.
13. Spec change usa snapshot vivo/propose e preserva secrets.
14. Smoke falho bloqueia promoção e deixa alpha/produção identificáveis.

## 9. Fora de escopo

- Kubernetes, service mesh ou plataforma nova de containers.
- Microfrontend por princípio.
- Duplicar banco por versão do app.
- Feature flag SaaS antes de provar insuficiência de `RuleConfig`/config atual.
- Blue/green de banco com escrita simultânea.
- Refazer os gates existentes que já provam build, drift e digest.
- Versionar API só para combinar o número visual da tela.
- Manter V1 indefinidamente “por segurança”.

## 10. Definição de pronto do WP completo

- [ ] Merge em `main` implanta alpha, mas não produção.
- [ ] Produção recebe somente promoção de digest previamente verde no alpha.
- [ ] Cada ambiente informa Release ID, SHA e digests ativos.
- [ ] Release set anterior é recuperável por um workflow sem rebuild.
- [ ] Coorte e kill switch funcionam sem deploy.
- [ ] V1 e V2 convivem sobre contratos compatíveis e uma única fonte de regra.
- [ ] Gates reconhecem o raio de explosão dos dois grupos de operador.
- [ ] Smokes cobrem jornada mínima dos nove apps, não apenas liveness.
- [ ] Marketing V2 concluiu dark launch, piloto, default e retirada de V1.
- [ ] Um drill documentado prova promoção e rollback ponta a ponta no alpha.
- [ ] Runbooks, ADRs e contratos refletem o mecanismo real.

## 11. Referências obrigatórias para cada executor

- [`CLAUDE.md`](../../CLAUDE.md)
- [`deploy-images.yml`](../../.github/workflows/deploy-images.yml)
- [`alpha-smoke.yml`](../../.github/workflows/alpha-smoke.yml)
- [`scripts/deploy_components.py`](../../scripts/deploy_components.py)
- [`ADR-015`](../decisions/adr-015-backward-compat-policy-post-prod.md)
- [`ADR-030`](../decisions/adr-030-operator-nuxt-dois-servicos.md)
- [`production-upgrades.md`](../guides/production-upgrades.md)
- [`rollback-de-deploy.md`](../runbooks/rollback-de-deploy.md)
- [`surfaces/registry.json`](../../surfaces/registry.json)
- [`headless-surface-contract.md`](../reference/headless-surface-contract.md)
- [`marketing-surface-contract.md`](../reference/marketing-surface-contract.md)

## 12. Primeiro próximo passo

Executar somente a **Fase R0**. Ela fecha o contrato e mede os pontos de
integração antes de qualquer alteração no mecanismo que hoje mantém o alpha no
ar. R1–R7 só começam depois que a ADR de build-once/promote e o schema do release
manifest forem revisados.
