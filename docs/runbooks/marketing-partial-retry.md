# Marketing — entrega parcial e retry seletivo

**Owner:** Marketing Ops. **Severidade:** alta quando parcial não tem Action.
**Invariante:** target lógico nunca é recriado para repetir um efeito.

## Quando abrir

- estado agregado `partial`;
- alerta `marketing_partial_without_action`;
- mistura de confirmed/accepted/failed/unknown no mesmo receipt.

## Primeiros 2 minutos

1. Copie receipt e plataforma da tela, sem copiar recipient.
2. Rode `make marketing-diagnose receipt=<receipt_ref> platform=<platform>`.
3. Separe as contagens `failed_retryable`, `failed_final`, `unknown`, `accepted` e
   `confirmed`; não trate “parcial” como uma lista única repetível.
4. Se houver unknown, abra primeiro `marketing-unknown-provider-effect.md`.

## Diagnóstico read-only

O diagnóstico mostra apenas contagens e refs técnicas. Compare o agregado exibido
com o ledger. `accepted` significa aceito, não confirmado; `unknown` significa efeito
incerto, nunca falha presumida.

## Freeze/circuit

Pause novas campanhas apenas na plataforma que está queimando error budget. Freeze
global se partial coexistir com opt-out/expiração/duplicidade ou se o escopo não puder
ser delimitado.

## Decisões proibidas

- não repetir `accepted`, `confirmed`, `unknown` ou `failed_final`;
- não selecionar telefones manualmente nem refazer audiência;
- não chamar provider fora do adapter/reconciler;
- não marcar campanha como “publicada” usando contagem planejada.

## Comunicação

Publique receipt, plataforma, contagens por estado, Action disponível, owner e ETA.
Use “confirmado/aceito/desconhecido”, nunca “enviado” como atalho.

## Recuperação idempotente

Execute a Action backend `retry_delivery` somente após a confirmação apresentada. Ela
reutiliza os targets e cria nova attempt apenas para `failed_retryable`. Replay da
mesma command key precisa retornar o mesmo receipt e zero target adicional.

## Fechamento e reconciliação

Feche quando todo target estiver terminal, unknown tiver sido reconciliado, partial
tiver Action/owner até desaparecer, e a soma por estados for igual ao total protegido.
Registre quantos foram elegíveis e quantos realmente receberam nova attempt.

## Drill local

`make marketing-drills` cria uma mistura sintética e prova que somente a falha
repetível volta à fila. O operador não autor deve negar retry cego e autorizar apenas
o subconjunto proposto pela Action.
