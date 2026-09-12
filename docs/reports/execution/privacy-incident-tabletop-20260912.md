# Exercício de mesa L6 — incidente de privacidade

**Estado:** exercício concluído e confirmado em 2026-09-12; 19 testes de backend
e 4 testes da interface passaram.
**Ambiente:** local, sintético, sem fornecedor, cliente ou escrita externa.  
**Responsável:** Pablo Valentini. **Suplente:** Laís Kohatsu Kataoka.

## Cenário único

Às 14h10, o alerta `marketing_consent_violation` informa que uma mensagem direta
pode ter sido aceita pelo provedor depois da revogação do consentimento. Há um
único destino sintético; o estado de leitura é desconhecido e o escopo completo
ainda está em apuração.

## Resposta esperada

1. Congelar imediatamente novas entregas de Marketing, sem apagar ledger,
   recibos ou evidências.
2. Diagnosticar e reconciliar; não reenviar “para testar” e não presumir que o
   escopo é zero.
3. Registrar linha do tempo, categorias de dados, quantidade de titulares,
   risco/dano possível, mitigação e a decisão fundamentada de comunicar ou não.
4. Se houver risco ou dano relevante, comunicar ANPD e titulares no prazo
   aplicável de três dias úteis; informação incompleta pode exigir comunicação
   preliminar e complemento posterior.
5. Retirar o bloqueio somente depois da reconciliação e de decisão conjunta do
   responsável e da suplente.
6. Conservar o registro do incidente por pelo menos cinco anos.

## O que o ensaio automático prova — e o que não prova

`make marketing-drills` prova localmente que a revogação ocorrida depois da
distribuição interna suprime o destino antes da reserva de execução e do
provedor, que o diagnóstico não expõe PII e que recuperação/reprocessamento não
ampliam a audiência. O teste não substitui a decisão humana acima, não chama
fornecedor e não mede tempo real de uma equipe.

Execução desta revisão: backend `19 passed`; health probe da interface `4
passed`; `npm audit` do app Marketing `0 vulnerabilities`. A primeira tentativa
da etapa de interface não encontrou as dependências locais da worktree; depois
de instalar exatamente o lockfile, o teste passou. Essa falha de ambiente não é
contada como evidência do produto.

## Confirmação humana registrada

Depois de ler o cenário, o responsável confirmou:

> Confirmo o exercício L6: diante desse alerta eu congelaria as entregas,
> preservaria evidências, proibiria reenvio cego, registraria a avaliação de
> risco e decidiria qualquer comunicação com Laís dentro do prazo aplicável;
> somente retiraríamos o bloqueio após reconciliação.

Uma resposta afirmativa registra a decisão do exercício; não autoriza disparo,
comunicação à ANPD, contato com titulares nem alteração em produção.

**Registro de 2026-09-12:** “Confirmo o exercício L6”. O exercício está
encerrado. A confirmação não ampliou o escopo técnico nem autorizou qualquer
ação em produção.
