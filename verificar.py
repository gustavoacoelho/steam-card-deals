"""Varredura carta a carta antes de comprar.

O volume.py amostra 3 cartas e tira a mediana, entao uma carta encalhada dentro
de um set saudavel passa despercebida -- e e ela que trava a venda dos seus
drops. Aqui cada carta normal do set e medida: preco, dias sem vender e vendas
em 30 dias.

Uso: python verificar.py 745740 753360 ...
"""
import argparse
import sys
import time
import unicodedata
import urllib.parse

from marketpage import (dispersao, pagina_valida, parse_cartas, parse_historico,
                        parse_precos, resumir)
from volume import BUSCA, ITEM, baixar

PARADA_DIAS = 30


def saida(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        msg = unicodedata.normalize("NFKC", msg)
        print(msg.encode(enc, "replace").decode(enc))


def verificar(appid, delay):
    """Devolve a lista de alertas do jogo (vazia = tudo vende)."""
    html, erro = baixar(BUSCA.format(app=appid))
    if erro:
        saida("  [%s] busca falhou" % erro)
        return ["busca falhou"]
    cartas, precos = parse_cartas(html), parse_precos(html)
    if not cartas:
        saida("  sem cartas no Mercado")
        return ["sem cartas"]
    vals = sorted(precos.values(), reverse=True)
    saida("  %d cartas | dispersao %.2f | carta mais cara = %.0f%% do set"
          % (len(cartas), dispersao(precos), 100 * vals[0] / sum(vals) if vals else 0))
    alertas = []
    agora = time.time()
    for hn in cartas:
        time.sleep(delay)
        pag, erro = baixar(ITEM.format(hash=urllib.parse.quote(hn)))
        nome = hn.split("-", 1)[1]
        if erro or not pagina_valida(pag):
            saida("    %-34s nao consegui medir (%s)" % (nome[:34], erro or "pagina invalida"))
            alertas.append("%s: nao medida" % nome)
            continue
        r = resumir(parse_historico(pag), agora)
        preco = precos.get(hn)
        if r["dias_parado"] is None:
            saida("    %-34s US$%5s | NUNCA VENDEU" % (nome[:34], "%.2f" % preco if preco else "?"))
            alertas.append("%s: nunca vendeu" % nome)
            continue
        ruim = r["dias_parado"] > PARADA_DIAS or r["v30"] == 0
        saida("    %-34s US$%5s | %4.0fd parada | 30d %4d%s"
              % (nome[:34], "%.2f" % preco if preco else "?", r["dias_parado"], r["v30"],
                 "  <<< PARADA" if ruim else ""))
        if ruim:
            alertas.append("%s: %.0fd parada, %d vendas/30d" % (nome, r["dias_parado"], r["v30"]))
    return alertas


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("appids", nargs="+")
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()
    total = {}
    for i, app in enumerate(args.appids):
        if i:
            time.sleep(args.delay)
        saida("")
        saida("=== appid %s ===" % app)
        total[app] = verificar(app, args.delay)
    saida("")
    ruins = {a: v for a, v in total.items() if v}
    if not ruins:
        saida("Nenhuma carta parada. Todos os %d jogos liberados." % len(total))
    for a, v in ruins.items():
        saida("ATENCAO appid %s: %s" % (a, "; ".join(v)))
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
