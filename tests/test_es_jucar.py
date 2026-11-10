"""Leitores das fontes espanholas. Trechos copiados das fontes reais em 10/11/2026."""

from aqua_foresight.ingestion import es_jucar as es

CSV_MITECO = '''AMBITO_NOMBRE,EMBALSE_NOMBRE,FECHA,AGUA_TOTAL,AGUA_ACTUAL,ELECTRICO_FLAG
"Miño - Sil","Albarellos","01/05/88 00:00:00","91,00","32,00",1
"Júcar","Alarcón","01/05/88 00:00:00","1112,00","291,00",0
"Júcar","Contreras","01/05/88 00:00:00","852,00","200,00",0
"Júcar","Tous","01/05/88 00:00:00","379,00","60,00",0
"Júcar","Benagéber","01/05/88 00:00:00","221,00","100,00",0
"Júcar","Alarcón","01/12/88 00:00:00","1112,00","297,00",0
'''

# Trecho real (pypdf) do Informe de la sequía y la escasez da CHJ, agosto de 2026
TEXTO_CHJ = """UTE sep- 25 oct- 25 nov- 25 dic- 25 ene- 26 feb- 26 mar- 26 abr- 26 may- 26 jun- 26 jul- 26 ago- 26
UTE 01. Cenia-
Maestrazgo 0,62 0,83 0,75 0,71 0,88 0,91 0,87 0,86 0,83 0,83 0,71 0,79
UTE 04. Turia 0,69 0,67 0,66 0,64 0,64 0,69 0,74 0,71 0,66 0,60 0,61 0,59
UTE 05. Júcar 0,81 0,81 0,76 0,69 0,65 0,92 0,91 0,90 0,71 0,66 0,66 0,70
UTE 08. Marina Baja 0,22 0,25 0,20 0,17 0,26 0,26 0,30 0,29 0,27 0,27 0,29 0,31
Tabla 7. Índice de estado de escasez por UTE sobre coloración del escenario diagnosticado
VE07 Volumen embalsado en Alarcón, Contreras y Tous 1,00
UTS 01 02 03 04A 04B 05A 05B 05C 05D 06 07 08 09 ago 26
Coef. 0,05 0,11 0,03 0,11 0,05 0,04 0,15 0,27 0,06 0,02 0,02 0,02 0,07 0,54 IES 0,64 0,46 0,45 0,46 0,63 0,68 0,48 0,51 0,77 0,73 0,62 0,46 0,60
Tabla 9. Indicador global de sequía del mes del informe
 Zona Norte Zona Central Zona Sur ago 26 UTE 01 02 03 04 05 06 07 08 09
IES 0,79 0,54 0,49 0,59 0,70 0,51 0,51 0,31 0,59 0,56  0,61 0,59 0,48
Tabla 10. Indicador global de escasez del mes del informe"""


def test_agregacao_semanal_jucar():
    linhas = es.agregar_jucar(CSV_MITECO)
    dem = {l["data"]: l for l in linhas if l["ambito"] == "demarcacion"}
    act = {l["data"]: l for l in linhas if l["ambito"] == "sistema_act"}
    assert dem["1988-01-05"]["volume_hm3"] == 651.0 and dem["1988-01-05"]["n_represas"] == 4
    assert act["1988-01-05"]["capacidade_hm3"] == 2343.0 and act["1988-01-05"]["pct"] == round(551 / 2343 * 100, 2)
    assert "1988-01-12" not in act  # só Alarcón nessa semana: sistema incompleto, descartado
    assert all(l["data"] != "1988-05-01" for l in linhas)  # data em mês/dia/ano


def test_parse_informe_chj():
    r = es.parse_informe_chj(TEXTO_CHJ)
    assert r["mes_referencia"] == "2026-08"
    juc = [x for x in r["iee_ute"] if x["ute"] == "05"]
    assert len(juc) == 12 and juc[0]["mes"] == "2025-09" and juc[-1]["iee"] == 0.70
    assert r["global_escasez"] == 0.56 and r["zonas_escasez"]["sur"] == 0.48
    assert r["global_sequia"] == 0.54
    assert r["ve07"] == 1.00


def test_faixas_do_iee():
    assert [es.faixa_iee(v) for v in (0.70, 0.50, 0.49, 0.30, 0.29, 0.15, 0.14)] == [
        "normalidad", "normalidad", "prealerta", "prealerta", "alerta", "alerta", "emergencia"]


def test_parse_recusa_global_inconsistente():
    ruim = TEXTO_CHJ.replace("0,56  0,61", "0,90  0,61")
    assert es.parse_informe_chj(ruim)["global_escasez"] is None
