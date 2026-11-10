from aqua_foresight import conversao_adasa as cv


def test_calibracao_reproduz_valores_divulgados_pela_adasa():
    for data, sar, adasa, _ in cv.CALIBRACAO_DESCOBERTO:
        assert abs(cv.sar_para_adasa_descoberto(sar) - adasa) <= 0.3, data


def test_santa_maria_sar_igual_adasa():
    for data, sar, adasa, _ in cv.VALIDACAO_SANTA_MARIA:
        assert abs(sar - adasa) <= 0.15, data


def test_limites_da_conversao():
    assert cv.sar_para_adasa_descoberto(100) == 100.0
    assert cv.sar_para_adasa_descoberto(5) == 0.0  # abaixo da tomada útil


def test_curva_cota_monotonica_e_interpolada():
    c = cv.CurvaCota.ajustar([(1020.0, 10.0), (1025.0, 40.0), (1025.0, 42.0), (1024.0, 45.0), (1030.0, 100.0)])
    assert c.pcts == sorted(c.pcts)  # forçada monotônica
    v, ok = c(1027.5)
    assert ok and 41 < v < 100
    assert c(1035.0) == (100.0, False)


def test_converter_serie():
    linhas = [{"data": f"2018-01-{d:02d}", "reservatorio": "descoberto", "cota_m": str(1020 + d * 0.3), "pct_sar": str(15 + d * 2.5)}
              for d in range(1, 31)]
    linhas += [{"data": "2010-05-01", "reservatorio": "descoberto", "cota_m": "1025.0", "pct_sar": "84.07"},
               {"data": "2018-01-01", "reservatorio": "santa_maria", "cota_m": "1070.0", "pct_sar": "77.5"}]
    obs, meta = cv.converter_serie(linhas)
    sm = [o for o in obs if o["res"] == "santa_maria"]
    assert sm[0]["valor"] == 77.5 and sm[0]["natureza"] == "observado"
    d2010 = next(o for o in obs if o["data"] == "2010-05-01")
    # recalculado pela cota, não pelos 84,07% da curva antiga
    assert d2010["natureza"] == "estimado" and d2010["valor"] < 60
    assert meta["descoberto"]["pontos_curva_cota"] == 30
