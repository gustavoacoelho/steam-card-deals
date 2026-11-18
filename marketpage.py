"""Parsing das paginas HTML do Mercado Steam. Sem rede, sem disco.

Os endpoints JSON do Mercado (/priceoverview/, /search/render/) respondem 429 de
forma persistente. As paginas HTML nao -- e trazem dado melhor: a pagina de um
item carrega o historico completo de vendas, com data e quantidade por dia,
sem exigir login.

As duas paginas usadas sao apps React com o cache do React Query serializado
dentro de um `JSON.parse("...")`, com JSON aninhado como string em varios niveis.
Por isso a varredura reparseia strings que parecem JSON: omitir esse passo faz a
busca devolver zero resultados sem erro nenhum.
"""
import json
import re

DECODER = json.JSONDecoder()


def _varre(obj, visita, prof=0):
    """Percorre a estrutura chamando `visita` em cada dict, entrando em strings
    que sao JSON aninhado."""
    if prof > 10:
        return
    if isinstance(obj, str):
        t = obj.strip()
        if t[:1] in "{[":
            try:
                _varre(json.loads(t), visita, prof + 1)
            except (ValueError, json.JSONDecodeError):
                pass
        return
    if isinstance(obj, dict):
        visita(obj)
        for v in obj.values():
            _varre(v, visita, prof + 1)
    elif isinstance(obj, list):
        for v in obj:
            _varre(v, visita, prof + 1)


def _e_foil(hash_name, obj):
    """Foil aparece como "(Foil)" ou "(Foil Trading Card)" no nome, e o tipo em
    asset_description nem sempre esta presente -- o nome e a pista confiavel."""
    tipo = (obj.get("asset_description") or {}).get("type") or ""
    return "Foil" in tipo or "(Foil" in hash_name


def _percorre_pagina(html, visita):
    for m in re.finditer(r"JSON\.parse\(", html or ""):
        try:
            i = html.index('"', m.end())
            blob, _ = DECODER.raw_decode(html[i:])
            _varre(json.loads(blob), visita)
        except (ValueError, json.JSONDecodeError):
            continue


def parse_cartas(html):
    """Hash names das cartas NORMAIS de um jogo, na ordem da pagina.

    Foils sao excluidos: eles nao entram no calculo de cobertura (que usa so o
    set normal) e negociam num mercado completamente diferente.
    """
    achados, vistos = [], set()

    def visita(o):
        hn = o.get("strHash")
        if not isinstance(hn, str) or hn in vistos:
            return
        if _e_foil(hn, o):
            return
        vistos.add(hn)
        achados.append(hn)

    _percorre_pagina(html, visita)
    return achados


def _valor_monetario(txt):
    """Converte o preco formatado da Steam em float, ou None.

    A Steam formata conforme o Accept-Language do pedido: "$0.08" em en-US e
    "US$ 0,08" em pt-BR. Assumir que a virgula e separador de milhar
    transformava 0,08 em 8,00 -- erro de 100x que passou despercebido porque os
    testes exploratorios nao mandavam o header.

    Regra: o ultimo separador com 1 ou 2 digitos depois e o decimal; qualquer
    outro separador e de milhar.
    """
    limpo = re.sub(r"[^0-9.,]", "", txt)
    if not limpo or not any(c.isdigit() for c in limpo):
        return None
    ultimo = max(limpo.rfind("."), limpo.rfind(","))
    try:
        if ultimo == -1:
            return float(limpo)
        casas = len(limpo) - ultimo - 1
        if casas in (1, 2):
            inteiro = re.sub(r"[.,]", "", limpo[:ultimo]) or "0"
            return float(inteiro + "." + limpo[ultimo + 1:])
        return float(re.sub(r"[.,]", "", limpo))
    except ValueError:
        return None


def _e_dolar(txt):
    """So aceita USD: o valor e convertido para BRL depois, e um preco que ja
    viesse em BRL causaria dupla conversao silenciosa."""
    t = txt.replace(" ", " ").strip()
    return t.startswith("US$") or t.startswith("$")


