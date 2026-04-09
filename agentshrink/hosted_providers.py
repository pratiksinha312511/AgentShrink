from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request

from agentshrink.app_setup import create_session, load_hosted_config


class AuthProviderError(RuntimeError):
    pass


def _hosted_auth_config() -> dict:
    return (load_hosted_config().get("auth") or {})


def _hosted_billing_config() -> dict:
    return (load_hosted_config().get("billing") or {})


class LocalSessionAuthProvider:
    name = "local-session"

    def describe(self) -> dict:
        return {"provider": self.name, "configured": True, "mode": "session"}


class Auth0AuthProvider:
    name = "auth0"

    def __init__(self) -> None:
        cfg = _hosted_auth_config()
        auth0 = cfg.get("auth0") or {}
        self.domain = (os.getenv("AUTH0_DOMAIN") or auth0.get("domain") or "").strip()
        self.client_id = (os.getenv("AUTH0_CLIENT_ID") or auth0.get("client_id") or "").strip()
        self.client_secret = (os.getenv("AUTH0_CLIENT_SECRET") or auth0.get("client_secret") or "").strip()
        self.audience = (os.getenv("AUTH0_AUDIENCE") or auth0.get("audience") or "").strip()
        self.redirect_path = (auth0.get("redirect_path") or "/auth").strip() or "/auth"

    def is_configured(self) -> bool:
        return bool(self.domain and self.client_id and self.client_secret)

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "configured": self.is_configured(),
            "domain": self.domain,
            "client_id": self.client_id,
            "redirect_path": self.redirect_path,
        }

    def start(self, redirect_uri: str) -> dict:
        if not self.is_configured():
            raise AuthProviderError("Auth0 is not configured. Set AUTH0_DOMAIN, AUTH0_CLIENT_ID, and AUTH0_CLIENT_SECRET.")
        state = secrets.token_urlsafe(18)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
        }
        if self.audience:
            params["audience"] = self.audience
        authorize_url = f"https://{self.domain}/authorize?{urllib.parse.urlencode(params)}"
        return {"authorize_url": authorize_url, "state": state}

    def callback(self, code: str, redirect_uri: str) -> dict:
        if not self.is_configured():
            raise AuthProviderError("Auth0 is not configured.")
        token_url = f"https://{self.domain}/oauth/token"
        token_payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        token_request = urllib.request.Request(
            token_url,
            data=json.dumps(token_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(token_request, timeout=10) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthProviderError("Auth0 did not return an access token.")
        userinfo_request = urllib.request.Request(
            f"https://{self.domain}/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(userinfo_request, timeout=10) as response:
            userinfo = json.loads(response.read().decode("utf-8"))
        user_name = userinfo.get("name") or userinfo.get("nickname") or userinfo.get("email") or "User"
        user_email = userinfo.get("email") or ""
        if not user_email:
            raise AuthProviderError("Auth0 user info did not include an email address.")
        session = create_session(user_name=user_name, user_email=user_email)
        return {"session": session, "userinfo": userinfo}


class ManualBillingProvider:
    name = "manual"

    def describe(self) -> dict:
        return {"provider": self.name, "configured": True}

    def checkout(self, *_, **__) -> dict:
        raise AuthProviderError("Manual billing mode does not expose a hosted checkout URL.")


class StripeBillingProvider:
    name = "stripe"

    def __init__(self) -> None:
        cfg = _hosted_billing_config()
        stripe = cfg.get("stripe") or {}
        self.secret_key = (os.getenv("STRIPE_SECRET_KEY") or stripe.get("secret_key") or "").strip()
        self.price_id = (os.getenv("STRIPE_PRICE_ID") or stripe.get("price_id") or "").strip()
        self.success_path = (stripe.get("success_path") or "/billing").strip() or "/billing"
        self.cancel_path = (stripe.get("cancel_path") or "/billing").strip() or "/billing"

    def is_configured(self) -> bool:
        return bool(self.secret_key and self.price_id)

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "configured": self.is_configured(),
            "price_id": self.price_id,
        }

    def checkout(self, *, public_app_url: str, tenant_id: str, account_id: str, account_name: str) -> dict:
        if not self.is_configured():
            raise AuthProviderError("Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID.")
        payload = {
            "mode": "subscription",
            "success_url": public_app_url.rstrip("/") + self.success_path,
            "cancel_url": public_app_url.rstrip("/") + self.cancel_path,
            "line_items[0][price]": self.price_id,
            "line_items[0][quantity]": "1",
            "metadata[tenant_id]": tenant_id,
            "metadata[account_id]": account_id,
            "metadata[account_name]": account_name,
        }
        request = urllib.request.Request(
            "https://api.stripe.com/v1/checkout/sessions",
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data


def get_auth_provider() -> LocalSessionAuthProvider | Auth0AuthProvider:
    auth_cfg = _hosted_auth_config()
    provider = (auth_cfg.get("provider") or "local-session").strip().lower()
    if provider == "auth0":
        return Auth0AuthProvider()
    return LocalSessionAuthProvider()


def get_billing_provider() -> ManualBillingProvider | StripeBillingProvider:
    billing_cfg = _hosted_billing_config()
    provider = (billing_cfg.get("provider") or "manual").strip().lower()
    if provider == "stripe":
        return StripeBillingProvider()
    return ManualBillingProvider()
