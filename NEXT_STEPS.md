# NEXT_STEPS — próxima execução

## Ações do usuário que destravam
1. Ativar o GitHub Pages (Settings → Pages → Source: GitHub Actions) e rodar **Actions → Pipeline diário → Run workflow**. Conferir no resumo da execução se o RONI ficou `verificado`.
2. Pedir credencial da API HidroWebService à ANA (hidro@ana.gov.br) e cadastrar os secrets `ANA_IDENTIFICADOR` e `ANA_SENHA`.
3. Obter a série histórica diária de volume útil de Descoberto e Santa Maria: SIRH da ADASA ou pedido pela Lei de Acesso à Informação. Enviar a planilha para `data/manual/volume/`.
4. Enquanto isso, enviar a exportação CSV diária do SAR (módulo DF) para `data/manual/volume/`.

## Tarefa prioritária da próxima execução
- Conferir o primeiro resultado real do workflow (status das fontes, RONI publicado) e corrigir o que falhar.
- Com credencial ANA: confirmar no inventário (`HidroInventarioEstacoes`) os códigos 60435500 e 60477100, a unidade da cota e os parâmetros exigidos pelo Swagger.
- Com série histórica: análise de defasagens RONI × volume por estação do ano e baseline sem ENOS (Modelo A).

## Fila seguinte
- Curva cota-volume oficial (ADASA/Caesb) para converter telemetria em volume útil.
- Alembic; trilha de auditoria à prova de alteração (hash encadeado).
- Adaptador Rnino34 mensal; probabilidades ENSO do CPC.
- Decisão D-04 sobre o parâmetro provisório de defasagem (7 dias).
