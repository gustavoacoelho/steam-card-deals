import unittest

from cesta import melhor_cesta


def j(nome, preco, lucro, dias=1.0):
    return {"game": nome, "preco": preco, "lucro": lucro, "dias": dias}


class TestMelhorCesta(unittest.TestCase):
    def test_escolhe_a_combinacao_de_maior_lucro(self):
        # 2+3 rende 7; 4 sozinho rende 5. O otimo nao e o item mais caro.
        c = melhor_cesta([j("A", 2.0, 3.0), j("B", 3.0, 4.0), j("C", 4.0, 5.0)], 5.0)
        self.assertEqual({x["game"] for x in c}, {"A", "B"})

    def test_respeita_o_orcamento(self):
        c = melhor_cesta([j("A", 10.0, 99.0), j("B", 1.0, 1.0)], 5.0)
        self.assertEqual([x["game"] for x in c], ["B"])

    def test_orcamento_insuficiente_devolve_vazio(self):
        self.assertEqual(melhor_cesta([j("A", 10.0, 99.0)], 5.0), [])

    def test_centavos_nao_se_perdem(self):
        c = melhor_cesta([j("A", 1.74, 0.03), j("B", 1.79, 1.93)], 1.79)
        self.assertEqual([x["game"] for x in c], ["B"])

    def test_lista_vazia(self):
        self.assertEqual(melhor_cesta([], 10.0), [])

    def test_limite_de_dias_exclui_os_lentos(self):
        c = melhor_cesta([j("lento", 2.0, 9.0, dias=40.0),
                          j("rapido", 2.0, 1.0, dias=1.0)], 2.0, dias_max=10.0)
        self.assertEqual([x["game"] for x in c], ["rapido"])


if __name__ == "__main__":
    unittest.main()


class TestSaidaLegivel(unittest.TestCase):
    """Nomes com pontuacao fullwidth ("I got a cat maid！") viravam "?" no
    console cp1252 -- e o nome exibido deixava de bater com o nome real, o que
    ja fez uma busca por "cat maid?" falhar em silencio."""

    def test_fullwidth_vira_ascii_equivalente(self):
        import io
        from unittest import mock
        import cesta
        buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")
        with mock.patch.object(cesta.sys, "stdout", buf):
            cesta.saida("I got a cat maid\uff01")
        buf.seek(0)
        self.assertIn("I got a cat maid!", buf.buffer.getvalue().decode("cp1252"))
