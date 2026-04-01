from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from src.models import Edital


class DedupService:
    def index_existing(self, editais: Iterable[dict]) -> dict[str, dict]:
        by_id = {item['id']: item for item in editais}
        by_alias: dict[str, str] = {}
        for item in editais:
            for key in self._build_keys(item):
                by_alias[key] = item['id']
        return {'by_id': by_id, 'by_alias': by_alias}

    def merge(self, existing: dict[str, dict], incoming: list[Edital]) -> tuple[list[Edital], dict[str, int]]:
        counters = {'novos': 0, 'prorrogados': 0, 'atualizados': 0, 'mantidos': 0, 'deduplicados_por_chave': 0}
        merged: list[Edital] = []
        seen_ids: set[str] = set()
        by_id = existing.get('by_id', {})
        by_alias = existing.get('by_alias', {})

        for edital in incoming:
            previous = by_id.get(edital.id)
            matched_by_alias = False

            if previous is None:
                for key in self._build_keys(edital):
                    alias_id = by_alias.get(key)
                    if alias_id and alias_id in by_id:
                        previous = by_id[alias_id]
                        matched_by_alias = True
                        break

            if previous is None:
                seen_ids.add(edital.id)
                counters['novos'] += 1
                merged.append(edital)
                continue

            seen_ids.add(previous['id'])
            updated = Edital(**previous)
            changed = False

            if matched_by_alias and updated.id != edital.id:
                counters['deduplicados_por_chave'] += 1

            for field_name in (
                'titulo',
                'orgao',
                'fonte',
                'uf',
                'categoria',
                'link',
                'resumo',
                'publico_alvo',
                'data_abertura',
                'data_expiracao',
                'data_ultima_coleta',
                'hash_conteudo',
                'instagram_caption',
                'pronto_para_postagem',
                'motivo_bloqueio_postagem',
                'revisao_humana_obrigatoria',
                'score_editorial',
                'pendencias_editoriais',
            ):
                current_value = getattr(updated, field_name)
                incoming_value = getattr(edital, field_name)
                new_value = self._resolve_field_value(field_name, current_value, incoming_value)
                if current_value != new_value:
                    setattr(updated, field_name, new_value)
                    changed = True

            previous_expiration = previous.get('data_expiracao')
            effective_expiration = updated.data_expiracao
            if effective_expiration and previous_expiration and effective_expiration != previous_expiration:
                updated.status = 'prorrogado'
                updated.houve_prorrogacao = True
                counters['prorrogados'] += 1
            elif previous.get('status') == 'encerrado' and edital.data_expiracao and edital.data_expiracao < edital.data_ultima_coleta[:10]:
                updated.status = 'encerrado'
                counters['mantidos'] += 1
            elif changed or previous.get('hash_conteudo') != edital.hash_conteudo:
                updated.status = 'atualizado'
                counters['atualizados'] += 1
            else:
                updated.status = previous.get('status', 'ativo')
                counters['mantidos'] += 1

            merged.append(updated)

        for edital_id, previous in by_id.items():
            if edital_id in seen_ids:
                continue
            merged.append(Edital(**previous))

        return merged, counters

    def collapse_payload(self, items: list[dict]) -> list[dict]:
        collapsed: dict[str, dict] = {}
        order: list[str] = []

        for item in items:
            key = self._canonical_key(item)
            current = collapsed.get(key)
            if current is None:
                collapsed[key] = dict(item)
                order.append(key)
                continue

            for field_name, incoming_value in item.items():
                current_value = current.get(field_name)
                resolved = self._resolve_field_value(field_name, current_value, incoming_value)
                if resolved not in (None, '', [], {}):
                    current[field_name] = resolved

            current['quantidade_postagens'] = max(
                int(current.get('quantidade_postagens', 0) or 0),
                int(item.get('quantidade_postagens', 0) or 0),
            )
            current['ultima_postagem'] = max(
                str(current.get('ultima_postagem') or ''),
                str(item.get('ultima_postagem') or ''),
            ) or None

        return [collapsed[key] for key in order]


    def _resolve_field_value(self, field_name: str, current_value, incoming_value):
        if field_name in {'data_abertura', 'data_expiracao', 'resumo', 'publico_alvo'} and current_value and not incoming_value:
            return current_value
        if field_name == 'link' and current_value and incoming_value:
            current_is_confap = 'news.confap.org.br' in str(current_value).lower()
            incoming_is_confap = 'news.confap.org.br' in str(incoming_value).lower()
            if not current_is_confap and incoming_is_confap:
                return current_value
        return incoming_value

    def _build_keys(self, item: Edital | dict) -> list[str]:
        source = self._normalize_text(self._value(item, 'fonte'))
        orgao = self._normalize_text(self._value(item, 'orgao'))
        titulo = self._normalize_text(self._value(item, 'titulo'))
        link = self._normalize_link(self._value(item, 'link'))

        keys: list[str] = []
        if source and link:
            keys.append(f'link|{source}|{link}')
        if source and titulo:
            keys.append(f'titulo|{source}|{titulo}')
        if source and orgao and titulo:
            keys.append(f'orgao_titulo|{source}|{orgao}|{titulo}')
        return keys

    def _canonical_key(self, item: Edital | dict) -> str:
        keys = self._build_keys(item)
        if keys:
            return keys[0]
        return self._normalize_text(self._value(item, 'id'))

    def _value(self, item: Edital | dict, field_name: str) -> str:
        if isinstance(item, dict):
            return str(item.get(field_name, '') or '')
        return str(getattr(item, field_name, '') or '')

    def _normalize_text(self, value: str) -> str:
        text = value.casefold().strip()
        text = re.sub(r'https?://', '', text)
        text = re.sub(r'[^a-z0-9]+', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _normalize_link(self, value: str) -> str:
        if not value:
            return ''
        parts = urlsplit(value.strip())
        clean_path = parts.path.rstrip('/')
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), clean_path, '', ''))
