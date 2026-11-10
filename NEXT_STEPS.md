# NEXT_STEPS — próxima execução

## Ações do usuário
1. Opcional: credencial da API HidroWebService (hidro@ana.gov.br) → secrets `ANA_IDENTIFICADOR` e `ANA_SENHA`.
2. Opcional, recomendado: pedir à ADASA (SIRH ou Lei de Acesso à Informação) a série oficial de volume útil do Descoberto, para validar a conversão estimada.
3. Opcional: pedir à CHJ o histórico de informes mensais do PES (IEE desde 2018) para alongar a série espanhola.

## Próxima execução
- Conferir a carga histórica SAR (workflow "Carga histórica"); se não cobriu 2011–2021, redisparar: ela retoma de onde parou.
- Conferir o GitHub Pages após o Pipeline diário (index, comparacao, tecnico).
- Fase 3: defasagens RONI × anomalia mensal de volume por estação do ano, começando pelo Santa Maria (base igual à ADASA); repetir para o Júcar com ENOS e NAO.
- Fase 4: baseline sem ENOS (Modelo A) com validação rolling-origin.

## Fila
- Validar a conversão do Descoberto com série oficial da ADASA; revisão jurídica da Res. ADASA 56/2025 e do PES do Júcar (Orden TED/601/2026); Alembic; auditoria com hash encadeado; Rnino34; probabilidades ENSO.
