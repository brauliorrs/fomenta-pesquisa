from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Edital:
    id: str
    titulo: str
    orgao: str
    fonte: str
    uf: str
    categoria: str
    link: str
    resumo: str
    publico_alvo: str
    data_abertura: str | None
    data_expiracao: str | None
    data_ultima_coleta: str
    ultima_postagem: str | None = None
    quantidade_postagens: int = 0
    status: str = 'novo'
    houve_prorrogacao: bool = False
    hash_conteudo: str = ''
    instagram_caption: str = ''
    instagram_asset: str = ''
    instagram_mock_asset: str = ''
    card_header: str = ''
    card_title: str = ''
    card_deadline: str = ''
    card_summary: str = ''
    card_handle: str = '@editais.pesquisa'
    pronto_para_postagem: bool = False
    motivo_bloqueio_postagem: str = ''
    revisao_humana_obrigatoria: bool = False
    bloqueio_editorial_definitivo: bool = False
    score_editorial: int = 0
    pendencias_editoriais: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceConfig:
    nome: str
    sigla: str
    uf: str
    site_oficial: str
    pagina_editais: str
    tipo_coleta: str
    ativo: bool = True
    parser: str = 'generic'
    selectors: dict[str, str] = field(default_factory=dict)


@dataclass
class PublicationResult:
    success: bool
    payload: dict[str, Any]
    asset_path: str
    message: str = ''
