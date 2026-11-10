"""Base normativa estruturada: Resolução ADASA nº 56, de 15 de agosto de 2025.

Transcrição da Tabela 1 ("Estados Hidrológicos dos reservatórios", volume útil em %,
comparador estrito "<"), conferida em duas fontes oficiais que coincidem entre si:

  [1] ADASA — SEI 178925819, processo SEI 00197-00001339/2019-82
      https://www.adasa.df.gov.br/images/storage/legislacao/resolucoes_adasa/2025/SEI_178925819_Resolucao_56.2025_Curvas_Reservat%C3%B3rios.pdf
  [2] DODF nº 157, de 21/08/2025, Seção I (SINJ-DF)
      https://www.sinj.df.gov.br/sinj/Diario/2b6a35b8-d04e-3202-9191-d7077ed7ef9a/DODF%20157%2021-08-2025%20INTEGRA.pdf

Conferência feita em 10/11/2026 a partir do texto indexado dessas fontes. Os valores de
novembro coincidem com a Especificação v2.0, §7.2. PENDENTE (decisão D-05): revisão
jurídica humana do texto integral, da cláusula de vigência e de eventuais alterações
posteriores — a própria ementa fala em "definição anual das curvas de referência".

Art. 2º (condições de uso nos estados hidrológicos), conforme [2]:
  I   – EH Verde: não há restrição aos usos outorgados;
  II  – EH Amarelo: os usos outorgados se submetem às condições estabelecidas nos Termos
        de Alocação de Água, nos Boletins de Acompanhamento da Alocação de Água ou em
        comandos regulatórios específicos;
  III – EH Vermelho: fica declarada situação de escassez hídrica e os usos se submetem
        às regras definidas pelos órgãos outorgantes.
"""

from __future__ import annotations

from datetime import date

NORMA_ID = "adasa_res_56_2025"

NORMA = {
    "id": NORMA_ID,
    "jurisdicao": "BR-DF",
    "titulo": (
        "Resolução ADASA nº 56, de 15 de agosto de 2025 — dispõe sobre o estabelecimento dos "
        "estados hidrológicos e a definição anual das curvas de referência para o acompanhamento "
        "do volume útil dos reservatórios do Descoberto e do Santa Maria"
    ),
    "orgao_emissor": "Agência Reguladora de Águas, Energia e Saneamento Básico do Distrito Federal (ADASA)",
    "data_ato": date(2025, 8, 15),
    "data_publicacao": date(2025, 8, 21),
    "publicacao": "DODF nº 157, Seção I, 21/08/2025",
    "vigencia_inicio": None,  # cláusula de vigência não extraída: não presumir
    "vigencia_fim": None,
    "vigencia_status": "a_conferir",
    "fontes": [
        "https://www.adasa.df.gov.br/images/storage/legislacao/resolucoes_adasa/2025/SEI_178925819_Resolucao_56.2025_Curvas_Reservat%C3%B3rios.pdf",
        "https://www.sinj.df.gov.br/sinj/Diario/2b6a35b8-d04e-3202-9191-d7077ed7ef9a/DODF%20157%2021-08-2025%20INTEGRA.pdf",
    ],
    # Códigos: nao_verificado | tabela_conferida_fonte_oficial | revisado_assessoria_juridica
    "status_verificacao": "tabela_conferida_fonte_oficial",
    "observacoes": (
        "Tabela 1 conferida em duas fontes oficiais (ADASA e DODF). Texto integral, vigência "
        "e alterações posteriores dependem de revisão jurídica humana (D-05)."
    ),
}

RESERVATORIOS = [
    {
        "id": "descoberto",
        "nome": "Reservatório do Descoberto",
        "uf": "DF",
        "orgao_regulador": "ADASA",
        "observacoes": None,
    },
    {
        "id": "santa_maria",
        "nome": "Reservatório do Santa Maria",
        "uf": "DF",
        "orgao_regulador": "ADASA",
        "observacoes": None,
    },
]

# Tabela 1 — limites "<" de volume útil (%), meses jan..dez.
TABELA_1: dict[str, dict[str, tuple[float, ...]]] = {
    "descoberto": {
        "amarelo": (50, 61, 70, 75, 75, 70, 62, 52, 38, 30, 30, 35),
        "vermelho": (40, 51, 60, 65, 65, 60, 52, 42, 28, 20, 20, 25),
    },
    "santa_maria": {
        "amarelo": (48, 55, 57, 57, 55, 51, 45, 38, 30, 23, 25, 28),
        "vermelho": (38, 45, 47, 47, 45, 41, 35, 28, 20, 13, 15, 18),
    },
}

DISPOSITIVOS = {
    "estados": "art. 1º, Tabela 1",
    "condicoes_de_uso": "art. 2º, I a III",
}

CONDICOES_DE_USO = {
    "verde": "Não há restrição aos usos outorgados (art. 2º, I).",
    "amarelo": (
        "Os usos outorgados se submetem às condições estabelecidas nos Termos de Alocação de Água, "
        "nos Boletins de Acompanhamento da Alocação de Água ou em comandos regulatórios específicos "
        "(art. 2º, II)."
    ),
    "vermelho": (
        "Fica declarada situação de escassez hídrica e os usos se submetem às regras definidas "
        "pelos órgãos outorgantes (art. 2º, III)."
    ),
}


def limiares_linhas() -> list[dict]:
    linhas = []
    for reservatorio, estados in TABELA_1.items():
        for estado, valores in estados.items():
            assert len(valores) == 12
            for mes, limite in enumerate(valores, start=1):
                linhas.append(
                    {
                        "norma_id": NORMA_ID,
                        "reservatorio_id": reservatorio,
                        "mes": mes,
                        "estado": estado,
                        "limite_pct": float(limite),
                        "comparador": "<",
                        "dispositivo": DISPOSITIVOS["estados"],
                    }
                )
    return linhas
