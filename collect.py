"""Alimenta cache/ com set_data, currency e precos da Steam. So faz rede + disco."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from cardcalc import needs_refresh, parse_price_response

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
SET_DATA_URL = "https://cdn.steam.tools/data/set_data.json"
CURRENCY_URL = "https://cdn.steam.tools/data/currency.json"
APPDETAILS = ("https://store.steampowered.com/api/appdetails"
              "?appids={ids}&cc={cc}&filters=price_overview")
BATCH = 200
TTL_SETS = 24 * 3600
UA = {"User-Agent": "steam-card-deals/1.0 (uso pessoal)"}


def fetch_json(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_cache(path):
    """Le um JSON do cache. Renomeia para .bak e devolve None se estiver corrompido."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        bak = path + ".bak"
        os.replace(path, bak)
        print("  aviso: %s corrompido, movido para %s" % (os.path.basename(path), bak))
        return None


def save_cache(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def refresh_static(name, url, force):
    """Baixa set_data/currency se a copia local estiver velha. Devolve o conteudo."""
    path = os.path.join(CACHE, name)
    if not force and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < TTL_SETS:
            cached = load_cache(path)
            if cached is not None:
                print("  %s: cache com %.1fh, mantido" % (name, age / 3600))
                return cached
    print("  %s: baixando..." % name)
    data = fetch_json(url)
    save_cache(path, data)
    return data


def fetch_batch(appids, cc, tries=3):
    """Consulta um lote. Devolve o payload cru, ou None se falhar de vez."""
    url = APPDETAILS.format(ids=",".join(appids), cc=cc)
    for attempt in range(1, tries + 1):
        try:
            return fetch_json(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            wait = 2 ** attempt
            print("    falha (%s), tentativa %d/%d, aguardando %ds"
                  % (e, attempt, tries, wait))
            time.sleep(wait)
    return None


def main():
    ap = argparse.ArgumentParser(description="Coleta precos da Steam para o cache.")
    ap.add_argument("--force", action="store_true", help="ignora TTL, rebusca tudo")
    ap.add_argument("--limit", type=int, help="processa so os N primeiros appids")
    ap.add_argument("--cc", default="br", help="pais da loja (padrao: br)")
    args = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    print("Dados estaticos:")
    try:
        set_data = refresh_static("set_data.json", SET_DATA_URL, args.force)
        refresh_static("currency.json", CURRENCY_URL, args.force)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print("ERRO: nao consegui baixar os dados do steam.tools: %s" % e,
              file=sys.stderr)
        return 1

    sets = set_data.get("sets", [])
    appids = [s["appid"] for s in sets if s.get("appid")]
    if args.limit:
        appids = appids[: args.limit]

    prices_path = os.path.join(CACHE, "prices.json")
    prices = load_cache(prices_path) or {}
    now = time.time()
    pending = [a for a in appids if args.force or needs_refresh(prices.get(a), now)]

    print("\n%d jogos com cartas, %d precisam de preco." % (len(appids), len(pending)))
    if not pending:
        print("Cache ja esta fresco. Nada a fazer.")
        return 0

    total = (len(pending) + BATCH - 1) // BATCH
    falhos = 0
    for i in range(0, len(pending), BATCH):
        lote = pending[i: i + BATCH]
        n = i // BATCH + 1
        print("  lote %d/%d (%d appids)..." % (n, total, len(lote)), end=" ", flush=True)
        payload = fetch_batch(lote, args.cc)
        if payload is None:
            falhos += 1
            print("PULADO")
            continue
        prices.update(parse_price_response(payload, time.time()))
        save_cache(prices_path, prices)
        print("ok")
        time.sleep(0.5)

    com_preco = sum(1 for v in prices.values() if v.get("status") == "ok")
    print("\nCache: %d appids, %d com preco." % (len(prices), com_preco))
    if falhos:
        print("%d lote(s) falharam e entram na proxima rodada." % falhos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
