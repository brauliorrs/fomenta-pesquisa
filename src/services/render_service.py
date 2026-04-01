from __future__ import annotations

from datetime import date
import re

from src.models import Edital
from src.utils.dates import parse_date


class RenderService:
    def build_caption(self, edital: Edital) -> str:
        prazo = self._format_date(edital.data_expiracao)
        abertura = self._format_date(edital.data_abertura)
        urgency = self._build_urgency_label(edital.data_expiracao)
        publico = edital.publico_alvo or 'Não informado'
        resumo = (edital.resumo or '').strip()
        resumo = resumo if len(resumo) <= 220 else resumo[:217].rstrip() + '...'

        lines = [f'Edital no radar: {edital.titulo}']
        if urgency:
            lines.append(urgency)

        lines.extend(
            [
                '',
                f'Órgão: {edital.orgao}',
                f'Público: {publico}',
                f'Abertura: {abertura}',
                f'Prazo: {prazo}',
            ]
        )

        if resumo and resumo != edital.titulo:
            lines.extend(['', f'Resumo: {resumo}'])

        lines.extend(
            [
                '',
                f'Link oficial: {edital.link}',
                '',
                'Salve este post para consultar depois e compartilhe com quem pode se interessar.',
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
        title = (edital.titulo or '').strip()
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
        summary = (edital.resumo or '').strip()
        if not summary or summary == edital.titulo:
            audience = (edital.publico_alvo or '').strip().lower()
            if audience:
                summary = f'Inscrições abertas para {audience}. Confira os critérios no link oficial.'
            else:
                summary = 'Inscrições abertas. Confira os critérios e o prazo no link oficial.'
        summary = ' '.join(summary.split())
        if len(summary) <= 160:
            return summary
        return summary[:157].rstrip(' ,;:-') + '...'
