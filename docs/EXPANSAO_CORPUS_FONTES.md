# Expansao continua do corpus de fontes — Bot Editais

O cadastro de fontes nao fica fixo. A cada dia, o robo examina um conjunto
rotativo de paginas institucionais ja monitoradas e identifica novas paginas
de editais, bolsas, chamadas e oportunidades de pesquisa.

## Principios

- Uma pagina de listagem e fonte de descoberta, nao oportunidade publicavel.
- Encontrar uma pagina nova nao autoriza publica-la no Instagram.
- Novas paginas da mesma instituicao sao verificadas por amostra.
- Ativacao automatica exige 2 observacoes em dias diferentes e 2 validacoes
  positivas em dias diferentes, cada uma com ao menos 2 oportunidades
  especificas e distintas.
- Enderecos de instituicoes externas sao registrados como
  externa_pendente_revisao e nao sao acessados nem ativados pelo coletor
  diario sem verificacao institucional posterior.
- Resultados, finalistas, premiacoes e inscricoes encerradas continuam
  bloqueadas pelo filtro editorial, inclusive nas republicacoes.
- Fontes adicionais recebem ID tecnico, mas a sigla institucional original
  continua sendo usada no registro do edital.

## Rotina

- .github/workflows/expand_fontes.yml: expansao diaria, limite de 20 fontes
  visitadas, 10 novas paginas, 8 validacoes e 2 ativacoes por execucao.
- .github/workflows/discover_fontes.yml: auditoria mensal completa.
- data/fontes_expansao.json: registro cumulativo de paginas e evidencias,
  com cursor rotativo e metricas.
- data/fontes_candidatas.json: paginas com evidencia inicial.
- data/fontes.json: fontes de coleta efetivamente integradas.

A expansao encontra paginas relacionadas a fontes ja monitoradas. Nao e uma
busca irrestrita em toda a web: dominios desconectados exigem novas
sementes ou futura integracao com um indice de busca.

## Validacao editorial

src/services/opportunity_guard.py continua bloqueando paginas de listagem,
resultados, premiacoes, datas vencidas e oportunidades sem prazo verificado.
Essa validacao e repetida antes da publicacao no Instagram.

## Testes

python -m unittest discover -s tests -p 'test_source_expansion.py' -v
python -m unittest discover -s tests -p 'test_opportunity_guard.py' -v
