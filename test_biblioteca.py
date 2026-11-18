import unittest

from biblioteca import extrair_steamid, parse_biblioteca


class TestExtrairSteamid(unittest.TestCase):
    def test_id64_puro_passa_direto(self):
        self.assertEqual(extrair_steamid("76561197960287930"), "76561197960287930")

    def test_url_de_vanity_precisa_de_resolucao(self):
        self.assertIsNone(extrair_steamid("https://steamcommunity.com/id/exemplo/"))

    def test_url_de_profiles_traz_o_id(self):
        self.assertEqual(
            extrair_steamid("https://steamcommunity.com/profiles/76561197960287930/"),
            "76561197960287930")

    def test_texto_solto_nao_vira_id(self):
        self.assertIsNone(extrair_steamid("exemplo"))

    def test_numero_curto_nao_e_id64(self):
        self.assertIsNone(extrair_steamid("12345"))


class TestParseBiblioteca(unittest.TestCase):
    def test_extrai_appids(self):
        p = {"success": True, "games": ["10", "220", "620"]}
        self.assertEqual(parse_biblioteca(p), {"10", "220", "620"})

    def test_normaliza_numeros_para_texto(self):
        p = {"success": True, "games": [10, 220]}
        self.assertEqual(parse_biblioteca(p), {"10", "220"})

    def test_insucesso_devolve_none(self):
        self.assertIsNone(parse_biblioteca({"success": False, "reason": "privado"}))
        self.assertIsNone(parse_biblioteca(None))

    def test_lista_privada_devolve_none_nao_conjunto_vazio(self):
        """games:null significa lista privada. Tratar como conjunto vazio faria a
        ferramenta achar que o usuario nao tem jogo nenhum e nao podar nada."""
        self.assertIsNone(parse_biblioteca({"success": True, "games": None}))

    def test_biblioteca_realmente_vazia_e_conjunto_vazio(self):
        self.assertEqual(parse_biblioteca({"success": True, "games": []}), set())


if __name__ == "__main__":
    unittest.main()


class TestMesclagem(unittest.TestCase):
    """O endpoint do steam.tools serve cache e demora a ver compras recentes.
    Sobrescrever o arquivo apagaria jogos ja conhecidos e faria a ferramenta
    recomendar de novo o que voce acabou de comprar."""

    def test_mescla_preserva_appids_conhecidos(self):
        from biblioteca import mesclar
        self.assertEqual(mesclar({"10", "20"}, {"20", "30"}), {"10", "20", "30"})

    def test_mescla_com_conjunto_vazio(self):
        from biblioteca import mesclar
        self.assertEqual(mesclar(set(), {"10"}), {"10"})
        self.assertEqual(mesclar({"10"}, set()), {"10"})

    def test_normaliza_para_texto(self):
        from biblioteca import mesclar
        self.assertEqual(mesclar({10}, {"20"}), {"10", "20"})
