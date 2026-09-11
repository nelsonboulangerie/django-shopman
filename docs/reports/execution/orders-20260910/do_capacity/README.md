# Capacidade na topologia existente — preparação isolada

Pablo confirmou PC da loja/rede local, backend DigitalOcean; essa configuração
não exige nova escolha de parâmetros técnicos pelo usuário. Spec ativo consultado
somente em leitura em11/09 (timestamp/versão em topology.json), sem exportar envs
secretas: web1×1CPU/1GB, Daphne único, Gestor1×1CPU/512MB, PostgreSQL16 e Valkey8
gerenciados emNYC. A documentação antiga contém snapshots obsoletos de domínio e
adapters; não foi tratada como configuração viva. Nenhum spec foi aplicado.

A tarefa PDV transmitiu autorização explícita de Pablo para publicar sua integração
após as validações. Ela coordena a publicação. Não autoriza novos recursos pagos,
relaxar budgets, executar efeitos financeiros/fiscais/comunicação reais ou considerar
piloto concluído. Nada publicado por esta tarefa nesta etapa.

## Ensaio preparado

Workflow `orders-isolated-capacity.yml`, somente branch codex isolada/manual;
permissão GitHub contents:read, sem secrets DO ou deploy. Reusa fixture e ensaio
anteriores,60 amostras por1/2/10 clientes,20 navegações,500 pedidos ricos+10 aparelhos.
Teto por cgroup do backend1CPU/1GiB e Nitro1CPU/512MiB; rede de saída desses processos
limitada a localhost. PostgreSQL/Valkey efêmeros do job; nenhum worker de efeitos.
A coleta salva amostras completas e primeiras leituras. Veredito reprova acima de
500ms backend/1500ms browser, mesmo se testes funcionais passarem.

Não cria infraestrutura DigitalOcean. CI existente é preparação técnica autorizada;
merge/main não é necessário e não será executado para medir. O workflow Deploy
Images só dispara por push main ou sua execução manual, nenhum deles usado aqui.
Artefatos são lista explícita de métricas e logs; cookies de autenticação sintética
não são exportados. Limpeza encerra apenas units criadas pelo próprio job.

## Limites

Runner Linux compartilhado não é hardware dedicado equivalente da DO. Banco local
não reproduz latência/pool gerenciados (usa conn age0 por não ter pool), nem mede
PC/rede da loja. Um passe constitui evidência controlada sob os tetos da aplicação,
não aceite automático de toda cadeia ou piloto. Uma falha de preparação não é
resultado de desempenho. Não esconder falha do runner/BPF/systemd/OOM como skip.

Preparação local: Python/YAML parseados; Ruff e check_workflow_budgets passaram.
Tentativa inicial de checker com `.venv` ausente nesta worktree falhou antes de
executar; repetido com interpretador canônico. Docker não instalado neste host;
escolhido runner CI já existente, sem instalar engine ou reservar recurso novo.
Execução remota e resultados serão acrescentados após a rodada, sem antecipar passe.
