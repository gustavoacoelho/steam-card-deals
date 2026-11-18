import unittest

from cardcalc import compute_deal, needs_refresh, parse_price_response

SET = {"appid": "221540", "game": "Defense Grid 2", "discount": "1.00",
       "f2p": False, "normal": {"count": 9}}
PRICE_OK = {"status": "ok", "final": 1000, "initial": 1000, "discount_percent": 0}


class TestComputeDeal(unittest.TestCase):
    def test_cobertura_e_custo_liquido(self):
        d = compute_deal(SET, PRICE_OK, brl_rate=5.154)
        self.assertAlmostEqual(d["cartas"], 5.154, places=4)
        self.assertAlmostEqual(d["preco"], 10.00, places=4)
        self.assertAlmostEqual(d["cobertura"], 0.5154, places=4)
        self.assertAlmostEqual(d["custo_liq"], 4.846, places=4)
        self.assertEqual(d["n_cartas"], 9)
        self.assertEqual(d["game"], "Defense Grid 2")

    def test_ajuste_conservador_reduz_valor_das_cartas(self):
        d = compute_deal(SET, PRICE_OK, brl_rate=5.154, adjust=0.5)
        self.assertAlmostEqual(d["cartas"], 2.577, places=4)
        self.assertAlmostEqual(d["cobertura"], 0.2577, places=4)

    def test_preco_zero_nao_divide_por_zero(self):
        free = dict(PRICE_OK, final=0)
        self.assertIsNone(compute_deal(SET, free, brl_rate=5.154))

    def test_status_nao_ok_e_descartado(self):
        self.assertIsNone(compute_deal(SET, {"status": "unavailable"}, brl_rate=5.154))
        self.assertIsNone(compute_deal(SET, {"status": "free"}, brl_rate=5.154))

    def test_set_sem_discount_e_descartado(self):
        self.assertIsNone(compute_deal({"appid": "1", "game": "X"}, PRICE_OK, brl_rate=5.154))
        self.assertIsNone(compute_deal(dict(SET, discount=None), PRICE_OK, brl_rate=5.154))

    def test_promocao_preserva_preco_cheio_e_percentual(self):
        promo = {"status": "ok", "final": 529, "initial": 2649, "discount_percent": 80}
        d = compute_deal(SET, promo, brl_rate=5.154)
        self.assertAlmostEqual(d["preco"], 5.29, places=4)
        self.assertAlmostEqual(d["preco_cheio"], 26.49, places=4)
        self.assertEqual(d["off"], 80)


if __name__ == "__main__":
    unittest.main()


class TestParsePriceResponse(unittest.TestCase):
    PAYLOAD = {
        "221540": {"success": True, "data": {"price_overview": {
            "currency": "BRL", "initial": 2898, "final": 2898, "discount_percent": 0}}},
        "1174180": {"success": True, "data": {"price_overview": {
            "currency": "BRL", "initial": 29990, "final": 7497, "discount_percent": 75}}},
        "570": {"success": True, "data": []},
        "999999": {"success": False},
    }

    def test_extrai_precos(self):
        out = parse_price_response(self.PAYLOAD, now=1000)
        self.assertEqual(out["221540"], {
            "status": "ok", "final": 2898, "initial": 2898,
            "discount_percent": 0, "currency": "BRL", "fetched_at": 1000})
        self.assertEqual(out["1174180"]["final"], 7497)
        self.assertEqual(out["1174180"]["discount_percent"], 75)

    def test_sem_price_overview_vira_free(self):
        out = parse_price_response(self.PAYLOAD, now=1000)
        self.assertEqual(out["570"], {"status": "free", "fetched_at": 1000})

    def test_success_false_vira_unavailable(self):
        out = parse_price_response(self.PAYLOAD, now=1000)
        self.assertEqual(out["999999"], {"status": "unavailable", "fetched_at": 1000})

    def test_entrada_nula_nao_quebra(self):
        out = parse_price_response({"1": None}, now=1000)
        self.assertEqual(out["1"]["status"], "unavailable")


HOUR = 3600