def parse_precos(html):
    """Preco da listagem mais barata de cada carta normal, em USD.

    Vem como string formatada ("$0.08", "$1,234.50"); float() direto falha e
    some com o dado calado. E a mesma base que o steam.tools usa -- conferido
    num set onde os dois batem ao centavo.
    """
    precos = {}

    def visita(o):
        hn = o.get("strHash")
        if not isinstance(hn, str) or hn in precos:
            return
        if _e_foil(hn, o):
            return
        bruto = o.get("strMinSellSubtotal")
        if not isinstance(bruto, str) or not _e_dolar(bruto):
            return
        v = _valor_monetario(bruto)
        if v is not None:
            precos[hn] = v

    _percorre_pagina(html, visita)
    return precos


def parse_historico(html):
    """Pontos {time, price_median, purchases} da pagina de um item.

    Lista vazia tem dois significados possiveis, distinguidos pelo chamador via
    `pagina_valida`: item que existe e nunca vendeu, ou hash name inexistente.
    """
    encontrados = []

    def visita(o):
        chave = o.get("queryKey")
        if isinstance(chave, list) and "pricehistory" in chave:
            precos = ((o.get("state") or {}).get("data") or {}).get("prices")
            if precos is not None:
                encontrados.append(precos)

    _percorre_pagina(html, visita)
    for p in encontrados:
        if p:
            return p
    return []


def pagina_valida(html):
    """True quando o hash name existe. Nome invalido devolve uma pagina generica
    sem a query de pricehistory."""
    return "pricehistory" in (html or "")


def resumir(precos, agora):
    """Ultima venda e volume por janela, para UMA carta."""
    if not precos:
        return {"ultima_venda": None, "dias_parado": None,
                "v7": 0, "v30": 0, "v90": 0, "total": 0}
    dia = 86400
    ult = max(p["time"] for p in precos)

    def janela(d):
        return sum(p["purchases"] for p in precos if agora - p["time"] <= d * dia)

    return {"ultima_venda": ult, "dias_parado": (agora - ult) / dia,
            "v7": janela(7), "v30": janela(30), "v90": janela(90),
            "total": sum(p["purchases"] for p in precos)}


def dispersao(precos):
    """Desvio-padrao sobre a media dos precos ao vivo do set.

    Acima de ~1 uma carta sozinha domina o valor, e o "valor esperado" vira
    loteria: voce recebe metade do set sorteada, entao ou pega a carta cara ou
    fica com centavos. Calcular isso sobre os precos ao vivo (e nao sobre o
    subconjunto que o steam.tools precificou) e o que revela o caso.
    """
    vals = list(precos.values()) if isinstance(precos, dict) else list(precos or [])
    if len(vals) < 2:
        return 0.0
    media = sum(vals) / len(vals)
    if media <= 0:
        return 0.0
    var = sum((v - media) ** 2 for v in vals) / len(vals)
    return (var ** 0.5) / media


def _mediana(vals):
    vals = sorted(vals)
    if not vals:
        return None
    meio = len(vals) // 2
    if len(vals) % 2:
        return vals[meio]
    return (vals[meio - 1] + vals[meio]) / 2


def agregar(resumos):
    """Consolida as cartas amostradas de um jogo pela mediana.

    Mediana e nao media porque uma carta recem-vendida num set morto puxaria a
    media para baixo e faria o jogo parecer liquido.
    """
    vivos = [r for r in resumos if r.get("dias_parado") is not None]
    if not vivos:
        return {"dias_parado": None, "v30": 0, "v90": 0, "n_amostra": 0}
    return {
        "dias_parado": _mediana([r["dias_parado"] for r in vivos]),
        "v30": int(_mediana([r["v30"] for r in vivos])),
        "v90": int(_mediana([r["v90"] for r in vivos])),
        "n_amostra": len(vivos),
    }


def pick_sample(nomes, k):
    """Ate k nomes espalhados pelo set, incluindo sempre a primeira e a ultima
    carta -- amostrar so o comeco enviesaria para uma ponta da faixa de precos."""
    if not nomes or k <= 0:
        return []
    if len(nomes) <= k:
        return list(nomes)
    if k == 1:
        return [nomes[0]]
    passo = (len(nomes) - 1) / (k - 1)
    return [nomes[int(i * passo + 0.5)] for i in range(k)]
