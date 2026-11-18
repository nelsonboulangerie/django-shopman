# CONCIERGE-R3: plano de ação da Concierge em pacotes delegáveis

Compromisso: DEV-2026-029. Modelo: Fable 5.2, esforço `high`. Nenhum código de produção.

## Tarefa

Revise o plano da Concierge contra o código de hoje e entregue um plano de ação em pacotes de
trabalho (WPs). O dono vai delegar cada WP a uma sessão Opus 5.5.

## Leia

- `docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md`: o alvo e as fatias F1 a F6 (escrito em 03/10).
- `docs/plans/ID3A-PLAN.md`: a porta de IA. A Concierge está na fase 3 (E11).
- `docs/coordination/DECISIONS.md`: D-018, D-035, D-039, e qualquer outra decisão sobre a Concierge.
- `docs/coordination/ROUNDS/OBS0310-*-concierge-*.md`: o que cada rodada já entregou.
- `shopman/storefront/concierge/`, `shopman/shop/ai.py`, `docs/reference/ai-connections.md`.

## Entregue

`docs/plans/CONCIERGE-PLANO-DE-ACAO.md`, num PR, com:

1. **Estado medido**: cada fatia (F1 a F6) marcada como pronta, parcial ou ausente, com caminho
   ou commit como prova.
2. **Cortes**: o que do V2 está obsoleto ou não paga o próprio custo, cada corte com o motivo.
   Diga também o que da LGPD e da porta (E1, E5) é pré-requisito real, já que a frente abre
   antes da fase 3.
3. **WPs**, cada um cabendo numa sessão, um branch e um PR, com:
   - objetivo em uma frase;
   - dependências;
   - arquivos que toca;
   - fora do escopo;
   - pronto quando: o comando que prova e a meta;
   - se muda o que o cliente vê;
   - tamanho;
   - um brief para a sessão Opus, que aponta o que ler e não copia o CLAUDE.md.
4. **Ondas**: o que pode correr em paralelo. Dois WPs da mesma onda nunca tocam o mesmo arquivo.
5. **Decisões do dono**: no máximo seis, só as que bloqueiam um WP e que nenhum documento já
   respondeu. Cada uma respondível com sim/1/2, com a recomendação primeiro.

## Limites

- Nenhuma chamada paga a modelo sem a palavra do dono.
- Banco do alpha: só leitura, pela conexão direta 25060.

## No chat, ao terminar

Em um parágrafo: quantos WPs, quantas ondas e o primeiro a delegar. Depois, as decisões do dono.
