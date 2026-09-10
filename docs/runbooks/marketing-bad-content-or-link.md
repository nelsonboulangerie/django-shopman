# Marketing — conteúdo, oferta, mídia ou link incorreto

**Owner:** Marketing Ops + Product. **Severidade:** alta se já aprovado/agendado.
**Invariante:** artifact aprovado é imutável e o dispatch usa exatamente seu hash.

## Quando abrir

- preço/validade/estoque diverge do fato canônico;
- URL externa, redirect/tracking ou mídia não confiável é detectada;
- variante/copy errada, placeholder desconhecido ou preview divergente;
- promoção vence antes do dispatch.

## Primeiros 2 minutos

1. Pause approve/fire e cancele somente lanes ainda não iniciadas pela Action exibida.
2. Copie receipt, artifact hash, plataforma e janela; não copie a copy em logs.
3. Rode `make marketing-diagnose receipt=<receipt_ref> platform=<platform>`.
4. Determine pelo ledger o que está planned/queued/sending/accepted/confirmed/unknown.

## Diagnóstico read-only

Compare artifact hash do preview, receipt e attempt; confirme reason code do resolver de
fatos/URL. O validador não resolve DNS nem busca conteúdo remoto durante essa etapa.
Material já confirmado pode exigir comunicação corretiva, não mutação retroativa.

## Freeze/circuit

Isole campanha/plataforma; use freeze global se a mesma fonte factual contaminou vários
artifacts ou se o link oferece risco de segurança/privacidade.

## Decisões proibidas

- não editar artifact/snapshot/receipt selado;
- não trocar URL ou copy diretamente no payload/fila/provider;
- não presumir que cancelar retira conteúdo já aceito/confirmado;
- não reutilizar aprovação antiga para uma variante corrigida.

## Comunicação

Informe hash/ref, canais e estados afetados, validade do fato, cancelamento possível,
owner da correção e checkpoint. Copy sensível fica apenas na ferramenta autorizada.

## Recuperação idempotente

Crie nova versão/draft, resolva novamente fatos e URL, obtenha preview com novo hash e
nova aprovação. Cancele/reconcilie a versão anterior pelas Actions canônicas. Uma
correção ao público é uma nova command auditada, nunca overwrite.

## Fechamento e reconciliação

Feche após todos os targets da versão ruim estarem terminais, unknown resolvido,
alcance real contabilizado, novo artifact aprovado e comunicação corretiva decidida.

## Drill local

`make marketing-drills` injeta redirect/tracking externo e prova bloqueio antes do
provider. O operador não autor deve cancelar o reversível e exigir nova versão/hash.
