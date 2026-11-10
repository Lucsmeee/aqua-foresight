# NEXT_STEPS — próxima execução

## Ações do usuário
1. **Ativar o GitHub Pages**: Settings → Pages → Build and deployment → Source: **GitHub Actions**. Depois, Actions → Pipeline diário → Run workflow.
2. Opcional: credencial da API HidroWebService (hidro@ana.gov.br) → secrets `ANA_IDENTIFICADOR` e `ANA_SENHA`.
3. Opcional, recomendado: pedir à ADASA (SIRH ou Lei de Acesso à Informação) a série oficial de volume útil do Descoberto, para validar a conversão estimada.

## Próxima execução
- Conferir a carga histórica SAR (workflow "Carga histórica"); se não cobriu 1990–2021, redisparar: ela retoma de onde parou.
- Fase 3: defasagens RONI × anomalia mensal de volume por estação do ano, começando pelo Santa Maria (base igual à ADASA).
- Fase 4: baseline sem ENOS (Modelo A) com validação rolling-origin.

## Fila
- Validar a conversão do Descoberto com série oficial da ADASA; Alembic; auditoria com hash encadeado; Rnino34; probabilidades ENSO.
