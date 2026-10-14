# WP-WATCHMAN: saúde, autocura e desempenho que se cuidam sozinhos

> Work package para um agente executar (Claude, Codex, DeepSeek). Leia antes o
> `CLAUDE.md` e `docs/plans/COORDENACAO-GO-LIVE.md` (regras comuns e checklist).
> Aberto pela coordenação em 14/10/2026, a pedido do dono.

## 1. Por que existe

Em 14/10/2026 o `web-operator` do alpha esgotou o pool de conexões com o banco às
15:06 UTC: 36 streams SSE abertos, nenhum fechado. PDV, Cozinha, Gestor e Admin
esperaram 10 s por request e caíram em erro por mais de meia hora, até a
coordenação reiniciar o serviço à mão. Ninguém foi avisado: os alertas da plataforma
(reinício, CPU, memória) não enxergam pool travado.

O dono decidiu: **não haverá webmaster.** O sistema tem de ser saudável por si só,
ao máximo possível, e isso não pode custar desempenho dos apps.

## 2. O que se pede

Um app pip-instalável **`packages/watchman`** (`shopman-watchman`), no mesmo padrão
dos outros pacotes (sem dependência dos outros cores, configurável por settings),
que cuide de três coisas:

1. **Saúde e autocura.** Sondas canônicas (viva, pronta, banco, cache, fila,
   workers), com a regra de ouro: *processo travado se reinicia sozinho; dependência
   fora não vira loop de reinício*. Detectores de travamento por processo: pool de
   banco esgotado com o banco respondendo, event loop ASGI parado, fila de
   directives sem andar, worker sem heartbeat, streams SSE acima do teto.
2. **Segurança de infraestrutura.** O que hoje está espalhado (drift do spec da
   DigitalOcean `scripts/check_do_spec_drift.py`, `production-readiness`, fallbacks
   perigosos, segredos, varredura de rotas de ataque nos logs) vira verificações do
   pacote, com o mesmo formato de resultado.
3. **Desempenho.** Orçamentos declarados por rota (tempo e número de consultas) com
   medição contínua barata (`Server-Timing` e o access log `shopman.access` que já
   existem), e aviso quando um orçamento estoura.

**Escada de resposta, nesta ordem:** curar sozinho (reiniciar o processo pela
liveness, fechar streams órfãos, recusar com 503 rápido em vez de pendurar) →
registrar com evidência → avisar gente só quando a cura não resolveu ou não é
possível (Sentry e e-mail ti@, com trava contra repetição).

**Fora de escopo nesta WP:** um agente de IA que mexe sozinho na produção. Um
vigia agêntico (diagnosticar e abrir PR) pode vir depois, alimentado pelos dados
deste pacote, e nunca aplica nada no vivo sem a palavra do dono.

## 3. Requisitos inegociáveis

- **Robusto.** O vigia nunca derruba o que vigia: toda verificação tem timeout
  curto, falha fechada no próprio resultado, e um erro do watchman não vira erro do
  request. Sem falso positivo que reinicie à toa: limiar com histerese (N falhas em
  T segundos), e banco fora NUNCA falha a liveness.
- **Sem custo de desempenho.** Nada no caminho quente do request além de contadores
  em memória (O(1), sem I/O, sem lock global). Sondas fora do request do usuário.
  Orçamento do próprio watchman medido e escrito no PR: **< 0,5 ms por request** e
  zero consulta extra ao banco por request. Os tetos dos apps não podem piorar
  (Pagamento do PDV ~1,6 s no alpha; projeção do PDV 46 consultas; cardápio sem N+1).
- **Flexível e reaproveitável.** Nada de Nelson, Shopman ou DigitalOcean no núcleo:
  verificações são plugins registrados por settings; o adaptador da DigitalOcean e
  as verificações do Shopman moram em `contrib/`. Um projeto Django novo instala o
  pacote, liga as sondas e ganha a autocura básica.
- **Replicável.** Um comando (`manage.py watchman check`) roda tudo localmente, na
  CI e no vivo, com o mesmo resultado JSON e o mesmo código de saída.

## 4. O que já existe (aproveitar, não duplicar)

- Sondas: `shopman/shop/views/health.py` (`/health/live/`, `/health/database/`,
  `/ready/`, limitador de taxa das sondas, checagem de workers e fila).
- No alpha desde 14/10/2026 (#1713 aplicado): readiness `/health/database/` nos dois
  serviços Django, liveness `/health/live/`, `SHOPMAN_ACCESS_LOG=true`.
  Runbook: `docs/runbooks/web-operator-resiliencia.md`.
- Medição: `shopman/shop/observability.py` (`Server-Timing`, sondas de etapa),
  `AccessLogMiddleware` (`shopman/shop/middleware.py`), testes de contagem de
  consultas (`web/test_catalog_nplus1_measure`).
- Alerta: `shopman/shop/services/critical_alerts.py` (e-mail com trava), Sentry
  (o dono confirma que a regra de alerta existe), alertas da DO (reinício, CPU,
  memória).
- Infraestrutura: `scripts/check_do_spec_drift.py`, `make production-readiness`,
  `scripts/golive_spec_delta.py`, `docs/plans/fallbacks-perigosos-go-live.md`.
- Em voo (14/10): o agente do vazamento de SSE corrige a causa e propõe a liveness
  que falha só com pool travado. **Leia o PR dele antes de começar**
  (`gh pr list --search "SSE"`); o watchman generaliza o mecanismo, não o refaz.

## 5. Ondas

1. **Desenho (sem código, levado ao dono em 1/2 com recomendação).** Contrato do
   plugin de verificação; o que vai para o núcleo e o que vai para `contrib`; como a
   liveness decide; orçamento de desempenho e como medir; nome do pacote (atenção:
   "Watchman" também é o observador de arquivos do Facebook; confirmar que o nome
   no PyPI e no import não colide).
2. **Núcleo + saúde e autocura.** Sondas e detectores, migração das sondas atuais
   para o pacote sem mudar as URLs, testes de esgotamento (liveness falha) e de banco
   fora (liveness não falha), teste de carga com mais streams SSE do que o pool.
3. **Desempenho.** Orçamentos por rota declarados em settings, coleta pelo access
   log, aviso de estouro, relatório diário barato.
4. **Infraestrutura e segurança.** Drift do spec, readiness de produção e fallbacks
   viram verificações do pacote; o comando único `watchman check`.
5. **Documentação de reaproveitamento.** README do pacote com a instalação num
   projeto Django novo do zero, e um exemplo funcionando nos testes.

Cada onda: um branch, um PR, esteira inteira até MERGED. Mudança no spec vivo da
DigitalOcean fica no arquivo `.do/` e o PR escreve o passo para a coordenação
aplicar pelo painel com a palavra do dono. Nunca aplicar no vivo por terminal.

## 6. Critério de aceite

- Simulação do incidente de 14/10 (streams SSE esgotando o pool) **se cura sozinha
  em menos de 2 minutos**, sem humano, provada em teste e no ensaio geral.
- Banco fora do ar não causa reinício em loop (teste).
- Orçamento do watchman medido e dentro do teto (< 0,5 ms por request, zero consulta
  extra), com o antes e depois dos tetos dos apps no PR.
- `watchman check` verde na CI e no alpha.
- Um projeto Django vazio instala o pacote e passa no próprio teste de autocura.
