"""Baixa a biblioteca Steam do usuario para podar a lista de candidatos.

Jogo que voce ja tem nao precisa ser comprado nem medido -- e cada candidato
medido custa ~4 requisicoes ao Mercado, entao podar antes economiza rede.

A pagina /games/ do perfil exige login mesmo com o perfil publico ("detalhes do
jogo" e uma configuracao separada da privacidade do perfil). O endpoint que o
steam.tools usa consulta a Web API com chave propria e devolve a lista sem isso.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

from cachedb import read_cache, write_cache

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
PERFIL_XML = "https://steamcommunity.com/id/{vanity}/?xml=1"
USERINFO = "https://{srv}.appspot.com/UserInfo?id={sid}"


def extrair_steamid(texto):
    """steamID64 a partir de um id cru ou de uma URL /profiles/. None para URL
    de vanity, que precisa de uma consulta para resolver."""
    t = (texto or "").strip().rstrip("/")
    m = re.search(r"/profiles/(\d{17})", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{17}", t):
        return t
    return None


def parse_biblioteca(payload):
    """Conjunto de appids possuidos, ou None quando a lista nao esta disponivel.

    `games: null` significa lista privada -- devolver conjunto vazio faria a
    ferramenta concluir que o usuario nao tem jogo nenhum e nao podar nada.
    """
    if not payload or not payload.get("success"):
        return None
    jogos = payload.get("games")
    if jogos is None:
        return None
    return {str(g) for g in jogos}


def mesclar(existentes, novos):
    """Uniao dos appids. Nunca remove: a fonte remota serve cache e demora a ver
    compras recentes, entao substituir apagaria o que ja sabemos."""
    return {str(a) for a in (existentes or set())} | {str(a) for a in (novos or set())}


def baixar_json(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def resolver_vanity(perfil):
    """Converte .../id/<vanity>/ em steamID64 pelo XML publico do perfil."""
    m = re.search(r"/id/([^/?#]+)", perfil.strip())
    vanity = m.group(1) if m else perfil.strip()
    req = urllib.request.Request(PERFIL_XML.format(vanity=vanity), headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r"<steamID64>(\d+)</steamID64>", html)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("perfil", nargs="?", help="URL do perfil ou steamID64")
    ap.add_argument("--adicionar", metavar="APPIDS",
                    help="appids separados por virgula, para compras que a fonte"
                         " remota ainda nao enxerga")
    ap.add_argument("--substituir", action="store_true",
                    help="descarta o cache local em vez de mesclar")
    args = ap.parse_args()

    atuais, _ = read_cache("owned.json", obrigatorio=False)
    atuais = {str(a) for a in (atuais or [])}

    if args.adicionar:
        extras = {a.strip() for a in args.adicionar.split(",") if a.strip()}
        combinado = mesclar(atuais, extras)
        write_cache("owned.json", sorted(combinado))
        print("%d appids adicionados manualmente | biblioteca: %d jogos"
              % (len(combinado) - len(atuais), len(combinado)))
        if not args.perfil:
            return 0

    if not args.perfil:
        ap.error("informe o perfil ou use --adicionar")

    sid = extrair_steamid(args.perfil)
    if not sid:
        try:
            sid = resolver_vanity(args.perfil)
        except (urllib.error.URLError, TimeoutError) as e:
            print("ERRO ao resolver o perfil: %s" % e, file=sys.stderr)
            return 1
    if not sid:
        print("ERRO: nao consegui o steamID64 de %r." % args.perfil, file=sys.stderr)
        return 1

    srv = ["stc-price", "stc-price2"][ord(sid[-1]) % 2]
    try:
        payload = baixar_json(USERINFO.format(srv=srv, sid=sid))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print("ERRO ao buscar a biblioteca: %s" % e, file=sys.stderr)
        return 1

    possuidos = parse_biblioteca(payload)
    if possuidos is None:
        motivo = (payload or {}).get("reason") or "lista de jogos privada"
        print("ERRO: %s. Em Privacidade, deixe 'Detalhes do jogo' como publico."
              % motivo, file=sys.stderr)
        return 1

    antes = len(atuais)
    final = possuidos if args.substituir else mesclar(atuais, possuidos)
    write_cache("owned.json", sorted(final))
    print("steamID64 %s | %d jogos na fonte remota | biblioteca local: %d"
          % (sid, len(possuidos), len(final)))
    so_local = atuais - possuidos
    if so_local and not args.substituir:
        print("%d appid(s) so no cache local (a fonte remota ainda nao viu): %s"
              % (len(so_local), ", ".join(sorted(so_local)[:10])))
    print("gravado em cache/owned.json -- volume.py e cesta.py ja vao podar por ele.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