class TestNeedsRefresh(unittest.TestCase):
    def test_sem_entrada_precisa_buscar(self):
        self.assertTrue(needs_refresh(None, now=100 * HOUR))

    def test_ok_recente_nao_precisa(self):
        e = {"status": "ok", "fetched_at": 100 * HOUR}
        self.assertFalse(needs_refresh(e, now=100 * HOUR + 5 * HOUR))

    def test_ok_vencido_precisa(self):
        e = {"status": "ok", "fetched_at": 100 * HOUR}
        self.assertTrue(needs_refresh(e, now=100 * HOUR + 7 * HOUR))

    def test_free_usa_ttl_longo(self):
        e = {"status": "free", "fetched_at": 100 * HOUR}
        self.assertFalse(needs_refresh(e, now=100 * HOUR + 100 * HOUR))
        self.assertTrue(needs_refresh(e, now=100 * HOUR + 200 * HOUR))

    def test_entrada_sem_fetched_at_precisa(self):
        self.assertTrue(needs_refresh({"status": "ok"}, now=100 * HOUR))

    def test_ttl_customizado(self):
        e = {"status": "ok", "fetched_at": 0}
        self.assertFalse(needs_refresh(e, now=10, ttl_ok=100))
        self.assertTrue(needs_refresh(e, now=200, ttl_ok=100))


class TestLiquidez(unittest.TestCase):
    def test_liquidez_vem_da_quantidade_listada(self):
        s = dict(SET, normal={"count": 9, "quantity": 862})
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["liquidez"], 862)

    def test_liquidez_ausente_vira_zero(self):
        d = compute_deal(SET, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["liquidez"], 0)


class TestDispersao(unittest.TestCase):
    def test_disp_e_std_sobre_avg(self):
        s = dict(SET, normal={"count": 6, "avg": "4.00", "std": "7.55", "quantity": 58})
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertAlmostEqual(d["disp"], 1.8875, places=4)

    def test_mercado_saudavel_tem_disp_baixa(self):
        s = dict(SET, normal={"count": 9, "avg": "0.05", "std": "0.01", "quantity": 862})
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertAlmostEqual(d["disp"], 0.2, places=4)

    def test_avg_zero_nao_divide_por_zero(self):
        s = dict(SET, normal={"count": 6, "avg": "0.00", "std": "0.00"})
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["disp"], 0.0)

    def test_campos_ausentes_viram_zero(self):
        d = compute_deal(SET, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["disp"], 0.0)


class TestDrops(unittest.TestCase):
    """O teto de drops da Steam e metade do set arredondada para cima -- a mesma
    regra embutida no campo `discount` (confirmada em 6772 sets, 100% ceil)."""

    def test_set_par(self):
        s = dict(SET, normal={"count": 10}, true_count=10)
        self.assertEqual(compute_deal(s, PRICE_OK, brl_rate=5.154)["drops"], 5)

    def test_set_impar_arredonda_para_cima(self):
        s = dict(SET, normal={"count": 9}, true_count=9)
        self.assertEqual(compute_deal(s, PRICE_OK, brl_rate=5.154)["drops"], 5)

    def test_set_completo_nao_sinaliza_falta(self):
        s = dict(SET, normal={"count": 8}, true_count=8)
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["n_real"], 8)
        self.assertEqual(d["drops"], 4)
        self.assertFalse(d["incompleto"])

    def test_drops_subestimados_sao_sinalizados(self):
        # mercado precifica 4 das 5 cartas: ceil(4/2)=2 contados, ceil(5/2)=3 reais
        s = dict(SET, normal={"count": 4}, true_count=5)
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["drops"], 3, "coluna mostra o que voce recebe")
        self.assertEqual(d["drops_contados"], 2, "o que o valor usou")
        self.assertTrue(d["incompleto"])

    def test_set_incompleto_sem_perda_de_drops_nao_sinaliza(self):
        # mercado precifica 7 das 8: ceil(7/2)=4 == ceil(8/2)=4, nada perdido
        s = dict(SET, normal={"count": 7}, true_count=8)
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["drops"], 4)
        self.assertEqual(d["drops_contados"], 4)
        self.assertFalse(d["incompleto"], "asterisco so quando ha drop a menos")

    def test_sem_true_count_assume_o_que_o_mercado_ve(self):
        s = dict(SET, normal={"count": 6})
        d = compute_deal(s, PRICE_OK, brl_rate=5.154)
        self.assertEqual(d["n_real"], 6)
        self.assertFalse(d["incompleto"])
