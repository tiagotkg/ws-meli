# coding: utf-8
"""Simple Selenium scraper for Mercado Livre search results."""
from __future__ import annotations

import json
from typing import Dict, List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


def _init_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def scrape_ml_search(url: str, limit: int = 10, pages: int = 1) -> List[Dict[str, str]]:
    """Return basic data for products listed on Mercado Livre search pages.

    Parameters
    ----------
    url:
        Initial search URL.
    limit:
        Maximum number of items to return across pages.
    pages:
        Number of result pages to traverse.
    """

    driver = _init_driver()
    results: List[Dict[str, str]] = []
    try:
        current_url = url
        visited = 0
        while visited < pages and len(results) < limit:
            driver.get(current_url)
            items = driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item")
            for item in items:
                if len(results) >= limit:
                    break
                try:
                    title = item.find_element(By.CSS_SELECTOR, "h2.ui-search-item__title").text.strip()
                    link = item.find_element(
                        By.CSS_SELECTOR, "a.ui-search-item__group__element"
                    ).get_attribute("href")
                    price = item.find_element(
                        By.CSS_SELECTOR, "span.andes-money-amount__fraction"
                    ).text.strip()
                except Exception:
                    continue
                results.append({"title": title, "link": link, "price": price})

            visited += 1
            if visited >= pages or len(results) >= limit:
                break

            try:
                next_btn = driver.find_element(
                    By.CSS_SELECTOR, "a.andes-pagination__link--next"
                )
                current_url = next_btn.get_attribute("href")
                if not current_url:
                    break
            except Exception:
                break
    finally:
        driver.quit()
    return results


if __name__ == "__main__":
    import sys

    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (
            "https://lista.mercadolivre.com.br/cartucho-667#D[A:cartucho%20667]"
            "&origin=UNKNOWN&as.comp_t=SUG&as.comp_v=cartucho&as.comp_id=SUG"
        )
    )
    data = scrape_ml_search(target, limit=5, pages=2)
    print(json.dumps(data, ensure_ascii=False, indent=2))
