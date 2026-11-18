"""Testes do parsing das paginas HTML do Mercado Steam.

As fixtures reproduzem a estrutura real: um `JSON.parse("...")` contendo o cache
do React Query, com JSON aninhado como string. Esse aninhamento ja causou um bug
(a varredura sem recursao em strings achava zero resultados calado), entao ele
esta explicito nas fixtures.
"""
import json
import unittest

from marketpage import (agregar, parse_cartas, parse_historico, parse_precos,
                        pick_sample, resumir)


def pagina(objeto, aninhar=True):
    """Embrulha um objeto como a Steam faz: JSON.parse de uma string JSON."""
    interno = json.dumps(objeto)
    payload = json.dumps({"dehydratedState": interno}) if aninhar else interno
    return "<html><script>window.SSR.x = JSON.parse(%s);</script></html>" % json.dumps(payload)


def carta(hash_name, tipo, sell=10, preco=None):
    o = {"strHash": hash_name, "cSellOrders": sell,
         "asset_description": {"type": tipo}}
    if preco is not None:
        o["strMinSellSubtotal"] = preco
    return o


class TestParsePrecos(unittest.TestCase):
    """O preco vem como string formatada ("$0.08"); converter com float() direto
    devolve None calado e some com o dado."""

    PAGINA = pagina({"q": [
        carta("1-A", "X Trading Card", 10, "$2.66"),
        carta("1-B", "X Trading Card", 20, "$0.08"),
        carta("1-F (Foil)", "X Foil Trading Card", 2, "$44.43"),
    ]})

    def test_extrai_precos_das_cartas_normais(self):
        self.assertEqual(parse_precos(self.PAGINA), {"1-A": 2.66, "1-B": 0.08})

    def test_exclui_foil(self):
        self.assertNotIn("1-F (Foil)", parse_precos(self.PAGINA))

    def test_formato_en_us(self):
        p = pagina({"q": [carta("1-A", "X Trading Card", 1, "$1,234.50")]})
        self.assertAlmostEqual(parse_precos(p)["1-A"], 1234.50)

    def test_formato_pt_br_com_virgula_decimal(self):
        """A Steam formata conforme o Accept-Language. Tratar a virgula como
        separador de milhar transformava US$ 0,08 em 8,00 -- inflacao de 100x."""
        p = pagina({"q": [carta("1-A", "X Trading Card", 1, "US$ 0,08")]})
        self.assertAlmostEqual(parse_precos(p)["1-A"], 0.08)

    def test_formato_pt_br_com_milhar(self):
        p = pagina({"q": [carta("1-A", "X Trading Card", 1, "US$ 1.234,50")]})
        self.assertAlmostEqual(parse_precos(p)["1-A"], 1234.50)

    def test_sem_separador_decimal(self):
        p = pagina({"q": [carta("1-A", "X Trading Card", 1, "$12")]})
        self.assertAlmostEqual(parse_precos(p)["1-A"], 12.0)

    def test_milhar_sem_centavos(self):
        p = pagina({"q": [carta("1-A", "X Trading Card", 1, "$1,234")]})
        self.assertAlmostEqual(parse_precos(p)["1-A"], 1234.0)

    def test_foil_com_sufixo_longo_nao_entra_no_preco(self):
        p = pagina({"q": [carta("1-A (Foil Trading Card)", "", 1, "$26.64"),
                          carta("1-A (Trading Card)", "", 1, "$0.08")]})
        self.assertEqual(parse_precos(p), {"1-A (Trading Card)": 0.08})

    def test_moeda_que_nao_e_dolar_e_recusada(self):
        """O valor e convertido de USD para BRL depois; aceitar um preco ja em
        BRL causaria dupla conversao silenciosa."""
        p = pagina({"q": [carta("1-A", "X Trading Card", 1, "R$ 5,00"),
                          carta("1-B", "X Trading Card", 1, "US$ 5,00")]})
        self.assertEqual(parse_precos(p), {"1-B": 5.0})

    def test_carta_sem_preco_e_omitida(self):
        p = pagina({"q": [carta("1-A", "X Trading Card", 1),
                          carta("1-B", "X Trading Card", 1, "$0.50")]})
        self.assertEqual(parse_precos(p), {"1-B": 0.50})

    def test_pagina_vazia(self):
        self.assertEqual(parse_precos("<html></html>"), {})


