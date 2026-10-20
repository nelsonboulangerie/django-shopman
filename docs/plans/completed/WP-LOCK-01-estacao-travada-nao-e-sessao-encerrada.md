# WP-LOCK-01 — Travar a estação deixa de encerrar a sessão da pessoa

> Separar dois conceitos que hoje são o mesmo objeto. Prompt auto-contido.

**Status**: Entregue no PR #1249 (merge `b9ee08f43`, commit `366c13b00`, 29/09/2026). Resta a prova em runtime, ver "Estado real"
**Dependências**: nenhuma. Convive com #769, #775 e #804, que mitigaram sintomas sem tocar a causa
**Severidade**: resolvida no código pelo #1249; era 🟠 Média (🔴 Alta com mais de uma estação por navegador)

---

## Estado real (29/09/2026)

Travar a estação **não é mais `logout()`**. O #1249 trocou a sessão encerrada por
uma **trava por capability dentro da sessão**:

- `shopman/backstage/services/operator_session.py` guarda as capabilities
  travadas na chave de sessão `shopman_locked_station_capabilities`
  (`lock_capability`, `unlock_capability`, `is_capability_locked`);
- `OperatorLockView` (`shopman/backstage/api/operations.py`) exige `perm` no
  corpo e trava só aquela capability; a identidade autenticada continua viva;
- o gate (`shopman/backstage/api/permissions.py`) devolve `station_locked`
  apenas para as APIs da capability travada. O Gestor aberto no mesmo
  navegador segue respondendo;
- PIN/crachá destrava a capability pedida; o `operator-kit`
  (`useOperatorLock.ts`) envia `perm` ao travar e ao destravar;
- o teste que fixava o logout da zona inteira foi **invertido**:
  `test_api_operator_pin.py::test_pdv_lock_keeps_shared_session_and_gestor_alive`,
  mais `test_unlock_clears_only_the_requested_capability` e
  `test_lock_requires_a_known_capability`.

Das perguntas abaixo, o #1249 respondeu a **1** (a trava mora na sessão Django,
não em `Terminal`: sem migração, e não é queryable por loja) e a **3** (destrava
quem provar PIN/crachá com a capability). As perguntas **2, 4 e 5** não foram
tratadas explicitamente no PR. Com o fim do `logout()`, o que o turno deixou na
sessão agora **fica** nela ao travar, o oposto do comportamento que a pergunta 2
descrevia.

**Pendente:** a prova em runtime pedida em "Como saber que deu certo" (dois apps
no mesmo navegador, travar um, observar o outro). O PR registra só testes
automatizados.

O texto a partir daqui é o diagnóstico de 17/09, mantido como histórico.

---

## O problema, em uma frase (até o #1249)

**Travar o PDV é `logout()` no Django, e a sessão é uma só para toda a zona
`.boulangerie.com.br`.** Proteger o balcão obriga a derrubar o Gestor.

`shopman/backstage/api/operations.py`:

```python
class OperatorLockView(APIView):
    """Trava a estação: a pessoa sai, o dispositivo fica. ..."""
    def post(self, request):
        logout(request)
        return Response({"ok": True})
```

O comportamento já está fixado como teste —
`shopman/backstage/tests/test_api_operator_pin.py`,
`test_pdv_lock_expires_the_session_cookie_for_the_whole_operator_zone`: o cookie
volta com `max-age=0` e `domain=.boulangerie.com.br`, e a requisição seguinte a
`/api/v1/backstage/orders/` responde 403.

Escopo real: **por navegador**, não por loja. O PDV do balcão travando não
derruba o notebook de ninguém. O estrago é o PDV aberto **no mesmo navegador**
que o Gestor, o BI ou o KDS.

## Por que não foi resolvido nas correções de 17/09

Três mudanças no mesmo dia atacaram o sintoma:

| PR | o que fez | o que não fez |
|---|---|---|
| #769 | o cadeado não dispara com a aba do PDV oculta | `visibilityState` **não detecta janela encoberta** |
| #775 | o relógio de ociosidade passa a ser do APARELHO, alimentado por todo app que estende o kit | o **Admin** é Django-rendered e não alimenta o relógio; abas de terceiros também não |
| #804 | erro de rede deixa de pedir senha | não muda o que travar faz |

Ou seja: hoje, trabalhar 60 s no **Admin** com o PDV aberto no mesmo navegador
ainda mata a sessão de todos os apps de operador. O mesmo vale para uma aba de
e-mail ou planilha.

Enquanto travar for `logout()`, cada nova superfície fora do kit reabre o
buraco. É por isso que isto é WP, e não mais um remendo.

## O que este WP entrega

**Separar "estação travada" de "sessão viva".**

- a sessão da PESSOA continua viva enquanto ela estiver trabalhando em qualquer
  app de operador;
- a ESTAÇÃO fica travada como estado próprio, e destravar pede PIN ou crachá
  como hoje;
- travar o balcão não tem efeito nenhum sobre o Gestor aberto ao lado.

O estado já existe em parte: `station_locked` é um ramo conhecido do
`httpError` do kit (`surfaces/operator-kit/app/utils/httpError.ts`), e
`flagIfStationLocked` já circula em `useOperatorLock`. Falta ele ser a fonte da
verdade em vez de consequência do logout.

## Perguntas a responder no WP (não decididas aqui)

1. **Onde mora "travada"** — coluna em `Terminal`, chave em `Terminal.metadata`,
   ou registro próprio com quem travou e quando? Envolve a decisão sobre o Core
   ser sagrado: `metadata` é JSONField e evita migração, mas "travada" é estado
   queryable e operacional.
2. **O que acontece com o turno de caixa** quando a estação trava com turno
   aberto. Hoje o `logout()` leva junto o que o turno deixou na sessão — é
   citado na docstring da view como intencional.
3. **Quem pode destravar**: qualquer operador com a permissão, ou só quem
   travou / um gestor? Hoje a resposta é "quem tiver PIN na estação".
4. **Troca de pessoa no balcão**: hoje travar+destravar com outro PIN é o gesto
   de troca de turno, e ele depende de a sessão morrer. Separado, precisa de um
   caminho explícito para "sou outra pessoa agora".
5. **O que fazer com a sessão de quem não voltar** — a estação travada mantém
   viva a sessão de quem foi embora? Precisa de prazo próprio, e ele conversa
   com `SHOPMAN_OPERATOR_SESSION_IDLE_SECONDS` (7 dias).

## Mitigação disponível hoje, sem código

`Terminal.metadata["auto_lock_seconds"]` (default **60**) é configurável por
terminal no Admin. Subir esse número no balcão espaça o sintoma. **Não resolve
nada estrutural**, e é decisão de segurança do balcão — quanto tempo o caixa
pode ficar destravado sem ninguém na frente.

## Como saber que deu certo

- travar o PDV com o Gestor aberto no mesmo navegador **não** faz o Gestor pedir
  nada;
- destravar o PDV continua pedindo PIN ou crachá;
- o teste `test_pdv_lock_expires_the_session_cookie_for_the_whole_operator_zone`
  é **invertido** com o motivo escrito — ele hoje garante exatamente o
  comportamento que este WP remove;
- prova em runtime, não em leitura: dois apps no mesmo navegador, travar um,
  observar o outro.
