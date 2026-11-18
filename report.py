"""Le o cache e emite deals.csv + deals.html. Nunca acessa a rede."""
import argparse
import csv
import os
import sys
import time

from cachedb import ROOT, build_deals, read_cache
from render import render_html

# Multiplica o valor das cartas. 1.0 = confia no numero do steam.tools.
# Baixe para 0.8 se quiser margem contra queda de preco e iliquidez.
AJUSTE_CONSERVADOR = 1.0

COLUNAS = ["appid", "game", "preco", "preco_cheio", "off",
           "cartas", "cobertura", "custo_liq", "n_cartas", "n_real", "drops", "drops_contados", "incompleto", "liquidez", "disp", "parado", "v30", "verificado", "stale", "f2p"]


def main():
    ap = argparse.ArgumentParser(description="Gera deals.csv e deals.html do cache.")
    ap.add_argument("--ajuste", type=float, default=AJUSTE_CONSERVADOR,
                    help="fator sobre o valor das cartas (padrao 1.0)")
    args = ap.parse_args()

    deals, sem_preco, rate, prices_mtime = build_deals(args.ajuste)

    # Liquidez real e opcional: so existe para os jogos que o volume.py mediu.
    vol, _ = read_cache("volume.json", obrigatorio=False)
    vol = vol or {}
    for d in deals:
        m = vol.get(d["appid"]) or {}
        d["parado"] = m.get("dias_parado")
        d["v30"] = m.get("v30") if m else None
        # Preco ao vivo manda: o publicado pelo steam.tools pode estar obsoleto
        # (visto 48x de diferenca). `stale` guarda o tamanho da correcao.
        # Dispersao ao vivo cobre o set inteiro; a do steam.tools so as cartas
        # que ele precificou, e cega quando a carta cara nao esta entre elas.
        if m.get("disp_vivo") is not None:
            d["disp"] = m["disp_vivo"]
        vivo = m.get("cartas_vivo")
        if vivo is not None and d["preco"]:
            d["stale"] = (d["cartas"] / vivo) if vivo > 0 else None
            d["cartas"] = vivo
            d["cobertura"] = vivo / d["preco"]
            d["custo_liq"] = d["preco"] - vivo
            d["verificado"] = True
        else:
            d["stale"] = None
            d["verificado"] = False
    medidos = sum(1 for d in deals if d["parado"] is not None)

    csv_path = os.path.join(ROOT, "deals.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, delimiter=";")
        w.writeheader()
        for d in deals:
            row = dict(d)
            for k in ("preco", "preco_cheio", "cartas", "custo_liq"):
                row[k] = ("%.2f" % row[k]).replace(".", ",")
            row["cobertura"] = ("%.1f" % (d["cobertura"] * 100)).replace(".", ",")
            row["disp"] = ("%.2f" % d["disp"]).replace(".", ",")
            row["parado"] = "" if d["parado"] is None else "%.0f" % d["parado"]
            row["v30"] = "" if d["v30"] is None else d["v30"]
            row["stale"] = "" if d["stale"] is None else ("%.1f" % d["stale"]).replace(".", ",")
            w.writerow(row)

    idade = (time.time() - prices_mtime) / 3600
    meta = ("%d jogos compar&aacute;veis &middot; %d ignorados (sem pre&ccedil;o, "
            "gr&aacute;tis ou delistados) &middot; taxa USD&rarr;BRL %.3f &middot; "
            "ajuste %g&times; &middot; pre&ccedil;os coletados h&aacute; %.1fh "
            "&middot; %d com pre&ccedil;o e liquidez verificados ao vivo"
            % (len(deals), sem_preco, rate, args.ajuste, idade, medidos))
    html_path = os.path.join(ROOT, "deals.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(deals, meta))

    print("%d jogos comparaveis, %d ignorados." % (len(deals), sem_preco))
    print("  " + csv_path)
    print("  " + html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