class TestParseCartas(unittest.TestCase):
    PAGINA = pagina({"queries": [
        carta("221540-Tower Firing", "Defense Grid 2 Trading Card", 121),
        carta("221540-Red Valley", "Defense Grid 2 Trading Card", 98),
        carta("221540-Tower Firing (Foil)", "Defense Grid 2 Foil Trading Card", 5),
        carta("221540-Red Valley (Foil)", "Defense Grid 2 Foil Trading Card", 5),
    ]})

    def test_devolve_so_cartas_normais(self):
        self.assertEqual(parse_cartas(self.PAGINA),
                         ["221540-Tower Firing", "221540-Red Valley"])

    def test_exclui_foil_pelo_tipo(self):
        self.assertNotIn("221540-Tower Firing (Foil)", parse_cartas(self.PAGINA))

    def test_exclui_foil_mesmo_sem_tipo_no_asset(self):
        p = pagina({"q": [{"strHash": "1-X (Foil)", "cSellOrders": 2},
                          {"strHash": "1-Y", "cSellOrders": 2}]})
        self.assertEqual(parse_cartas(p), ["1-Y"])

    def test_exclui_foil_com_sufixo_longo(self):
        """Nem toda foil termina em "(Foil)": existe "(Foil Trading Card)", e sem
        asset_description o nome e a unica pista. Uma foil de US$26 entre cartas
        de centavos multiplica o valor medio do set por 6."""
        p = pagina({"q": [{"strHash": "1-The Crowd (Foil Trading Card)"},
                          {"strHash": "1-The Crowd (Trading Card)"}]})
        self.assertEqual(parse_cartas(p), ["1-The Crowd (Trading Card)"])

    def test_nao_duplica(self):
        p = pagina({"a": [carta("1-X", "T Trading Card")],
                    "b": [carta("1-X", "T Trading Card")]})
        self.assertEqual(parse_cartas(p), ["1-X"])

    def test_pagina_sem_dados_devolve_vazio(self):
        self.assertEqual(parse_cartas("<html>nada</html>"), [])
        self.assertEqual(parse_cartas(""), [])


class TestParseHistorico(unittest.TestCase):
    def test_extrai_precos_de_query_aninhada(self):
        p = pagina({"queries": [{
            "queryKey": ["market", "pricehistory", 753, "607230-Dwarf"],
            "state": {"status": "success", "data": {"prices": [
                {"time": 1000, "price_median": 0.3, "purchases": 2}]}}}]})
        self.assertEqual(parse_historico(p),
                         [{"time": 1000, "price_median": 0.3, "purchases": 2}])

    def test_item_valido_sem_vendas_devolve_lista_vazia(self):
        p = pagina({"queries": [{
            "queryKey": ["market", "pricehistory", 753, "607230-X"],
            "state": {"status": "success", "data": {"prices": []}}}]})
        self.assertEqual(parse_historico(p), [])

    def test_pagina_sem_pricehistory(self):
        self.assertEqual(parse_historico("<html>nada</html>"), [])


class TestResumir(unittest.TestCase):
    AGORA = 1000 * 86400

    def test_janelas_e_dias_parado(self):
        pr = [{"time": self.AGORA - 200 * 86400, "purchases": 50},
              {"time": self.AGORA - 60 * 86400, "purchases": 7},
              {"time": self.AGORA - 5 * 86400, "purchases": 3}]
        r = resumir(pr, self.AGORA)
        self.assertAlmostEqual(r["dias_parado"], 5.0)
        self.assertEqual(r["v7"], 3)
        self.assertEqual(r["v30"], 3)
        self.assertEqual(r["v90"], 10)
        self.assertEqual(r["total"], 60)

    def test_sem_historico(self):
        r = resumir([], self.AGORA)
        self.assertIsNone(r["ultima_venda"])
        self.assertIsNone(r["dias_parado"])
        self.assertEqual(r["v30"], 0)


