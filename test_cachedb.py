import unittest

from cachedb import regra_alvo


def jogo(preco, custo_liq):
    return {"preco": preco, "custo_liq": custo_liq}


class TestRegraAlvo(unittest.TestCase):
    """Alvo: jogo que sai de graca ou melhor. Barato com qualquer lucro entra;
    caro so entra se o lucro justificar o desembolso."""

    def test_barato_com_lucro_entra(self):
        self.assertTrue(regra_alvo(jogo(8.0, -2.0)))

    def test_barato_sem_lucro_fica_de_fora(self):
        self.assertFalse(regra_alvo(jogo(8.0, 0.50)))

    def test_custo_liquido_zero_nao_e_lucro(self):
        self.assertFalse(regra_alvo(jogo(8.0, 0.0)))

    def test_caro_com_lucro_pequeno_fica_de_fora(self):
        self.assertFalse(regra_alvo(jogo(50.0, -2.50)))

    def test_caro_com_lucro_grande_entra(self):
        self.assertTrue(regra_alvo(jogo(50.0, -8.0)))

    def test_limite_do_preco_e_exclusivo(self):
        self.assertTrue(regra_alvo(jogo(14.99, -1.0)))
        self.assertFalse(regra_alvo(jogo(15.0, -1.0)))

    def test_limite_do_lucro_alto_e_exclusivo(self):
        self.assertFalse(regra_alvo(jogo(20.0, -5.0)))
        self.assertTrue(regra_alvo(jogo(20.0, -5.01)))

    def test_parametros_customizados(self):
        self.assertTrue(regra_alvo(jogo(25.0, -1.0), preco_teto=30.0))
        self.assertTrue(regra_alvo(jogo(25.0, -3.0), lucro_alto=2.0))


if __name__ == "__main__":
    unittest.main()
