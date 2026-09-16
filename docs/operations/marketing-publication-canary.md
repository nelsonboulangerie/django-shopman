# Canário unitário de publicação Marketing

Use este caminho somente depois de o operador aprovar a peça e a consequência na UI.
Ele não serve para mensagens diretas e nunca escolhe audiência. O alcance é uma única
publicação pública no Instagram, Facebook ou Perfil da Empresa no Google.

## Por que existe

Os consumers normais drenam trabalho elegível em lotes. Ligá-los apenas para “fazer um
teste” pode alcançar consequências históricas pendentes. O canário exige uma outbox
exata e recusa executar enquanto qualquer consumer global de Marketing estiver ligado.
Assim, outras outboxes e targets continuam intocados.

## Gates antes de qualquer efeito

1. mantenha `SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED=false` e
   `SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED=false`;
2. confira que Marketing não está congelado e que não existe outro executor;
3. habilite somente `SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED` e a flag da
   plataforma escolhida; a UI então libera apenas a lane pública cujo adapter estiver
   realmente pronto e a identifica como canário unitário;
4. forneça somente as credenciais/identificadores daquela plataforma;
5. no Instagram Story, use uma imagem JPEG final pública por HTTPS, preferencialmente
   vertical 9:16 e digna de permanecer pública durante o teste; não há fallback
   silencioso para Feed;
6. confirme conta/página/local correto, prévia, texto, formato, horário, expiração e
   plano de remoção manual se a peça precisar sair do ar;
7. obtenha autorização humana explícita para a consequência pública exata.

## Preflight sem publicação

Use o número que já aparece em `/announcements/ID`; não é preciso procurar UUID no
banco:

```bash
python manage.py run_marketing_publication_canary \
  --announcement-id ID \
  --platform instagram
```

O comando mostra plataforma, formato, host da mídia, prontidão, estado e a referência
exata. Também imprime a invocação de execução pronta para copiar. Até aqui não há
alteração de fila nem chamada externa.

## Execução unitária

Depois da conferência humana, execute a linha impressa pelo preflight. Ela contém:

```text
--outbox-ref UUID --platform instagram --execute \
--confirm "PUBLICAR instagram UUID"
```

O comando aceita somente a consequência exata, materializa no máximo um destino
público e chama somente a integração daquela plataforma. Repetir o comando sobre um
destino já encerrado não chama o fornecedor novamente. Resultado `unknown` permanece
incerto e não deve ser repetido;
use a reconciliação read-only prevista no ledger.

## Encerramento

- confira o comprovante sanitizado e a presença pública diretamente na conta certa;
- registre horário e resultado sem copiar token, corpo de resposta ou PII;
- desligue `SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED` e a flag da plataforma;
- mantenha os consumers globais desligados até existir gate separado para avaliar e
  tratar o backlog;
- remover a publicação é uma nova consequência externa e exige decisão humana.
