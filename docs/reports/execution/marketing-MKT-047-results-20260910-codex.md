# MKT-047 — resultados das sessões de gestores

**Estado:** coleta não iniciada  
**Commit sob avaliação:** `9fd2b6a5d` + correção factual `bcc00fc48`  
**Perfil:** `config.settings_marketing_demo`, adapter `SIMULATION_ONLY`  
**Política de dados:** somente códigos P01–P05 e métricas; sem nomes, conteúdo ou PII

## Preparação do ambiente

Em 2026-09-10, antes da sessão P01:

- o banco SQLite descartável recebeu backup local e as migrations correntes;
- a única directive vencida era um check sintético de produção e foi concluída pelo
  handler local, sem provider externo;
- Django `/health/live/` e `/health/ready/` retornaram 200;
- BFF `/health/live` e `/health/ready` retornaram 200;
- o adapter de Marketing permanece `SIMULATION_ONLY` e as flags externas permanecem
  desligadas.

## Participantes

| Código | Perfil operacional resumido, sem identificação | Data | Estado |
|---|---|---|---|
| P01 | proprietário/gestor | — | pendente |
| P02 | gestor real | — | pendente |
| P03 | gestor real | — | pendente |
| P04 | participante cumulativo do piloto | — | futuro |
| P05 | participante cumulativo do piloto | — | futuro |

## Resultados por tarefa

O facilitador preenche esta tabela; o participante não precisa anotar cliques ou tempos.

| Participante | Tarefa | Sem ajuda | Ações | Digitação extra | Telas | Espera máx. | Consulta externa | Recuperação preservada | Certeza completa | Resultado/achado sem PII |
|---|---:|:---:|---:|:---:|---:|---:|---:|:---:|:---:|---|
| P01 | 1 | — | — | — | — | — | — | — | — | pendente |
| P01 | 2 | — | — | — | — | — | — | — | — | pendente |
| P01 | 3 | — | — | — | — | — | — | — | — | pendente |
| P01 | 4 | — | — | — | — | — | — | — | — | pendente |
| P01 | 5 | — | — | — | — | — | — | — | — | pendente |
| P01 | 6 | — | — | — | — | — | — | — | — | pendente |
| P01 | 7 | — | — | — | — | — | — | — | — | pendente |
| P01 | 8 | — | — | — | — | — | — | — | — | pendente |
| P01 | 9 | — | — | — | — | — | — | — | — | pendente |

As linhas P02–P05 serão adicionadas no início de cada sessão, nunca antecipadas como
evidência. O resumo e a decisão G-H05 só serão escritos depois da coleta real.
