# Steam Card Deals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cruzar o valor das cartas de cada jogo Steam (campo `discount` do steam.tools) com o preço atual da loja em BRL, para achar jogos cujo custo líquido é próximo de zero.

**Architecture:** Dois CLIs separados por um cache em disco. `collect.py` só fala com a rede e escreve `cache/prices.json` de forma resumível; `report.py` só lê o cache e emite `deals.csv` + `deals.html`. Toda a aritmética e todo o parsing vivem em `cardcalc.py`, que é puro e testável sem rede.

**Tech Stack:** Python 3.14, apenas biblioteca padrão (`urllib.request`, `json`, `csv`, `html`, `argparse`, `unittest`). Sem dependências externas, sem CDN no HTML gerado.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `cardcalc.py` | Funções puras: parsing da resposta do appdetails, política de TTL, cálculo de cobertura/custo líquido. Zero I/O. |
| `collect.py` | CLI de coleta. Baixa set_data/currency, consulta preços em lotes, grava o cache incrementalmente. |
| `render.py` | Geração do HTML self-contained a partir de uma lista de deals. |
| `report.py` | CLI de relatório. Lê cache → `cardcalc` → `deals.csv` + `render.py`. |
| `test_cardcalc.py` | Testes unitários da lógica pura. |
| `cache/` | `set_data.json`, `currency.json`, `prices.json`. Fora do git. |

Ordem das tasks: `cardcalc` primeiro (com testes), porque `collect` e `report` dependem dele.

---

### Task 1: Cálculo de cobertura e custo líquido

**Files:**
- Create: `cardcalc.py`
- Test: `test_cardcalc.py`

- [ ] **Step 1: Write the failing test**

```python
# test_cardcalc.py
import unittest
from cardcalc import compute_deal

SET = {"appid": "221540", "game": "Defense Grid 2", "discount": "1.00",
       "f2p": False, "normal": {"count": 9}}
PRICE_OK = {"status": "ok", "final": 1000, "initial": 1000, "discount_percent": 0}


class TestComputeDeal(unittest.TestCase):
    def test_cobertura_e_custo_liquido(self):
        d = compute_deal(SET, PRICE_OK, brl_rate=5.154)
        self.assertAlmostEqual(d["cartas"], 5.154, places=4)
        self.assertAlmostEqual(d["preco"], 10.00, places=4)
        self.assertAlmostEqual(d["cobertura"], 0.5154, places=4)
        self.assertAlmostEqual(d["custo_liq"], 4.846, places=4)
        self.assertEqual(d["n_cartas"], 9)
        self.assertEqual(d["game"], "Defense Grid 2")

    def test_ajuste_conservador_reduz_valor_das_cartas(self):
        d = compute_deal(SET, PRICE_OK, brl_rate=5.154, adjust=0.5)
        self.assertAlmostEqual(d["cartas"], 2.577, places=4)
        self.assertAlmostEqual(d["cobertura"], 0.2577, places=4)

    def test_preco_zero_nao_divide_por_zero(self):
        free = dict(PRICE_OK, final=0)
        self.assertIsNone(compute_deal(SET, free, brl_rate=5.154))

    def test_status_nao_ok_e_descartado(self):
        self.assertIsNone(compute_deal(SET, {"status": "unavailable"}, brl_rate=5.154))
        self.assertIsNone(compute_deal(SET, {"status": "free"}, brl_rate=5.154))

    def test_set_sem_discount_e_descartado(self):
        self.assertIsNone(compute_deal({"appid": "1", "game": "X"}, PRICE_OK, brl_rate=5.154))
        self.assertIsNone(compute_deal(dict(SET, discount=None), PRICE_OK, brl_rate=5.154))

    def test_promocao_preserva_preco_cheio_e_percentual(self):
        promo = {"status": "ok", "final": 529, "initial": 2649, "discount_percent": 80}
        d = compute_deal(SET, promo, brl_rate=5.154)
        self.assertAlmostEqual(d["preco"], 5.29, places=4)
        self.assertAlmostEqual(d["preco_cheio"], 26.49, places=4)
        self.assertEqual(d["off"], 80)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cardcalc -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cardcalc'`

- [ ] **Step 3: Write minimal implementation**

