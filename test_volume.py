"""Exercita o loop do volume.py com a rede mockada.

Necessario porque o Mercado Steam limita por IP: nao da para depender de
chamadas reais para saber se backoff, cache e retomada funcionam.
"""
import time
import unittest
from unittest import mock

import volume
from test_marketpage import pagina

DEALS = [
    {"appid": "1", "game": "Jogo Um", "preco": 10.0, "liquidez": 200, "disp": 0.3,
     "off": 0, "f2p": False, "cobertura": 1.2, "custo_liq": -2.0, "drops": 3},
    {"appid": "2", "game": "Jogo Dois", "preco": 20.0, "liquidez": 300, "disp": 0.4,
     "off": 50, "f2p": False, "cobertura": 1.1, "custo_liq": -6.0, "drops": 4},
]

def busca_html(preco="$3.00"):
    """Pagina de busca com dois cards normais e um foil, a um preco dado."""
    return pagina({"q": [
        {"strHash": "1-A", "strMinSellSubtotal": preco,
         "asset_description": {"type": "X Trading Card"}},
        {"strHash": "1-B", "strMinSellSubtotal": preco,
         "asset_description": {"type": "X Trading Card"}},
        {"strHash": "1-F (Foil)", "strMinSellSubtotal": "$40.00",
         "asset_description": {"type": "X Foil Trading Card"}},
    ]})


# US$3,00 x 3 drops x 5,154 / 1,15 = R$40,3 -> bem acima dos R$10 do jogo
BUSCA_HTML = busca_html()


def item_html(dias_atras, purchases):
    t = time.time() - dias_atras * 86400
    return pagina({"q": [{"queryKey": ["market", "pricehistory", 753, "1-A"],
                          "state": {"data": {"prices": [
                              {"time": t, "price_median": 1.0,
                               "purchases": purchases}]}}}]})


def rodar(baixar, cache=None, nomes=None, argv=("volume.py", "--delay", "0.01")):
    gravado = {}

    def fake_write(nome, data):
        gravado[nome] = dict(data)

    def fake_read(nome, obrigatorio=True):
        if nome == "volume.json":
            return (cache or {}), 0
        if nome == "cardnames.json":
            return (nomes or {}), 0
        return {}, 0

    with mock.patch.object(volume, "build_deals", return_value=(DEALS, 0, 5.0, 0)), \
         mock.patch.object(volume, "read_cache", side_effect=fake_read), \
         mock.patch.object(volume, "write_cache", side_effect=fake_write), \
         mock.patch.object(volume, "baixar", side_effect=baixar), \
         mock.patch.object(volume.time, "sleep"), \
         mock.patch.object(volume.sys, "argv", list(argv)):
        rc = volume.main()
    return rc, gravado


class TestMedicao(unittest.TestCase):
    def test_grava_dias_parado_e_v30(self):
        def baixar(url, timeout=45):
            return (BUSCA_HTML if "search" in url else item_html(3, 7)), None

        rc, g = rodar(baixar)
        self.assertEqual(rc, 0)
        v = g["volume.json"]["1"]
        self.assertAlmostEqual(v["dias_parado"], 3.0, places=1)
        self.assertEqual(v["v30"], 7)
        self.assertEqual(v["game"], "Jogo Um")

    def test_nomes_das_cartas_sao_cacheados_sem_foil(self):
        def baixar(url, timeout=45):
            return (BUSCA_HTML if "search" in url else item_html(1, 1)), None

        _, g = rodar(baixar)
        self.assertEqual(g["cardnames.json"]["1"], ["1-A", "1-B"])

    def test_busca_e_refeita_toda_rodada_pelos_precos(self):
        """Nome nao muda, mas preco sim -- e e o preco que revela valor obsoleto."""
        urls = []

        def baixar(url, timeout=45):
            urls.append(url)
            return (BUSCA_HTML if "search" in url else item_html(1, 1)), None

        rodar(baixar, nomes={"1": ["1-A"], "2": ["2-A"]})
        self.assertTrue([u for u in urls if "search" in u])

    def test_cache_de_nomes_socorre_quando_a_busca_falha(self):
        def baixar(url, timeout=45):
            if "search" in url:
                return None, "503"
            return item_html(4, 2), None

        _, g = rodar(baixar, nomes={"1": ["1-A"], "2": ["2-A"]})
        self.assertIn("volume.json", g, "deve medir usando os nomes do cache")


