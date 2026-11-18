"""Acesso ao cache em disco e montagem da lista de deals. Compartilhado por
report.py e volume.py, para que os dois enxerguem exatamente o mesmo universo."""
import json
import os
import sys

from cardcalc import compute_deal

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")


def read_cache(name, obrigatorio=True):
    """Le um JSON do cache. Sai com erro se faltar um arquivo obrigatorio."""
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        if not obrigatorio:
            return None, None
        print("ERRO: %s nao existe. Rode `python collect.py` primeiro." % path,
              file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f), os.path.getmtime(path)


def write_cache(name, data):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def build_deals(ajuste=1.0):
    """Devolve (deals ordenados por cobertura, ignorados, taxa_brl, idade_precos)."""
    set_data, _ = read_cache("set_data.json")
    currency, _ = read_cache("currency.json")
    prices, prices_mtime = read_cache("prices.json")

    rate = currency.get("BRL")
    if not rate:
        print("ERRO: currency.json sem taxa BRL.", file=sys.stderr)
        sys.exit(1)

    deals, ignorados = [], 0
    for s in set_data.get("sets", []):
        d = compute_deal(s, prices.get(s.get("appid")), rate, ajuste)
        if d is None:
            ignorados += 1
        else:
            deals.append(d)
    deals.sort(key=lambda d: d["cobertura"], reverse=True)
    return deals, ignorados, rate, prices_mtime


def carregar_possuidos():
    """Appids que o usuario ja tem, de cache/owned.json.

    Conjunto vazio quando o arquivo nao existe -- a poda e opcional, e a
    ferramenta funciona sem ela.
    """
    dados, _ = read_cache("owned.json", obrigatorio=False)
    return {str(a) for a in (dados or [])}


def regra_alvo(d, preco_teto=15.0, lucro_alto=5.0):
    """O jogo vale a analise cara?

    O objetivo e jogo virtualmente de graca, entao so entra quem ja promete
    lucro. Acima do teto de preco o lucro precisa ser grande o bastante para
    justificar o desembolso: 105% de cobertura num jogo de R$50 sao R$2,50 de
    ganho para R$50 parados.
    """
    lucro = -d["custo_liq"]
    if lucro <= 0:
        return False
    return d["preco"] < preco_teto or lucro > lucro_alto


def aplicar_filtros(deals, preco_min=0.0, preco_max=None, liquidez_min=0,
                    disp_max=None, so_promo=False, sem_f2p=True):
    """Mesmos filtros do HTML, para que a lista curta do volume.py bata com o
    que voce ve na tabela."""
    out = []
    for d in deals:
        if d["preco"] < preco_min:
            continue
        if preco_max is not None and d["preco"] > preco_max:
            continue
        if d["liquidez"] < liquidez_min:
            continue
        if disp_max is not None and d["disp"] > disp_max:
            continue
        if so_promo and not d["off"]:
            continue
        if sem_f2p and d["f2p"]:
            continue
        out.append(d)
    return out
