"""Etapa 2: mede a liquidez real de uma lista curta, pelo historico do Mercado.

Estoque listado nao diz nada sobre giro. ClockwiZZZe tem 188 cartas a venda,
112% de cobertura e passa em todos os filtros baratos -- e vende uma carta por
mes. So o historico de vendas separa isso de um mercado vivo.

A selecao da lista curta se apoia em `disp` (dispersao de precos do set), nao em
`liquidez`: entre os primeiros jogos medidos, estoque listado correlacionou +0.18
com o giro real enquanto a dispersao correlacionou -0.56. Set com precos coerentes
e set que negocia; set com uma carta desalinhada e set onde nada vendeu para
corrigir o preco.

Mede 3 cartas espalhadas pelo set e consolida pela mediana. Uma carta so mente:
no ClockwiZZZe a carta Dwarf vendeu ha 26 dias enquanto a mediana do set e 338.
Foils ficam de fora -- negociam em outro mercado e nao entram na cobertura.

Nomes de carta nunca mudam, entao ficam num cache permanente: a pagina de busca
(5 MB) e custo unico por jogo; rodadas seguintes so pagam as paginas de item.
"""
import argparse
import sys
import unicodedata
import time
import urllib.error
import urllib.parse
import urllib.request

from cachedb import (aplicar_filtros, build_deals, carregar_possuidos,
                     read_cache, regra_alvo, write_cache)
from cardcalc import FEE_MERCADO
from marketpage import (agregar, dispersao, pagina_valida, parse_cartas,
                        parse_historico, parse_precos, pick_sample, resumir)

BUSCA = ("https://steamcommunity.com/market/search?category_item_class=item_class_2"
         "&category_Game=app_{app}&appid=753&sort=3&dir=1")
ITEM = "https://steamcommunity.com/market/listings/753/{hash}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9"}
TTL_VOL = 7 * 24 * 3600      # historico de vendas muda devagar


