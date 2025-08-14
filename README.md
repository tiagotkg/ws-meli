# Scrapers Mercado Livre

Scripts simples em Python usando Selenium para coletar dados do site do Mercado Livre.

## Busca

`scrape_ml_search.py` captura título, link e preço dos produtos exibidos em resultados de busca e pode percorrer múltiplas páginas.

> ⚠️ Requer que **Google Chrome** (ou Chromium) e um binário do **Chromedriver** compatível estejam instalados e acessíveis no `PATH`. Se necessário, indique os caminhos via variáveis de ambiente `GOOGLE_CHROME_BIN` e `CHROMEDRIVER`.

```bash
python scrape_ml_search.py "https://lista.mercadolivre.com.br/cartucho-667"
```

O script coleta até 5 itens em até 2 páginas por padrão. Ajuste os valores de `limit` e `pages` no próprio código conforme necessário.

## Produto

`scrape_ml_product.py` obtém informações detalhadas de uma página de produto.

```bash
python scrape_ml_product.py "https://www.mercadolivre.com.br/..."
```
