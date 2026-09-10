"""Which providers this deployment offers.

A provider with no client id and secret is not merely disabled, it is absent:
it does not appear in ``/auth/oauth/providers``, so the frontend never renders
a button that could only fail. Obseil ships with nothing configured, which is
the correct default for a self-hosted tool - credentials belong to whoever runs
it, not to the project.
"""

from __future__ import annotations

from app.core.config import settings
from app.oauth.base import OAuthProvider
from app.oauth.providers import GitHubProvider, GoogleProvider


def build_providers() -> dict[str, OAuthProvider]:
    """Every provider that has credentials, keyed by name."""
    candidates: list[OAuthProvider] = [
        GoogleProvider(settings.oauth_google_client_id, settings.oauth_google_client_secret),
        GitHubProvider(settings.oauth_github_client_id, settings.oauth_github_client_secret),
    ]
    return {provider.name: provider for provider in candidates if provider.is_configured}


#: Built once at import, because credentials come from the environment and do
#: not change while the process runs.
_providers: dict[str, OAuthProvider] = build_providers()


def available_providers() -> list[OAuthProvider]:
    return list(_providers.values())


def get_provider(name: str) -> OAuthProvider | None:
    return _providers.get(name)


def reload_providers() -> None:
    """Rebuild from current settings. Used by tests that configure providers."""
    global _providers
    _providers = build_providers()