def saida(msg):
    """print que sobrevive a console legado.

    O console do Windows usa cp1252; nomes de jogo com caracteres fora dessa
    tabela (exclamacao fullwidth, kana) lancavam UnicodeEncodeError e derrubavam
    a rodada inteira no meio.
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        # NFKC converte pontuacao fullwidth no equivalente ASCII ("！" -> "!"),
        # para o nome exibido continuar batendo com o nome buscado.
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        msg = unicodedata.normalize("NFKC", msg)
        print(msg.encode(enc, "replace").decode(enc))


def baixar(url, timeout=45):
    """Devolve (html, erro). erro='429' sinaliza rate limit ao chamador."""
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        return r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return None, "429" if e.code == 429 else str(e.code)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return None, str(e)


def buscar_jogo(appid, nomes_cache):
    """Fase A: nomes e precos ATUAIS das cartas, numa requisicao so.

    A pagina de busca e baixada toda rodada porque os precos mudam -- e sao eles
    que revelam quando o valor publicado pelo steam.tools ficou obsoleto. Os
    nomes vao para cache mesmo assim, como rede de seguranca se a busca falhar.
    """
    html, erro = baixar(BUSCA.format(app=appid))
    if erro:
        if appid in nomes_cache:
            return nomes_cache[appid], {}, None
        return None, None, erro
    cartas = parse_cartas(html)
    if not cartas:
        return None, None, "sem cartas na busca"
    nomes_cache[appid] = cartas
    write_cache("cardnames.json", nomes_cache)
    return cartas, parse_precos(html), None


def valor_ao_vivo(precos, drops, taxa_brl):
    """Valor liquido dos drops em BRL pelos precos de agora.

    Mesma formula do steam.tools (drops x preco medio, menos a taxa), com dado
    fresco. Divergencia grande contra o publicado significa preco fantasma: uma
    listagem cara que o steam.tools registrou e que ja nao existe.
    """
    if not precos:
        return None
    media = sum(precos.values()) / len(precos)
    return drops * media * taxa_brl * FEE_MERCADO


def medir_jogo(cartas, k, delay):
    """Fase B: amostra k cartas e consolida o giro. Devolve (agregado, erro)."""
    resumos = []
    for i, hn in enumerate(pick_sample(cartas, k)):
        time.sleep(delay)
        html, erro = baixar(ITEM.format(hash=urllib.parse.quote(hn)))
        if erro:
            return None, erro
        if not pagina_valida(html):
            continue                      # hash name invalido: ignora a amostra
        resumos.append(resumir(parse_historico(html), time.time()))
    if not resumos:
        return None, "nenhuma carta valida"
    return agregar(resumos), None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=60, help="quantos jogos medir (padrao 60)")
    ap.add_argument("--cartas", type=int, default=3, help="cartas amostradas por jogo")
    ap.add_argument("--preco-min", type=float, default=0.0)
    ap.add_argument("--preco-max", type=float, default=None)
    # Estoque listado quase nao prevoe giro (correlacao +0.18 com vendas 30d).
    # O piso baixo aqui e restricao de capacidade, nao sinal de qualidade: um set
    # com 15 cartas listadas nao absorve seus drops por mais rapido que gire.
    ap.add_argument("--liquidez-min", type=int, default=40)
    ap.add_argument("--disp-max", type=float, default=1.0)
    ap.add_argument("--so-promo", action="store_true")
    ap.add_argument("--todos", action="store_true",
                    help="ignora a regra de alvo e mede tudo que passar nos filtros")
    ap.add_argument("--preco-teto", type=float, default=15.0,
                    help="acima disso, so entra com lucro alto (padrao 15)")
    ap.add_argument("--lucro-alto", type=float, default=5.0,
                    help="lucro que justifica um jogo acima do teto (padrao 5)")
    ap.add_argument("--delay", type=float, default=2.5, help="segundos entre requisicoes")
    ap.add_argument("--max-minutos", type=float, default=45.0)
    ap.add_argument("--force", action="store_true", help="ignora o TTL de 7 dias")
    ap.add_argument("--so-precos", action="store_true",
                    help="refaz so a fase A (precos e dispersao), 1 requisicao por jogo")
    args = ap.parse_args()

    deals, _, taxa_brl, _ = build_deals()
    alvo = aplicar_filtros(deals, preco_min=args.preco_min, preco_max=args.preco_max,
                           liquidez_min=args.liquidez_min, disp_max=args.disp_max,
                           so_promo=args.so_promo)
    if not args.todos:
        alvo = [d for d in alvo
                if regra_alvo(d, args.preco_teto, args.lucro_alto)]
    # Jogo que voce ja tem nao rende drop novo, e cada medicao custa ~4
    # requisicoes ao Mercado -- podar antes economiza rede.
    possuidos = carregar_possuidos()
    if possuidos:
        antes = len(alvo)
        alvo = [d for d in alvo if d["appid"] not in possuidos]
        if antes != len(alvo):
            saida("%d ja na sua biblioteca, removidos." % (antes - len(alvo)))
    alvo = alvo[: args.top]
    if not alvo:
        saida("Nenhum jogo passou nos filtros.")
        return 0

    vol, _ = read_cache("volume.json", obrigatorio=False)
    vol = vol or {}
    nomes, _ = read_cache("cardnames.json", obrigatorio=False)
    nomes = nomes or {}
    agora = time.time()
    pend = [d for d in alvo if args.force
            or (agora - (vol.get(d["appid"], {}).get("fetched_at") or 0)) >= TTL_VOL]

    saida("%d jogos na lista curta, %d precisam de medicao." % (len(alvo), len(pend)))
    if not pend:
        saida("Cache fresco. Rode `python report.py` para gerar a tabela.")
        return 0
    saida("%d cartas por jogo, %.1fs entre requisicoes, teto de %.0f min."
          % (args.cartas, args.delay, args.max_minutos))
    saida("Ctrl+C nao perde progresso.")
    saida("")

    inicio = time.time()
    backoff = args.delay
    feitos = bloqueios = falhos = descartados = 0
    for d in pend:
        if (time.time() - inicio) / 60 >= args.max_minutos:
            saida("")
            saida("Teto de tempo atingido. Rode de novo para continuar.")
            break

        # Fase A: uma requisicao traz nomes e precos atuais.
        cartas, precos, erro = buscar_jogo(d["appid"], nomes)
        agg = None
        if erro is None:
            vivo = valor_ao_vivo(precos, d["drops"], taxa_brl)
            cob_viva = (vivo / d["preco"]) if vivo is not None and d["preco"] else None
            disp_viva = dispersao(precos)
            if args.so_precos:
                # Mantem a liquidez ja medida; so atualiza preco e dispersao.
                reg = dict(vol.get(d["appid"]) or {})
                reg.update({"game": d["game"], "cartas_vivo": vivo,
                            "cobertura_viva": cob_viva, "disp_vivo": disp_viva,
                            "n_precos": len(precos or {}), "fetched_at": time.time()})
                vol[d["appid"]] = reg
                write_cache("volume.json", vol)
                feitos += 1
                saida("  %-36s R$%6.2f em cartas | disp ao vivo %.2f"
                      % (d["game"][:36], vivo or 0, disp_viva))
                time.sleep(backoff)
                continue
            if cob_viva is not None and cob_viva < 1.0 and not args.todos:
                # Valor colapsou contra o publicado: nao gasta a fase B nele.
                vol[d["appid"]] = {
                    "game": d["game"], "cartas_vivo": vivo, "cobertura_viva": cob_viva,
                    "n_precos": len(precos), "disp_vivo": disp_viva,
                    "dias_parado": None, "v30": None,
                    "v90": None, "n_amostra": 0, "pulou": True,
                    "fetched_at": time.time()}
                write_cache("volume.json", vol)
                descartados += 1
                saida("  %-36s valor caiu para %3.0f%% do publicado - pulado"
                      % (d["game"][:36], cob_viva * 100 / (d["cobertura"] or 1)))
                time.sleep(backoff)
                continue
            agg, erro = medir_jogo(cartas, args.cartas, backoff)

        if erro == "429":
            bloqueios += 1
            backoff = min(backoff * 2, 120)
            saida("  [429] rate limit; proxima espera %.0fs" % backoff)
            time.sleep(backoff)
            continue
        if erro:
            falhos += 1
            saida("  [%-18s] %s" % (erro[:18], d["game"][:36]))
            time.sleep(backoff)
            continue

        backoff = args.delay
        agg["game"] = d["game"]
        agg["cartas_vivo"] = vivo
        agg["cobertura_viva"] = cob_viva
        agg["n_precos"] = len(precos or {})
        agg["disp_vivo"] = disp_viva
        agg["pulou"] = False
        agg["fetched_at"] = time.time()
        vol[d["appid"]] = agg
        write_cache("volume.json", vol)
        feitos += 1
        saida("  %-36s parado %5s d | 30d %4d | amostra %d"
              % (d["game"][:36],
                 "?" if agg["dias_parado"] is None else "%.0f" % agg["dias_parado"],
                 agg["v30"], agg["n_amostra"]))
        time.sleep(backoff)

    saida("")
    saida("%d medidos, %d descartados por valor obsoleto, %d falhas, %d bloqueios."
          % (feitos, descartados, falhos, bloqueios))
    saida("Cache: %d jogos." % len(vol))
    if bloqueios:
        saida("Muitos 429? Aumente --delay ou reduza --top.")
    saida("Rode `python report.py` para as colunas aparecerem na tabela.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
