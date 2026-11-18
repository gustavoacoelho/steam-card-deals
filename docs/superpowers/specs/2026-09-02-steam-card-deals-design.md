# Steam Card Deals — Design

**Data:** 2026-09-02
**Status:** Aprovado

## Problema

A coluna *Discount* do [steam.tools/cards](https://steam.tools/cards/#) mostra quanto se recupera vendendo as cartas que dropam de um jogo. Esse número sozinho não diz nada — só vira decisão de compra quando cruzado com o preço atual do jogo na loja. O objetivo é achar jogos cujo valor em cartas cobre uma fração grande (ou toda) do preço pago, principalmente durante promoções.

## O que este projeto **não** é

Explicitando para evitar leitura errada dos resultados:

- **Não é reembolso.** O retorno das cartas é saldo da carteira Steam, não dinheiro de volta.
- **Não é automático na compra.** Cartas caem por tempo de jogo; tipicamente só metade do set dropa por conta.
- **Liquidez é modelada em três níveis**, adicionados depois da versão inicial: `À venda` (estoque listado), `Disp.` (dispersão de preços no set) e `Vendas 24h` (fluxo real, via `volume.py`). Ainda assim, para cartas de centavos o piso de R$ 0,03 do Mercado corrói o retorno.
- **Não recomenda compra.** É um filtro de candidatos.

## Fontes de dados

| Fonte | Endpoint | Conteúdo |
|---|---|---|
| steam.tools | `https://cdn.steam.tools/data/set_data.json` | 13.817 sets. Campos usados: `appid`, `game`, `discount` (USD), `f2p`, `normal.count`, `normal.price`, `foil.price` |
| steam.tools | `https://cdn.steam.tools/data/currency.json` | Taxas USD→X. Usado só o `BRL` |
| Steam Store | `store.steampowered.com/api/appdetails?appids=<até 200 csv>&cc=br&filters=price_overview` | `initial`, `final`, `discount_percent` em centavos de BRL |

**Verificado empiricamente:** o `appdetails` aceita 200 appids por requisição e devolve todos com preço (numa amostra de 200: 187 com preço, 11 sem `price_overview` — gratuitos/não lançados, 2 com `success:false` — delistados). São ~70 requisições para a base inteira.

### Sobre o campo `discount`

Usado **como está**, sem recálculo. A fórmula foi confirmada contra a base inteira (341/341 sets acima de US$ 5, exato ao centavo):

```
discount = ceil(count / 2) * avg * (1 / 1.15)
```

O `ceil` reflete o arredondamento para cima de meio set ímpar; o `1/1.15` é a taxa do Mercado Steam (5% plataforma + 10% desenvolvedor). **O valor já está líquido da taxa** — não há correção a aplicar em cima dele.

Um fator `AJUSTE_CONSERVADOR` (padrão `1.0`) no topo do `report.py` permite descontar esse valor globalmente para quem quiser margem de segurança.

## Arquitetura

Dois executáveis, um cache no meio. Separados porque a coleta é lenta e envolve rede, e a renderização é instantânea e offline — quem quiser mudar um piso de preço não deve pagar o custo da rede de novo.

```
collect.py ──escreve──> cache/prices.json ──lê──> report.py ──> deals.html
                        cache/set_data.json                     deals.csv
                        cache/currency.json
```

### `collect.py` — alimenta o cache

Responsabilidade única: deixar o cache fresco. Não calcula nada, não renderiza nada.

1. Baixa `set_data.json` e `currency.json` se as cópias locais tiverem mais de `TTL_SETS` (24 h).
2. Lê `cache/prices.json`: `{ appid: {final, initial, discount_percent, currency, fetched_at, status} }`.
3. Seleciona os appids com `fetched_at` mais velho que `TTL_PRICES` (6 h) ou ausentes.
4. Consulta em lotes de 200, gravando o cache **a cada lote** — uma interrupção no meio não perde o trabalho já feito.
5. Marca appids sem preço com `status` (`free`, `unavailable`) para não serem reconsultados a cada rodada com a mesma frequência.

Flags: `--force` (ignora TTL), `--limit N` (só os N primeiros, para teste).

### `report.py` — lê o cache e gera a saída

Responsabilidade única: transformar cache em tabela. Nunca acessa a rede.

Para cada jogo com preço e com `discount`:

```
cartas_brl   = discount_usd * taxa_brl * AJUSTE_CONSERVADOR
preco_brl    = final / 100
cobertura    = cartas_brl / preco_brl          # 1.0 = virtualmente de graça
custo_liq    = preco_brl - cartas_brl          # o que sai do bolso
```

Emite `deals.csv` (todas as linhas, ordenado por cobertura) e `deals.html`.

### `deals.html` — saída self-contained

Arquivo único, aberto localmente, sem CDN e sem rede. Todos os dados embutidos como JSON no próprio HTML; ordenação e filtros em JS puro sobre esse array.

Colunas: Jogo · Preço · Preço cheio · % off na loja · Cartas (R$) · **Cobertura %** · **Custo líquido** · Nº cartas · F2P · link para a loja.

Ordenação padrão por cobertura decrescente. Clicar em qualquer cabeçalho reordena. Filtros: busca por nome, preço máximo, **preço mínimo** (para afogar o shovelware de R$ 1,99 que sempre lidera a cobertura), só-em-promoção, esconder F2P.

## Tratamento de erros

- **Rede fora / CDN fora:** `collect.py` falha com mensagem clara e sai com código ≠ 0. O cache anterior fica intacto; `report.py` continua funcionando com dados velhos e o HTML mostra a idade do cache no cabeçalho.
- **Lote com falha:** retry com backoff (3 tentativas). Persistindo, o lote é pulado e registrado; os appids ficam sem `fetched_at` e entram na próxima rodada.
- **Cache corrompido:** JSON inválido é renomeado para `.bak` e a coleta recomeça do zero, com aviso.
- **`report.py` sem cache:** erro explícito mandando rodar o `collect.py` antes.
- **Jogo sem preço ou sem `discount`:** excluído da tabela, contabilizado no rodapé ("N jogos ignorados: sem preço").

## Testes

Um `test_report.py` cobrindo a lógica de cálculo, que é onde um erro passa despercebido:

- Cobertura e custo líquido com números conhecidos (`discount` 1,00 USD, taxa 5,154, preço R$ 10,00 → cobertura 51,54%, custo líquido R$ 4,85).
- `AJUSTE_CONSERVADOR` aplicado corretamente.
- Jogo grátis (`final: 0`) não gera divisão por zero.
- Entradas sem `discount` ou sem preço são descartadas, não viram zero.
- Parsing do cache: entrada com `status: unavailable` é ignorada sem quebrar.

A coleta em si não é testada contra a rede real; `collect.py` isola o parsing da resposta numa função pura testável com um payload fixo.

## Fora de escopo (YAGNI)

Histórico de preços, alertas, integração com perfil Steam (jogos já possuídos), preço de foils no cálculo principal, ITAD/comparação com outras lojas, outras moedas além de BRL.
