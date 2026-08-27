"""POST /api/v1/auth/access/ — magic-link token → store-domain session.

The destination is derived from the token metadata (no client `next`), so a link
can only ever land on a safe in-store path. The session cookie is set on the
store host (the Nuxt page posts here through the BFF).
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from shopman.doorman.models import AccessLink
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

pytestmark = pytest.mark.django_db


class TestAccessLinkExchangeApi:
    URL = "/api/v1/auth/access/"

    def _token(self, customer, *, metadata=None, minutes=5):
        return AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            metadata=metadata or {},
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    def _order(self, channel, customer, *, ref: str):
        return Order.objects.create(
            ref=ref,
            channel_ref=channel.ref,
            status="new",
            total_q=1000,
            handle_type="phone",
            handle_ref=customer.phone,
            data={"customer_ref": customer.ref},
        )

    def test_valid_token_creates_session_and_defaults_to_home(self, client: Client, customer):
        _link, raw_token = self._token(customer)

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert client.session.get("_auth_user_id") is not None
        body = response.json()
        assert body["redirect"] == "/"
        assert body["is_authenticated"] is True

    def test_order_metadata_grants_access_and_redirects_to_tracking(self, client: Client, channel, customer):
        self._order(channel, customer, ref="ORD-NUXT-1")
        _link, raw_token = self._token(customer, metadata={"order_ref": "ORD-NUXT-1"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert response.json()["redirect"] == "/pedido/ORD-NUXT-1"
        assert "ORD-NUXT-1" in client.session.get("shopman_order_access_refs", [])

    def test_payment_action_redirects_to_tracking(self, client: Client, channel, customer):
        # PAYMENT-TRACKING-MERGE: pagamento é um degrau do acompanhamento, então
        # um magic link de pagamento aterrissa no próprio acompanhamento.
        self._order(channel, customer, ref="ORD-PAY-1")
        _link, raw_token = self._token(customer, metadata={"order_ref": "ORD-PAY-1", "action": "payment"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.json()["redirect"] == "/pedido/ORD-PAY-1"

    def test_reorder_action_redirects_to_order_history(self, client: Client, channel, customer):
        self._order(channel, customer, ref="ORD-RE-1")
        _link, raw_token = self._token(customer, metadata={"order_ref": "ORD-RE-1", "action": "reorder"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.json()["redirect"] == "/conta/pedidos"

    def test_expired_token_is_rejected_without_session(self, client: Client, customer):
        _link, raw_token = self._token(customer, minutes=-1)

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 400
        assert client.session.get("_auth_user_id") is None

    def test_invalid_token_is_rejected(self, client: Client):
        response = client.post(self.URL, {"token": "nonexistent-token"})

        assert response.status_code == 400
        assert client.session.get("_auth_user_id") is None

    def test_used_token_is_rejected(self, client: Client, customer):
        link, raw_token = self._token(customer)
        link.used_at = timezone.now() - timedelta(minutes=5)
        link.save()

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 400
        assert client.session.get("_auth_user_id") is None

    def test_cart_session_key_adopted_when_session_empty(self, client: Client, customer):
        # Fluxo do site: o código NB dobrou a sacola anônima na metadata do token.
        _link, raw_token = self._token(customer, metadata={"cart_session_key": "sk_from_site"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert client.session.get("cart_session_key") == "sk_from_site"

    def test_cart_session_key_not_overridden_when_session_has_cart(self, client: Client, customer):
        session = client.session
        session["cart_session_key"] = "sk_local"
        session.save()
        _link, raw_token = self._token(customer, metadata={"cart_session_key": "sk_from_site"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert client.session.get("cart_session_key") == "sk_local"

    def test_handoff_expired_metadata_surfaces_notice(self, client: Client, customer):
        # Handoff do site expirou (código NB não resolveu no create): entra logado, mas
        # avisamos que a sacola não veio — flag + copy gentil, sem bloquear a entrada.
        _link, raw_token = self._token(customer, metadata={"handoff_expired": True})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        body = response.json()
        assert body["is_authenticated"] is True
        assert body["handoff_expired"] is True
        assert body["notice"]  # copy resolvida do registro (LOGIN_HANDOFF_EXPIRED)

    def test_clean_metadata_carries_no_handoff_notice(self, client: Client, customer):
        # Login/handoff normal: sem flag nem notice (não polui a UI de quem entrou ok).
        _link, raw_token = self._token(customer, metadata={"cart_session_key": "sk_ok"})

        body = client.post(self.URL, {"token": raw_token}).json()
        assert "handoff_expired" not in body
        assert "notice" not in body

    def test_missing_token_is_rejected(self, client: Client):
        response = client.post(self.URL, {})

        assert response.status_code == 400


class TestIdentityStrength:
    """Quanto sabemos sobre quem está do outro lado — a única cerca deste desenho.

    ⚠️ O `audience` do `AccessLink` existe no model e **ninguém o aplica**:
    `exchange_token` nunca passa `required_audience`. Então a cerca não pode ser ele. A
    pergunta que decide é outra, e é mais simples: **este aparelho é conhecido?**
    """

    def _campaign_token(self, customer, **metadata):
        from datetime import timedelta

        from django.utils import timezone

        return AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_CHECKOUT,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(hours=2),
            metadata={"login_source": "campaign", "next": "/sacola", **metadata},
        )

    @pytest.mark.django_db
    def test_a_campaign_link_on_an_unknown_device_knows_only_the_number(self, client, customer):
        _link, raw = self._campaign_token(customer)

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.status_code == 200, response.content
        assert response.json()["identity_strength"] == "number"
        assert client.session["identity_strength"] == "number"

    @pytest.mark.django_db
    def test_the_same_link_on_a_KNOWN_device_knows_the_person(self, client, customer, monkeypatch):
        """É o celular dela: o cookie de confiança já provou identidade um dia.

        Este é o caso da esmagadora maioria de quem volta — e nele o link é só
        conveniência. Nada a reduzir, nada a confirmar.
        """
        from shopman.shop.services import auth as auth_service

        monkeypatch.setattr(auth_service, "device_is_trusted", lambda *a, **kw: True)
        _link, raw = self._campaign_token(customer)

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.json()["identity_strength"] == "device"

    @pytest.mark.django_db
    def test_a_link_that_is_not_from_a_campaign_is_left_alone(self, client, customer):
        """Login normal e handoff do site não passam por aqui: a força padrão é a forte,
        e marcar tudo como fraco esconderia dado de quem provou identidade."""
        from datetime import timedelta

        from django.utils import timezone

        _link, raw = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.json()["identity_strength"] == "device"
        assert "identity_strength" not in client.session

    @pytest.mark.django_db
    def test_a_broken_trust_check_degrades_to_the_weak_identity(self, client, customer, monkeypatch):
        """Na dúvida, reduzir o que aparece. Assumir confiança não verificada seria o erro
        na direção perigosa."""
        from shopman.shop.services import auth as auth_service

        def explode(*a, **kw):
            raise RuntimeError("cookie ilegível")

        monkeypatch.setattr(auth_service, "device_is_trusted", explode)
        _link, raw = self._campaign_token(customer)

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.json()["identity_strength"] == "number"


class TestSpentTokenWithLiveSession:
    """⚠️ O segundo toque na mesma mensagem não pode virar parede.

    O token é de uso único, e isso é bom — mas torna o reclique COMUM: a pessoa clica,
    compra, volta na conversa e clica de novo. Antes, a resposta era 400 "Este link expirou
    ou já foi usado" para alguém que já estava logado: a informação mais desanimadora
    possível para quem já está dentro.

    Quem sabe as duas coisas é o servidor. A página não tem como responder isso numa carga
    nova — o estado do cliente nasce vazio e só o cookie sabe.
    """

    def _spent(self, customer):
        from datetime import timedelta

        from django.utils import timezone

        link, raw = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_CHECKOUT,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(hours=2),
            metadata={"login_source": "campaign", "next": "/oferta/semana"},
        )
        return link, raw

    @pytest.mark.django_db
    def test_the_second_click_lands_on_the_destination(self, client, customer):
        _link, raw = self._spent(customer)

        first = client.post("/api/v1/auth/access/", {"token": raw})
        assert first.status_code == 200

        again = client.post("/api/v1/auth/access/", {"token": raw})

        assert again.status_code == 200, again.content
        body = again.json()
        assert body["already_authenticated"] is True
        assert body["redirect"] == "/oferta/semana"
        assert body["is_authenticated"] is True

    @pytest.mark.django_db
    def test_the_second_click_never_redirects_to_a_foreign_order(self, client, channel, customer):
        foreign = Customer.objects.create(
            ref="CUS-SPENT-FOREIGN",
            first_name="Outra",
            phone="+5543999992020",
        )
        order = Order.objects.create(
            ref="ORD-SPENT-FOREIGN",
            channel_ref=channel.ref,
            status="new",
            total_q=1000,
            handle_type="phone",
            handle_ref=foreign.phone,
            data={"customer_ref": foreign.ref},
        )
        _link, raw = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(hours=2),
            metadata={"order_ref": order.ref},
        )
        first = client.post("/api/v1/auth/access/", {"token": raw})
        assert first.status_code == 200

        again = client.post("/api/v1/auth/access/", {"token": raw})

        assert again.status_code == 200, again.content
        assert again.json()["already_authenticated"] is True
        assert again.json()["redirect"] == "/"
        assert order.ref not in client.session.get("shopman_order_access_refs", [])

    @pytest.mark.django_db
    def test_a_spent_token_without_a_session_still_fails(self, client, customer):
        """Sem sessão, token gasto é porta fechada — como deve ser."""
        _link, raw = self._spent(customer)
        client.post("/api/v1/auth/access/", {"token": raw})
        client.cookies.clear()

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.status_code == 400
        assert "expirou" in response.json()["detail"]

    @pytest.mark.django_db
    def test_garbage_is_never_a_way_in(self, client, customer):
        """Token inventado não abre nada, nem quando há sessão de outra origem."""
        response = client.post("/api/v1/auth/access/", {"token": "nao-existe"})

        assert response.status_code == 400


class TestReplyProvesPossession:
    """⚠️ A distinção que faz a confirmação valer para sempre — e não virar pedágio.

    `source=manychat` significa que o link nasceu porque a pessoa MANDOU mensagem no
    WhatsApp. Enviar de um número prova posse dele: é a mesma prova que o OTP dá, e o OTP já
    confia no aparelho. `source=internal` é link que NÓS empurramos (campanha): prova que
    sabemos o número, não que quem tocou é a dona.

    Sem essa distinção, ou nenhuma confirmação seria durável, ou toda campanha confiaria no
    aparelho de quem tocasse primeiro — que é exactamente o que não se quer.
    """

    def _token(self, customer, *, source):
        from datetime import timedelta

        from django.utils import timezone

        return AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_ACCOUNT,
            source=source,
            expires_at=timezone.now() + timedelta(minutes=10),
            metadata={"next": "/finalizar"},
        )

    @pytest.mark.django_db
    def test_a_link_born_from_her_message_trusts_the_device(self, client, customer):
        from shopman.doorman.models import TrustedDevice

        _link, raw = self._token(customer, source=AccessLink.Source.MANYCHAT)

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.status_code == 200, response.content
        assert response.json()["device_trusted"] is True
        assert response.json()["identity_strength"] == "device"
        assert TrustedDevice.objects.filter(subject_id=str(customer.uuid)).exists()

    @pytest.mark.django_db
    def test_a_link_we_pushed_does_not_trust_the_device(self, client, customer):
        """Campanha identifica para comprar; não promete que é ela."""
        from shopman.doorman.models import TrustedDevice

        _link, raw = self._token(customer, source=AccessLink.Source.INTERNAL)

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.status_code == 200
        assert "device_trusted" not in response.json()
        assert not TrustedDevice.objects.filter(subject_id=str(customer.uuid)).exists()

    @pytest.mark.django_db
    def test_a_failure_to_remember_still_lets_her_in(self, client, customer, monkeypatch):
        """O cookie é atalho, não a entrada: se não gravar, ela entra igual."""
        from shopman.shop.services import auth as auth_service

        def explode(**kwargs):
            raise RuntimeError("cookie não gravou")

        monkeypatch.setattr(auth_service, "trust_device", explode)
        _link, raw = self._token(customer, source=AccessLink.Source.MANYCHAT)

        response = client.post("/api/v1/auth/access/", {"token": raw})

        assert response.status_code == 200
        assert response.json()["is_authenticated"] is True


class TestBrowserHandoff:
    """A travessia do webview para o navegador de verdade dela.

    ⚠️ Existe por um fato de plataforma: o navegador embutido do WhatsApp tem **pote de cookie
    próprio**. Sessão e aparelho confiado conquistados ali não existem no Safari que ela usa no
    resto do dia — "confirmado para sempre neste aparelho" era, na prática, "neste webview".

    A regra que estes testes guardam: a travessia **carrega** a identidade, nunca a promove.
    Trocar de navegador não é prova de nada — é a mesma pessoa, no mesmo aparelho, com a mesma
    dúvida.
    """

    URL = "/api/v1/auth/handoff/"

    def _sign_in(self, client, customer, *, strength=None):
        from datetime import timedelta

        from django.utils import timezone

        _link, raw = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_CHECKOUT,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(hours=1),
            metadata={"login_source": "campaign", "next": "/finalizar"} if strength else {},
        )
        assert client.post("/api/v1/auth/access/", {"token": raw}).status_code == 200

    @pytest.mark.django_db
    def test_a_visitor_gets_no_handoff(self, client):
        """Travessia leva identidade. Sem identidade não há o que levar."""
        response = client.post(self.URL, {"next": "/finalizar"})

        assert response.status_code == 401

    @pytest.mark.django_db
    def test_it_mints_a_one_time_link_to_the_same_screen(self, client, customer):
        from shopman.doorman.models import AccessLink as Link

        self._sign_in(client, customer)
        before = Link.objects.count()

        response = client.post(self.URL, {"next": "/finalizar"})

        assert response.status_code == 200, response.content
        assert "/a?t=" in response.json()["url"]
        assert Link.objects.count() == before + 1
        fresh = Link.objects.order_by("-created_at").first()
        assert fresh.metadata["next"] == "/finalizar"
        assert fresh.metadata["login_source"] == "handoff"

    @pytest.mark.django_db
    def test_the_handoff_link_is_short_lived(self, client, customer):
        """Não é link para guardar: é um trilho entre dois navegadores do mesmo aparelho."""
        from datetime import timedelta

        from django.utils import timezone
        from shopman.doorman.models import AccessLink as Link

        self._sign_in(client, customer)
        client.post(self.URL, {"next": "/conta"})

        fresh = Link.objects.order_by("-created_at").first()
        assert fresh.expires_at <= timezone.now() + timedelta(minutes=5)

    @pytest.mark.django_db
    def test_it_carries_the_weak_identity_without_promoting_it(self, client, customer):
        """⚠️ O invariante. Se ela chegou sabendo só o número, do outro lado continua igual."""
        from shopman.doorman.models import AccessLink as Link

        self._sign_in(client, customer, strength=True)
        assert client.session["identity_strength"] == "number"

        response = client.post(self.URL, {"next": "/finalizar"})
        url = response.json()["url"]
        raw = url.split("?t=")[1]
        assert Link.objects.order_by("-created_at").first().metadata["identity_strength"] == "number"

        # Do outro lado (navegador novo = cliente novo, pote novo):
        from django.test import Client

        other = Client()
        landed = other.post("/api/v1/auth/access/", {"token": raw})

        assert landed.status_code == 200, landed.content
        assert landed.json()["identity_strength"] == "number"
        assert landed.json()["redirect"] == "/finalizar"

    @pytest.mark.django_db
    def test_a_strong_identity_arrives_strong(self, client, customer):
        """E o contrário também vale: quem já era reconhecida não é rebaixada pela travessia."""
        from django.test import Client

        self._sign_in(client, customer)  # sem marca ⇒ força `device`

        raw = client.post(self.URL, {"next": "/conta"}).json()["url"].split("?t=")[1]
        landed = Client().post("/api/v1/auth/access/", {"token": raw})

        assert landed.json()["identity_strength"] == "device"

    @pytest.mark.django_db
    def test_the_cart_crosses_over_too(self, client, customer):
        """Sessão nova sem sacola é a pior surpresa para quem estava no meio de um pedido."""
        from django.test import Client

        self._sign_in(client, customer)
        session = client.session
        session["cart_session_key"] = "sacola-abc"
        session.save()

        raw = client.post(self.URL, {"next": "/sacola"}).json()["url"].split("?t=")[1]
        other = Client()
        other.post("/api/v1/auth/access/", {"token": raw})

        assert other.session["cart_session_key"] == "sacola-abc"

    @pytest.mark.django_db
    def test_a_foreign_destination_is_refused(self, client, customer):
        """Destino é caminho interno. Aceitar URL de fora aqui seria redirect com sessão na mão."""
        from shopman.doorman.models import AccessLink as Link

        self._sign_in(client, customer)
        client.post(self.URL, {"next": "https://outro.site/roubo"})

        assert Link.objects.order_by("-created_at").first().metadata["next"] == "/"

    @pytest.mark.django_db
    def test_a_protocol_relative_destination_is_refused_too(self, client, customer):
        """`//evil.com` é URL absoluta disfarçada de caminho."""
        from shopman.doorman.models import AccessLink as Link

        self._sign_in(client, customer)
        client.post(self.URL, {"next": "//evil.com/x"})

        assert Link.objects.order_by("-created_at").first().metadata["next"] == "/"
