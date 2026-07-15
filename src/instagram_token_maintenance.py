from __future__ import annotations

import argparse
import os
import sys
from datetime import timezone

from src.config import Settings
from src.services.instagram_token_service import InstagramTokenService, InstagramTokenState


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _write_summary(state: InstagramTokenState, mode: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    valid_label = "desconhecido"
    if state.valid is True:
        valid_label = "sim"
    elif state.valid is False:
        valid_label = "não"

    lines = [
        "## Saúde do token do Instagram",
        f"- modo: `{mode}`",
        f"- válido: **{valid_label}**",
        f"- refresh nesta execução: **{'sim' if state.refreshed else 'não'}**",
        f"- suporta auto-refresh: **{'sim' if state.can_auto_refresh else 'não'}**",
    ]

    if state.expires_at:
        lines.append(f"- expira em: `{state.expires_at.astimezone(timezone.utc).isoformat()}`")
    if state.expires_in_days is not None:
        lines.append(f"- dias restantes: **{state.expires_in_days}**")
    if state.note:
        lines.append(f"- observação: {state.note}")
    if state.error:
        lines.append(f"- erro: {state.error}")

    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _emit_state(state: InstagramTokenState, mode: str) -> None:
    if state.access_token:
        print(f"::add-mask::{state.access_token}")

    _write_output("access_token", state.access_token)
    _write_output("token_refreshed", "true" if state.refreshed else "false")
    _write_output("token_valid", "true" if state.valid is True else "false" if state.valid is False else "unknown")
    _write_output("supports_auto_refresh", "true" if state.can_auto_refresh else "false")
    _write_output("expires_in_days", "" if state.expires_in_days is None else str(state.expires_in_days))
    _write_output("expires_at", "" if state.expires_at is None else state.expires_at.isoformat())
    _write_output("status_note", state.note.replace("\n", " ").strip())
    _write_summary(state, mode)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mantem e inspeciona o token do Instagram usado pelo bot.")
    parser.add_argument(
        "mode",
        choices=("status", "ensure", "refresh"),
        help="status: inspeciona; ensure: refresca se estiver perto de expirar; refresh: força renovação agora.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = Settings()
    service = InstagramTokenService(settings)

    if args.mode == "ensure" and settings.instagram_publish_mode.lower() != "real":
        state = InstagramTokenState(
            access_token=(settings.instagram_access_token or "").strip(),
            valid=None,
            note="Modo mock ativo; checagem/refresh do token foi ignorada.",
        )
        _emit_state(state, args.mode)
        print(state.note)
        return

    try:
        if args.mode == "status":
            state = service.inspect_token((settings.instagram_access_token or "").strip())
        elif args.mode == "refresh":
            state = service.ensure_token(force_refresh=True)
        else:
            state = service.ensure_token(force_refresh=False)
    except Exception as exc:
        state = InstagramTokenState(
            access_token=(settings.instagram_access_token or "").strip(),
            valid=False,
            can_auto_refresh="graph.instagram.com" in (settings.instagram_api_host or "").lower(),
            note=str(exc),
            error=str(exc),
        )
        _emit_state(state, args.mode)
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    _emit_state(state, args.mode)

    if state.error:
        print(state.error, file=sys.stderr)
        raise SystemExit(1)

    if state.valid is False:
        print(state.note, file=sys.stderr)
        raise SystemExit(1)

    print(state.note or "Token processado com sucesso.")


if __name__ == "__main__":
    main()