```python
# cardcalc.py
"""Lógica pura do cruzamento cartas x preço. Sem rede, sem disco."""


def compute_deal(setinfo, price, brl_rate, adjust=1.0):
    """Cruza um set do steam.tools com uma entrada de preço do cache.

    Devolve None quando o par não é comparável (sem preço, jogo grátis,
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

    return {
        "appid": setinfo.get("appid"),
        "game": setinfo.get("game"),
        "preco": preco,
        "preco_cheio": initial / 100.0,
        "off": price.get("discount_percent", 0),
        "cartas": cartas,
        "cobertura": cartas / preco,
        "custo_liq": preco - cartas,
        "n_cartas": normal.get("count") or 0,
        "f2p": bool(setinfo.get("f2p")),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cardcalc -v`
Expected: PASS — 6 tests OK

- [ ] **Step 5: Commit**

```bash
git add cardcalc.py test_cardcalc.py
git commit -m "feat: calculo de cobertura e custo liquido"
```

---

### Task 2: Parsing da resposta do appdetails

**Files:**
- Modify: `cardcalc.py`
- Test: `test_cardcalc.py`

- [ ] **Step 1: Write the failing test**

Adicionar em `test_cardcalc.py`:

```python
from cardcalc import parse_price_response


class TestParsePriceResponse(unittest.TestCase):
    PAYLOAD = {
        "221540": {"success": True, "data": {"price_overview": {
            "currency": "BRL", "initial": 2898, "final": 2898, "discount_percent": 0}}},
        "1174180": {"success": True, "data": {"price_overview": {
            "currency": "BRL", "initial": 29990, "final": 7497, "discount_percent": 75}}},
        "570": {"success": True, "data": []},
        "999999": {"success": False},
    }

    def test_extrai_precos(self):
        out = parse_price_response(self.PAYLOAD, now=1000)
        self.assertEqual(out["221540"], {
            "status": "ok", "final": 2898, "initial": 2898,
            "discount_percent": 0, "currency": "BRL", "fetched_at": 1000})
        self.assertEqual(out["1174180"]["final"], 7497)
        self.assertEqual(out["1174180"]["discount_percent"], 75)

    def test_sem_price_overview_vira_free(self):
        out = parse_price_response(self.PAYLOAD, now=1000)
        self.assertEqual(out["570"], {"status": "free", "fetched_at": 1000})

    def test_success_false_vira_unavailable(self):
        out = parse_price_response(self.PAYLOAD, now=1000)
        self.assertEqual(out["999999"], {"status": "unavailable", "fetched_at": 1000})

    def test_entrada_nula_nao_quebra(self):
        out = parse_price_response({"1": None}, now=1000)
        self.assertEqual(out["1"]["status"], "unavailable")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cardcalc -v`
Expected: FAIL — `ImportError: cannot import name 'parse_price_response'`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `cardcalc.py`:

```python
def parse_price_response(payload, now):
    """Converte a resposta do appdetails em entradas de cache.

    Cada appid vira uma das três formas:
      ok          -> tem preço
      free        -> success, mas sem price_overview (gratuito/não lançado)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cardcalc -v`
Expected: PASS — 10 tests OK

- [ ] **Step 5: Commit**

```bash
git add cardcalc.py test_cardcalc.py
git commit -m "feat: parsing da resposta do appdetails"
```

---

### Task 3: Política de TTL do cache

**Files:**
- Modify: `cardcalc.py`
- Test: `test_cardcalc.py`

Preços válidos expiram rápido (promoções mudam); jogos grátis e delistados quase não mudam, então recebem TTL longo para não desperdiçar requisição em toda rodada.

- [ ] **Step 1: Write the failing test**

Adicionar em `test_cardcalc.py`:

```python
from cardcalc import needs_refresh

HOUR = 3600


class TestNeedsRefresh(unittest.TestCase):
    def test_sem_entrada_precisa_buscar(self):
        self.assertTrue(needs_refresh(None, now=100 * HOUR))

    def test_ok_recente_nao_precisa(self):
        e = {"status": "ok", "fetched_at": 100 * HOUR}
        self.assertFalse(needs_refresh(e, now=100 * HOUR + 5 * HOUR))

    def test_ok_vencido_precisa(self):
        e = {"status": "ok", "fetched_at": 100 * HOUR}
        self.assertTrue(needs_refresh(e, now=100 * HOUR + 7 * HOUR))

    def test_free_usa_ttl_longo(self):
        e = {"status": "free", "fetched_at": 100 * HOUR}
        self.assertFalse(needs_refresh(e, now=100 * HOUR + 100 * HOUR))
        self.assertTrue(needs_refresh(e, now=100 * HOUR + 200 * HOUR))

    def test_entrada_sem_fetched_at_precisa(self):
        self.assertTrue(needs_refresh({"status": "ok"}, now=100 * HOUR))

    def test_ttl_customizado(self):
        e = {"status": "ok", "fetched_at": 0}
        self.assertFalse(needs_refresh(e, now=10, ttl_ok=100))
        self.assertTrue(needs_refresh(e, now=200, ttl_ok=100))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_cardcalc -v`
