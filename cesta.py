"""Escolhe o que comprar com um saldo dado. Sem rede, sem disco.

Cada jogo so dropa cartas uma vez por conta, entao a compra e um problema de
mochila: nao adianta repetir o melhor item, e o mais caro raramente e o melhor
uso do dinheiro.
"""
import argparse
import csv
import json
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))


def melhor_cesta(candidatos, orcamento, dias_max=None):
    """Combinacao de maior lucro que cabe no orcamento.

    Mochila exata em centavos -- trabalhar em float faz um jogo de R$1,79 nao
    caber num saldo de R$1,79.
    """
    itens = [c for c in candidatos
             if dias_max is None or c.get("dias", 0) <= dias_max]
    teto = int(round(orcamento * 100))
    if teto <= 0 or not itens:
        return []
    dp = [0.0] * (teto + 1)
    escolha = [[] for _ in range(teto + 1)]
    for c in itens:
        custo = int(round(c["preco"] * 100))
        if custo <= 0 or custo > teto:
            continue
        for v in range(teto, custo - 1, -1):
            if dp[v - custo] + c["lucro"] > dp[v]:
                dp[v] = dp[v - custo] + c["lucro"]
                escolha[v] = escolha[v - custo] + [c]
    melhor = max(range(teto + 1), key=lambda v: dp[v])
    return escolha[melhor]


def _num(txt):
    return float(txt.replace(",", ".")) if txt else None


def carregar(caminho, possuidos, disp_max=1.0):
    """Candidatos verificados ao vivo, com lucro real e mercado que absorve."""
    out = []
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for x in csv.DictReader(f, delimiter=";"):
            if x["verificado"] != "True" or x["appid"] in possuidos:
                continue
            lucro = -_num(x["custo_liq"])
            v30 = int(x["v30"] or 0)
            parado = _num(x["parado"]) if x["parado"] else 999
            if lucro <= 0 or v30 < 3 or parado > 30:
                continue
            # Dispersao alta = uma carta domina o set. O "valor esperado" vira
            # loteria, porque voce recebe metade do set sorteada.
            if _num(x["disp"]) > disp_max:
                continue
            drops = int(x["drops"].split("/")[0])
            out.append({"game": x["game"], "appid": x["appid"],
                        "preco": _num(x["preco"]), "lucro": lucro,
                        "v30": v30, "off": int(x["off"] or 0),
                        "dias": drops / (v30 / 30.0)})
    return out


def saida(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        # NFKC converte pontuacao fullwidth no equivalente ASCII ("！" -> "!"),
        # para o nome exibido continuar batendo com o nome buscado.
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        msg = unicodedata.normalize("NFKC", msg)
        print(msg.encode(enc, "replace").decode(enc))


def main():
    ap = argparse.ArgumentParser(description="O que comprar com o saldo atual.")
    ap.add_argument("carteira", type=float, help="saldo na carteira Steam, em BRL")
    ap.add_argument("--dias-max", type=float, default=None,
                    help="ignora jogos que demoram mais que isso para escoar")
    ap.add_argument("--disp-max", type=float, default=1.0,
                    help="descarta sets onde uma carta domina o valor (padrao 1.0)")
    args = ap.parse_args()

    owned = os.path.join(ROOT, "cache", "owned.json")
    possuidos = set()
    if os.path.exists(owned):
        with open(owned, encoding="utf-8") as f:
            possuidos = {str(a) for a in json.load(f)}

    cand = carregar(os.path.join(ROOT, "deals.csv"), possuidos, args.disp_max)
    if not cand:
        saida("Nenhum candidato. Rode `python report.py` (e `volume.py` antes).")
        return 1

    cesta = melhor_cesta(cand, args.carteira, args.dias_max)
    saida("saldo R$%.2f | %d candidatos (%d jogos da sua biblioteca ignorados)"
          % (args.carteira, len(cand), len(possuidos)))
    if not cesta:
        mais_barato = min(c["preco"] for c in cand)
        saida("Nada cabe. O mais barato custa R$%.2f." % mais_barato)
        return 0

    saida("")
    # O link sai na MESMA linha do jogo: montar a lista de links separada e
    # casar por posicao ja trocou 4 de 8 appids numa compra real.
    saida("%-36s %7s %7s %6s %7s  %s" % ("comprar", "preco", "lucro", "30d", "escoar", "link"))
    for c in sorted(cesta, key=lambda c: -c["lucro"]):
        saida("%-36s %7.2f %7.2f %6d %5.1fd  store.steampowered.com/app/%s%s"
              % (c["game"][:36], c["preco"], c["lucro"], c["v30"], c["dias"],
                 c["appid"], "  (promo)" if c["off"] else ""))
    gasto = sum(c["preco"] for c in cesta)
    lucro = sum(c["lucro"] for c in cesta)
    saida("")
    saida("gasta R$%.2f, sobra R$%.2f | carteira volta a R$%.2f em ~%.0f dias"
          % (gasto, args.carteira - gasto, args.carteira + lucro,
             max(c["dias"] for c in cesta)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
