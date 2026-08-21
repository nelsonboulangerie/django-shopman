"""Shared pytest fixtures for the shopman surfaces (shop, storefront, backstage)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_rules_state():
    """Keep process-level singletons deterministic across tests, regardless of order.

    Several process-level stores leak between tests because a transaction rollback
    removes DB rows without firing the signals/teardown that would clean up the
    derived in-Python state:

    * ``django.core.cache`` caches the active RuleConfig list under ``CACHE_KEY``
      and the singleton ``Shop`` under ``SHOP_CACHE_KEY``. A test that creates a
      ``Shop`` (rolled back afterwards) leaves a stale instance cached for the
      next test's ``Shop.load()``.
    * ``shopman.orderman`` registers validator *instances* (e.g. a
      ``business_hours`` rule with custom params) in an in-process registry; a
      test that registers one leaves it grabbed for every later test.
    * ``shopman.shop.rules.engine._bootstrapped`` is a module-level flag set once
      by ``bootstrap_active_rules()`` and never reset, so a test that triggers a
      bootstrap blocks re-bootstrap for every later test.
    * ``shopman.shop.adapters._external._suppressed_reason`` is a module-level
      flag set by ``suppress()`` — which the ``seed`` command calls at startup and
      never restores. A test that runs ``seed`` (e.g. the Nelson seed coverage in
      backstage) leaves every external adapter inert for the rest of the process,
      so a later test that asserts a real send (``test_sms_opt_in_...``) sees no
      call and fails. It only reproduces under full-suite ordering, never in
      isolation — the classic test-pollution signature.

    Clear the caches, reset the bootstrap flag, drop the suppression flag, and
    snapshot/restore the validator registry around each test so state created in
    one test cannot bleed into another.
    """
    from django.core.cache import cache
    from shopman.orderman import registry as orderman_registry

    from shopman.shop.adapters import _external
    from shopman.shop.models.shop import SHOP_CACHE_KEY
    from shopman.shop.rules import engine as rules_engine

    reg = orderman_registry._registry
    with reg._lock:
        validators_snapshot = list(reg._validators)

    def _reset_process_state() -> None:
        cache.delete(rules_engine.CACHE_KEY)
        cache.delete(SHOP_CACHE_KEY)
        rules_engine._bootstrapped = False
        _external._suppressed_reason = None

    _reset_process_state()

    yield

    _reset_process_state()
    with reg._lock:
        reg._validators[:] = validators_snapshot


@pytest.fixture(autouse=True)
def _identifica_o_operador_da_sessao(request, monkeypatch):
    """``force_login`` numa superfície de operador também IDENTIFICA a pessoa.

    Com ``SHOPMAN_REQUIRE_ACTIVE_OPERATOR`` ligado — o valor do staging, e o da
    suíte desde 21/08/2026 — a sessão do Django é apenas a **estação**: ela diz
    qual aparelho está falando, não quem está operando. A permissão é avaliada
    contra o **operador ativo**, estabelecido por PIN ou crachá
    (``HasBackstagePermission``, Opção C).

    O harness não tinha esse segundo passo. 302 testes chamavam
    ``client.force_login(alguem)`` e batiam na API, e o gate respondia 403
    ``station_locked`` — corretíssimo, e inútil como sinal: nenhum deles era
    sobre a trava. Editar 302 testes para digitar PIN seria ruído; o que faltava
    era o harness saber que, num balcão, entrar E se identificar são o mesmo
    gesto.

    Esta fixture NÃO esconde a trava — mas só porque quem a testa sai dela
    explicitamente, com ``@pytest.mark.estacao_travada``. Sem esse marcador ela
    seria a própria cegueira que veio remover: o estado TRAVADO é a ausência do
    operador, e uma fixture que sempre o preenche apagaria o único jeito de
    provar que a trava existe. Foi o que aconteceu na primeira versão disto —
    ``test_station_locked_code`` passou a receber 200 onde exige 403.

    O default é o honesto (quem entrou, se identificou); a exceção é declarada.
    """
    if request.node.get_closest_marker("estacao_travada"):
        return

    from django.test import Client
    from rest_framework.test import APIClient

    from shopman.backstage.services.operator import ACTIVE_OPERATOR_SESSION_KEY

    def _identifica(cliente, user):
        # Só faz sentido para quem opera: cliente da loja não tem operador ativo,
        # e marcá-lo como tal seria mentira que um teste de storefront herdaria.
        if user is None or not getattr(user, "is_staff", False):
            return
        sessao = cliente.session
        sessao[ACTIVE_OPERATOR_SESSION_KEY] = {
            "id": user.pk,
            "username": user.get_username(),
            "name": user.get_full_name().strip() or user.get_username(),
            "since": "2026-01-01T00:00:00+00:00",  # fixo: data não é o assunto aqui
        }
        sessao.save()

    # DUAS portas de entrada, e as duas precisam identificar. O `force_login` do
    # Django e o `force_authenticate` do DRF fazem a mesma coisa por caminhos
    # diferentes — o segundo nem passa por autenticação, injeta o usuário direto.
    # Cobrir só uma deixaria metade da suíte no escuro, que foi o que aconteceu
    # na primeira tentativa (as APIs de produção continuaram em 403).
    login_original = Client.force_login
    auth_original = APIClient.force_authenticate

    def force_login_e_identifica(self, user, backend=None):
        login_original(self, user, backend=backend)
        _identifica(self, user)

    def force_authenticate_e_identifica(self, user=None, token=None):
        auth_original(self, user=user, token=token)
        _identifica(self, user)

    monkeypatch.setattr(Client, "force_login", force_login_e_identifica)
    monkeypatch.setattr(APIClient, "force_authenticate", force_authenticate_e_identifica)