class TestValorAoVivo(unittest.TestCase):
    """Fase A: os precos atuais podem desmentir o valor publicado pelo steam.tools
    (visto na pratica: Kaiju Wars 48x, Laser Lasso 5,5x). Quando desmentem, nao
    faz sentido gastar a fase B medindo o giro de um valor que nao existe."""

    def test_valor_colapsado_pula_a_fase_B(self):
        urls = []

        def baixar(url, timeout=45):
            urls.append(url)
            # US$0,01 x 3 drops -> centavos, muito abaixo dos R$10 do jogo
            return (busca_html("$0.01") if "search" in url else item_html(1, 1)), None

        _, g = rodar(baixar)
        self.assertFalse([u for u in urls if "listings" in u],
                         "nenhuma pagina de item deve ser baixada")
        reg = g["volume.json"]["1"]
        self.assertTrue(reg["pulou"])
        self.assertIsNone(reg["dias_parado"])

    def test_valor_confirmado_segue_para_a_fase_B(self):
        def baixar(url, timeout=45):
            return (busca_html("$3.00") if "search" in url else item_html(2, 8)), None

        _, g = rodar(baixar)
        reg = g["volume.json"]["1"]
        self.assertFalse(reg["pulou"])
        self.assertEqual(reg["v30"], 8)
        self.assertGreater(reg["cobertura_viva"], 1.0)

    def test_todos_ignora_o_descarte(self):
        def baixar(url, timeout=45):
            return (busca_html("$0.01") if "search" in url else item_html(1, 1)), None

        _, g = rodar(baixar, argv=("volume.py", "--delay", "0.01", "--todos"))
        self.assertFalse(g["volume.json"]["1"]["pulou"])


class TestPodaPelaBiblioteca(unittest.TestCase):
    """Jogo ja possuido nao rende drop novo e cada medicao custa ~4 requisicoes."""

    def test_jogo_possuido_nao_gasta_requisicao(self):
        urls = []

        def baixar(url, timeout=45):
            urls.append(url)
            return (BUSCA_HTML if "search" in url else item_html(1, 5)), None

        with mock.patch.object(volume, "build_deals", return_value=(DEALS, 0, 5.154, 0)),              mock.patch.object(volume, "carregar_possuidos", return_value={"1"}),              mock.patch.object(volume, "read_cache", return_value=({}, 0)),              mock.patch.object(volume, "write_cache"),              mock.patch.object(volume, "baixar", side_effect=baixar),              mock.patch.object(volume.time, "sleep"),              mock.patch.object(volume.sys, "argv", ["volume.py", "--delay", "0.01"]):
            volume.main()
        self.assertFalse([u for u in urls if "app_1&" in u],
                         "jogo possuido nao deve ser consultado")
        self.assertTrue([u for u in urls if "app_2&" in u],
                        "os demais devem seguir normalmente")

    def test_sem_biblioteca_nada_e_podado(self):
        urls = []

        def baixar(url, timeout=45):
            urls.append(url)
            return (BUSCA_HTML if "search" in url else item_html(1, 5)), None

        with mock.patch.object(volume, "build_deals", return_value=(DEALS, 0, 5.154, 0)),              mock.patch.object(volume, "carregar_possuidos", return_value=set()),              mock.patch.object(volume, "read_cache", return_value=({}, 0)),              mock.patch.object(volume, "write_cache"),              mock.patch.object(volume, "baixar", side_effect=baixar),              mock.patch.object(volume.time, "sleep"),              mock.patch.object(volume.sys, "argv", ["volume.py", "--delay", "0.01"]):
            volume.main()
        self.assertTrue([u for u in urls if "app_1&" in u])


