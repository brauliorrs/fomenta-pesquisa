# Fomenta Pesquisa

**Sistema automatizado para monitoramento de editais, bolsas e chamadas de pesquisa, com coleta em fontes públicas, fila editorial, geração de cards e publicação assistida.**

O **Fomenta Pesquisa** é um projeto em Python voltado à automação da descoberta, organização e divulgação de oportunidades acadêmicas e científicas. Ele monitora fontes públicas de fomento, consolida editais em arquivos versionados, extrai informações relevantes, organiza uma fila editorial e prepara materiais para publicação em redes sociais.

O objetivo é reduzir o trabalho manual de acompanhamento de oportunidades e transformar chamadas públicas dispersas em um fluxo organizado de inteligência editorial para pesquisadores, instituições e projetos de comunicação científica.

---

## Resumo executivo

**Entrega principal:** bot de monitoramento + base consolidada + fila editorial + cards de divulgação + painel local  
**Stack:** Python, GitHub Actions, scraping responsável, JSON, CSV, HTML, APIs e automação editorial  
**Uso:** comunicação científica, pesquisa institucional, curadoria de editais, divulgação acadêmica e operação editorial  
**Status:** MVP funcional com workflows agendados, modo mock e preparação para publicação real via API

---

## Problema

Editais, bolsas e chamadas de pesquisa são publicados em dezenas de páginas institucionais, frequentemente com estruturas diferentes, prazos curtos e pouca padronização.

Na prática, isso gera problemas como:

- acompanhamento manual repetitivo;
- risco de perder prazos relevantes;
- dificuldade de comparar oportunidades;
- dispersão de fontes oficiais;
- retrabalho na criação de posts e legendas;
- ausência de memória histórica dos editais monitorados;
- dependência de busca manual em sites de agências, fundações e instituições.

O projeto responde a esse problema criando um fluxo automatizado de monitoramento, organização e preparação editorial.

---

## Solução

O **Fomenta Pesquisa** executa um pipeline que:

1. monitora fontes públicas de editais e chamadas;
2. coleta páginas, HTML, PDFs e endpoints JSON quando disponíveis;
3. extrai título, fonte, resumo, link oficial, prazo e status;
4. consolida os dados em arquivos versionados;
5. calcula prioridade editorial com base em urgência e validade;
6. gera uma fila de publicação;
7. produz cards visuais e textos de apoio;
8. registra histórico de postagens;
9. permite operação local por painel;
10. executa ciclos automáticos via GitHub Actions.

---

## Fontes monitoradas

O projeto trabalha com fontes públicas de fomento, pesquisa, inovação e ciência, incluindo agências nacionais, fundações estaduais e instituições de apoio.

Entre as fontes monitoradas ou previstas estão:

- ANP
- CNPq
- CAPES
- CONFAP
- IPEA
- Fiocruz
- Embrapa
- EMBRAPII
- Fundeci
- Banco da Amazônia
- BNDES
- DECIT
- Finep
- FAPESP
- FAPERJ
- FACEPE
- FAPAC
- FAPEAL
- FAPEAP
- FAPEAM
- FAPESB
- FUNCAP
- FAPDF
- FAPES
- FAPEG
- FAPEMA
- FAPEMAT
- FUNDECT
- FAPEMIG
- FAPESPA
- FAPESQ
- Fundação Araucária / FAPPR
- FAPEPI
- FAPERN
- FAPERGS
- FAPERO
- FAPITEC
- FAPT
- FAPESC
- Instituto Serrapilheira

A lista pode ser expandida por meio de catálogos de fontes planejadas, candidatas e descobertas.

---

## O que esta versão entrega

