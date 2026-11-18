"""Logica pura do cruzamento cartas x preco. Sem rede, sem disco."""
import math

# Taxa do Mercado Steam: 5% plataforma + 10% desenvolvedor. Ja embutida no
# campo `discount` do steam.tools (conferido em 341/341 sets acima de US$5).
FEE_MERCADO = 1 / 1.15

TTL_OK = 6 * 3600         # precos mudam com promocoes
TTL_DEAD = 7 * 24 * 3600  # gratis/delistado raramente muda


def _dispersao(normal):
    """std/avg das cartas do set: o quanto os precos divergem entre si.

    Valores altos indicam mercado quebrado -- uma carta cara sozinha inflando a
    media, em vez de um set com precos coerentes. 0.0 quando nao da para saber.
    """
    try:
        avg = float(normal.get("avg") or 0)
        std = float(normal.get("std") or 0)
    except (TypeError, ValueError):
        return 0.0
    return std / avg if avg > 0 else 0.0


def compute_deal(setinfo, price, brl_rate, adjust=1.0):
    """Cruza um set do steam.tools com uma entrada de preco do cache.

    Devolve None quando o par nao e comparavel (sem preco, jogo gratis,
    delistado, ou set sem valor de cartas informado).
    """
    if not price or price.get("status") != "ok":
        return None

    final = price.get("final")
    if not final or final <= 0:
        return None

    raw = setinfo.get("discount")
    if raw in (None, ""):
        return None
    try:
        discount_usd = float(raw)
    except (TypeError, ValueError):
        return None

    cartas = discount_usd * brl_rate * adjust
    preco = final / 100.0
    initial = price.get("initial") or final
    normal = setinfo.get("normal") or {}

    # `count` sao as cartas que o steam.tools achou precificadas no mercado;
    # `true_count` e o tamanho real do set. Quando o mercado nao tem todas, o
    # discount conta menos drops do que voce de fato recebe -- valor subestimado.
    n_mercado = int(normal.get("count") or 0)
    try:
        n_real = int(setinfo.get("true_count") or n_mercado)
    except (TypeError, ValueError):
        n_real = n_mercado
    n_real = max(n_real, n_mercado)
    drops_reais = math.ceil(n_real / 2) if n_real else 0
    drops_contados = math.ceil(n_mercado / 2) if n_mercado else 0

    return {
        "appid": setinfo.get("appid"),
        "game": setinfo.get("game"),
        "preco": preco,
        "preco_cheio": initial / 100.0,
        "off": price.get("discount_percent", 0),
        "cartas": cartas,
        "cobertura": cartas / preco,
        "custo_liq": preco - cartas,
        "n_cartas": n_mercado,
        "n_real": n_real,
        "drops": drops_reais,
        "drops_contados": drops_contados,
        "incompleto": drops_contados < drops_reais,
        "liquidez": normal.get("quantity") or 0,
        "disp": _dispersao(normal),
        "f2p": bool(setinfo.get("f2p")),
    }


def parse_price_response(payload, now):
    """Converte a resposta do appdetails em entradas de cache.

    Cada appid vira uma das tres formas:
      ok          -> tem preco
      free        -> success, mas sem price_overview (gratuito/nao lancado)
      unavailable -> success:false (delistado/regional)
    """
    out = {}
    for appid, entry in (payload or {}).items():
        if not isinstance(entry, dict) or not entry.get("success"):
            out[appid] = {"status": "unavailable", "fetched_at": now}
            continue

        data = entry.get("data")
        po = data.get("price_overview") if isinstance(data, dict) else None
        if not po:
            out[appid] = {"status": "free", "fetched_at": now}
            continue

        out[appid] = {
            "status": "ok",
            "final": po.get("final"),
            "initial": po.get("initial"),
            "discount_percent": po.get("discount_percent", 0),
            "currency": po.get("currency"),
            "fetched_at": now,
        }
    return out


def needs_refresh(entry, now, ttl_ok=TTL_OK, ttl_dead=TTL_DEAD):
    """True quando o appid precisa ser consultado de novo."""
    if not entry:
        return True
    fetched = entry.get("fetched_at")
    if fetched is None:
        return True
    ttl = ttl_ok if entry.get("status") == "ok" else ttl_dead
    return (now - fetched) >= ttl
