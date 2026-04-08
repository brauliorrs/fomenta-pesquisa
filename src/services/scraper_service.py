from __future__ import annotations

import io
import logging
import re
import unicodedata
import warnings
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.exceptions import SSLError

from src.models import Edital, SourceConfig
from src.services.normalize_service import NormalizeService
from src.services.render_service import RenderService
from src.sources.anp import ANPSource
from src.sources.basa import BASASource
from src.sources.bndes import BNDESSource
from src.sources.capes import CAPESSource
from src.sources.cnpq import CNPQSource
from src.sources.confap import CONFAPSource
from src.sources.decit import DECITSource
from src.sources.embrapa import EMBRAPASource
from src.sources.embrapii import EMBRAPIISource
from src.sources.facepe import FACEPESource
from src.sources.fapac import FAPACSource
from src.sources.fapeal import FAPEALSource
from src.sources.fapeam import FAPEAMSource
from src.sources.fapeap import FAPEAPSource
from src.sources.fapepi import FAPEPISource
from src.sources.fapdf import FAPDFSource
from src.sources.fapes import FAPESSource
from src.sources.fapesb import FAPESBSource
from src.sources.fapesq import FAPESQSource
from src.sources.fapeg import FAPEGSource
from src.sources.fapema import FAPEMASource
from src.sources.fapemat import FAPEMATSource
from src.sources.fapern import FAPERNSource
from src.sources.fapespa import FAPESPASource
from src.sources.fapesp import FAPESPSource
from src.sources.fapemig import FAPEMIGSource
from src.sources.fapergs import FAPERGSSource
from src.sources.fapero import FAPEROSource
from src.sources.fapitec import FAPITECSource
from src.sources.fapt import FAPTSource
from src.sources.fapesc import FAPESCSource
from src.sources.fappr import FAPPRSource
from src.sources.faperj import FAPERJSource
from src.sources.finep import FINEPSource
from src.sources.fiocruz import FIOCRUZSource
from src.sources.faps import FAPSource
from src.sources.fundeci import FUNDECISource
from src.sources.funcap import FUNCAPSource
from src.sources.fundect import FUNDECTSource
from src.sources.ipea import IPEASource
from src.sources.serrapilheira import SERRAPILHEIRASource

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


