# coding: utf-8
"""Selenium-based scraper for Mercado Livre product pages.

This module exposes `scrape_ml_product` which navigates to a product URL and
returns structured information as a dict. The scraper is designed to be
resilient to small DOM changes by trying multiple selectors and applying
explicit waits with fallbacks. It uses Chrome in headless mode and attempts to
mimic a regular browser session to avoid trivial anti-automation blocks.
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


class ProductNotAvailable(Exception):
    """Raised when a Mercado Livre product page is not available."""


def _jitter():
    time.sleep(random.uniform(0.2, 0.6))


def _init_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
    options.add_argument(f"--user-agent={ua}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=pt-BR")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Network.setUserAgentOverride",
        {
            "userAgent": ua,
            "acceptLanguage": "pt-BR,pt;q=0.9",
            "platform": "Win32",
        },
    )
    return driver


def _try_selectors(
    driver: webdriver.Chrome, selectors: Iterable[str], by: By, attr: Optional[str] = None
) -> Optional[str]:
    for sel in selectors:
        try:
            el = driver.find_element(by, sel)
            val = el.get_attribute(attr) if attr else el.text
            if val:
                print(f"[selector] {sel} -> {val[:60]!r}")
                return val
        except NoSuchElementException:
            continue
    return None


def _parse_price(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9,]", "", value)
    if not cleaned:
        return None
    return float(cleaned.replace(".", "").replace(",", "."))


def _scroll_into_view(driver: webdriver.Chrome, selectors: Iterable[str], by: By):
    for sel in selectors:
        try:
            el = driver.find_element(by, sel)
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
            _jitter()
            return
        except NoSuchElementException:
            continue


def _get_json_ld(driver: webdriver.Chrome) -> Dict[str, Any]:
    scripts = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
    for s in scripts:
        try:
            data = json.loads(s.get_attribute("innerText"))
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        except json.JSONDecodeError:
            continue
    return {}


def scrape_ml_product(url: str, timeout: int = 20) -> Dict[str, Any]:
    driver = _init_driver()
    wait = WebDriverWait(driver, timeout)

    try:
        driver.get(url)
        try:
            wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ui-pdp-title")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "span.price-tag-fraction")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "section.ui-pdp-gallery")),
                )
            )
        except TimeoutException as exc:
            raise ProductNotAvailable("Essential elements not found") from exc
        _jitter()

        json_ld = _get_json_ld(driver)

        title = _try_selectors(
            driver,
            [
                "h1.ui-pdp-title",
                "//h1[contains(@class,'ui-pdp-title')]",
                "meta[property='og:title']",
            ],
            By.CSS_SELECTOR,
        )
        if not title and json_ld.get("name"):
            title = json_ld["name"]

        price_text = _try_selectors(
            driver,
            ["span.price-tag-fraction", "meta[itemprop='price']"],
            By.CSS_SELECTOR,
            attr="content",
        )
        price = _parse_price(price_text)

        cents = _try_selectors(
            driver,
            ["span.price-tag-cents", "span.andes-money-amount__cents"],
            By.CSS_SELECTOR,
        )
        if cents and price is not None and cents.isdigit():
            price = float(f"{int(price)}.{int(cents):02d}")

        stock_msg = _try_selectors(
            driver,
            [
                "span.ui-pdp-stock-information__title",
                "//p[contains(@class,'ui-pdp-stock')]",
            ],
            By.CSS_SELECTOR,
        )
        in_stock = None
        if stock_msg:
            in_stock = not bool(re.search("(esgotado|último)", stock_msg, re.I))

        _scroll_into_view(driver, ["section.ui-pdp-variations"], By.CSS_SELECTOR)
        var_active = {}
        var_options: Dict[str, List[str]] = {}
        try:
            variations = driver.find_elements(By.CSS_SELECTOR, "section.ui-pdp-variations")
            for block in variations:
                name = block.find_element(By.CSS_SELECTOR, "span.ui-pdp-variations__subtitle").text.strip()
                opts = [
                    o.text.strip()
                    for o in block.find_elements(By.CSS_SELECTOR, "li.ui-pdp-variations__item")
                    if o.text.strip()
                ]
                var_options[name] = opts
                try:
                    selected = block.find_element(By.CSS_SELECTOR, "li.ui-pdp-variations__item--selected").text.strip()
                    var_active[name] = selected
                except NoSuchElementException:
                    pass
        except Exception:
            pass

        seller_name = _try_selectors(
            driver,
            ["a.ui-pdp-seller__link", "//a[contains(@href,'/perfil/')]"],
            By.CSS_SELECTOR,
        )
        seller_profile = _try_selectors(
            driver,
            ["a.ui-pdp-seller__link", "//a[contains(@href,'/perfil/')]"],
            By.CSS_SELECTOR,
            attr="href",
        )
        reputation = _try_selectors(
            driver,
            ["span.ui-pdp-seller__reputation-title"],
            By.CSS_SELECTOR,
        )

        rating_avg = _try_selectors(
            driver,
            ["span.ui-pdp-review__rating", "meta[itemprop='ratingValue']"],
            By.CSS_SELECTOR,
        )
        rating_count = _try_selectors(
            driver,
            ["span.ui-review-preview__quantity", "meta[itemprop='ratingCount']"],
            By.CSS_SELECTOR,
        )
        qna_count = _try_selectors(
            driver,
            ["section.ui-pdp-questions span", "//a[contains(.,'Perguntas')]/span"],
            By.CSS_SELECTOR,
        )

        _scroll_into_view(driver, ["div.ui-pdp-description__content"], By.CSS_SELECTOR)
        description = _try_selectors(
            driver,
            [
                "div.ui-pdp-description__content",
                "p.ui-pdp-description__content",
                "article[data-testid='description']",
            ],
            By.CSS_SELECTOR,
        )

        _scroll_into_view(driver, ["table.ui-pdp-specs__table"], By.CSS_SELECTOR)
        attributes: Dict[str, str] = {}
        try:
            tables = driver.find_elements(By.CSS_SELECTOR, "table.ui-pdp-specs__table")
            for table in tables:
                rows = table.find_elements(By.CSS_SELECTOR, "tr")
                for row in rows:
                    try:
                        k = row.find_element(By.CSS_SELECTOR, "th").text.strip()
                        v = row.find_element(By.CSS_SELECTOR, "td").text.strip()
                        if k:
                            attributes[k] = v
                    except NoSuchElementException:
                        continue
        except Exception:
            pass

        _scroll_into_view(driver, ["figure.ui-pdp-gallery__figure img"], By.CSS_SELECTOR)
        images = []
        try:
            imgs = driver.find_elements(By.CSS_SELECTOR, "figure.ui-pdp-gallery__figure img")
            for img in imgs:
                src = img.get_attribute("data-zoom") or img.get_attribute("data-src") or img.get_attribute("src")
                if src and src not in images:
                    images.append(src)
        except Exception:
            pass
        if not images and json_ld.get("image"):
            img_field = json_ld["image"]
            images = img_field if isinstance(img_field, list) else [img_field]

        breadcrumbs = []
        try:
            crumbs = driver.find_elements(By.CSS_SELECTOR, "nav.andes-breadcrumb ol li")
            for c in crumbs:
                txt = c.text.strip()
                if txt:
                    breadcrumbs.append(txt)
        except Exception:
            pass

        data = {
            "source_url": url,
            "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": {
                "title": title,
                "brand": attributes.get("Marca") or json_ld.get("brand", {}).get("name") if isinstance(json_ld.get("brand"), dict) else json_ld.get("brand"),
                "model": attributes.get("Modelo") or json_ld.get("model"),
                "ml_product_id": re.search(r"MLB\d+", url).group(0) if re.search(r"MLB\d+", url) else None,
                "listing_id": None,
                "breadcrumbs": breadcrumbs,
                "description": description,
                "attributes": attributes,
                "images": images,
                "variations": {"active": var_active, "options": var_options},
            },
            "pricing": {
                "price": price,
                "currency": "BRL",
                "original_price": None,
                "installments": {"count": None, "amount": None, "interest_free": None},
            },
            "availability": {"in_stock": in_stock, "stock_message": stock_msg},
            "seller": {
                "name": seller_name,
                "profile_url": seller_profile,
                "is_official_store": None,
                "reputation_badge": reputation,
                "location": None,
            },
            "shipping": {
                "is_full": None,
                "free_shipping": None,
                "shipping_message": None,
                "estimated_delivery": None,
            },
            "social_proof": {
                "rating_average": _parse_price(rating_avg),
                "rating_count": int(rating_count) if rating_count and rating_count.isdigit() else None,
                "qna_count": int(re.sub(r"\D", "", qna_count)) if qna_count else None,
            },
        }

        if not title and not price:
            raise ProductNotAvailable("Title and price unavailable")

        return data
    finally:
        driver.quit()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.mercadolivre.com.br/cartucho-tinta-tricolor-667-hp/p/MLB22546333"
    result = scrape_ml_product(target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
