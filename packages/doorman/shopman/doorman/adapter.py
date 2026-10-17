"""
DefaultAuthAdapter — single point of customization for auth behavior.

Inspired by django-allauth's DefaultAccountAdapter. Provides hooks for
customer resolution, code delivery, login events, and redirects.

The default implementation delegates to the IdentityResolver and
MessageSender ports.

Usage::

    # settings.py
    DOORMAN = {
        "AUTH_ADAPTER": "myapp.auth.MyAuthAdapter",
    }

    # myapp/auth.py
    from shopman.doorman.adapter import DefaultAuthAdapter

    class MyAuthAdapter(DefaultAuthAdapter):
        def on_customer_authenticated(self, request, customer, user, method):
            analytics.track("login", customer_id=str(customer.subject_id))
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .conf import doorman_settings, get_identity_resolver
from .protocols.identity import IdentityHandle, IdentityView
from .utils import normalize_phone

if TYPE_CHECKING:
    from django.http import HttpRequest

    from .models.device_trust import TrustedDevice

logger = logging.getLogger("shopman.doorman.adapter")


class DefaultAuthAdapter:
    """
    Default auth adapter.

    Delegates to IdentityResolver and MessageSender from settings.
    Override methods in a subclass for custom behavior.
    """

    def __init__(self):
        self._resolver = None
        self._sender = None

    # ===========================================
    # Customer resolution
    # ===========================================

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = get_identity_resolver()
        return self._resolver

    def resolve_identity(self, kind: str, value: str, *, purpose: str = "login") -> IdentityView | None:
        return self.resolver.resolve(kind, value, purpose=purpose)

    def identity(self, subject_id, *, purpose: str = "session") -> IdentityView | None:
        return self.resolver.get(subject_id, purpose=purpose)

    def lock_active_identity(self, subject_id, *, purpose: str = "login") -> IdentityView | None:
        return self.resolver.lock_active(subject_id, purpose=purpose)

    def login_target_belongs_to_customer(
        self,
        customer: IdentityView,
        handle: IdentityHandle,
    ) -> bool:
        """Revalidate a login handle after acquiring the canonical customer lock.

        ``resolve_identity`` is deliberately called again here.  Production
        resolvers consult Guestman's current ContactPoint source of truth and
        its current Customer cache; comparing the UUID prevents a phone/email
        that moved or was removed while we waited for the row lock from being
        used to issue or accept an OTP for the stale owner.
        """
        current_owner = self.resolve_identity(handle.kind, handle.value, purpose="login")
        return bool(
            current_owner
            and current_owner.is_active
            and str(current_owner.subject_id) == str(customer.subject_id)
        )

    def login_handle(self, raw: str) -> IdentityHandle:
        """Parse and normalize the sole login handle supplied by the ingress."""
        kind = "email" if "@" in (raw or "") else "phone"
        value = str(raw or "").strip().lower() if kind == "email" else normalize_phone(raw)
        return IdentityHandle(kind=kind, value=value, verified=False, primary=False)

    def create_identity(self, handle: IdentityHandle) -> IdentityView:
        return self.resolver.create(handle.kind, handle.value)

    def bind_verified_handle(
        self,
        identity: IdentityView,
        handle: IdentityHandle,
        *,
        proof: str,
    ) -> IdentityView:
        return self.resolver.bind_verified_handle(
            identity.subject_id,
            handle.kind,
            handle.value,
            proof=proof,
        )

    # ===========================================
    # Code delivery
    # ===========================================

    @property
    def sender(self):
        if self._sender is None:
            from django.utils.module_loading import import_string

            sender_class = import_string(doorman_settings.MESSAGE_SENDER_CLASS)
            self._sender = sender_class()
        return self._sender

    def send_code(self, target: str, code: str, method: str) -> bool:
        """
        Send a verification code via a single method.

        Args:
            target: Phone (E.164) or email.
            code: The raw OTP code.
            method: Delivery method (whatsapp, sms, email).

        Returns:
            True if sent successfully.
        """
        return self.sender.send_code(target, code, method)

    def send_code_with_fallback(
        self, target: str, code: str, preferred_method: str = "whatsapp",
    ) -> tuple[bool, str]:
        """
        Send a verification code, iterating through the delivery chain.

        Tries each sender in DELIVERY_CHAIN order. Falls back to the next
        sender on failure. If DELIVERY_CHAIN is empty, uses the default
        MESSAGE_SENDER_CLASS with the preferred method.

        Args:
            target: Phone (E.164) or email.
            code: The raw OTP code.
            preferred_method: Preferred delivery method (whatsapp, sms, email).

        Returns:
            (success, method_used) — method_used is the delivery method
            that succeeded, or the last one attempted on failure.
        """
        chain = self.get_delivery_chain(target)
        if not chain:
            # No chain configured, use default sender with preferred method
            success = self.send_code(target, code, preferred_method)
            return success, preferred_method

        for method in chain:
            sender = self._get_chain_sender(method)
            if sender is None:
                logger.warning(
                    "No sender configured for method %s, skipping", method
                )
                continue
            try:
                success = sender.send_code(target, code, method)
                if success:
                    logger.info(
                        "Code sent via %s", method,
                        extra={"handle_kind": self.login_handle(target).kind, "method": method},
                    )
                    return True, method
                logger.warning(
                    "Sender %s returned False, trying next", method,
                    extra={"handle_kind": self.login_handle(target).kind},
                )
            except Exception:
                logger.warning(
                    "Sender %s failed with exception, trying next", method,
                    extra={"handle_kind": self.login_handle(target).kind},
                )

        # Chain exhausted
        last_method = chain[-1] if chain else "unknown"
        logger.error(
            "Delivery chain exhausted, all senders failed",
            extra={"handle_kind": self.login_handle(target).kind, "chain": chain},
        )
        return False, last_method

    def _get_chain_sender(self, method: str):
        """Get the sender instance for a delivery chain method."""
        from django.utils.module_loading import import_string

        senders_map = doorman_settings.DELIVERY_SENDERS
        cls_path = senders_map.get(method)
        if not cls_path:
            return None
        # Cache sender instances
        cache_attr = f"_chain_sender_{method}"
        if not hasattr(self, cache_attr):
            cls = import_string(cls_path)
            setattr(self, cache_attr, cls())
        return getattr(self, cache_attr)

    def send_access_link(self, channel: str, customer: IdentityView, url: str) -> bool:
        """
        Send an access link via the specified channel.

        Args:
            channel: Delivery channel (email, whatsapp, sms, api).
            customer: The target customer.
            url: The access link URL.

        Returns:
            True if sent successfully.
        """
        if channel == "email":
            return self._send_access_link_email(customer, url)
        elif channel == "api":
            # API channel: the caller handles delivery
            return True
        else:
            # For whatsapp/sms: send the URL as a code/message
            handle = customer.handle("phone") or customer.handle("whatsapp")
            target = handle.value if handle else ""
            return self.sender.send_code(target, url, channel)

    def _send_access_link_email(self, customer: IdentityView, url: str) -> bool:
        """Send access link via email."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.translation import gettext as _

        handle = customer.handle("email")
        email = handle.value if handle else ""
        if not email:
            logger.warning("No email for subject", extra={"subject_id": str(customer.subject_id)})
            return False

        ttl = doorman_settings.ACCESS_LINK_TTL_MINUTES
        context = {"url": url, "ttl_minutes": ttl, "email": email}

        try:
            subject = _("Your login link")
            text_body = render_to_string(
                doorman_settings.TEMPLATE_ACCESS_LINK_EMAIL_TXT, context
            )
            html_body = render_to_string(
                doorman_settings.TEMPLATE_ACCESS_LINK_EMAIL_HTML, context
            )

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=None,
                to=[email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)

            logger.info("Access link email sent", extra={"subject_id": str(customer.subject_id)})
            return True
        except Exception:
            logger.error(
                "Access link email send failed",
                extra={"subject_id": str(customer.subject_id)},
            )
            return False

    def get_delivery_chain(self, target: str) -> list[str]:
        """
        Get the delivery chain for a target.

        Returns the canonical DELIVERY_CHAIN configured for the installation.
        An empty chain delegates delivery to MESSAGE_SENDER_CLASS.
        """
        chain = list(doorman_settings.DELIVERY_CHAIN)
        if self.login_handle(target).kind == "phone":
            return [method for method in chain if method != "email"]
        return [method for method in chain if method not in {"whatsapp", "sms"}]

    # ===========================================
    # Lifecycle hooks
    # ===========================================

    def on_customer_authenticated(
        self,
        request: HttpRequest,
        customer: IdentityView,
        user,
        method: str,
    ) -> None:
        """
        Called after successful authentication.

        Override for custom post-auth logic (analytics, sync, etc.).
        Signals still fire independently.

        Args:
            request: Django request.
            customer: Authenticated customer.
            user: Django User.
            method: Auth method (access_link, verification_code).
        """
        pass

    def on_device_trusted(
        self,
        request: HttpRequest,
        customer: IdentityView,
        device: TrustedDevice,
    ) -> None:
        """Called after a device is marked as trusted."""
        pass

    def on_login_failed(
        self,
        request: HttpRequest | None,
        target: str,
        reason: str,
    ) -> None:
        """Called when a login attempt fails."""
        pass

    # ===========================================
    # Configuration
    # ===========================================

    def should_auto_create_customer(self) -> bool:
        """Whether to auto-create customers on first login."""
        return doorman_settings.AUTO_CREATE_CUSTOMER

    def is_login_allowed(self, target: str, method: str) -> bool:
        """
        Whether login is allowed for this target/method.

        Override to block specific targets or methods.
        """
        return True

    # ===========================================
    # Redirects
    # ===========================================

    def get_login_redirect_url(self, request: HttpRequest, customer: IdentityView) -> str:
        """Get the URL to redirect to after login."""
        return doorman_settings.LOGIN_REDIRECT_URL

    def get_logout_redirect_url(self, request: HttpRequest) -> str:
        """Get the URL to redirect to after logout."""
        return doorman_settings.LOGOUT_REDIRECT_URL
