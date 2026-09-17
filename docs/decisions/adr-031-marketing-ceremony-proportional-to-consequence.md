# ADR-031 — A cerimônia de confirmação do Marketing mede a consequência

**Status:** Aceito em 2026-09-17

## Contexto

Disparar uma campanha de teste, para uma pessoa, pedia este caminho:

```
Disparar → escolher o público → Disparar agora
        → caixa: digitar "PREPARAR 1" + senha → Criar para revisão
        → Revisar anúncio agora
        → Enviar agora
        → caixa: digitar "PUBLICAR 1" + senha → Confirmar consequência
        → "Anúncio preparado para publicação"
```

Duas frases digitadas e duas senhas para mandar uma mensagem para uma pessoa. O gestor
descreveu como "protocolo de teste nuclear", e a descrição é justa.

A causa estava em `requirement_for`: a escalada disparava por `immediate or count >= 50`,
e `immediate` era verdadeiro para toda aprovação, todo disparo e toda reentrega sem
agendamento. O limiar de 50 existia no código e nunca era alcançado, porque a primeira
condição já tinha escalado tudo. Duas consequências absurdas caíam daí:

- **o disparo pagava o preço da entrega.** `fire` não publica e não envia: cria um
  anúncio que nasce em revisão. O próprio módulo já o tratava como consequência zero —
  `_reserve_external_quota` o isenta da quota de destinos externos. Ainda assim cobrava
  frase digitada e senha, e cobrava ANTES de a aprovação cobrar de novo, pelo mesmo
  envio;
- **agendar era mais barato que entregar.** Quinhentas pessoas agendadas caíam no resumo;
  uma pessoa agora exigia senha. O agendamento adia o efeito, não o diminui.

## Decisão

A cerimônia passa a medir só a consequência — quantos destinos externos o comando cria.

- **`fire` não pede cerimônia nenhuma** (`AuthorizationRequirement("none", "none", False, "")`).
  O token continua sendo emitido e consumido dentro da transação: é ele que ancora
  versão, capacidade, impressão digital de permissão e geração de congelamento. O que
  deixa de existir é a interrupção do gestor. Um novo modo `none` em
  `MarketingConfirmation.Mode` diz isso explicitamente, e o navegador consome o token
  assim que lê esse modo. Quem escolhe a política continua sendo o servidor.
- **abaixo de 50 destinos:** resumo + um toque. Sem frase, sem senha.
- **de 50 a 499 destinos:** frase digitada + senha.
- **500 destinos ou mais:** frase digitada + TOTP + duplo controle.
- **`immediate` deixa de escalar sozinho.** Agendar e entregar agora pedem a mesma coisa
  para o mesmo público.

Os limiares viram constantes nomeadas — `CEREMONY_TYPED_THRESHOLD` e
`CEREMONY_DUAL_CONTROL_THRESHOLD` — para que mudar a política seja mudar um número com
nome, e não descobrir um booleano escondido numa condição.

Nada mais foi afrouxado: RBAC, token de uso único, CAS por versão, idempotência,
comprovante, congelamento de emergência, quota durável de 5.000 destinos externos por dia,
teto de 5.000 destinos por comando e a obrigação de agendar acima de 2.000 continuam
exatamente como estavam. O teto de 2.000 deixa de valer para `fire`, porque preparar um
rascunho não entrega nada.

## Consequências

O caminho do disparo pequeno passa a ter uma confirmação, não duas, e essa confirmação é
ler o resumo e tocar um botão que diz o efeito pelo nome — "Enviar agora", "Publicar
agora", "Entregar agora", "Agendar" — em vez de "Confirmar consequência".

O risco que se aceita é explícito: um operador com sessão aberta e capacidade de publicar
passa a conseguir entregar para até 49 destinos com um toque a menos. Em troca, o ritual
volta a significar alguma coisa: quando a tela pedir uma senha, é porque o volume mudou de
categoria — e não porque ela pede senha para tudo.

## Referências

- `shopman/shop/services/marketing_security.py` — `requirement_for`
- `shopman/shop/tests/test_marketing_security.py`
- [ADR-029](adr-029-marketing-fire-logical-rate-limit.md) — a quota lógica do disparo, que
  descreve o protocolo de dois POSTs de quando o `fire` ainda pedia `PREPARAR <count>`
- `docs/reference/marketing-surface-contract.md`
