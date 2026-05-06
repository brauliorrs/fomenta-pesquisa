from __future__ import annotations

from dataclasses import asdict
from typing import Any
from urllib.parse import urljoin, urlparse
import warnings

import requests
from bs4 import BeautifulSoup
from requests.exceptions import SSLError

from src.models import SourceConfig
from src.sources.generic_discovery import GenericDiscoverySource


class SourceDiscoveryService:
    DISCOVERY_HEADERS = {"User-Agent": "editais-bot-discovery/1.0"}
    DISCOVERY_KEYWORDS = (
        'edital',
        'editais',
        'chamada',
        'chamadas',
        'oportunidade',
        'oportunidades',
        'inscri',
        'submiss',
        'pesquisa',
        'inovacao',
        'inovação',
        'bolsa',
        'fomento',
    )
    CLOSED_HINTS = ('encerrad', 'resultado', 'homolog', 'cancelad', 'suspens', 'revogad')
    COMMON_PATHS = (
        '/editais',
        '/editais/',
        '/editais-abertos',
        '/editais-abertos/',
        '/editais-em-aberto',
        '/editais-em-aberto/',
        '/chamadas',
        '/chamadas/',
        '/chamadas-abertas',
        '/chamadas-abertas/',
        '/oportunidades',
        '/oportunidades/',
        '/oportunidades/chamadas-e-editais/',
        '/publicacoes/',
        '/noticias/',
    )

    def __init__(self, logger) -> None:
        self.logger = logger

    def run(
        self,
        active_sources: list[dict[str, Any]],
        planned_sources: dict[str, Any],
        candidate_sources: list[dict[str, Any]],
        now_iso: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        active_results: list[dict[str, Any]] = []
        candidate_results: list[dict[str, Any]] = []

        active_index = {str(item.get('sigla', '')).upper(): item for item in active_sources}

        for source in active_sources:
            result = self._audit_active_source(source)
            active_results.append(result)
            detected_page = result.get('pagina_editais_detectada')
            if detected_page and detected_page != source.get('pagina_editais'):
                source['pagina_editais'] = detected_page
            detected_site = result.get('site_oficial_detectado')
            if detected_site and detected_site != source.get('site_oficial'):
                source['site_oficial'] = detected_site

        for candidate in candidate_sources:
            result = self._evaluate_candidate(candidate, active_index, now_iso)
            candidate_results.append(result)
            planned_sources = self._upsert_planned_source(planned_sources, candidate, result, now_iso)

            if result.get('auto_activated') and not active_index.get(candidate['sigla'].upper()):
                new_source = self._build_auto_source_config(candidate, result)
                active_sources.append(new_source)
                active_index[candidate['sigla'].upper()] = new_source

        payload = {
            'generated_at': now_iso,
            'sumario': {
                'fontes_ativas_auditadas': len(active_results),
                'candidatas_avaliadas': len(candidate_results),
                'fontes_ativas_atualizadas': sum(1 for item in active_results if item.get('atualizada')),
                'candidatas_viaveis': sum(1 for item in candidate_results if item.get('viavel_monitoramento')),
                'candidatas_auto_ativadas': sum(1 for item in candidate_results if item.get('auto_activated')),
            },
            'fontes_ativas': active_results,
            'candidatas': candidate_results,
        }
        return active_sources, planned_sources, payload

    def _audit_active_source(self, source: dict[str, Any]) -> dict[str, Any]:
        current_page = str(source.get('pagina_editais', '')).strip()
        site_oficial = str(source.get('site_oficial', '')).strip() or current_page
        current_probe = self._probe_url(current_page) if current_page else self._empty_probe()
        best_candidate = current_probe

        if not self._looks_viable(current_probe):
            discovered = self._discover_best_page(site_oficial, current_page=current_page)
            if (
                discovered.get('score', 0) > current_probe.get('score', 0)
                and self._is_listing_page(discovered.get('final_url', ''))
            ):
                best_candidate = discovered

        detected_page = best_candidate.get('final_url') or current_page
        return {
            'sigla': source.get('sigla'),
            'nome': source.get('nome'),
            'status': 'ok' if self._looks_viable(best_candidate) else 'atencao',
            'site_oficial_detectado': site_oficial,
            'pagina_editais_anterior': current_page,
            'pagina_editais_detectada': detected_page,
            'score': best_candidate.get('score', 0),
            'status_code': best_candidate.get('status_code'),
            'motivo': best_candidate.get('reason', ''),
            'atualizada': bool(detected_page and detected_page != current_page and self._looks_viable(best_candidate)),
            'keyword_hits': best_candidate.get('keyword_hits', 0),
            'preview_anchor_hits': best_candidate.get('anchor_hits', 0),
        }

    def _evaluate_candidate(
        self,
        candidate: dict[str, Any],
        active_index: dict[str, dict[str, Any]],
        now_iso: str,
    ) -> dict[str, Any]:
        sigla = str(candidate.get('sigla', '')).upper()
        site_oficial = str(candidate.get('site_oficial', '')).strip()
        hint_page = str(candidate.get('pagina_editais_hint', '')).strip()

        if sigla in active_index:
            active_source = active_index[sigla]
            return {
                'sigla': sigla,
                'nome': candidate.get('nome'),
                'segmento': candidate.get('segmento'),
                'status': 'ja_monitorada',
                'viavel_monitoramento': True,
                'auto_activated': False,
                'site_oficial_detectado': active_source.get('site_oficial', site_oficial),
                'pagina_editais_detectada': active_source.get('pagina_editais', hint_page),
                'score': 999,
                'preview_count': 0,
                'preview_titulos': [],
                'motivo': 'Fonte ja esta no hall ativo de monitoramento.',
                'checked_at': now_iso,
            }

        best_candidate = self._discover_best_page(
            site_oficial,
            current_page=hint_page,
            extra_paths=tuple(candidate.get('candidate_paths', []) or ()),
            anchor_keywords=tuple(candidate.get('anchor_keywords', []) or ()),
        )
        preview_count, preview_titles = self._preview_candidate(candidate, best_candidate)
        viable = self._looks_viable(best_candidate) and preview_count > 0
        auto_activate = (
            candidate.get('activation_mode') == 'auto_when_viable'
            and viable
            and best_candidate.get('score', 0) >= 6
            and str(candidate.get('parser', '')).strip().lower() in {'generic', 'generic_discovery'}
        )

        reason = best_candidate.get('reason', '')
        if viable and not reason:
            reason = 'Pagina oficial com sinais de edital aberto e parse generico viavel.'
        elif not viable and not reason:
            reason = 'Nao foi possivel validar uma pagina oficial viavel para monitoramento automatico.'

        return {
            'sigla': sigla,
            'nome': candidate.get('nome'),
            'segmento': candidate.get('segmento'),
            'status': 'viavel' if viable else 'pendente',
            'viavel_monitoramento': viable,
            'auto_activated': auto_activate,
            'site_oficial_detectado': site_oficial,
            'pagina_editais_detectada': best_candidate.get('final_url', hint_page),
            'score': best_candidate.get('score', 0),
            'preview_count': preview_count,
            'preview_titulos': preview_titles,
            'motivo': reason,
            'checked_at': now_iso,
        }

    def _build_auto_source_config(self, candidate: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        config = SourceConfig(
            nome=str(candidate.get('nome', '')).strip(),
            sigla=str(candidate.get('sigla', '')).strip().upper(),
            uf=str(candidate.get('uf', 'BR')).strip().upper() or 'BR',
            site_oficial=str(result.get('site_oficial_detectado') or candidate.get('site_oficial') or '').strip(),
            pagina_editais=str(result.get('pagina_editais_detectada') or candidate.get('pagina_editais_hint') or '').strip(),
            tipo_coleta=str(candidate.get('tipo_coleta', 'html')).strip() or 'html',
            ativo=True,
            parser=str(candidate.get('parser', 'generic_discovery')).strip() or 'generic_discovery',
            selectors=dict(candidate.get('selectors', {}) or {}),
        )
        return asdict(config)

    def _upsert_planned_source(
        self,
        planned_sources: dict[str, Any],
        candidate: dict[str, Any],
        result: dict[str, Any],
        now_iso: str,
    ) -> dict[str, Any]:
        segmento = str(candidate.get('segmento', 'federais')).strip().lower()
        collection = planned_sources.setdefault(segmento, [])
        sigla = str(candidate.get('sigla', '')).upper()

        entry = next((item for item in collection if str(item.get('sigla', '')).upper() == sigla), None)
        status_integracao = (
            'integrada_auto'
            if result.get('auto_activated')
            else 'descoberta_viavel'
            if result.get('viavel_monitoramento')
            else 'pendente'
        )

        payload = {
            'sigla': sigla,
            'nome': candidate.get('nome'),
            'status_integracao': status_integracao,
            'prioridade': candidate.get('prioridade', 'mensal'),
            'estrategia': candidate.get('estrategia', 'descoberta_mensal'),
            'ultima_descoberta': now_iso,
            'site_oficial_detectado': result.get('site_oficial_detectado', ''),
            'pagina_editais_detectada': result.get('pagina_editais_detectada', ''),
            'motivo_descoberta': result.get('motivo', ''),
        }

        if entry is None:
            collection.append(payload)
            return planned_sources

        entry.update(payload)
        if entry.get('status_integracao') == 'integrada':
            entry['status_integracao'] = 'integrada'
        return planned_sources

    def _discover_best_page(
        self,
        site_oficial: str,
        current_page: str = '',
        extra_paths: tuple[str, ...] = (),
        anchor_keywords: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        candidates: list[str] = []
        seen: set[str] = set()

        def register(url: str) -> None:
            cleaned = str(url or '').strip()
            if not cleaned or cleaned in seen:
                return
            seen.add(cleaned)
            candidates.append(cleaned)

        register(current_page)
        register(site_oficial)
        for path in (*extra_paths, *self.COMMON_PATHS):
            if site_oficial:
                register(urljoin(site_oficial.rstrip('/') + '/', path.lstrip('/')))

        homepage_probe = self._probe_url(site_oficial)
        if homepage_probe.get('html'):
            for discovered_link in self._extract_candidate_links(
                homepage_probe['html'],
                homepage_probe.get('final_url') or site_oficial,
                anchor_keywords or self.DISCOVERY_KEYWORDS,
            ):
                register(discovered_link)

        best = self._empty_probe()
        for url in candidates:
            probe = self._probe_url(url)
            if probe.get('score', 0) > best.get('score', 0):
                best = probe
        return best

    def _extract_candidate_links(
        self,
        html: str,
        base_url: str,
        anchor_keywords: tuple[str, ...],
    ) -> list[str]:
        soup = BeautifulSoup(html, 'html.parser')
        links: list[str] = []
        seen: set[str] = set()
        base_host = urlparse(base_url).netloc

        for anchor in soup.select('a[href]'):
            href = str(anchor.get('href') or '').strip()
            text = anchor.get_text(' ', strip=True).lower()
            full_href = urljoin(base_url, href)
            full_lower = full_href.lower()
            if not full_href.startswith(('http://', 'https://')):
                continue
            if urlparse(full_href).netloc != base_host:
                continue
            if full_href in seen:
                continue
            signal = f'{text} {full_lower}'
            if not any(keyword in signal for keyword in anchor_keywords):
                continue
            seen.add(full_href)
            links.append(full_href)
        return links

    def _preview_candidate(self, candidate: dict[str, Any], best_candidate: dict[str, Any]) -> tuple[int, list[str]]:
        if not self._looks_viable(best_candidate):
            return 0, []
        parser_name = str(candidate.get('parser', '')).strip().lower()
        if parser_name not in {'generic', 'generic_discovery'}:
            return 0, []

        selectors = dict(candidate.get('selectors', {}) or {})
        if not selectors.get('item'):
            return 0, []

        config = SourceConfig(
            nome=str(candidate.get('nome', '')).strip(),
            sigla=str(candidate.get('sigla', '')).strip().upper(),
            uf=str(candidate.get('uf', 'BR')).strip().upper() or 'BR',
            site_oficial=str(candidate.get('site_oficial', '')).strip(),
            pagina_editais=str(best_candidate.get('final_url', '')).strip(),
            tipo_coleta=str(candidate.get('tipo_coleta', 'html')).strip() or 'html',
            ativo=True,
            parser='generic_discovery',
            selectors=selectors,
        )
        try:
            source = GenericDiscoverySource(config)
            items = source.parse(best_candidate.get('html', ''))
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning('Falha no preview da descoberta %s: %s', candidate.get('sigla'), exc)
            return 0, []
        titles = [str(item.get('titulo', '')).strip() for item in items if str(item.get('titulo', '')).strip()]
        return len(titles), titles[:5]

    def _probe_url(self, url: str) -> dict[str, Any]:
        if not url:
            return self._empty_probe(reason='URL ausente.')

        try:
            response = requests.get(url, headers=self.DISCOVERY_HEADERS, timeout=30)
            response.raise_for_status()
        except SSLError:
            try:
                warnings.filterwarnings('ignore', message='Unverified HTTPS request')
                response = requests.get(url, headers=self.DISCOVERY_HEADERS, timeout=30, verify=False)
                response.raise_for_status()
            except Exception as exc:
                return self._empty_probe(url=url, reason=f'Falha SSL/HTTP: {exc}')
        except Exception as exc:
            return self._empty_probe(url=url, reason=f'Falha HTTP: {exc}')

        if not response.encoding and response.apparent_encoding:
            response.encoding = response.apparent_encoding
        elif response.apparent_encoding and response.encoding.lower() == 'iso-8859-1':
            response.encoding = response.apparent_encoding

        html = response.text
        text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
        lower_text = text.lower()
        keyword_hits = sum(lower_text.count(keyword) for keyword in self.DISCOVERY_KEYWORDS)
        anchor_hits = html.lower().count('<a')
        score = keyword_hits + min(anchor_hits, 10)
        if any(token in response.url.lower() for token in ('edital', 'editais', 'chamada', 'oportunidades')):
            score += 3
        if any(token in lower_text for token in self.CLOSED_HINTS):
            score -= 2
        if 'cloudflare' in lower_text or 'attention required' in lower_text:
            score -= 4

        reason = ''
        if keyword_hits == 0:
            reason = 'Pagina sem sinais editoriais fortes de edital.'
        elif 'cloudflare' in lower_text:
            reason = 'Pagina bloqueada por Cloudflare.'

        return {
            'url': url,
            'final_url': response.url,
            'status_code': response.status_code,
            'html': html,
            'score': score,
            'keyword_hits': keyword_hits,
            'anchor_hits': anchor_hits,
            'reason': reason,
        }

    def _looks_viable(self, probe: dict[str, Any]) -> bool:
        if not probe.get('final_url'):
            return False
        if probe.get('status_code') != 200:
            return False
        if probe.get('score', 0) < 4:
            return False
        if 'cloudflare' in str(probe.get('reason', '')).lower():
            return False
        return True

    def _is_listing_page(self, url: str) -> bool:
        lowered = str(url or '').lower()
        listing_markers = (
            '/editais',
            '/chamadas',
            '/oportunidades',
            '/publicacoes',
            '/aberto',
            '/abertas',
            'programas-abertos',
            'situacao=aberta',
        )
        return any(marker in lowered for marker in listing_markers)

    def _empty_probe(self, url: str = '', reason: str = '') -> dict[str, Any]:
        return {
            'url': url,
            'final_url': '',
            'status_code': None,
            'html': '',
            'score': 0,
            'keyword_hits': 0,
            'anchor_hits': 0,
            'reason': reason,
        }