class TestRegraDeAlvo(unittest.TestCase):
    def test_jogo_sem_lucro_nao_e_medido(self):
        sem_lucro = [dict(DEALS[0], custo_liq=3.0)]
        chamadas = []

        def baixar(url, timeout=45):
            chamadas.append(url)
            return BUSCA_HTML, None

        with mock.patch.object(volume, "build_deals", return_value=(sem_lucro, 0, 5.154, 0)),              mock.patch.object(volume, "read_cache", return_value=({}, 0)),              mock.patch.object(volume, "write_cache"),              mock.patch.object(volume, "baixar", side_effect=baixar),              mock.patch.object(volume.time, "sleep"),              mock.patch.object(volume.sys, "argv", ["volume.py"]):
            volume.main()
        self.assertEqual(chamadas, [], "nao deve gastar requisicao em jogo sem lucro")


class TestFalhas(unittest.TestCase):
    def test_429_nao_grava_e_dobra_a_espera(self):
        esperas = []

        def baixar(url, timeout=45):
            return None, "429"

        with mock.patch.object(volume, "build_deals", return_value=(DEALS, 0, 5.0, 0)), \
             mock.patch.object(volume, "read_cache", return_value=({}, 0)), \
             mock.patch.object(volume, "write_cache"), \
             mock.patch.object(volume, "baixar", side_effect=baixar), \
             mock.patch.object(volume.time, "sleep", side_effect=esperas.append), \
             mock.patch.object(volume.sys, "argv", ["volume.py", "--delay", "4"]):
            rc = volume.main()
        self.assertEqual(rc, 0)
        self.assertEqual(esperas, [8.0, 16.0], "backoff deve dobrar a cada 429")

    def test_pagina_invalida_nao_vira_medicao(self):
        def baixar(url, timeout=45):
            if "search" in url:
                return BUSCA_HTML, None
            return "<html>Market Item</html>", None   # sem pricehistory

        _, g = rodar(baixar)
        self.assertNotIn("volume.json", g, "nenhuma medicao deve ser gravada")

    def test_busca_sem_cartas_e_erro_nao_medicao(self):
        def baixar(url, timeout=45):
            return "<html>vazio</html>", None

        _, g = rodar(baixar)
        self.assertNotIn("volume.json", g)


class TestRetomada(unittest.TestCase):
    def test_entrada_fresca_e_pulada(self):
        chamadas = []

        def baixar(url, timeout=45):
            chamadas.append(url)
            return (BUSCA_HTML if "search" in url else item_html(1, 1)), None

        rodar(baixar, cache={"1": {"dias_parado": 5, "fetched_at": time.time()}})
        self.assertTrue(all("app_1&" not in u for u in chamadas),
                        "jogo com cache fresco nao deve ser rebuscado")

    def test_force_remede_tudo(self):
        vistos = []

        def baixar(url, timeout=45):
            vistos.append(url)
            return (BUSCA_HTML if "search" in url else item_html(1, 1)), None

        rodar(baixar, cache={"1": {"dias_parado": 5, "fetched_at": time.time()}},
              argv=("volume.py", "--delay", "0.01", "--force"))
        self.assertTrue(any("app_1&" in u for u in vistos))


class TestSaidaNaoAsciiEmConsoleLegado(unittest.TestCase):
    """O console do Windows usa cp1252. Nomes de jogo com caracteres fora dessa
    tabela (ex.: a exclamacao fullwidth de varios titulos japoneses) derrubavam
    a rodada inteira no meio, com UnicodeEncodeError."""

    def test_nome_fullwidth_nao_derruba_a_rodada(self):
        import io
        exotico = [dict(DEALS[0], appid="9", game="Ore no Kouhai！ Special")]

        def baixar(url, timeout=45):
            return (BUSCA_HTML if "search" in url else item_html(2, 4)), None

        cp1252 = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")
        with mock.patch.object(volume, "build_deals", return_value=(exotico, 0, 5.0, 0)),              mock.patch.object(volume, "read_cache", return_value=({}, 0)),              mock.patch.object(volume, "write_cache"),              mock.patch.object(volume, "baixar", side_effect=baixar),              mock.patch.object(volume.time, "sleep"),              mock.patch.object(volume.sys, "argv", ["volume.py", "--delay", "0.01"]),              mock.patch.object(volume.sys, "stdout", cp1252):
            rc = volume.main()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