Expected: FAIL — `ImportError: cannot import name 'needs_refresh'`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `cardcalc.py`, no topo do arquivo (após a docstring):

```python
TTL_OK = 6 * 3600        # preços mudam com promoções
TTL_DEAD = 7 * 24 * 3600 # grátis/delistado raramente muda
```

E a função:

```python
def needs_refresh(entry, now, ttl_ok=TTL_OK, ttl_dead=TTL_DEAD):
    """True quando o appid precisa ser consultado de novo."""
    if not entry:
        return True
    fetched = entry.get("fetched_at")
    if not fetched:
        return True
    ttl = ttl_ok if entry.get("status") == "ok" else ttl_dead
    return (now - fetched) >= ttl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_cardcalc -v`
Expected: PASS — 16 tests OK

- [ ] **Step 5: Commit**

```bash
git add cardcalc.py test_cardcalc.py
git commit -m "feat: politica de TTL do cache de precos"
```

---

### Task 4: Coletor

**Files:**
- Create: `collect.py`

Sem teste automatizado: é I/O de rede puro, e a parte com lógica já está coberta em `cardcalc`. Verificação é manual, rodando com `--limit`.

- [ ] **Step 1: Write the implementation**

```python
# collect.py
"""Alimenta cache/ com set_data, currency e preços da Steam. Só faz rede + disco."""
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
    """Lê um JSON do cache. Renomeia para .bak e devolve None se estiver corrompido."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        bak = path + ".bak"
        os.replace(path, bak)
        print(f"  aviso: {os.path.basename(path)} corrompido, movido para {bak}")
        return None


def save_cache(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def refresh_static(name, url, force):
    """Baixa set_data/currency se a cópia local estiver velha. Devolve o conteúdo."""
    path = os.path.join(CACHE, name)
    if not force and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < TTL_SETS:
            cached = load_cache(path)
            if cached is not None:
                print(f"  {name}: cache com {age / 3600:.1f}h, mantido")
                return cached
    print(f"  {name}: baixando...")
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
            print(f"    falha ({e}), tentativa {attempt}/{tries}, aguardando {wait}s")
            time.sleep(wait)
    return None


def main():
    ap = argparse.ArgumentParser(description="Coleta preços da Steam para o cache.")
    ap.add_argument("--force", action="store_true", help="ignora TTL, rebusca tudo")
    ap.add_argument("--limit", type=int, help="processa só os N primeiros appids")
    ap.add_argument("--cc", default="br", help="país da loja (padrão: br)")
    args = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    print("Dados estáticos:")
    try:
        set_data = refresh_static("set_data.json", SET_DATA_URL, args.force)
        refresh_static("currency.json", CURRENCY_URL, args.force)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"ERRO: não consegui baixar os dados do steam.tools: {e}", file=sys.stderr)
        return 1

    sets = set_data.get("sets", [])
    appids = [s["appid"] for s in sets if s.get("appid")]
    if args.limit:
        appids = appids[: args.limit]

    prices_path = os.path.join(CACHE, "prices.json")
    prices = load_cache(prices_path) or {}
    now = time.time()
    pending = [a for a in appids
               if args.force or needs_refresh(prices.get(a), now)]

    print(f"\n{len(appids)} jogos com cartas, {len(pending)} precisam de preço.")
    if not pending:
        print("Cache já está fresco. Nada a fazer.")
        return 0

    total = (len(pending) + BATCH - 1) // BATCH
    falhos = 0
    for i in range(0, len(pending), BATCH):
        lote = pending[i: i + BATCH]
        n = i // BATCH + 1
        print(f"  lote {n}/{total} ({len(lote)} appids)...", end=" ", flush=True)
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
    print(f"\nCache: {len(prices)} appids, {com_preco} com preço.")
    if falhos:
        print(f"{falhos} lote(s) falharam e entram na próxima rodada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify against a small slice**

Run: `python collect.py --limit 400`
Expected: baixa set_data e currency, faz 2 lotes, imprime `Cache: 400 appids, ~370 com preço.`

- [ ] **Step 3: Verify resumability**

Run: `python collect.py --limit 400` novamente
Expected: `Cache já está fresco. Nada a fazer.` (nenhuma requisição de preço)

- [ ] **Step 4: Commit**

```bash
git add collect.py
git commit -m "feat: coletor de precos com cache resumivel"
```

---

### Task 5: Renderização do HTML

**Files:**
- Create: `render.py`

`render.py` expõe uma função só: `render_html(deals, meta) -> str`. Todos os dados vão embutidos como JSON; ordenação e filtros são JS puro, sem CDN.

- [ ] **Step 1: Write the implementation**

```python
# render.py
"""Gera o deals.html self-contained a partir da lista de deals."""
import json

TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Steam Card Deals</title>
<style>
  :root {
    --bg: #12151c; --panel: #1a1f2b; --line: #2a3140;
    --fg: #e6e9ef; --dim: #98a2b8; --accent: #66c0f4;
    --good: #6ee7a8; --warn: #f5c451;
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; background: var(--bg); color: var(--fg);
         font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .meta { color: var(--dim); font-size: 12px; margin-bottom: 18px; }
  .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
              background: var(--panel); border: 1px solid var(--line);
              border-radius: 8px; padding: 14px; margin-bottom: 14px; }
  .controls label { font-size: 12px; color: var(--dim);
                    display: flex; gap: 6px; align-items: center; }
  input[type=text], input[type=number] {
    background: #0e1117; border: 1px solid var(--line); color: var(--fg);
    border-radius: 5px; padding: 6px 8px; font: inherit; }
  input[type=text] { width: 220px; }
  input[type=number] { width: 90px; }
  .count { margin-left: auto; color: var(--dim); font-size: 12px; }
  .wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; min-width: 900px; }
  th, td { padding: 8px 10px; text-align: right; white-space: nowrap;
           border-bottom: 1px solid var(--line); }
  th { background: var(--panel); cursor: pointer; user-select: none;
       position: sticky; top: 0; font-size: 12px; color: var(--dim); }
  th:hover { color: var(--fg); }
  th.sorted::after { content: " \\25BE"; color: var(--accent); }
  th.asc::after { content: " \\25B4"; color: var(--accent); }
  td.game, th.game { text-align: left; white-space: normal; min-width: 260px; }
  td.game a { color: var(--fg); text-decoration: none; }
  td.game a:hover { color: var(--accent); text-decoration: underline; }
  tbody tr:hover { background: #1e2431; }
  .cov { font-weight: 600; }
  .cov.full { color: var(--good); }
  .cov.half { color: var(--warn); }
  .off { color: var(--good); }
  .strike { color: var(--dim); text-decoration: line-through; font-size: 12px; }
  .note { margin-top: 16px; color: var(--dim); font-size: 12px; max-width: 780px; }
</style>
</head>
<body>
<h1>Steam Card Deals</h1>
<div class="meta">__META__</div>

<div class="controls">
  <label>Busca <input type="text" id="q" placeholder="nome do jogo"></label>
  <label>Preço min R$ <input type="number" id="pmin" value="5" min="0" step="1"></label>
  <label>Preço max R$ <input type="number" id="pmax" placeholder="sem limite" min="0" step="1"></label>
  <label><input type="checkbox" id="promo"> só em promoção</label>
  <label><input type="checkbox" id="nof2p" checked> esconder F2P</label>
  <span class="count" id="count"></span>
</div>

<div class="wrap">
<table>
  <thead><tr>
    <th class="game" data-k="game">Jogo</th>
    <th data-k="preco">Preço</th>
    <th data-k="preco_cheio">Cheio</th>
    <th data-k="off">% off</th>
    <th data-k="cartas">Cartas R$</th>
    <th data-k="cobertura">Cobertura</th>
    <th data-k="custo_liq">Custo líq.</th>
    <th data-k="n_cartas">Cartas</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
</div>

<p class="note">
  <b>Cobertura</b> = valor das cartas &divide; preço pago. 100% significa que as cartas,
  se vendidas ao preço de mercado atual, cobrem o custo do jogo — em <i>saldo da carteira
  Steam</i>, não em dinheiro. As cartas caem por tempo de jogo e tipicamente só metade do
  set dropa por conta. Cartas de centavos sofrem com o piso de R$&nbsp;0,03 do mercado.
</p>

<script>
const DATA = __DATA__;
const brl = n => "R$ " + n.toFixed(2).replace(".", ",");
let sortKey = "cobertura", sortAsc = false;

function filtered() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const pmin = parseFloat(document.getElementById("pmin").value);
  const pmax = parseFloat(document.getElementById("pmax").value);
  const promo = document.getElementById("promo").checked;
  const nof2p = document.getElementById("nof2p").checked;
  return DATA.filter(d => {
    if (q && !d.game.toLowerCase().includes(q)) return false;
    if (!isNaN(pmin) && d.preco < pmin) return false;
    if (!isNaN(pmax) && d.preco > pmax) return false;
    if (promo && !d.off) return false;
    if (nof2p && d.f2p) return false;
    return true;
  });
}

