from __future__ import annotations

from datetime import date
import re

from src.models import Edital
from src.services.normalize_service import NormalizeService
from src.utils.dates import parse_date


class RenderService:
    def __init__(self) -> None:
        self.normalize_service = NormalizeService()

    def build_caption(self, edital: Edital) -> str:
        prazo = self._format_date(edital.data_expiracao)
        abertura = self._format_date(edital.data_abertura)
        urgency = self._build_urgency_label(edital.data_expiracao)
        titulo = self._display_text(edital.titulo)
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
                'Link oficial para copiar e colar no navegador:',
                self._display_text(edital.link),
                '',
                'Salve este post para consultar depois e compartilhe com quem pode aproveitar esta oportunidade.',
                'No post do perfil, o link oficial e mais informações ficam logo abaixo na legenda.',
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
            'card_footer_note': 'Link e detalhes no post do perfil',
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

    def _build_hashtags(self, edital: Edital) -> str:
        tags = ['#Edital', '#Pesquisa', '#OportunidadeAcademica']
        source_map = {
            'CNPQ': '#CNPq',
            'CAPES': '#CAPES',
            'CONFAP': '#CONFAP',
            'IPEA': '#IPEA',
        }
        source_tag = source_map.get(edital.fonte.upper())
        if source_tag:
            tags.append(source_tag)

        category = edital.categoria.lower()
        if 'bolsa' in category:
            tags.append('#Bolsa')
        if 'pesquisa' in category:
            tags.append('#FomentoPesquisa')

        unique_tags: list[str] = []
        for tag in tags:
            if tag not in unique_tags:
                unique_tags.append(tag)
        return ' '.join(unique_tags)

    def _build_card_header(self, edital: Edital) -> str:
        source_map = {
            'CNPQ': 'EDITAL CNPq',
            'CAPES': 'EDITAL CAPES',
            'CONFAP': 'EDITAL CONFAP',
            'IPEA': 'EDITAL IPEA',
        }
        return source_map.get(edital.fonte.upper(), f'EDITAL {edital.fonte.upper()}')

    def _build_card_title(self, edital: Edital) -> str:
        title = self._display_text(edital.titulo)
        replacements = (
            ('Chamada Pública', ''),
            ('Chamada CNPq/', ''),
            ('Chamada ', ''),
            ('Edital ', ''),
            ('Programa de ', ''),
        )
        for source, target in replacements:
            if len(title) <= 72:
                break
            title = title.replace(source, target, 1)

        title = ' '.join(title.split())
        title = self._refine_card_title(title)
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

    def _refine_card_title(self, title: str) -> str:
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
        return title

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
