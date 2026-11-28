"""Triagem conservadora de conteúdos que claramente não anunciam inscrições.

A triagem não apaga itens do catálogo: apenas evita gastar a auditoria
de prazos em notícias de eventos, retrospectivas ou homenagens. Em caso
de dúvida, mantém o documento na auditoria.
"""
from __future__ import annotations

import re
from typing import Any

from src.services.deadline_evidence import fold

REGISTRATION_TITLE = re.compile(
    r'\b(?:edital|chamada\s+publica|inscri(?:cao|coes)|candidat|'
    r'submiss|processo\s+seletivo|selecao\s+de\s+bolsistas|'
    r'prazo\s+para\s+propostas|vagas?\s+(?:abertas?|disponiveis))\b'
)
NON_APPLICATION_NEWS = re.compile(
    r'\b(?:celebra|comemora|homenageia|reune|reuniu|'
    r'realizou|participou|inaugura|debates?|seminarios?|'
    r'palestras?|aniversario|evento\s+reuniu|'
    r'pesquisa\s+apoiada\s+.*\s+recebe\s+premio|'
    r'feira\s+de\s+ciencias|mostra\s+cientifica)\b'
)


def is_clear_non_application_news(item: dict[str, Any]) -> bool:
    title = fold(item.get('titulo') or '')
    if not title or REGISTRATION_TITLE.search(title):
        return False
    return bool(NON_APPLICATION_NEWS.search(title))
