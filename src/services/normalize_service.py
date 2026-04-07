from __future__ import annotations

import re
from typing import Any

from src.utils.dates import parse_date
from src.utils.hashing import short_hash, slugify


class NormalizeService:
    COMMON_REPAIRS = {
        'NÂº': 'Nº',
        'NÃº': 'Nú',
        'PÃºblica': 'Pública',
        'PÃºblico': 'Público',
        'Fundacao': 'Fundação',
        'fundacao': 'fundação',
        'Fundacoes': 'Fundações',
        'fundacoes': 'fundações',
        'Instituicoes': 'Instituições',
        'instituicoes': 'instituições',
        'Inscricoes': 'Inscrições',
        'inscricoes': 'inscrições',
        'Selecao': 'Seleção',
        'selecao': 'seleção',
        'Criterios': 'Critérios',
        'criterios': 'critérios',
        'Coordenacao': 'Coordenação',
        'coordenacao': 'coordenação',
        'Aperfeicoamento': 'Aperfeiçoamento',
        'aperfeicoamento': 'aperfeiçoamento',
        'Pessoal': 'Pessoal',
        'Nivel': 'Nível',
        'nivel': 'nível',
        'academica': 'acadêmica',
        'Academica': 'Acadêmica',
        'cientifico': 'científico',
        'Cientifico': 'Científico',
        'tecnologico': 'tecnológico',
        'Tecnologico': 'Tecnológico',
        'IniciaÃ§Ã£o': 'Iniciação',
        'CooperaÃ§Ã£o': 'Cooperação',
        'CiÃªncia': 'Ciência',
        'TecnolÃ³gico': 'Tecnológico',
        'TecnolÃ³gica': 'Tecnológica',
        'InovaÃ§Ã£o': 'Inovação',
        'CoordenaÃ§Ã£o': 'Coordenação',
        'prorrogaÃ§Ã£o': 'prorrogação',
        'ProrrogaÃ§Ã£o': 'Prorrogação',
        'Ã s': 'às',
        'amanhÃ£': 'amanhã',
        'cientÃ­fica': 'científica',
        'FranÃ§a': 'França',
        'lanÃ§a': 'lança',
        'CÃ¡tedras': 'Cátedras',
        'MÃ©xico': 'México',
        'Ã©': 'é',
        'Ã¡': 'á',
        'Ã£': 'ã',
        'Ã§': 'ç',
        'Ã³': 'ó',
        'Ãª': 'ê',
        'Ãº': 'ú',
        'Ã­': 'í',
        'Amparo a Pesquisa': 'Amparo à Pesquisa',
        'Comunidade academica': 'Comunidade acadêmica',
        'Conselho Nacional de Desenvolvimento Cientifico e Tecnologico': 'Conselho Nacional de Desenvolvimento Científico e Tecnológico',
        'Conselho Nacional das Fundacoes Estaduais de Amparo a Pesquisa': 'Conselho Nacional das Fundações Estaduais de Amparo à Pesquisa',
        'Coordenacao de Aperfeicoamento de Pessoal de Nivel Superior': 'Coordenação de Aperfeiçoamento de Pessoal de Nível Superior',
        'Pesquisadores e instituicoes de pesquisa': 'Pesquisadores e instituições de pesquisa',
    }

    def clean_text(self, value: str | None) -> str:
        if not value:
            return ""
        text = self._repair_text(value)
        return re.sub(r"\s+", " ", text).strip()

    def clean_url(self, value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", "", value).strip()

    def normalize_date(self, value: str | None) -> str | None:
        parsed = parse_date(value)
        return parsed.date().isoformat() if parsed else None

    def build_edital_id(self, orgao: str, titulo: str, link: str) -> str:
        clean_orgao = self.clean_text(orgao)
        clean_titulo = self.clean_text(titulo)
        clean_link = self.clean_url(link)
        base = f"{clean_orgao} {clean_titulo} {clean_link}".strip()
        slug = slugify(f"{clean_orgao}_{clean_titulo}")[:40]
        return f"{slug}_{short_hash(base, size=8)}"

    def content_hash(self, payload: dict[str, Any]) -> str:
        relevant = "|".join(
            [
                self.clean_text(str(payload.get("titulo", ""))),
                self.clean_text(str(payload.get("resumo", ""))),
                self.clean_text(str(payload.get("data_expiracao", ""))),
                self.clean_text(str(payload.get("link", ""))),
            ]
        )
        return short_hash(relevant, size=12)

    def _repair_text(self, value: str) -> str:
        text = value.strip()
        if not text:
            return text

        suspicious = ('Ã', 'Â', 'â€™', 'â€œ', 'â€', '�')
        if any(token in text for token in suspicious):
            for _ in range(2):
                try:
                    repaired = text.encode('latin-1').decode('utf-8')
                    if repaired and repaired != text:
                        text = repaired
                    else:
                        break
                except (UnicodeEncodeError, UnicodeDecodeError):
                    break

        for source, target in self.COMMON_REPAIRS.items():
            text = text.replace(source, target)

        return text
