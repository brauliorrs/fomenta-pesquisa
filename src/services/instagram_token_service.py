from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from src.config import Settings


@dataclass
class InstagramTokenState:
    access_token: str
    refreshed: bool = False
    valid: bool | None = None
    checked_with_debug: bool = False
    expires_at: datetime | None = None
    expires_in_seconds: int | None = None
    expires_in_days: int | None = None
    can_auto_refresh: bool = False
    note: str = ""
    error: str = ""


class InstagramTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    def ensure_token(self, force_refresh: bool = False) -> InstagramTokenState:
        token = (self.settings.instagram_access_token or "").strip()
        if not token:
            return InstagramTokenState(
                access_token="",
                valid=False,
                note="INSTAGRAM_ACCESS_TOKEN ausente.",
                error="INSTAGRAM_ACCESS_TOKEN ausente.",
            )

        if not self._supports_instagram_login_refresh():
            return InstagramTokenState(
                access_token=token,
                valid=True,
                note=(
                    "Stack de publicacao nao usa graph.instagram.com. "
                    "A automacao de refresh implementada aqui cobre o fluxo Instagram Login."
                ),
            )

        state = self.inspect_token(token)
        if state.valid is False:
            return state

        should_refresh = force_refresh
        if not should_refresh and state.checked_with_debug and state.expires_in_days is not None:
            should_refresh = state.expires_in_days <= self.settings.instagram_token_refresh_threshold_days

        if not should_refresh:
            if not state.note:
                state.note = "Token mantido sem refresh nesta execucao."
            return state

        refreshed_token, expires_in = self.refresh_token(token)
        refreshed_state = self.inspect_token(refreshed_token)
        refreshed_state.access_token = refreshed_token
        refreshed_state.refreshed = True
        refreshed_state.can_auto_refresh = True

        if not refreshed_state.checked_with_debug:
            refreshed_state.valid = True
            refreshed_state.expires_in_seconds = expires_in
            refreshed_state.expires_in_days = self._seconds_to_days(expires_in)
            refreshed_state.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        refreshed_state.note = "Token renovado com sucesso."
        return refreshed_state

    def inspect_token(self, token: str) -> InstagramTokenState:
        token = (token or "").strip()
        state = InstagramTokenState(access_token=token, can_auto_refresh=self._supports_instagram_login_refresh())
        if not token:
            state.valid = False
            state.note = "INSTAGRAM_ACCESS_TOKEN ausente."
            state.error = state.note
            return state

        if not self.settings.meta_app_id or not self.settings.meta_app_secret:
            state.note = (
                "META_APP_ID/META_APP_SECRET ausentes. "
                "Nao foi possivel inspecionar a expiracao; o refresh programatico ainda pode funcionar."
            )
            return state

        try:
            payload = self._debug_token(token)
        except Exception as exc:
            state.note = f"Nao foi possivel inspecionar o token via debug_token: {exc}"
            return state

        data = payload.get("data") or {}
        state.checked_with_debug = True
        state.valid = bool(data.get("is_valid"))
        expires_at_value = data.get("expires_at")
        if isinstance(expires_at_value, (int, float)) and expires_at_value > 0:
            state.expires_at = datetime.fromtimestamp(int(expires_at_value), tz=timezone.utc)
            seconds_left = int(expires_at_value - datetime.now(timezone.utc).timestamp())
            state.expires_in_seconds = max(seconds_left, 0)
            state.expires_in_days = self._seconds_to_days(seconds_left)

        if state.valid is False:
            state.error = "Token da Meta/Instagram invalido ou expirado."
            state.note = state.error
            return state

        if state.expires_in_days is not None:
            state.note = f"Token valido; expira em aproximadamente {state.expires_in_days} dia(s)."
        else:
            state.note = "Token valido; a expiracao nao foi informada pelo debug_token."
        return state

    def refresh_token(self, token: str) -> tuple[str, int]:
        if not self._supports_instagram_login_refresh():
            raise RuntimeError(
                "O refresh automatico foi implementado apenas para o fluxo Instagram Login em graph.instagram.com."
            )

        response = self.session.get(
            "https://graph.instagram.com/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": token,
            },
            timeout=60,
        )
        self._raise_for_status_with_details(response, "Falha ao renovar token do Instagram")
        payload = response.json()
        refreshed_token = str(payload.get("access_token") or "").strip()
        expires_in = int(payload.get("expires_in") or 0)
        if not refreshed_token:
            raise RuntimeError("A Meta nao retornou um access_token renovado.")
        return refreshed_token, expires_in

    def _debug_token(self, token: str) -> dict:
        app_access_token = f"{self.settings.meta_app_id}|{self.settings.meta_app_secret}"
        response = self.session.get(
            "https://graph.facebook.com/debug_token",
            params={
                "input_token": token,
                "access_token": app_access_token,
            },
            timeout=60,
        )
        self._raise_for_status_with_details(response, "Falha ao consultar debug_token")
        return response.json()

    def _supports_instagram_login_refresh(self) -> bool:
        return "graph.instagram.com" in (self.settings.instagram_api_host or "").lower()

    def _raise_for_status_with_details(self, response: requests.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()
            try:
                detail = json.dumps(response.json(), ensure_ascii=False)
            except Exception:
                detail = detail[:1000]
            raise RuntimeError(f"{context}: HTTP {response.status_code} - {detail}") from exc

    def _seconds_to_days(self, seconds_left: int) -> int:
        if seconds_left <= 0:
            return 0
        return max(1, int((seconds_left + 86399) // 86400))