- Estrutura modular para evolução do projeto
- Coleta ativa em fontes públicas de editais
- Enriquecimento com resumo, links oficiais e extração de datas
- Leitura de HTML, PDF e endpoints JSON
- Memória persistida dos editais coletados
- Fila editorial ordenada por urgência
- Geração de card visual em JPEG
- Geração de mock textual com legenda
- Painel local para visualização e revisão
- Workflow agendado e manual no GitHub Actions
- Workflow mensal de descoberta de novas fontes
- Auditoria de páginas oficiais já monitoradas
- Controle de publicação em modo mock por padrão
- Preparação para publicação real via API oficial

---

## Arquitetura do projeto

```text
.
├── src/
│   ├── main.py
│   └── ...
├── data/
│   ├── editais.json
│   ├── fila_publicacao.json
│   ├── historico_postagens.csv
│   ├── fontes.json
│   ├── fontes_planejadas.json
│   ├── fontes_candidatas.json
│   └── fontes_descobertas.json
├── dashboard/
├── templates/
├── posts/
├── logs/
├── .github/
│   └── workflows/
├── requirements.txt
├── .env.example
└── README.md
```

---

## Fluxo de funcionamento

```text
Fontes oficiais
      ↓
Coleta e leitura de páginas
      ↓
Extração de título, prazo, fonte e link
      ↓
Enriquecimento com resumo e metadados
      ↓
Atualização da base consolidada
      ↓
Geração da fila editorial
      ↓
Criação de card e legenda
      ↓
Modo mock ou publicação real
      ↓
Histórico de postagens
      ↓
Auditoria e descoberta de novas fontes
```

---

## Saídas principais

Depois da execução, o projeto pode gerar ou atualizar:

```text
data/editais.json
data/fila_publicacao.json
data/historico_postagens.csv
data/fontes_descobertas.json
posts/*.jpg
posts/*.txt
logs/bot.log
```

| Arquivo/Pasta | Função |
|---|---|
| `data/editais.json` | Base consolidada dos editais monitorados |
| `data/fila_publicacao.json` | Itens prontos ou candidatos à publicação |
| `data/historico_postagens.csv` | Histórico de publicação ou simulação |
| `data/fontes_descobertas.json` | Diagnóstico mensal de novas fontes candidatas |
| `posts/*.jpg` | Cards visuais gerados automaticamente |
| `posts/*.txt` | Textos de apoio e legendas em modo mock |
| `logs/` | Registros de execução e diagnóstico |

---

## Painel local

O projeto inclui um painel local para consulta, revisão e operação editorial.

Para abrir o painel, execute um servidor simples na raiz do projeto:

```bash
python -m http.server 8000
```

Depois acesse:

```text
http://localhost:8000/dashboard/
```

O painel permite:

- buscar por título, órgão ou resumo;
- filtrar por fonte;
- filtrar por status;
- acompanhar urgência de prazo;
- visualizar score editorial;
- revisar pendências antes da publicação;
- consultar itens prontos para divulgação.

---

## Como executar localmente

### 1. Criar ambiente virtual

```bash
python -m venv .venv
```

No Windows:

```bash
.venv\Scripts\activate
```

No Linux/macOS:

```bash
source .venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Executar o bot

```bash
python -m src.main
```

---

## Variáveis de ambiente

O arquivo `.env.example` existe como referência para desenvolvimento local.

Para uso local, copie o modelo:

```bash
copy .env.example .env
```

ou, em Linux/macOS:

```bash
cp .env.example .env
```

### Variáveis principais

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
INSTAGRAM_MAX_NEW_PUBLICATIONS_PER_DAY=10
META_APP_ID=
META_APP_SECRET=
TIMEZONE=America/Sao_Paulo
```

### Segurança

Valores sensíveis, como tokens e secrets, não devem ser versionados no repositório.

Em produção no GitHub Actions, configure:

```text
Settings > Secrets and variables > Actions
```

Use **Secrets** para dados sensíveis e **Variables** para parâmetros públicos ou operacionais.

---

## Modos de publicação

O projeto opera em modo seguro por padrão.

### Modo mock

```env
INSTAGRAM_PUBLISH_MODE=mock
```

