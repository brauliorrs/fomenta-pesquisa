# Projeto Editais Instagram

Bot em Python para monitorar editais de pesquisa, manter memória em arquivos versionados e apoiar a operação de publicação no Instagram.

## O que esta versão entrega

- Estrutura modular para evolução do projeto
- Coleta ativa de CNPq, CAPES, CONFAP e IPEA
- Enriquecimento com resumo, links oficiais e extração de datas em HTML, PDF e endpoints JSON
- Memória persistida em `data/editais.json` e `data/historico_postagens.csv`
- Fila editorial pronta em `data/fila_publicacao.json`
- Geração de card visual (`.svg`) e mock textual (`.txt`) em `posts/`
- Painel local para visualizar editais em `dashboard/`
- Workflow do GitHub Actions para execução agendada e manual

## Estrutura

```text
src/
data/
dashboard/
templates/
posts/
logs/
.github/workflows/
```

## Requisitos

- Python 3.11+

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Execução do bot

```bash
python -m src.main
```

## Saídas principais

Depois de rodar a coleta, você passa a ter:

- `data/editais.json`: base consolidada dos editais
- `data/fila_publicacao.json`: fila dos itens prontos para postagem, ordenada por urgência
- `data/historico_postagens.csv`: histórico do mock de publicação
- `posts/*.svg`: card visual automático pronto para revisão
- `posts/*.txt`: mock textual com legenda pronta para revisão

## Painel local de editais

Depois de rodar a coleta, suba um servidor simples na raiz do projeto:

```bash
python -m http.server 8000
```

Depois abra:

```text
http://localhost:8000/dashboard/
```

O painel permite:

- busca por título, órgão e resumo
- filtro por fonte
- filtro por status
- filtro por urgência de prazo
- leitura rápida dos principais campos
- visualização de score editorial e pendências

## Variáveis de ambiente

Crie um arquivo `.env` opcional com:

```env
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_BUSINESS_ACCOUNT_ID=
INSTAGRAM_PUBLISH_MODE=mock
INSTAGRAM_API_HOST=https://graph.facebook.com
INSTAGRAM_API_VERSION=v22.0
PUBLIC_ASSET_BASE_URL=
INSTAGRAM_PUBLISH_STORIES=false
META_APP_ID=
META_APP_SECRET=
GITHUB_REPOSITORY=
GITHUB_TOKEN=
TIMEZONE=America/Sao_Paulo
```

## Observações

- A publicação no Instagram continua em modo mock.
- Para ativar publicação real, use `INSTAGRAM_PUBLISH_MODE=real`.
- A mídia precisa estar em uma URL pública no momento da chamada à Meta; por isso o projeto usa `PUBLIC_ASSET_BASE_URL` para montar a URL do card gerado.
- Para publicar em feed e também em stories pela API, a conta do Instagram precisa ser profissional; stories exigem conta Business nas limitações atuais da API oficial.
- O código já está preparado para duas etapas de publicação real:
  - feed com `image_url + caption`
  - stories com `image_url` quando `INSTAGRAM_PUBLISH_STORIES=true`
- Os scrapers usam configuração em `data/fontes.json` e toleram falhas por fonte.
- A extração de prazos usa heurísticas, leitura de PDF e alguns endpoints auxiliares quando a página oficial expõe cronograma fora do HTML principal.
- Quando não houver mudanças, o workflow evita falha no commit.
- O workflow do GitHub Actions está configurado em UTC para equivaler a `00:00` e `12:00` de `America/Sao_Paulo` no cenário atual, usando `0 3,15 * * *`.