function draw() {
  const rows = filtered().sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    const c = typeof x === "string" ? x.localeCompare(y) : x - y;
    return sortAsc ? c : -c;
  });
  document.getElementById("count").textContent =
    rows.length + " de " + DATA.length + " jogos";
  const shown = rows.slice(0, 3000);
  document.getElementById("rows").innerHTML = shown.map(d => `
    <tr>
      <td class="game"><a href="https://store.steampowered.com/app/${d.appid}/"
        target="_blank" rel="noopener">${d.game}</a></td>
      <td>${brl(d.preco)}</td>
      <td class="strike">${d.off ? brl(d.preco_cheio) : ""}</td>
      <td class="off">${d.off ? "-" + d.off + "%" : ""}</td>
      <td>${brl(d.cartas)}</td>
      <td class="cov ${d.cobertura >= 1 ? "full" : d.cobertura >= 0.5 ? "half" : ""}">${(d.cobertura * 100).toFixed(0)}%</td>
      <td>${brl(d.custo_liq)}</td>
      <td>${d.n_cartas}</td>
    </tr>`).join("");
  document.querySelectorAll("th").forEach(th => {
    th.className = th.dataset.k === "game" ? "game" : "";
    if (th.dataset.k === sortKey) th.classList.add(sortAsc ? "asc" : "sorted");
  });
}

document.querySelectorAll("th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  if (k === sortKey) sortAsc = !sortAsc; else { sortKey = k; sortAsc = false; }
  draw();
});
["q", "pmin", "pmax", "promo", "nof2p"].forEach(
  id => document.getElementById(id).addEventListener("input", draw));
