# Prompt para a sessão dedicada de execução do PDV

Use o texto abaixo na nova sessão. O plano, este prompt e o relatório de auditoria devem estar acessíveis; se ainda não estiverem na branch-base, copie somente esses três documentos para a worktree nova e confira seus hashes. O caminho relativo do plano é normativo; o SHA auditado é referência para comparação, não ordem para executar sobre uma base antiga.

```text
Leia integralmente, analise e execute o plano:

docs/plans/PDV-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-10.md

Leia também seu relatório de evidências:
docs/reports/PDV-EXCELLENCE-PLANNING-AUDIT-2026-09-10.md

Se os arquivos não estiverem no checkout de entrada, os três documentos foram
entregues na branch codex/pdv-excellence-plan-current-20260910, sob a worktree:
/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-pdv-plan-current-20260910
Leia-os ali como inputs; não execute nessa worktree de planejamento. Transporte
somente plano, prompt e relatório para sua worktree exclusiva, conferindo hashes.
Não use a branch de planejamento como desculpa para começar sobre código antigo.

Esta é uma sessão dedicada à EXECUÇÃO, com mudanças reversíveis no repositório,
testes sintéticos, documentação, migrations aditivas necessárias e commits
locais coesos. Siga a ordem e as dependências dos work packages, todos os gates
humanos, critérios de aceite, budgets operacionais, Definition of Done e o
protocolo de convivência multiagente do plano.

Antes de escrever, leia as instruções locais/AGENTS.md e skills aplicáveis,
registre git status, HEAD e worktrees, e confronte a base disponível com o SHA
auditado 696f541055f396a16fb1c080c7bea69243df720d. Não assuma que o checkout de
entrada é o mais recente. Verifique no código atual cada achado; correção já
existente vira prova de regressão e item já satisfeito, nunca reimplementação.
Trate hipóteses como hipóteses até demonstrar a cadeia e o efeito.

Trabalhe exclusivamente em worktree e branch codex/ isolados. Preserve
integralmente mudanças rastreadas e não rastreadas de terceiros. Não reutilize
worktrees alheias, não copie código sujo, não use reset/clean/restore/stash
abrangentes, não formate o repositório inteiro nem use git add -A ou git add .
Releia trecho e diff antes de cada patch. Coordene hotspots e dependências
entre sessões antes da escrita; não integre branches de terceiros por conta
própria. Registre progresso num log exclusivo, não num arquivo compartilhado.

Trate omotenashi como requisito central desde P0: torne o trabalho do operador
ridiculamente fácil, reduzindo esforço, memória, navegação, redigitação, espera,
conferências externas e incerteza. Antecipe a próxima decisão com os fatos
conhecidos, preserve contexto em interrupção e ofereça recuperação no objeto
exato. Demonstre os ganhos pelos roteiros R01–R14, medição antes/depois,
testes de fluxo e critérios de aceite; não use acabamento visual como prova.
Não retire confirmação, segunda assinatura ou autorização para bater budget.

Preserve os donos canônicos: Orderman para sessão/pedido, Payman para pagamento,
Cashman para custódia e ledger, Stockman para estoque, Guestman/Doorman para
identidade, KDS/Craftsman para cozinha/produção e Fiscalman/directives para
fiscal. Reuse idempotência, locks, recibos e reconciliação existentes antes de
propor infraestrutura nova. Não crie segundo writer, livro-caixa, lifecycle de
pagamento, command bus ou regra de preço no PDV. Admin é configuração/auditoria
Unfold canônica; se alterá-lo, aplique a skill e rode make admin integral.

Priorize contexto estação→terminal→turno correto, tender explícito, review/close
correspondentes, revisão concorrente, idempotência completa e certeza honesta
após timeout. Diferencie pedido criado, pagamento confirmado, entrada de caixa,
cozinha acionada, nota autorizada, job aceito e efeito físico comprovado.
Resultado desconhecido não autoriza repetir cobrança, venda, nota ou impressão
às cegas. Não declare que o pedido não foi fechado com base só em falha de rede.

Execute por fatias verticais: reproduzir → contratar → implementar → provar
sob concorrência/falha → registrar. Teste com banco, Redis namespace, portas e
adapters isolados da sessão. SQLite não prova locks PostgreSQL; mock de UI não
prova jornada Django; spooler aceito não prova papel ou gaveta. Não esconda
warnings, skips, falhas de ambiente ou ausência de teste real.

Não habilite commit offline; mantenha ADR-013. Não faça merge, push, PR, deploy,
escrita em produção, cobrança/estorno real, emissão/cancelamento fiscal real,
envio a destinatário real, provisionamento/revogação de estação, troca de
credencial, instalação no balcão ou acionamento de hardware real sem autorização
humana explícita e específica. Aprovar este plano não aprova esses atos nem as
decisões de negócio pendentes. Não reduza gates nem invente política.

Avance autonomamente em tudo que estiver autorizado. Ao alcançar um gate,
prepare fatos, alternativas, recomendação, impacto, reversibilidade e a decisão
exata necessária; pare a fatia dependente. Continue WPs independentes seguros
enquanto houver caminho autorizado. Pare integralmente quando o próximo caminho
crítico depender da decisão/autorização humana. Silêncio não é aprovação.

Entregue handoff com SHA-base, branch/worktree, commits, matriz de achados,
WPs concluídos/pendentes, gates e decisões, migrations/flags, comandos e
resultados, métricas antes/depois, riscos, integração semântica e rollback.
Declare somente o estado verdadeiro: implementação técnica concluída, pronto
para piloto, rollout concluído ou plano concluído conforme a DoD. Não trate
teste local como prova de piloto, hardware ou produção.
```

O prompt não manda criar outra sessão: ele é o texto de entrada da sessão que o usuário abrirá. Também não exige delegar a subagentes; caso haja delegação autorizada, aplicar o protocolo de ownership/isolamento do plano.
