"""Gera o deals.html self-contained a partir da lista de deals."""
import json

BACKSLASH = chr(92)  # evita ambiguidade de escaping na fonte

TEMPLATE = r"""<!doctype html>
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
  th.sorted::after { content: " \25BE"; color: var(--accent); }
  th.asc::after { content: " \25B4"; color: var(--accent); }
  td.game, th.game { text-align: left; white-space: normal; min-width: 260px; }
  td.game a { color: var(--fg); text-decoration: none; }
  td.game a:hover { color: var(--accent); text-decoration: underline; }
  tbody tr:hover { background: #1e2431; }
  .cov { font-weight: 600; }
  .cov.full { color: var(--good); }
  .cov.half { color: var(--warn); }
  .off { color: var(--good); }
  .thin { color: #f0806a; }
  .unk { color: #4a5468; }
  .ok { color: var(--good); }
  .part { color: var(--warn); cursor: help; }
  .strike { color: var(--dim); text-decoration: line-through; font-size: 12px; }
  .note { margin-top: 16px; color: var(--dim); font-size: 12px; max-width: 780px; }
  .note b { color: var(--fg); }
</style>
</head>
<body>
<h1>Steam Card Deals</h1>
<div class="meta">__META__</div>

<div class="controls">
  <label>Busca <input type="text" id="q" placeholder="nome do jogo"></label>
  <label>Pre&ccedil;o min R$ <input type="number" id="pmin" value="5" min="0" step="1"></label>
  <label>Pre&ccedil;o max R$ <input type="number" id="pmax" placeholder="sem limite" min="0" step="1"></label>
  <label>Liquidez min <input type="number" id="lmin" value="40" min="0" step="10"></label>
  <label>Disp. m&aacute;x <input type="number" id="dmax" value="1" min="0" step="0.1"></label>
  <label><input type="checkbox" id="promo"> s&oacute; em promo&ccedil;&atilde;o</label>
  <label><input type="checkbox" id="nof2p" checked> esconder F2P</label>
  <span class="count" id="count"></span>
</div>

<div class="wrap">
<table>
  <thead><tr>
    <th class="game" data-k="game">Jogo</th>
    <th data-k="preco">Pre&ccedil;o</th>
    <th data-k="preco_cheio">Cheio</th>
    <th data-k="off">% off</th>
    <th data-k="cartas">Cartas R$</th>
    <th data-k="cobertura">Cobertura</th>
    <th data-k="stale">Corre&ccedil;&atilde;o</th>
    <th data-k="custo_liq">Custo l&iacute;q.</th>
    <th data-k="drops">Drops</th>
    <th data-k="liquidez">&Agrave; venda</th>
    <th data-k="disp">Disp.</th>
    <th data-k="parado">Parado</th>
    <th data-k="v30">Vendas 30d</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
</div>

<p class="note">
  <b>Cobertura</b> = valor das cartas &divide; pre&ccedil;o pago. O valor j&aacute; est&aacute;
  <b>l&iacute;quido da taxa de 15% do Mercado</b>, ent&atilde;o 100% significa que os drops,
  vendidos ao pre&ccedil;o atual, cobrem mesmo o custo do jogo &mdash; em <i>saldo da carteira
  Steam</i>, n&atilde;o em dinheiro.
  <br><br><b>Drops</b> = quantas cartas voc&ecirc; realmente recebe jogando, sobre o tamanho
  do set. A Steam solta metade do set arredondada para cima, e esse teto <i>j&aacute;
  est&aacute;</i> embutido na coluna Cartas R$. Um <b>*</b> amarelo indica que o Mercado n&atilde;o
  precifica cartas suficientes e a conta usou <i>menos</i> drops do que voc&ecirc; recebe &mdash;
  cobertura subestimada, nunca inflada. Passe o mouse para ver quantos.
  <br><br>As tr&ecirc;s colunas seguintes medem liquidez, em ordem crescente de confiabilidade:
  <br><br><b>&Agrave; venda</b> = cartas listadas no Mercado inteiro. &Eacute; <i>estoque</i>, e
  estoque quase n&atilde;o prev&ecirc; giro: entre os jogos medidos, a correla&ccedil;&atilde;o
  com as vendas de 30 dias foi de apenas <b>+0,18</b> &mdash; h&aacute; sets com 215 cartas
  listadas e zero venda no m&ecirc;s. Serve como piso de <i>capacidade</i>: com 15 cartas
  no mercado inteiro voc&ecirc; n&atilde;o escoa 5 drops, por mais r&aacute;pido que gire.
  <br><br><b>Disp.</b> = desvio-padr&atilde;o dos pre&ccedil;os do set dividido pela m&eacute;dia.
  Perto de 0,2 o set tem pre&ccedil;os coerentes; acima de 1,0 (vermelho) uma carta sozinha infla
  a m&eacute;dia e o valor total &eacute; ilus&oacute;rio. Surpreendentemente &eacute; o melhor
  preditor barato de liquidez que existe aqui (correla&ccedil;&atilde;o <b>&minus;0,56</b> com
  vendas de 30 dias): set com pre&ccedil;os coerentes &eacute; set que negocia.
  <br><br><b>Parado</b> e <b>Vendas 30d</b> = h&aacute; quantos dias a carta t&iacute;pica do set
  n&atilde;o vende, e quantas unidades sa&iacute;ram no m&ecirc;s. Vem do hist&oacute;rico real do
  Mercado, sobre 3 cartas espalhadas pelo set, consolidado pela mediana &mdash; uma carta sozinha
  mente. <b>Este &eacute; o sinal que importa</b>: as outras duas contam estoque, esta conta giro.
  ClockwiZZZe tem 188 cartas listadas, 112% de cobertura e passa em todos os filtros baratos
  &mdash; e vende uma carta por m&ecirc;s. S&oacute; aparece nos jogos medidos com
  <code>volume.py</code>; <b>&mdash;</b> &eacute; n&atilde;o medido, e essas linhas v&atilde;o
  para o fim ao ordenar por elas.
</p>

<script>
const DATA = __DATA__;
const brl = n => "R$ " + n.toFixed(2).replace(".", ",");
const esc = s => String(s).replace(/[&<>"]/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
let sortKey = "cobertura", sortAsc = false;

function filtered() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const pmin = parseFloat(document.getElementById("pmin").value);
  const pmax = parseFloat(document.getElementById("pmax").value);
  const lmin = parseFloat(document.getElementById("lmin").value);
  const dmax = parseFloat(document.getElementById("dmax").value);
  const promo = document.getElementById("promo").checked;
  const nof2p = document.getElementById("nof2p").checked;
  return DATA.filter(d => {
    if (q && !d.game.toLowerCase().includes(q)) return false;
    if (!isNaN(pmin) && d.preco < pmin) return false;
    if (!isNaN(pmax) && d.preco > pmax) return false;
    if (!isNaN(lmin) && d.liquidez < lmin) return false;
    if (!isNaN(dmax) && d.disp > dmax) return false;
    if (promo && !d.off) return false;
    if (nof2p && d.f2p) return false;
    return true;
  });
}

function draw() {
  const rows = filtered().sort((a, b) => {
    let x = a[sortKey], y = b[sortKey];
    if (x === null || y === null) {          // nao medido fica no fim sempre
      if (x === y) return 0;
      return x === null ? 1 : -1;
    }
    const c = typeof x === "string" ? x.localeCompare(y) : x - y;
    return sortAsc ? c : -c;
  });
  document.getElementById("count").textContent =
    rows.length + " de " + DATA.length + " jogos";
  const shown = rows.slice(0, 3000);
  document.getElementById("rows").innerHTML = shown.map(d => `
    <tr>
      <td class="game"><a href="https://store.steampowered.com/app/${encodeURIComponent(d.appid)}/"
        target="_blank" rel="noopener">${esc(d.game)}</a></td>
      <td>${brl(d.preco)}</td>
      <td class="strike">${d.off ? brl(d.preco_cheio) : ""}</td>
      <td class="off">${d.off ? "-" + d.off + "%" : ""}</td>
      <td>${brl(d.cartas)}</td>
      <td class="cov ${d.cobertura >= 1 ? "full" : d.cobertura >= 0.5 ? "half" : ""}" title="${d.verificado ? 'preco verificado ao vivo' : 'preco do steam.tools, nao verificado'}">${(d.cobertura * 100).toFixed(0)}%${d.verificado ? '&#10003;' : ''}</td>
      <td class="${d.stale === null ? 'unk' : d.stale >= 2 ? 'thin' : d.stale >= 1.3 ? 'part' : 'ok'}" title="${d.stale === null ? '' : 'o steam.tools publicava ' + d.stale.toFixed(1) + 'x este valor'}">${d.stale === null ? '&mdash;' : d.stale.toFixed(1) + '×'}</td>
      <td>${brl(d.custo_liq)}</td>
      <td class="${d.incompleto ? 'part' : ''}" title="${d.incompleto ? 'o valor contou so ' + d.drops_contados + ' drops: o Mercado precifica ' + d.n_cartas + ' das ' + d.n_real + ' cartas' : ''}">${d.drops}/${d.n_real}${d.incompleto ? '*' : ''}</td>
      <td class="${d.liquidez < 150 ? 'thin' : ''}">${d.liquidez}</td>
      <td class="${d.disp > 1 ? 'thin' : ''}">${d.disp.toFixed(2)}</td>
      <td class="${d.parado === null ? 'unk' : d.parado >= 60 ? 'thin' : d.parado >= 14 ? 'part' : 'ok'}">${d.parado === null ? '&mdash;' : Math.round(d.parado) + 'd'}</td>
      <td class="${d.v30 === null ? 'unk' : d.v30 === 0 ? 'thin' : d.v30 >= 20 ? 'ok' : 'part'}">${d.v30 === null ? '&mdash;' : d.v30}</td>
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
["q", "pmin", "pmax", "lmin", "dmax", "promo", "nof2p"].forEach(
  id => document.getElementById(id).addEventListener("input", draw));
draw();
</script>
</body>
</html>
"""


def render_html(deals, meta):
    """deals: lista de dicts do compute_deal. meta: string de cabecalho (HTML)."""
    payload = json.dumps(deals, ensure_ascii=False, separators=(",", ":"))
    # Neutraliza "</script>" vindo de um nome de jogo: o parser HTML fecha o
    # bloco no primeiro "</script>" literal, mesmo dentro de uma string JS.
    payload = payload.replace("<", BACKSLASH + "u003c")
    return TEMPLATE.replace("__META__", meta).replace("__DATA__", payload)
