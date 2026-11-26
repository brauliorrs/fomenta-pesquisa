# Auditoria de prazos do Bot Editais

A publicacao nao deve ser baseada na ultima data encontrada no HTML/PDF.
Datas de realizacao de eventos, resultados, contratacao, avaliacao e
execucao nao sao prazos de inscricao de propostas.

## Auditoria diaria

O job \`Auditar Prazos de Inscricao\` consulta as URLs cadastradas, ate
8 itens com prazos proximos e 12 itens sem prazo por execucao. A
amostragem dos sem prazo e rotativa: inclui todos os elegiveis em ciclos
e nao escolhe apenas casos que parecem validar o sistema.

Cada registro tem:
- prazo armazenado;
- datas textualmente associadas a inscricao/submissao;
- trecho literal que originou cada data;
- URL efetivamente consultada e data da verificacao;
- classificacao: corroborado, divergente, multiplo, sem evidencia,
  prazo vencido, possibilidade de recuperacao ou erro tecnico.

**A analise automatizada nao comprova a oficialidade da pagina nem
identifica com certeza erratas e todas as fases processuais.**
A equipe deve verificar o documento completo, a fase correta e
as retificacoes antes de corrigir a base. O job nao altera
\`data/editais.json\`, \`fila_publicacao.json\` nem publica no Instagram.

O resultado acumulado e salvo em \`data/auditoria_prazos.json\`.
A classificacao \`possivel_recuperacao\` significa apenas que foi
encontrado um prazo com contexto de inscricao num registro antes
bloqueado por ausencia de data; nao e liberacao automatica.

## Correcao no extrator

O processo normal de coleta agora so considera como fechamento uma
data ligada explicitamente a inscricao ou submissao, ou periodo de
inscricoes descrito com inicio/fim. Nao usa a ultima data generica de
uma pagina (como data de resultado ou contratacao) nem transforma
uma data de publicacao no inicio das inscricoes.

Prazos extraidos anteriormente permanecem no banco para auditoria,
sem serem reclassificados silenciosamente como comprovados.