class TestAgregar(unittest.TestCase):
    """Mediana entre as cartas amostradas: uma carta sozinha mente (ClockwiZZZe
    tinha carta de 26 dias num set cuja mediana era 217)."""

    def test_mediana_entre_cartas(self):
        a = agregar([{"dias_parado": 26.0, "v30": 1, "v90": 3},
                     {"dias_parado": 217.0, "v30": 0, "v90": 0},
                     {"dias_parado": 506.0, "v30": 0, "v90": 0}])
        self.assertAlmostEqual(a["dias_parado"], 217.0)
        self.assertEqual(a["v30"], 0)
        self.assertEqual(a["n_amostra"], 3)

    def test_ignora_cartas_sem_historico(self):
        a = agregar([{"dias_parado": None, "v30": 0, "v90": 0},
                     {"dias_parado": 10.0, "v30": 5, "v90": 9}])
        self.assertAlmostEqual(a["dias_parado"], 10.0)
        self.assertEqual(a["n_amostra"], 1)

    def test_nenhuma_carta_com_historico(self):
        a = agregar([{"dias_parado": None, "v30": 0, "v90": 0}])
        self.assertIsNone(a["dias_parado"])
        self.assertEqual(a["n_amostra"], 0)

    def test_lista_vazia(self):
        self.assertEqual(agregar([])["n_amostra"], 0)


class TestPickSample(unittest.TestCase):
    def test_espalha_incluindo_as_pontas(self):
        self.assertEqual(pick_sample(list("abcdefghi"), 3), ["a", "e", "i"])

    def test_menos_itens_que_a_amostra(self):
        self.assertEqual(pick_sample(["a", "b"], 3), ["a", "b"])

    def test_vazio(self):
        self.assertEqual(pick_sample([], 3), [])


if __name__ == "__main__":
    unittest.main()


class TestTemplateHtml(unittest.TestCase):
    """Cabecalhos e celulas sao escritos em pontos distintos do template; ja
    saiu de sincronia uma vez, com a coluna Correcao 3 posicoes fora do lugar."""

    def test_cabecalhos_e_celulas_tem_a_mesma_contagem(self):
        import re

        import render
        ths = re.findall(r'<th[^>]*data-k="[^"]+"', render.TEMPLATE)
        corpo = render.TEMPLATE[render.TEMPLATE.index("shown.map"):]
        corpo = corpo[:corpo.index('.join("")')]
        tds = re.findall(r"<td[^>]*>", corpo)
        self.assertEqual(len(ths), len(tds),
                         "%d cabecalhos para %d celulas" % (len(ths), len(tds)))


class TestDispersaoViva(unittest.TestCase):
    """A dispersao do steam.tools usa so as cartas que ELE precificou. Quando a
    carta cara nao esta entre elas, o set parece coerente e nao esta: Pulstario
    mostrava disp 0,96 sobre 4 cartas enquanto a 5a valia 10x as outras juntas."""

    def test_set_coerente_tem_dispersao_baixa(self):
        from marketpage import dispersao
        self.assertLess(dispersao({"a": 0.30, "b": 0.32, "c": 0.28}), 0.2)

    def test_uma_carta_dominante_estoura_a_dispersao(self):
        from marketpage import dispersao
        d = dispersao({"a": 0.06, "b": 0.14, "c": 0.49, "d": 0.61,
                       "e": 1.20, "f": 11.77})
        self.assertGreater(d, 1.5)

    def test_precos_iguais_dao_zero(self):
        from marketpage import dispersao
        self.assertEqual(dispersao({"a": 1.0, "b": 1.0}), 0.0)

    def test_vazio_ou_media_zero_devolve_zero(self):
        from marketpage import dispersao
        self.assertEqual(dispersao({}), 0.0)
        self.assertEqual(dispersao({"a": 0.0}), 0.0)

    def test_uma_carta_so_nao_tem_dispersao(self):
        from marketpage import dispersao
        self.assertEqual(dispersao({"a": 5.0}), 0.0)