class ScraperService:
    PT_MONTHS = {
        'janeiro': 1,
        'fevereiro': 2,
        'marco': 3,
        'março': 3,
        'abril': 4,
        'maio': 5,
        'junho': 6,
        'julho': 7,
        'agosto': 8,
        'setembro': 9,
        'outubro': 10,
        'novembro': 11,
        'dezembro': 12,
    }

    DEADLINE_HINTS = (
        'inscri', 'submiss', 'encerramento', 'prazo final', 'prazo para', 'até', 'ate', 'se encerra', 'deadline'
    )

    OPENING_HINTS = (
        'publicado em', 'publicada em', 'publicação em', 'publicacao em', 'lançada em', 'lancada em', 'divulgada em', 'abertura em', 'lançamento da chamada', 'lancamento da chamada'
    )
    CLOSED_STATUS_HINTS = (
        'encerrad', 'fechad', 'resultad', 'cancelad', 'revogad', 'suspens', 'analise', 'análise'
    )

    STRICT_CONTEXT_SOURCES = {'CONFAP', 'CAPES'}
    OFFICIAL_LINK_EXCLUDE = ('news.confap.org.br', 'facebook.com', 'instagram.com', 'twitter.com', 'linkedin.com', 'youtube.com', 'confap.org.br', 'mailto:', 'tel:', 'mestradigital.com.br')

    def __init__(self, logger: logging.Logger, normalize_service: NormalizeService, render_service: RenderService) -> None:
        self.logger = logger
        self.normalize_service = normalize_service
        self.render_service = render_service

    def _build_source(self, config: SourceConfig):
        mapping = {
            'ANP': ANPSource,
            'BASA': BASASource,
            'BNDES': BNDESSource,
            'CNPQ': CNPQSource,
            'CAPES': CAPESSource,
            'CONFAP': CONFAPSource,
            'DECIT': DECITSource,
            'EMBRAPA': EMBRAPASource,
            'EMBRAPII': EMBRAPIISource,
            'FACEPE': FACEPESource,
            'FAPAC': FAPACSource,
            'FAPEAL': FAPEALSource,
            'FAPEAM': FAPEAMSource,
            'FAPEAP': FAPEAPSource,
            'FAPEPI': FAPEPISource,
            'FAPDF': FAPDFSource,
            'FAPES': FAPESSource,
            'FAPESB': FAPESBSource,
            'FAPESQ': FAPESQSource,
            'FAPEG': FAPEGSource,
            'FAPEMA': FAPEMASource,
            'FAPEMAT': FAPEMATSource,
            'FAPERN': FAPERNSource,
            'FAPESPA': FAPESPASource,
            'FAPESP': FAPESPSource,
            'FAPEMIG': FAPEMIGSource,
            'FAPERGS': FAPERGSSource,
            'FAPERO': FAPEROSource,
            'FAPITEC': FAPITECSource,
            'FAPT': FAPTSource,
            'FAPESC': FAPESCSource,
            'FAPPR': FAPPRSource,
            'FAPERJ': FAPERJSource,
            'FINEP': FINEPSource,
            'FIOCRUZ': FIOCRUZSource,
            'FAP': FAPSource,
            'FUNDECI': FUNDECISource,
            'FUNCAP': FUNCAPSource,
            'FUNDECT': FUNDECTSource,
            'IPEA': IPEASource,
            'SERRAPILHEIRA': SERRAPILHEIRASource,
        }
        source_class = mapping.get(config.sigla.upper())
        if source_class is None:
            raise ValueError(f'Fonte nao suportada: {config.sigla}')
        return source_class(config)

    def collect(self, configs: list[SourceConfig], collected_at: str) -> tuple[list[Edital], list[dict[str, str]]]:
        editais: list[Edital] = []
        errors: list[dict[str, str]] = []
        current_date = self.normalize_service.normalize_date(collected_at) or self._parse_collected_at(collected_at).date().isoformat()

        for config in configs:
            if not config.ativo:
                continue
            try:
                source = self._build_source(config)
                raw_items = source.collect()
                self.logger.info('Fonte %s retornou %s itens', config.sigla, len(raw_items))
                for item in raw_items:
                    if self._should_skip_closed_item(item, current_date):
                        continue
                    enriched_item = self._enrich_item(item, collected_at)
                    if self._should_skip_closed_item(enriched_item, current_date):
                        continue
                    edital = self._to_edital(enriched_item, collected_at)
                    if self._should_skip_closed_edital(edital, current_date):
                        continue
                    editais.append(edital)
            except Exception as exc:
                self.logger.exception('Erro ao processar fonte %s', config.sigla)
                errors.append({'fonte': config.sigla, 'erro': str(exc)})

        return editais, errors

    def _should_skip_closed_item(self, item: dict[str, Any], current_date: str) -> bool:
        status = self.normalize_service.clean_text(item.get('status')).lower()
        if status and any(hint in status for hint in self.CLOSED_STATUS_HINTS):
            return True

        expiration = self.normalize_service.normalize_date(item.get('data_expiracao'))
        if expiration and expiration < current_date:
            return True

        return False

    def _should_skip_closed_edital(self, edital: Edital, current_date: str) -> bool:
        if edital.status == 'encerrado':
            return True
        if edital.data_expiracao and edital.data_expiracao < current_date:
            return True
        return False

    def _enrich_item(self, item: dict[str, Any], collected_at: str) -> dict[str, Any]:
        link = self.normalize_service.clean_url(item.get('link'))
        if not link:
            return item

        response = self._request(link)
        if response is None:
            return item

        source = self.normalize_service.clean_text(item.get('fonte')).upper()
        base_dt = self._parse_collected_at(collected_at)
        soup, extraction_text, extraction_line_text, description = self._response_to_content(response)

        if source == 'CONFAP' and soup is not None:
            official_link = self._extract_official_link(soup)
            if official_link:
                item['link'] = official_link
                official_response = self._request(official_link)
                if official_response is not None:
                    official_soup, extraction_text, extraction_line_text, official_description = self._response_to_content(official_response)
                    if official_description:
                        description = official_description
                    pdf_link = self._extract_embedded_pdf_link(official_soup, official_response.url) if official_soup is not None else None
                    if pdf_link:
                        pdf_response = self._request(pdf_link)
                        if pdf_response is not None:
                            item['link'] = pdf_link
                            _, extraction_text, extraction_line_text, _ = self._response_to_content(pdf_response)

        if description and (not item.get('resumo') or item.get('resumo') == item.get('titulo')):
            item['resumo'] = description

        range_opening, range_expiration = self._extract_explicit_range(extraction_text)
        if range_opening and not item.get('data_abertura'):
            item['data_abertura'] = range_opening
        if range_expiration and not item.get('data_expiracao'):
            item['data_expiracao'] = range_expiration

        opening_date, expiration_date = self._extract_contextual_dates(extraction_line_text, collected_at, description)
        if opening_date and not item.get('data_abertura'):
            item['data_abertura'] = opening_date
        if expiration_date and not item.get('data_expiracao'):
            item['data_expiracao'] = expiration_date

        if item.get('link') and 'programacentelha.com.br' in item['link'] and not item.get('data_expiracao'):
            countdown_expiration = self._extract_centelha_deadline(item['link'])
            if countdown_expiration:
                item['data_expiracao'] = countdown_expiration

        extracted_dates = self._extract_dates(extraction_text, collected_at, description)
        if source not in self.STRICT_CONTEXT_SOURCES and extracted_dates and not item.get('data_abertura'):
            item['data_abertura'] = extracted_dates[0]
        if extracted_dates and not item.get('data_expiracao'):
            if len(extracted_dates) > 1 and source not in self.STRICT_CONTEXT_SOURCES:
                item['data_expiracao'] = extracted_dates[-1]
            elif description and any(token in description.lower() for token in self.DEADLINE_HINTS):
                item['data_expiracao'] = extracted_dates[-1]

        return item

    def _request(self, url: str) -> requests.Response | None:
        try:
            response = requests.get(url, headers={'User-Agent': 'editais-bot/1.0'}, timeout=30)
            response.raise_for_status()
        except SSLError:
            try:
                warnings.filterwarnings('ignore', message='Unverified HTTPS request')
                response = requests.get(url, headers={'User-Agent': 'editais-bot/1.0'}, timeout=30, verify=False)
                response.raise_for_status()
                self.logger.info('Fallback SSL sem verificacao usado para %s', url)
            except Exception as exc:
                self.logger.warning('Falha ao enriquecer item %s: %s', url, exc)
                return None
        except Exception as exc:
            self.logger.warning('Falha ao enriquecer item %s: %s', url, exc)
            return None

        refresh_url = self._extract_meta_refresh_url(response)
        if refresh_url and refresh_url != url:
            return self._request(refresh_url)
        return response

    def _extract_meta_refresh_url(self, response: requests.Response) -> str | None:
        content_type = (response.headers.get('content-type') or '').lower()
        if 'html' not in content_type:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        meta = soup.find('meta', attrs={'http-equiv': re.compile('refresh', re.I)})
        if not meta:
            return None
        content = meta.get('content') or ''
        match = re.search(r"url\s*=\s*['\"]?([^'\">]+)", content, flags=re.I)
        if not match:
            return None
        return urljoin(response.url, match.group(1).strip())

    def _response_to_content(self, response: requests.Response) -> tuple[BeautifulSoup | None, str, str, str | None]:
        content_type = (response.headers.get('content-type') or '').lower()
        final_url = response.url.lower()

        if 'pdf' in content_type or final_url.endswith('.pdf'):
            pdf_text = self._extract_pdf_text(response.content)
            return None, pdf_text, pdf_text, None

        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(' ', strip=True)
        line_text = soup.get_text('\n', strip=True)
        description = self._extract_meta_description(soup)
        return soup, text, line_text, description

    def _extract_pdf_text(self, content: bytes) -> str:
        if PdfReader is None:
            return ''
        try:
            reader = PdfReader(io.BytesIO(content))
            return '\n'.join((page.extract_text() or '') for page in reader.pages)
        except Exception as exc:
            self.logger.warning('Falha ao ler PDF de edital: %s', exc)
            return ''

    def _extract_centelha_deadline(self, link: str) -> str | None:
        match = re.match(r'https?://[^/]+', link)
        if not match:
            return None
        base_url = match.group(0)
        response = self._request(f'{base_url}/bloqueio/contador')
        if response is None:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None

        for key in ('date', 'dateFase2', 'dateFase3'):
            value = payload.get(key)
            if isinstance(value, list) and value and value[0]:
                normalized = self.normalize_service.normalize_date(str(value[0]))
                if normalized:
                    return normalized
        return None


    def _extract_embedded_pdf_link(self, soup: BeautifulSoup | None, base_url: str) -> str | None:
        if soup is None:
            return None
        candidates: list[tuple[str, int]] = []
        for anchor in soup.select('a[href]'):
            href = self.normalize_service.clean_url(anchor.get('href'))
            label = self.normalize_service.clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue
            full_href = urljoin(base_url, href)
            lower_href = full_href.lower()
            if not lower_href.endswith('.pdf'):
                continue
            if 'errata' in label or 'errata' in lower_href:
                continue

            score = 0
            if any(token in label for token in ('edital', 'chamada')):
                score += 3
            if 'edital' in lower_href or 'chamada' in lower_href:
                score += 2
            if 'formulario' in label or 'manual' in label:
                score -= 2
            if 'edital' in label and '2026' in label:
                score += 2

            candidates.append((full_href, score))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[1], len(item[0])))
        return candidates[0][0]

    def _extract_official_link(self, soup: BeautifulSoup) -> str | None:
        candidates: list[tuple[str, str]] = []
        selectors = (
            'article a[href]',
            '.entry-content a[href]',
            '.td-post-content a[href]',
            '.post-content a[href]',
            'main a[href]',
        )

        anchors = []
        for selector in selectors:
            anchors.extend(soup.select(selector))
        if not anchors:
            anchors = soup.select('a[href]')

        seen: set[str] = set()
        for anchor in anchors:
            href = self.normalize_service.clean_url(anchor.get('href'))
            if not href:
                continue
            href = href.split()[0].rstrip('.,);]')
            href = re.sub(r'/\.[A-ZÀ-Ú][^/]*$', '/', href)
            text = self.normalize_service.clean_text(anchor.get_text(' ', strip=True))
            if not href or href in seen or not href.startswith(('http://', 'https://')):
                continue
            seen.add(href)

            lower_href = href.lower()
            lower_text = text.lower()
            if any(token in lower_href for token in self.OFFICIAL_LINK_EXCLUDE):
                continue

            signal = f'{lower_text} {lower_href}'
            has_strong_signal = any(token in signal for token in ('edital', 'chamada', 'inscri', 'bolsa', 'programa', 'premio', 'prêmio', '.pdf'))
            path_part = lower_href.split('://', 1)[-1].split('/', 1)
            is_root = len(path_part) == 1 or not path_part[1].strip('/')
            if is_root and not has_strong_signal:
                continue

            candidates.append((href, text))

        if not candidates:
            return None

        preferred = sorted(
            candidates,
            key=lambda item: (
                0 if item[0].lower().endswith('.pdf') else 1,
                0 if any(token in f'{item[1].lower()} {item[0].lower()}' for token in ('edital', 'chamada', 'inscri', 'bolsa', 'programa', 'premio', 'prêmio')) else 1,
                0 if len(item[0].split('://', 1)[-1].split('/', 1)) > 1 and item[0].split('://', 1)[-1].split('/', 1)[1].strip('/') else 1,
                len(item[0]),
            ),
        )
        return preferred[0][0]


    def _normalize_match_text(self, value: str) -> str:
        normalized = unicodedata.normalize('NFKD', value.lower())
        ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
        return ascii_text.replace('?', 'c')

    def _extract_schedule_label_dates(self, lines: list[str], year_hint: int, base_dt: datetime) -> tuple[str | None, str | None]:
        opening: str | None = None
        expiration: str | None = None
        opening_markers = (
            'data de in?cio para submiss?o de propostas',
            'data de inicio para submissao de propostas',
            'submiss?o de propostas on-line',
            'submissao de propostas on-line',
            'submiss?o de propostas on line',
            'submissao de propostas on line',
        )
        expiration_markers = (
            'data-limite para submiss?o de propostas',
            'data-limite para submissao de propostas',
            '?ltimo dia para submiss?o de propostas',
            'ultimo dia para submiss?o de propostas',
            'ultimo dia para submissao de propostas',
        )
        for index, line in enumerate(lines):
            next_line = lines[index + 1] if index + 1 < len(lines) else ''
            lower = self._normalize_match_text(line)
            if any(marker in lower for marker in opening_markers):
                parsed = self._extract_first_date_from_text(next_line, year_hint, base_dt) or self._extract_first_date_from_text(line, year_hint, base_dt)
                if parsed:
                    opening = parsed
            if any(marker in lower for marker in expiration_markers):
                parsed = self._extract_first_date_from_text(next_line, year_hint, base_dt) or self._extract_first_date_from_text(line, year_hint, base_dt)
                if parsed:
                    expiration = parsed
        return opening, expiration

    def _extract_meta_description(self, soup: BeautifulSoup) -> str | None:
        for attrs in ({'property': 'og:description'}, {'name': 'description'}):
            node = soup.find('meta', attrs=attrs)
            content = node.get('content') if node else None
            if content:
                return self.normalize_service.clean_text(content)
        return None

    def _extract_explicit_range(self, text: str) -> tuple[str | None, str | None]:
        patterns = (
            r'Inscri(?:ç|c)(?:ões|oes):\s*(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})',
            r'Submiss[aã]o de propostas(?: on-line)?\s*(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})',
        )
        for pattern in patterns:
            range_match = re.search(pattern, text, flags=re.I)
            if not range_match:
                continue
            start_value, end_value = range_match.groups()
            start_dt = self.normalize_service.normalize_date(start_value)
            end_dt = self.normalize_service.normalize_date(end_value)
            return start_dt, end_dt

        extenso_match = re.search(
            r'Inscri(?:ç|c)(?:ões|oes)\s+de\s+(\d{1,2})\s+de\s+([A-Za-zçãéíóúâêôà]+)\s+a\s+(\d{1,2})\s+de\s+([A-Za-zçãéíóúâêôà]+)\s+de\s+(\d{4})',
            text,
            flags=re.I,
        )
        if extenso_match:
            start_day, start_month_name, end_day, end_month_name, year = extenso_match.groups()
            start_month = self.PT_MONTHS.get(start_month_name.lower())
            end_month = self.PT_MONTHS.get(end_month_name.lower())
            if start_month and end_month:
                try:
                    start_dt = datetime(int(year), start_month, int(start_day)).date().isoformat()
                    end_dt = datetime(int(year), end_month, int(end_day)).date().isoformat()
                    return start_dt, end_dt
                except ValueError:
                    return None, None
        return None, None

    def _extract_contextual_dates(self, line_text: str, collected_at: str, description: str | None) -> tuple[str | None, str | None]:
        lines = [self.normalize_service.clean_text(line) for line in line_text.splitlines() if self.normalize_service.clean_text(line)]
        base_dt = self._parse_collected_at(collected_at)
        year_hint = base_dt.year
        opening, expiration = self._extract_schedule_label_dates(lines, year_hint, base_dt)

        for index, line in enumerate(lines):
            lower = line.lower()
            match_line = self._normalize_match_text(line)
            next_line = lines[index + 1] if index + 1 < len(lines) else ''
            combined = f'{line} {next_line}'.strip()

            if any(marker in match_line for marker in ('data de inicio para submissao de propostas', 'submissao de propostas on-line', 'submissao de propostas on line')):
                parsed = self._extract_first_date_from_text(next_line, year_hint, base_dt) or self._extract_first_date_from_text(combined, year_hint, base_dt)
                if parsed:
                    opening = parsed
                    continue

            if any(marker in match_line for marker in ('data-limite para submissao de propostas', 'ultimo dia para submissao de propostas')):
                parsed = self._extract_first_date_from_text(next_line, year_hint, base_dt) or self._extract_first_date_from_text(combined, year_hint, base_dt)
                if parsed:
                    expiration = parsed
                    continue

            if expiration is None and any(hint in lower for hint in self.DEADLINE_HINTS):
                parsed = self._extract_first_date_from_text(combined, year_hint, base_dt) or self._extract_first_date_from_text(line, year_hint, base_dt) or self._extract_first_date_from_text(next_line, year_hint, base_dt)
                if parsed:
                    expiration = parsed

            if opening is None and any(hint in lower for hint in self.OPENING_HINTS):
                parsed = self._extract_first_date_from_text(combined, year_hint, base_dt) or self._extract_first_date_from_text(line, year_hint, base_dt) or self._extract_first_date_from_text(next_line, year_hint, base_dt)
                if parsed:
                    opening = parsed

        if expiration is None and description:
            expiration = self._extract_first_date_from_text(description, year_hint, base_dt)

        return opening, expiration

    def _extract_first_date_from_text(self, text: str, default_year: int, base_dt: datetime) -> str | None:
        if not text:
            return None

        text = re.sub(r'mar\?o', 'marco', text, flags=re.I)
        lower = text.lower()
        if re.search(r'(até|ate|prazo|encerr|inscri|submiss|envio|termina)[^.\n]{0,40}\bamanh[ãa]\b', lower):
            return (base_dt.date() + timedelta(days=1)).isoformat()
        if re.search(r'(publicad|divulgad|abertur|ontem)[^.\n]{0,40}\bontem\b', lower):
            return (base_dt.date() - timedelta(days=1)).isoformat()

        range_match = re.search(r'de\s+(\d{1,2})\s+de\s+([A-Za-zçãéíóúâêôà]+)\s+até\s+(?:as\s+\d{1,2}h\s+de\s+)?(\d{1,2})\s+de\s+([A-Za-zçãéíóúâêôà]+)', text, flags=re.I)
        if range_match:
            _, _, end_day, end_month_name = range_match.groups()
            month = self.PT_MONTHS.get(end_month_name.lower())
            if month:
                try:
                    return datetime(default_year, month, int(end_day)).date().isoformat()
                except ValueError:
                    return None

        slash_match = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text)
        if slash_match:
            day, month, year = map(int, slash_match.groups())
            try:
                return datetime(year, month, day).date().isoformat()
            except ValueError:
                return None

        ext_match = re.search(r'\b(\d{1,2}) de ([A-Za-zçãéíóúâêôà]+) de (\d{4})\b', text, flags=re.I)
        if ext_match:
            day, month_name, year = ext_match.groups()
            month = self.PT_MONTHS.get(month_name.lower())
            if month:
                try:
                    return datetime(int(year), month, int(day)).date().isoformat()
                except ValueError:
                    return None

        short_ext_match = re.search(r'(?:até|ate|encerramento das submissões:?|inscrições devem ser feitas até|submissões serão recebidas até|data-limite para submissão de propostas:?|último dia para submissão de propostas|ultimo dia para submissão de propostas|se encerra em|o prazo para inscrições irá de .*? até as? .*? de)\s*(\d{1,2}) de ([A-Za-zçãéíóúâêôà]+)(?: de (\d{4}))?', text, flags=re.I)
        if short_ext_match:
            day, month_name, explicit_year = short_ext_match.groups()
            month = self.PT_MONTHS.get(month_name.lower())
            year = int(explicit_year) if explicit_year else default_year
            if month:
                try:
                    return datetime(year, month, int(day)).date().isoformat()
                except ValueError:
                    return None

        return None

    def _extract_dates(self, text: str, collected_at: str, description: str | None = None) -> list[str]:
        text = re.sub(r'mar\?o', 'marco', text, flags=re.I)
        found: list[datetime] = []

        for day, month, year in re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text):
            try:
                found.append(datetime(int(year), int(month), int(day)))
            except ValueError:
                continue

        for day, month_name, year in re.findall(r'\b(\d{1,2}) de ([A-Za-zçãéíóúâêôà]+) de (\d{4})\b', text, flags=re.I):
            month = self.PT_MONTHS.get(month_name.lower())
            if not month:
                continue
            try:
                found.append(datetime(int(year), month, int(day)))
            except ValueError:
                continue

        if description:
            year_hint = self._infer_year(found, collected_at)
            for day, month_name in re.findall(r'(?:até|ate)\s+(\d{1,2}) de ([A-Za-zçãéíóúâêôà]+)', description, flags=re.I):
                month = self.PT_MONTHS.get(month_name.lower())
                if not month:
                    continue
                try:
                    found.append(datetime(year_hint, month, int(day)))
                except ValueError:
                    continue

        unique_sorted = sorted({dt.date().isoformat() for dt in found})
        return unique_sorted

    def _infer_year(self, found_dates: list[datetime], collected_at: str) -> int:
        if found_dates:
            return max(dt.year for dt in found_dates)
        parsed = self.normalize_service.normalize_date(collected_at)
        if parsed:
            return int(parsed[:4])
        return datetime.now().year

    def _parse_collected_at(self, collected_at: str) -> datetime:
        normalized = collected_at.replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.now()

    def _to_edital(self, item: dict[str, Any], collected_at: str) -> Edital:
        titulo = self.normalize_service.clean_text(item.get('titulo'))
        orgao = self.normalize_service.clean_text(item.get('orgao'))
        link = self.normalize_service.clean_url(item.get('link'))
        edital_id = self.normalize_service.build_edital_id(orgao, titulo, link)
        normalized = {
            'id': edital_id,
            'titulo': titulo,
            'orgao': orgao,
            'fonte': self.normalize_service.clean_text(item.get('fonte')),
            'uf': self.normalize_service.clean_text(item.get('uf')) or 'BR',
            'categoria': self.normalize_service.clean_text(item.get('categoria')) or 'geral',
            'link': link,
            'resumo': self.normalize_service.clean_text(item.get('resumo')),
            'publico_alvo': self.normalize_service.clean_text(item.get('publico_alvo')),
            'data_abertura': self.normalize_service.normalize_date(item.get('data_abertura')),
            'data_expiracao': self.normalize_service.normalize_date(item.get('data_expiracao')),
            'data_ultima_coleta': collected_at,
            'status': 'novo',
            'pronto_para_postagem': False,
            'motivo_bloqueio_postagem': '',
            'instagram_feed_publicado': False,
            'instagram_feed_media_id': '',
            'instagram_story_media_id': '',
            'instagram_story_asset': '',
        }
        normalized['hash_conteudo'] = self.normalize_service.content_hash(normalized)
        edital = Edital(**normalized)
        edital.instagram_caption = self.render_service.build_caption(edital)
        return edital