draw();
</script>
</body>
</html>
"""


def render_html(deals, meta):
    """deals: lista de dicts do compute_deal. meta: string de cabeçalho."""
    payload = json.dumps(deals, ensure_ascii=False, separators=(",", ":"))
    return TEMPLATE.replace("__DATA__", payload).replace("__META__", meta)
```

- [ ] **Step 2: Smoke test the renderer**

Run:
```bash
python -c "from render import render_html; h=render_html([{'appid':'1','game':'Teste','preco':10.0,'preco_cheio':20.0,'off':50,'cartas':5.0,'cobertura':0.5,'custo_liq':5.0,'n_cartas':9,'f2p':False}], 'meta de teste'); assert '__DATA__' not in h and '__META__' not in h and 'Teste' in h; print('ok', len(h))"
```
Expected: `ok <n>` sem AssertionError

- [ ] **Step 3: Commit**

```bash
git add render.py
git commit -m "feat: renderizacao do HTML self-contained"
```

---

### Task 6: Relatório

**Files:**
- Create: `report.py`

- [ ] **Step 1: Write the implementation**

```python
# report.py
"""Lê o cache e emite deals.csv + deals.html. Nunca acessa a rede."""
import argparse
import csv
import json
import os
import sys
import time

from cardcalc import compute_deal
from render import render_html

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")

# Multiplica o valor das cartas. 1.0 = confia no número do steam.tools.
# Baixe para 0.8 se quiser margem contra queda de preço e iliquidez.
AJUSTE_CONSERVADOR = 1.0

COLUNAS = ["appid", "game", "preco", "preco_cheio", "off",
           "cartas", "cobertura", "custo_liq", "n_cartas", "f2p"]


def read_cache(name):
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"ERRO: {path} não existe. Rode `python collect.py` primeiro.",
              file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f), os.path.getmtime(path)


def main():
    ap = argparse.ArgumentParser(description="Gera deals.csv e deals.html do cache.")
    ap.add_argument("--ajuste", type=float, default=AJUSTE_CONSERVADOR,
                    help="fator sobre o valor das cartas (padrão 1.0)")
    args = ap.parse_args()

    set_data, _ = read_cache("set_data.json")
    currency, _ = read_cache("currency.json")
    prices, prices_mtime = read_cache("prices.json")

    rate = currency.get("BRL")
    if not rate:
        print("ERRO: currency.json sem taxa BRL.", file=sys.stderr)
        return 1

    deals, sem_preco = [], 0
    for s in set_data.get("sets", []):
        d = compute_deal(s, prices.get(s.get("appid")), rate, args.ajuste)
        if d is None:
            sem_preco += 1
        else:
            deals.append(d)
    deals.sort(key=lambda d: d["cobertura"], reverse=True)

    csv_path = os.path.join(ROOT, "deals.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, delimiter=";")
        w.writeheader()
        for d in deals:
            row = dict(d)
            for k in ("preco", "preco_cheio", "cartas", "custo_liq"):
                row[k] = f"{row[k]:.2f}".replace(".", ",")
            row["cobertura"] = f"{d['cobertura'] * 100:.1f}".replace(".", ",")
            w.writerow(row)

    idade = (time.time() - prices_mtime) / 3600
    meta = (f"{len(deals)} jogos comparáveis &middot; {sem_preco} ignorados "
            f"(sem preço, grátis ou delistados) &middot; taxa USD&rarr;BRL {rate:.3f} "
            f"&middot; ajuste {args.ajuste:g}&times; &middot; "
            f"preços coletados há {idade:.1f}h")
    html_path = os.path.join(ROOT, "deals.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(deals, meta))

    print(f"{len(deals)} jogos comparáveis, {sem_preco} ignorados.")
    print(f"  {csv_path}")
    print(f"  {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the partial cache**

Run: `python report.py`
Expected: imprime a contagem e os dois caminhos; `deals.html` e `deals.csv` existem e não estão vazios.

- [ ] **Step 3: Commit**

```bash
git add report.py
git commit -m "feat: relatorio CSV + HTML"
```

---

### Task 7: Coleta completa e verificação final

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the full collection**

Run: `python collect.py`
Expected: ~70 lotes, terminando com `Cache: ~13800 appids, ~11000 com preço.`

- [ ] **Step 2: Generate the final report**

Run: `python report.py`
Expected: alguns milhares de jogos comparáveis.

- [ ] **Step 3: Sanity-check the top results**

Run:
```bash
python -c "import csv;r=list(csv.DictReader(open('deals.csv',encoding='utf-8-sig'),delimiter=';'));[print(x['game'],x['preco'],x['cobertura']+'%') for x in r[:10]]"
```
Expected: jogos com cobertura alta; confirmar manualmente 1–2 contra o steam.tools e a loja.

- [ ] **Step 4: Run the full test suite**

Run: `python -m unittest test_cardcalc -v`
Expected: 16 tests OK

- [ ] **Step 5: Write the README**

`README.md` com: o que é, as duas ressalvas (saldo de carteira, drop por tempo de jogo), como rodar (`collect.py` → `report.py`), o que cada arquivo faz, e o significado de `--ajuste`.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: README"
```

---

## Self-Review

**Spec coverage:** fontes de dados → Task 4; `discount` usado como está + `AJUSTE_CONSERVADOR` → Tasks 1 e 6; arquitetura em dois executáveis → Tasks 4 e 6; cálculo de cobertura e custo líquido → Task 1; HTML self-contained com as colunas e os cinco filtros → Task 5; tratamento de erros (rede fora, lote falho, cache corrompido, report sem cache, jogo sem preço) → Tasks 4 e 6; testes → Tasks 1–3. Sem lacunas.

**Placeholders:** nenhum. Todo passo com código traz o código completo.

**Type consistency:** `compute_deal` devolve as chaves `appid, game, preco, preco_cheio, off, cartas, cobertura, custo_liq, n_cartas, f2p` — as mesmas consumidas por `COLUNAS` em `report.py` e pelo template em `render.py`. `parse_price_response` emite `status/final/initial/discount_percent/currency/fetched_at`, lidos por `compute_deal` e `needs_refresh`.
