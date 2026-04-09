from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from urllib.parse import urlparse

from src.models import Edital
from src.services.normalize_service import NormalizeService
from src.utils.dates import parse_date
from src.utils.hashing import slugify


class RenderService:
    def __init__(self) -> None:
        self.normalize_service = NormalizeService()

    def build_caption(self, edital: Edital) -> str:
        prazo = self._format_date(edital.data_expiracao)
        abertura = self._format_date(edital.data_abertura)
        urgency = self._build_urgency_label(edital.data_expiracao)
        titulo = self._preferred_title(edital)
        orgao = self._display_text(edital.orgao) or 'Não informado'
        publico = self._display_text(edital.publico_alvo) or 'Não informado'
        categoria = self._humanize_category(edital.categoria)
        resumo = self._build_caption_summary(edital)

        lines = [f'Oportunidade no radar: {titulo}']
        if urgency:
            lines.append(urgency)

        if resumo:
            lines.extend(['', resumo])

        lines.extend(
            [
                '',
                f'Instituição: {orgao}',
                f'Público-alvo: {publico}',
                f'Tipo: {categoria}',
                f'Abertura das inscrições: {abertura}',
                f'Prazo final: {prazo}',
            ]
        )

        lines.extend(
            [
                '',
                'Link oficial do edital:',
                self._display_text(edital.link),
                '',
                'Salve este post para consultar depois e compartilhe com quem pode aproveitar esta oportunidade.',
                'No post, o link do edital e os detalhes ficam logo abaixo na legenda.',
                '',
                self._build_hashtags(edital),
            ]
        )
        return '\n'.join(lines)

    def build_card_fields(self, edital: Edital) -> dict[str, str]:
        return {
            'card_header': self._build_card_header(edital),
            'card_title': self._build_card_title(edital),
            'card_deadline': self._build_card_deadline(edital.data_expiracao),
            'card_summary': self._build_card_summary(edital),
            'card_handle': '@editais.pesquisa',
            'card_footer_note': 'Link do edital e detalhes abaixo.',
        }

    def _format_date(self, value: str | None) -> str:
        parsed = parse_date(value)
        if not parsed:
            return 'Não informado'
        return parsed.strftime('%d/%m/%Y')

    def _build_urgency_label(self, expiration_date: str | None) -> str:
        parsed = parse_date(expiration_date)
        if not parsed:
            return ''
        days_left = (parsed.date() - date.today()).days
        if days_left < 0:
            return 'Prazo encerrado.'
        if days_left == 0:
            return 'Último dia de inscrição.'
        if days_left == 1:
            return 'Prazo encerra amanhã.'
        if days_left <= 7:
            return f'Prazo encerra em {days_left} dias.'
        return ''

    def _days_left(self, expiration_date: str | None) -> int | None:
        parsed = parse_date(expiration_date)
        if not parsed:
            return None
        return (parsed.date() - date.today()).days

    def _build_hashtags(self, edital: Edital) -> str:
        tags: list[str] = []
        title = self._display_text(edital.titulo).lower()
        summary = self._display_text(edital.resumo).lower()
        category = self._display_text(edital.categoria).lower()
        audience = self._display_text(edital.publico_alvo).lower()
        combined = ' '.join(part for part in (title, summary, category, audience) if part)
        days_left = self._days_left(edital.data_expiracao)

        for tag in ('EditalAberto', 'FomentoPesquisa', 'Pesquisa', 'Ciencia', 'OportunidadeAcademica'):
            self._append_hashtag(tags, tag)

        source_tag = self._build_source_hashtag(edital.fonte)
        if source_tag:
            self._append_hashtag(tags, source_tag)

        if 'pesquisa' in category or 'pesquisa' in combined:
            self._append_hashtag(tags, 'ProjetosDePesquisa')
        if 'bolsa' in category or 'bolsa' in combined:
            self._append_hashtag(tags, 'BolsaPesquisa')
        if 'selec' in category or 'selecao' in combined or 'seleção' in combined:
            self._append_hashtag(tags, 'Selecao')
        if any(token in combined for token in ('chamada', 'chamamento', 'edital')):
            self._append_hashtag(tags, 'ChamadaPublica')
        if any(token in combined for token in ('inov', 'centelha', 'startup', 'empreendedor')):
            self._append_hashtag(tags, 'Inovacao')
            self._append_hashtag(tags, 'Empreendedorismo')
        if any(token in combined for token in ('cooperacao', 'cooperação', 'internacional', 'brics')):
            self._append_hashtag(tags, 'CooperacaoCientifica')
        if any(token in combined for token in ('evento', 'congresso', 'seminario', 'seminário')):
            self._append_hashtag(tags, 'EventosCientificos')
        if any(token in combined for token in ('mulher', 'mulheres')):
            self._append_hashtag(tags, 'MulheresNaCiencia')

        if any(token in audience for token in ('pesquis', 'cientista')):
            self._append_hashtag(tags, 'Pesquisadores')
        if 'institui' in audience:
            self._append_hashtag(tags, 'InstituicoesDePesquisa')
        if any(token in audience for token in ('estudant', 'discente')):
            self._append_hashtag(tags, 'Estudantes')
        if any(token in audience for token in ('academica', 'acadêmica', 'universidade', 'universitario', 'universitário')):
            self._append_hashtag(tags, 'Universidades')
        if edital.uf and edital.uf.upper() not in {'', 'BR'}:
            self._append_hashtag(tags, f'Pesquisa{edital.uf.upper()}')
        if days_left is not None and days_left <= 7:
            self._append_hashtag(tags, 'PrazoFinal')

        return ' '.join(tags[:10])

    def _build_source_hashtag(self, fonte: str | None) -> str:
        normalized = self._display_text(fonte).upper()
        source_map = {
            'ANP': 'ANP',
            'CAPES': 'CAPES',
            'CNPQ': 'CNPq',
            'CONFAP': 'CONFAP',
            'EMBRAPA': 'EMBRAPA',
            'EMBRAPII': 'EMBRAPII',
            'FACEPE': 'FACEPE',
            'FAPEG': 'FAPEG',
            'FAPEMA': 'FAPEMA',
            'FAPEMAT': 'FAPEMAT',
            'FAPEMIG': 'FAPEMIG',
            'FAPERGS': 'FAPERGS',
            'FAPERJ': 'FAPERJ',
            'FAPES': 'FAPES',
            'FAPESB': 'FAPESB',
            'FAPESC': 'FAPESC',
            'FAPESP': 'FAPESP',
            'FAPPR': 'FundacaoAraucaria',
            'FINEP': 'FINEP',
            'FIOCRUZ': 'Fiocruz',
            'FUNDECT': 'FUNDECT',
            'IPEA': 'IPEA',
            'SERRAPILHEIRA': 'Serrapilheira',
        }
        mapped = source_map.get(normalized)
        if mapped:
            return mapped

        fallback = ''.join(part.capitalize() for part in slugify(normalized).split('_') if part)
        return fallback

    def _append_hashtag(self, tags: list[str], value: str | None) -> None:
        token = self._normalize_hashtag_token(value)
        if token and token not in tags:
            tags.append(token)

    def _normalize_hashtag_token(self, value: str | None) -> str:
        normalized = self._display_text(value)
        if not normalized:
            return ''
        token = ''.join(part.capitalize() for part in slugify(normalized).split('_') if part)
        if len(token) < 2:
            return ''
        return f'#{token}'

    def _build_card_header(self, edital: Edital) -> str:
        source_map = {
            'CNPQ': 'EDITAL CNPq',
            'CAPES': 'EDITAL CAPES',
            'CONFAP': 'EDITAL CONFAP',
            'IPEA': 'EDITAL IPEA',
        }
        return source_map.get(edital.fonte.upper(), f'EDITAL {edital.fonte.upper()}')

    def _build_card_title(self, edital: Edital) -> str:
        original_title = self._preferred_title(edital)
        title = original_title
        replacements = (
            ('Chamada Pública', ''),
            ('Chamada CNPq/', ''),
            ('Chamada conjunta ', ''),
            ('Chamada ', ''),
            ('Edital ', ''),
            ('Programa de ', ''),
        )
        for source, target in replacements:
            if len(title) <= 72:
                break
            candidate = title.replace(source, target, 1)
            if candidate == title:
                continue
            if not self._can_strip_card_prefix(candidate):
                continue
            title = candidate

        title = ' '.join(title.split())
        title = self._refine_card_title(title, edital, original_title)
        strong_breaks = (
            ' e homenageia ',
            ' com inscrições ',
            ' com inscricoes ',
            ' com recursos ',
            ' com apoio ',
            ' para apoiar ',
        )
        lowered = title.lower()
        for marker in strong_breaks:
            index = lowered.find(marker)
            if index > 28:
                candidate = title[:index].rstrip(' ,;:-')
                if len(candidate) >= 32:
                    title = candidate
                    break

        if len(title) <= 88:
            return title
        words = title.split()
        shortened: list[str] = []
        for word in words:
            trial = ' '.join(shortened + [word]).strip()
            if len(trial) > 88:
                break
            shortened.append(word)

        if shortened:
            return ' '.join(shortened).rstrip(' ,;:-')
        return title[:88].rstrip(' ,;:-')

    def _refine_card_title(self, title: str, edital: Edital, original_title: str) -> str:
        rewrites = (
            (
                r'^Terceira edição do Programa Centelha RO oferecerá recursos financeiros de até R\$?\s*80 mil\b.*$',
                'Programa Centelha RO oferece até R$ 80 mil',
            ),
            (
                r'^FAPERJ lança edital para jovens cientistas mulheres\b.*$',
                'FAPERJ lança edital para jovens cientistas mulheres',
            ),
            (
                r'^CAPES abre chamamento para criação de estatueta institucional\b.*$',
                'CAPES abre chamamento para criação de estatueta institucional',
            ),
        )
        for pattern, replacement in rewrites:
            if re.match(pattern, title, flags=re.I):
                return replacement

        refined = title.strip(' -:;')
        if self._looks_like_fragment(refined):
            return self._fallback_card_title(edital, original_title)
        return refined or self._fallback_card_title(edital, original_title)

    def _can_strip_card_prefix(self, title: str) -> bool:
        stripped = title.strip()
        if not stripped:
            return False

        match = re.search(r'[A-Za-zÀ-ÿ0-9]', stripped)
        if not match:
            return False

        first_visible = stripped[match.start()]
        if first_visible.isalpha() and first_visible.islower():
            return False
        return True

    def _looks_like_fragment(self, title: str) -> bool:
        if not title:
            return True

        lowered = title.lower()
        fragment_prefixes = (
            'de ',
            'do ',
            'da ',
            'dos ',
            'das ',
            'e ',
            'em ',
            'para ',
            'com ',
            'conjunta ',
            'propostas ',
        )
        if lowered.startswith(fragment_prefixes):
            return True

        if re.fullmatch(r'\d{1,2}/\d{4}\s*[-–—]?', title):
            return True

        if title.endswith('-') and len(title) <= 24:
            return True

        words = title.split()
        if len(words) <= 2 and any(char.isdigit() for char in title):
            return True

        return False

    def _fallback_card_title(self, edital: Edital, original_title: str) -> str:
        cleaned = original_title.strip()
        source_prefixes = (
            f'{edital.fonte.upper()} / ' if edital.fonte else '',
            f'{edital.fonte.upper()} - ' if edital.fonte else '',
            f'{edital.fonte.upper()}: ' if edital.fonte else '',
        )
        for prefix in source_prefixes:
            if prefix and cleaned.upper().startswith(prefix):
                candidate = cleaned[len(prefix):].strip()
                if candidate:
                    cleaned = candidate
                    break

        return cleaned.strip(' -:;') or original_title.strip()

    def _preferred_title(self, edital: Edital) -> str:
        original_title = self._display_text(edital.titulo)
        if not self._looks_like_fragment(original_title):
            return original_title

        link_title = self._title_from_link(edital.link, edital.fonte)
        if link_title and not self._looks_like_fragment(link_title):
            return link_title
        return original_title

    def _title_from_link(self, link: str | None, fonte: str | None) -> str:
        cleaned_link = self._display_text(link)
        if not cleaned_link:
            return ''

        path = urlparse(cleaned_link).path
        title = Path(path).stem
        if not title:
            return ''

        title = re.sub(r'^\d{4}[._-]\d{2}[._-]\d{2}[._-]?', '', title)
        title = title.replace('___', ' - ').replace('__', ' ').replace('_', ' ')
        title = re.sub(r'\bFNAL\b', '', title, flags=re.I)
        title = re.sub(r'\bFINAL\b', '', title, flags=re.I)
        title = re.sub(r'\bEdital[ -]+0*(\d{1,2})[ -]+(\d{4})\b', r'Edital \1/\2', title, flags=re.I)
        title = re.sub(r'\b0*(\d{1,2})[ -]+(\d{4})\b', r'\1/\2', title)
        if fonte:
            title = re.sub(rf'\b{re.escape(fonte)}\b', '', title, flags=re.I)
        title = re.sub(r'\bcatedras\b', 'Cátedras', title, flags=re.I)
        title = re.sub(r'\bcientista arretado\b', 'Cientista Arretado', title, flags=re.I)
        title = re.sub(r'\bbalanco energetico estadual\b', 'Balanço Energético Estadual', title, flags=re.I)
        title = re.sub(r'\bjornadapibic\b', 'Jornada PIBIC', title, flags=re.I)
        title = re.sub(r'\bprf\b', 'PRF', title, flags=re.I)
        title = re.sub(r'\bbfp\b', 'BFP', title, flags=re.I)
        title = re.sub(r'\s+-\s+-\s+', ' - ', title)
        title = re.sub(r'\s{2,}', ' ', title).strip(' -_')
        if not title:
            return ''
        return title[:1].upper() + title[1:]

    def _build_card_deadline(self, expiration_date: str | None) -> str:
        parsed = parse_date(expiration_date)
        if not parsed:
            return ''

        days_left = (parsed.date() - date.today()).days
        if days_left < 0:
            return 'PRAZO ENCERRADO'
        if days_left == 0:
            return 'ÚLTIMO DIA'
        if days_left == 1:
            return 'PRAZO: AMANHÃ'
        return f'PRAZO: {parsed.strftime("%d/%m")}'

    def _build_card_summary(self, edital: Edital) -> str:
        summary = self._extract_summary_excerpt(edital, max_chars=160)
        if summary:
            return summary

        audience = self._display_text(edital.publico_alvo)
        prazo = self._format_date(edital.data_expiracao)
        parts: list[str] = []
        if audience and audience != 'Não informado':
            parts.append(f'Voltado a {self._start_lower(audience)}.')
        else:
            parts.append('Inscrições abertas.')
        if prazo != 'Não informado':
            parts.append(f'Prazo final em {prazo}.')
        parts.append('Confira os critérios no edital.')
        return self._truncate_text(' '.join(parts), 160)

    def _build_caption_summary(self, edital: Edital) -> str:
        summary = self._extract_summary_excerpt(edital, max_chars=320)
        if summary:
            return summary

        audience = self._display_text(edital.publico_alvo)
        prazo = self._format_date(edital.data_expiracao)
        abertura = self._format_date(edital.data_abertura)
        category = self._humanize_category(edital.categoria).lower()

        opening = 'A oportunidade está aberta'
        if audience and audience != 'Não informado':
            opening += f' para {self._start_lower(audience)}'
        if category and category != 'não informado':
            opening += f' na categoria {category}'

        details = []
        if abertura != 'Não informado':
            details.append(f'abertura registrada em {abertura}')
        if prazo != 'Não informado':
            details.append(f'prazo final em {prazo}')

        if details:
            opening += ', com ' + ' e '.join(details)

        return opening.rstrip(' ,;:-') + '.'

    def _extract_summary_excerpt(self, edital: Edital, max_chars: int) -> str:
        title = self._display_text(edital.titulo)
        summary = self._sanitize_summary(edital.resumo)
        if not summary or summary == title:
            return ''

        sentences = self._split_sentences(summary)
        if not sentences:
            return ''

        selected: list[str] = []
        for sentence in sentences:
            candidate = ' '.join(selected + [sentence]).strip()
            if len(candidate) > max_chars:
                break
            selected.append(sentence)
            if len(candidate) >= min(180, max_chars):
                break

        excerpt = ' '.join(selected).strip()
        if excerpt:
            return excerpt

        first_sentence = sentences[0]
        if len(first_sentence) <= max_chars:
            return first_sentence
        return ''

    def _sanitize_summary(self, value: str | None) -> str:
        summary = self._display_text(value)
        if not summary:
            return ''
        summary = summary.replace('[…]', '').replace('[...]', '').replace('…', '...')
        summary = re.sub(r'\s+', ' ', summary).strip(' -')
        return summary

    def _split_sentences(self, value: str) -> list[str]:
        parts = re.split(r'(?<=[.!?])\s+', value)
        sentences: list[str] = []
        for part in parts:
            cleaned = part.strip(' ,;:-')
            if not cleaned:
                continue
            if cleaned.endswith('...'):
                continue
            if cleaned[-1] not in '.!?':
                cleaned = cleaned + '.'
            sentences.append(cleaned)
        return sentences

    def _truncate_text(self, value: str, max_chars: int) -> str:
        text = self._display_text(value)
        if len(text) <= max_chars:
            return text
        shortened = text[: max_chars - 3].rstrip(' ,;:-')
        if ' ' in shortened:
            shortened = shortened.rsplit(' ', 1)[0]
        return shortened.rstrip(' ,;:-') + '...'

    def _display_text(self, value: str | None) -> str:
        return self.normalize_service.clean_text(value)

    def _humanize_category(self, value: str | None) -> str:
        category = self._display_text(value)
        if not category:
            return 'Não informado'
        label = category.replace('_', ' ').strip()
        return label[:1].upper() + label[1:]

    def _start_lower(self, value: str) -> str:
        if not value:
            return value
        return value[:1].lower() + value[1:]