Nesse modo, o sistema gera cards e textos de apoio, mas não publica diretamente.

### Modo real

```env
INSTAGRAM_PUBLISH_MODE=real
```

Nesse modo, o projeto pode enviar publicações usando a API oficial configurada.

A publicação real depende de token válido, conta profissional compatível, URL pública para a mídia, permissões adequadas na API e configuração correta dos secrets.

---

## Ciclo de automação

O projeto pode operar com dois tipos principais de workflow:

### Workflow operacional

Executa coleta, atualização da fila editorial, geração de cards e publicação em modo mock ou real. Pode ser acionado manualmente ou por agendamento.

### Workflow de descoberta de fontes

Executado mensalmente para:

- auditar páginas oficiais das fontes já ativas;
- detectar mudanças de URL;
- avaliar fontes candidatas;
- registrar descobertas;
- indicar quais páginas são viáveis para coleta automatizada.

---

## Primeira carga de publicação

Para fazer uma primeira carga com todos os itens prontos:

1. Abra a aba **Actions** no GitHub.
2. Escolha o workflow **Bot Editais**.
3. Clique em **Run workflow**.
4. Marque `publish_all_ready=true`.
5. Execute manualmente.

A execução publica ou simula todos os itens prontos e ainda inéditos, respeitando os limites editoriais e técnicos configurados.

---

## Boas práticas

Antes de ativar publicação real:

- revise manualmente os cards gerados;
- confira links oficiais;
- valide datas e prazos;
- teste em modo mock;
- verifique se o `PUBLIC_ASSET_BASE_URL` está acessível publicamente;
- confirme se os secrets não aparecem em logs;
- revise o histórico de postagens;
- mantenha limite diário de publicações.

---

## O que este projeto demonstra

Este repositório evidencia competências em:

- automação com Python;
- scraping responsável;
- integração com GitHub Actions;
- organização de dados em JSON e CSV;
- leitura de HTML, PDF e endpoints estruturados;
- desenho de pipeline editorial;
- geração automática de assets;
- operação com APIs;
- gestão segura de tokens e secrets;
- comunicação científica;
- curadoria de oportunidades de pesquisa;
- transformação de dados públicos em fluxo operacional.

---

## Roadmap

### Concluído ou em funcionamento

- Estrutura modular do bot
- Coleta em múltiplas fontes públicas
- Base consolidada de editais
- Fila editorial
- Geração de cards em JPEG
- Geração de mocks textuais
- Painel local
- Workflow agendado e manual
- Workflow mensal de descoberta de fontes
- Modo mock por padrão
- Preparação para publicação real

### Próximas etapas

- Melhorar classificação temática dos editais
- Ampliar validação automática de prazos
- Criar painel público em Streamlit ou aplicação web
- Implementar camada de revisão editorial antes da publicação real
- Adicionar testes automatizados
- Criar relatórios periódicos de oportunidades por área
- Melhorar documentação técnica dos scrapers
- Criar métricas de desempenho editorial

---

## Limitações

O projeto depende de fontes públicas externas, que podem mudar estrutura, remover páginas, bloquear acesso automatizado ou publicar informações em formatos pouco padronizados.

Algumas limitações esperadas:

- páginas oficiais instáveis;
- editais publicados apenas em PDF;
- datas distribuídas em anexos;
- ausência de APIs públicas;
- mudanças de layout;
- links quebrados;
- prazos ambíguos;
- necessidade de revisão humana antes da publicação real.

Essas limitações fazem parte do problema que o projeto busca organizar.

---

## Licença

Consulte o arquivo `LICENSE` deste repositório.

---

## Autor

**Bráulio Roberto Rangel da Silva**

Pesquisador e desenvolvedor com atuação em dados públicos, automação, observatórios digitais, comunicação científica, IA aplicada e produtos digitais.

GitHub: [@brauliorrs](https://github.com/brauliorrs)
