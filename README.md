# Projeto Editais Instagram

Bot em Python para monitorar editais de pesquisa, manter memória em arquivos versionados e apoiar a operação de publicação no Instagram.

## O que esta versão entrega

- Estrutura modular para evolução do projeto
- Coleta ativa de ANP, CNPq, CAPES, CONFAP, IPEA, Fiocruz, Embrapa, EMBRAPII, Finep, FAPESP, FAPERJ, FACEPE, FAPAC, FAPEAL, FAPEAP, FAPEAM, FAPESB, FUNCAP, FAPDF, FAPES, FAPEG, FAPEMA, FAPEMAT, FUNDECT, FAPEMIG, FAPESPA, FAPESQ, FAPPR, FAPEPI, FAPERN, FAPERGS, FAPERO, FAPITEC, FAPT, FAPESC e Serrapilheira
- Enriquecimento com resumo, links oficiais e extração de datas em HTML, PDF e endpoints JSON
- Memória persistida em `data/editais.json` e `data/historico_postagens.csv`
- Fila editorial pronta em `data/fila_publicacao.json`
- Geração de card visual (`.jpg`) e mock textual (`.txt`) em `posts/`
- Painel local para visualizar editais em `dashboard/`
- Workflow do GitHub Actions para execução agendada e manual
- Catálogo de expansão de fontes em `data/fontes_planejadas.json`

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
- `posts/*.jpg`: card visual automático temporário para revisão e publicação
- `posts/*.txt`: mock textual temporário com legenda pronta para revisão

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

O arquivo `.env.example` existe apenas como referência.

Para desenvolvimento local, você pode copiar esse modelo para `.env`.

Para produção no GitHub Actions, o projeto não depende de `.env` local:

- use `Settings > Secrets and variables > Actions > Secrets` para valores sensíveis
- use `Settings > Secrets and variables > Actions > Variables` para valores públicos ou operacionais

### `.env` opcional para desenvolvimento local

```env
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_BUSINESS_ACCOUNT_ID=
INSTAGRAM_PUBLISH_MODE=mock
INSTAGRAM_API_HOST=https://graph.instagram.com
INSTAGRAM_API_VERSION=v24.0
PUBLIC_ASSET_BASE_URL=
INSTAGRAM_PUBLISH_TARGET=both
INSTAGRAM_REPOST_TARGET=story
INSTAGRAM_PUBLISH_STORIES=false
META_APP_ID=
META_APP_SECRET=
GITHUB_REPOSITORY=
GITHUB_TOKEN=
TIMEZONE=America/Sao_Paulo
```

### Configuração recomendada no GitHub

Secrets:

- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- `META_APP_SECRET`

Variables:

- `INSTAGRAM_PUBLISH_MODE`
- `INSTAGRAM_API_HOST`
- `INSTAGRAM_API_VERSION`
- `INSTAGRAM_BOOTSTRAP_PUBLISH_ALL`
- `PUBLIC_ASSET_BASE_URL`
- `INSTAGRAM_PUBLISH_TARGET`
- `INSTAGRAM_REPOST_TARGET`
- `INSTAGRAM_PUBLISH_STORIES`
- `META_APP_ID`
- `TIMEZONE`

O workflow já usa `github.repository` e `github.token`, então não é necessário manter `GITHUB_REPOSITORY` ou `GITHUB_TOKEN` em secrets para a automação padrão.

## Observações

- O `.env` é opcional e serve só para rodar localmente.
- No GitHub Actions, o workflow já consegue operar só com `Secrets` e `Variables`.
- A publicação no Instagram continua em modo mock por padrão.
- Para ativar publicação real, use `INSTAGRAM_PUBLISH_MODE=real`.
- O fluxo padrão do projeto para publicação real usa a Graph API em `https://graph.instagram.com`.
- Em `INSTAGRAM_ACCESS_TOKEN`, use o token do stack que já foi validado na sua conta profissional.
- Em `INSTAGRAM_BUSINESS_ACCOUNT_ID`, use o identificador da conta profissional compatível com esse mesmo stack de autenticação.
- A mídia precisa estar em uma URL pública no momento da chamada à Meta; por isso o projeto usa `PUBLIC_ASSET_BASE_URL` para montar a URL do card gerado.
- Em `INSTAGRAM_PUBLISH_TARGET`, use `feed`, `story` ou `both` para a primeira publicação. Para o fluxo editorial atual, o recomendado é `both`, para sair no feed e também no story na primeira ida.
- Em `INSTAGRAM_REPOST_TARGET`, use `feed`, `story` ou `both` para as republicações automáticas até o edital vencer. Se ficar vazio, o projeto reaproveita o alvo da primeira publicação.
- O bot nunca publica `story` sozinho antes de existir um `feed` daquele edital; se um item ainda nao foi ao feed, a regra editorial força o feed primeiro.
- Para publicar em stories pela API, a conta do Instagram precisa ser profissional; stories exigem conta Business nas limitações atuais da API oficial.
- O código já está preparado para três destinos de publicação real:
  - `feed` com `image_url + caption`
  - `story` com `image_url`
  - `both` para enviar aos dois destinos na mesma execução
- O ciclo recomendado do bot é:
  - primeira carga manual com `workflow_dispatch` e `publish_all_ready=true` para publicar todos os itens inéditos já prontos
  - execuções agendadas às `00:00` e `12:00` para pesquisar os fomentadores, atualizar a fila e publicar o próximo item novo
  - repost diário em `story` para edital válido, conforme `INSTAGRAM_REPOST_TARGET=story`
  - nenhuma nova ida ao feed depois que `instagram_feed_publicado=true`, a menos que você limpe o histórico conscientemente
- Os cards de publicação agora são gerados em `JPEG`, formato compatível com a etapa de publish da API oficial.
- Os scrapers usam configuração em `data/fontes.json` e toleram falhas por fonte.
- A extração de prazos usa heurísticas, leitura de PDF e alguns endpoints auxiliares quando a página oficial expõe cronograma fora do HTML principal.
- Quando não houver mudanças, o workflow evita falha no commit.
- O workflow do GitHub Actions está configurado em UTC para equivaler a `00:00` e `12:00` de `America/Sao_Paulo` no cenário atual, usando `0 3,15 * * *`.

## Primeira carga de publicacao

Para fazer a primeira carga com todos os itens prontos da fila:

1. Abra `Actions` no GitHub.
2. Escolha o workflow `Bot Editais`.
3. Clique em `Run workflow`.
4. Marque `publish_all_ready=true`.
5. Execute manualmente.

Nessa execucao manual, o bot publica todos os itens prontos e ainda inéditos, com `feed + story` conforme a configuracao atual.
