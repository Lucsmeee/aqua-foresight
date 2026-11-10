# Planilhas de volume útil

Coloque aqui arquivos `.csv` ou `.xlsx` com volume útil (%) de Descoberto e/ou Santa Maria. O pipeline diário lê todos os arquivos desta pasta, em ordem alfabética; quando duas planilhas trazem a mesma data e o mesmo reservatório, vale a de nome posterior.

## Exportação do SAR (ANA)

1. Abra https://www.ana.gov.br/sar/ e entre no módulo de outros sistemas hídricos, página do Distrito Federal.
2. Use o botão de exportação no canto superior direito da tabela (CSV).
3. Renomeie com a data, por exemplo `sar_df_2026-11-10.csv`, e envie para esta pasta pelo GitHub (Add file → Upload files).

O push dispara o pipeline e a página é atualizada em poucos minutos.

## Série histórica (ADASA ou outra fonte)

Qualquer planilha com uma coluna de data e uma de volume útil (%) funciona. Se não houver coluna de reservatório, inclua o nome no arquivo: `descoberto_2010-2026.csv`, `santa_maria_2010-2026.csv`.

Regras aplicadas: datas `dd/mm/aaaa` ou `aaaa-mm-dd`; vírgula ou ponto decimal; linhas com data futura, valor fora de 0–100% ou reservatório fora do piloto são rejeitadas e contadas no relatório.
