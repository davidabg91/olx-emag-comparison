import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import time
from bs4 import BeautifulSoup
import logging
import random
import configparser
import os
from fuzzywuzzy import fuzz # За fuzzywuzzy
import schedule
import re
import google.generativeai as genai # Добавено за Google AI
from models import db, Offer
from datetime import datetime
from selenium.webdriver.chrome.options import Options
import sys
import json
from urllib.parse import quote_plus
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue
import signal
import atexit

# --- НАСТРОЙКИ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

config = configparser.ConfigParser()
config_file_path = 'config.ini'

if not os.path.exists(config_file_path):
    logging.warning(f"Файлът '{config_file_path}' не е намерен. Създаване на примерен файл.")
    config['TELEGRAM'] = {
        'bot_token': 'YOUR_TELEGRAM_BOT_TOKEN', 
        'chat_id': 'YOUR_TELEGRAM_CHAT_ID'    
    }
    config['SETTINGS'] = {
        'min_emag_price': '50',
        'discount_threshold': '0.4', 
        'title_similarity_threshold': '60', 
        'max_missing_words_threshold': '3', 
        'min_words_for_emag_search': '3', 
        'page_load_timeout': '30', 
        'element_wait_timeout': '20', 
        'short_element_wait': '5' 
    }
    config['GOOGLE_AI'] = { 
        'API_KEY': 'YOUR_GOOGLE_AI_API_KEY_HERE'
    }
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    logging.info(f"Примерен файл '{config_file_path}' е създаден. Моля, попълнете вашите данни за Telegram и Google AI API ключ.")
    # exit() 

config.read(config_file_path)

# Telegram
TELEGRAM_BOT_TOKEN = config['TELEGRAM'].get('bot_token')
TELEGRAM_CHAT_ID = config['TELEGRAM'].get('chat_id')

# Настройки
MIN_EMAG_PRICE = int(config['SETTINGS'].get('min_emag_price', 50))
DISCOUNT_THRESHOLD = float(config['SETTINGS'].get('discount_threshold', 0.4))
TITLE_SIMILARITY_THRESHOLD = int(config['SETTINGS'].get('title_similarity_threshold', 60))
MAX_MISSING_WORDS_THRESHOLD = int(config['SETTINGS'].get('max_missing_words_threshold', 3))
MIN_WORDS_FOR_EMAG_SEARCH = int(config['SETTINGS'].get('min_words_for_emag_search', 3))
PAGE_LOAD_TIMEOUT = int(config['SETTINGS'].get('page_load_timeout', 30))
ELEMENT_WAIT_TIMEOUT = int(config['SETTINGS'].get('element_wait_timeout', 20))
SHORT_ELEMENT_WAIT = int(config['SETTINGS'].get('short_element_wait', 5))

# Google AI
GOOGLE_AI_API_KEY = config['GOOGLE_AI'].get('API_KEY')

if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN' or \
   not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == 'YOUR_TELEGRAM_CHAT_ID':
    logging.critical(f"Моля, попълнете 'bot_token' и 'chat_id' във файла '{config_file_path}'!")
    # exit()

if GOOGLE_AI_API_KEY and GOOGLE_AI_API_KEY != 'YOUR_GOOGLE_AI_API_KEY_HERE':
    try:
        genai.configure(api_key=GOOGLE_AI_API_KEY)
        logging.info("Google AI API ключ е успешно конфигуриран.")
    except Exception as e_ai_config:
        logging.error(f"Грешка при конфигуриране на Google AI API ключ: {e_ai_config}")
        GOOGLE_AI_API_KEY = None 
else:
    logging.warning("Google AI API ключ не е намерен или е примерен в config.ini. AI проверката ще бъде пропусната.")
    GOOGLE_AI_API_KEY = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0",
]

# --- ТЕЛЕГРАМ ---
def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or TELEGRAM_BOT_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN':
        logging.warning("Telegram bot_token или chat_id не са конфигурирани. Съобщението няма да бъде изпратено.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        logging.info(f"Съобщението е изпратено до Telegram: {text[:50]}...")
        return response.ok
    except requests.exceptions.RequestException as e:
        logging.error(f"Грешка при изпращане на Telegram съобщение: {e}")
        return False

# --- ПОМОЩНИ ФУНКЦИИ ---
def calculate_fuzzy_similarity(text1, text2):
    if not text1 or not text2:
        return 0
    return fuzz.token_set_ratio(str(text1).lower(), str(text2).lower())

def get_words_from_title(title):
    if not title:
        return set()
    words = re.findall(r'\b\w+\b', str(title).lower())
    extended_filler_words = [
        "продавам", "чисто", "нови", "нова", "ново", "перфектна", "перфектно", "перфектен",
        "състояние", "добро", "запазен", "запазена", "запазено", "спешно", "изгодно",
        "уникален", "уникална", "уникално", "оригинален", "оригинална", "оригинално",
        "комплект", "както", "вижда", "снимките", "без", "забележки", "забележка",
        "цена", "договаряне", "коментар", "възможен", "възможно", "само", "лично", "предаване",
        "за", "на", "и", "с", "в", "от", "до", "по", "при", "със", "качество", "качествено",
        "1бр", "2бр", "3бр", "бр", "броя", "много", "спешна", "оферта", "намаление", "разпродажба",
        "dual", "sim", "ram", "5g", "4g", "lte", "смартфон", "телефон", "мобилен",
        "wifi", "bluetooth", "nfc", "gps", "oled", "amoled", "lcd", "plus", "pro", "max", "mini", "ultra", "lite", "fe",
        "цвят", "черен", "бял", "сив", "син", "зелен", "червен", "жълт", "розов", "лилав", "оранжев", "кафяв",
        "златист", "сребърен", "графит", "тъмносин", "светлосин", "тъмнозелен", "светлозелен",
        "black", "white", "gray", "grey", "blue", "green", "red", "yellow", "pink", "purple", "orange", "brown",
        "gold", "silver", "graphite", "spacegray", "midnight", "starlight", "sierra", "alpine",
        "размер", "голям", "малък", "среден", "xl", "l", "m", "s", "xs", "xxl",
        "версия", "издание", "глобална", "европейска", "международна", "внос", "вносител",
        "разопакован", "мострен", "мостра", "тестов", "тестова", "разопакована",
        "модел", "година", "нов модел", "стар модел", "г", "инча", "mah", "вата", "w", "v", "волта", "ah", "ампера"
    ]
    storage_pattern_for_comparison = r'^\d+(gb|mb|tb)$' 
    final_words = set()
    for word in words:
        is_storage_word = bool(re.match(storage_pattern_for_comparison, word))
        if len(word) > 1 and \
           word not in extended_filler_words and \
           not is_storage_word:
            final_words.add(word)
    return final_words

# --- AI ПРОВЕРКА ---
def are_products_a_match_ai(olx_title_for_ai, emag_title_for_ai):
    """
    Използва Google AI за да прецени дали две заглавия описват един и същ продукт.
    OLX заглавието, което се подава тук, е вече почистеното за търсене.
    """
    if not GOOGLE_AI_API_KEY: 
        logging.debug("Google AI API ключ не е наличен. Пропускане на AI продуктово сравнение, приемаме за съвпадение.")
        return True 

    if not emag_title_for_ai or emag_title_for_ai == "Няма заглавие в eMAG":
        logging.warning("eMAG заглавието е празно или невалидно за AI сравнение. Приемаме за несъвпадение.")
        return False

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest') 
        prompt = f"""
        Инструкция: Имаш две заглавия на продукти. Първото е от OLX (вече леко почистено от общи думи), а второто е от eMAG. 
        Трябва да прецениш дали те описват един и същ ТИП продукт и МОДЕЛ, или много близък еквивалент, подходящ за сравнение на цени. 
        Бъди МНОГО СТРИКТЕН. Ако OLX заглавието е твърде общо (напр. само "Марка + Тип продукт") и не съдържа специфичен модел/линия/артикулен номер, който присъства в eMAG заглавието, тогава отговори с "НЕ".
        Фокусирай се върху ключовите характеристики: МАРКА, МОДЕЛ, ТИП НА ПРОДУКТА (напр. телефон, телевизор, маратонки, шенкел, компресор, калъф, зарядно), основни спецификации (напр. конкретен номер на част, ако има). 
        Игнорирай малки разлики като цвят (освен ако не е ключов за модела), състояние (нов/използван), информация за гаранция или доставка, освен ако не променят фундаментално продукта.

        Примери за СЪВПАДЕНИЕ (отговори с "ДА"):
        - OLX: "Apple iPhone 15 Pro 256GB син" | eMAG: "Смартфон Apple iPhone 15 Pro, 256GB, Blue Titanium" (ТИП: Смартфон, Марка: Apple, Модел: iPhone 15 Pro)
        - OLX: "Телевизор Samsung QE55Q80A" | eMAG: "Телевизор Samsung 55 инча QE55Q80A QLED 4K UHD Smart TV" (ТИП: Телевизор, Марка: Samsung, Модел: QE55Q80A)
        - OLX: "Маратонки Nike Pegasus 39 43" | eMAG: "Мъжки маратонки за бягане Nike Air Zoom Pegasus 39, Размер 43, Черни" (ТИП: Маратонки, Марка: Nike, Модел: Pegasus 39)
        - OLX: "Samsung Galaxy S23 Ultra 512GB Green" | eMAG: "Мобилен телефон Samsung Galaxy S23 Ultra, Dual SIM, 12GB RAM, 512GB, 5G, Phantom Black" (ТИП: Телефон, Марка: Samsung, Модел: S23 Ultra. Цветът е различен, но основният продукт е същият)
        - OLX: "Bosch Акумулаторен винтоверт GSR 12V-15" | eMAG: "Акумулаторен винтоверт Bosch Professional GSR 12V-15, 2 батерии x 2.0 Ah, зарядно, куфар" (ТИП: Винтоверт, Марка: Bosch, Модел: GSR 12V-15)

        Примери за НЕСЪВПАДЕНИЕ (отговори с "НЕ"):
        - OLX: "Шенкел Мерцедес ML-W164" | eMAG: "Въздушен компресор за Мерцедес Ml / Gl W164" (ТИП: Шенкел срещу ТИП: Компресор. Различни авточасти, въпреки че са за същия модел кола)
        - OLX: "iPhone 13" | eMAG: "Калъф за iPhone 13" (ТИП: Телефон срещу ТИП: Калъф. Продукт срещу аксесоар)
        - OLX: "Samsung Galaxy S22" | eMAG: "Samsung Galaxy S22 Ultra" (Различни под-модели от една серия. "Ultra" е значима разлика.)
        - OLX: "Маратонки Nike" | eMAG: "Тениска Nike" (ТИП: Маратонки срещу ТИП: Тениска. Различни типове продукти от една марка)
        - OLX: "Лаптоп Dell XPS 15" | eMAG: "Зарядно за лаптоп Dell XPS 15" (ТИП: Лаптоп срещу ТИП: Зарядно. Продукт срещу аксесоар)
        - OLX: "Слушалки Sony WH-1000XM4" | eMAG: "Слушалки Sony WH-1000XM5" (Различни поколения/модели, които се считат за различни продукти)
        - OLX: "Проходилка Leo Lorelli" | eMAG: "Проходилка Ricokids" (ТИП: Проходилка, но Марка: Lorelli срещу Марка: Ricokids. Различни марки)
        - OLX: "Дамски дънки Replay" | eMAG: "Дамски дънки Replay Luz Е-183836273 10-44" (ТИП: Дънки, Марка: Replay, но OLX е твърде общо и не споменава конкретния модел/линия "Luz" или артикулния номер, които присъстват в eMAG. Това е НЕСЪВПАДЕНИЕ.)
        - OLX: "Мъжки панталон" | eMAG: "Мъжки панталон Adidas" (OLX е твърде общо, за да се каже, че е същият като конкретния в eMAG, освен ако eMAG също не е много общ)
        
        Ключов въпрос: Дали потребител, търсещ продукта от OLX, би бил доволен да му се предложи продукта от eMAG като директен еквивалент или много близка алтернатива по отношение на ОСНОВНИЯ ПРОДУКТ и неговия МОДЕЛ/ТИП? Ако OLX заглавието е значително по-малко специфично от eMAG заглавието по отношение на модела/линията, отговорът е "НЕ". Ако са фундаментално различни неща, отговорът е "НЕ".

        Твоята задача е да отговориш само с една дума: "ДА" или "НЕ".

        OLX Заглавие (почистено): "{olx_title_for_ai}"
        eMAG Заглавие: "{emag_title_for_ai}"
        Отговор:
        """
        
        logging.info(f"AI Сравнение: OLX='{olx_title_for_ai}' vs eMAG='{emag_title_for_ai}'")
        response = model.generate_content(prompt)
        
        if not response.parts:
            safety_feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
            safety_ratings_str = str(safety_feedback.safety_ratings) if safety_feedback and hasattr(safety_feedback, 'safety_ratings') else "N/A"
            logging.warning(f"AI не върна части в отговора за сравнение. Prompt Feedback: {safety_ratings_str}. Приемаме за съвпадение.")
            return True 

        ai_response_text = response.text.strip().upper()
        logging.info(f"Отговор от AI за сравнението: {ai_response_text}")

        if ai_response_text == "ДА":
            return True
        elif ai_response_text == "НЕ":
            return False
        else:
            logging.warning(f"Неочакван отговор от AI за сравнение: '{response.text}'. Ще се приеме за съвпадение по подразбиране.")
            return True 
    except Exception as e:
        logging.error(f"Грешка при извикване на Google AI API за сравнение: {e}")
        return True 


# --- eMAG ТЪРСЕНЕ ---
def get_emag_data(query):
    search_url = f"https://www.emag.bg/search/{quote_plus(query)}"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        logging.info(f"Търсене в eMAG за: '{query}'")
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        product_card = soup.select_one('div.card-v2') 
        if not product_card:
            logging.warning(f"Не е намерен продукт в eMAG за '{query}'.")
            return None, None, None, None
        price_tag = product_card.select_one('.product-new-price')
        if not price_tag:
            logging.warning(f"Не е намерена цена за продукта в eMAG за '{query}'.")
            return None, None, None, None
        price_text = price_tag.get_text(strip=True)
        price_str = price_text.replace('лв.', '').replace(' ', '').strip()
        if ',' in price_str and '.' in price_str:
            price_str = price_str.replace('.', '') if price_str.find(',') > price_str.find('.') else price_str.replace(',', '')
            price_str = price_str.replace(',', '.')
        elif ',' in price_str: price_str = price_str.replace(',', '.')
        elif price_str.count('.') > 1: parts = price_str.split('.'); price_str = "".join(parts[:-1]) + "." + parts[-1]
        try: price = float(price_str)
        except ValueError:
            logging.error(f"Невалиден формат на цена в eMAG за '{query}': '{price_str}'"); return None, None, None, None
        link_tag = product_card.select_one('a.js-product-url')
        emag_product_link = link_tag['href'] if link_tag and link_tag.has_attr('href') else None
        if emag_product_link and not emag_product_link.startswith('http'): emag_product_link = "https://www.emag.bg" + emag_product_link
        title_tag = product_card.select_one('h2.card-v2-title a, h3.card-v2-title a, a.product-title-link, .card-v2-title-wrapper a')
        emag_product_title = (img_tag['alt'].strip() if (img_tag := product_card.select_one('img.w-100')) and img_tag.has_attr('alt') else "Няма заглавие в eMAG") if not title_tag else title_tag.get_text(strip=True)
        
        # Извличане на изображение от eMAG
        emag_image_url = None
        try:
            image_tag = product_card.select_one('img.w-100')
            if image_tag and image_tag.has_attr('src'):
                emag_image_url = image_tag['src']
                if emag_image_url and not emag_image_url.startswith('http'):
                    emag_image_url = "https:" + emag_image_url
                logging.info(f"Намерено eMAG изображение: {emag_image_url}")
        except Exception as e:
            logging.warning(f"Грешка при извличане на eMAG изображение: {e}")
        
        if price < MIN_EMAG_PRICE:
            logging.info(f"eMAG цена ({price} лв.) е под минималния праг ({MIN_EMAG_PRICE} лв.) за '{query}'. Пропускане.")
            return None, None, None, None
        logging.info(f"Намерена eMAG цена за '{emag_product_title}': {price} лв.")
        return price, emag_product_link, emag_product_title, emag_image_url
    except requests.exceptions.RequestException as e: logging.error(f"Грешка при HTTP заявка към eMAG за '{query}': {e}")
    except Exception as e: logging.error(f"Неочаквана грешка при търсене в eMAG за '{query}': {e}", exc_info=True)
    return None, None, None, None

def save_offer_to_db(title, price, olx_link, emag_price=None, emag_link=None, discount_percentage=None, category=None, location=None, image_url=None, emag_image_url=None):
    try:
        from app import app
        from models import db, Offer
        
        with app.app_context():
            try:
                # Ако няма OLX изображение, използваме eMAG изображението
                if not image_url and emag_image_url:
                    image_url = emag_image_url
                    logging.info(f"Използване на eMAG изображение: {image_url}")
                # Проверка дали офертата вече съществува
                existing_offer = Offer.query.filter_by(olx_link=olx_link).first()
                if existing_offer:
                    # Обновяване на съществуващата оферта
                    existing_offer.title = title
                    existing_offer.price = price
                    existing_offer.emag_price = emag_price
                    existing_offer.emag_link = emag_link
                    existing_offer.discount_percentage = discount_percentage
                    existing_offer.category = category
                    existing_offer.location = location
                    existing_offer.image_url = image_url
                    existing_offer.created_at = datetime.utcnow()
                    logging.info(f"Офертата е обновена в базата данни: {title}")
                else:
                    # Създаване на нова оферта
                    new_offer = Offer(
                        title=title,
                        price=price,
                        olx_link=olx_link,
                        emag_price=emag_price,
                        emag_link=emag_link,
                        discount_percentage=discount_percentage,
                        category=category,
                        location=location,
                        image_url=image_url
                    )
                    db.session.add(new_offer)
                    logging.info(f"Нова оферта е добавена в базата данни: {title}")
                db.session.commit()
                return True
            except Exception as e:
                db.session.rollback()
                logging.error(f"Грешка при работа с базата данни: {e}")
                return False
    except ImportError as e:
        logging.error(f"Грешка при импортиране на app или models: {e}")
        return False
    except Exception as e:
        logging.error(f"Неочаквана грешка при запазване на офертата в базата данни: {e}")
        return False

# --- ГЛАВНА ФУНКЦИЯ ЗА СКРАНИРАНЕ ---
def run_scraper_job():
    logging.info("--- Стартиране на задача за скрапинг ---")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument('--blink-settings=imagesEnabled=false')
    # Добавяме нови опции за WebGL
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-webgl')
    options.add_argument('--disable-webgl2')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = None
    try:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            s = Service(ChromeDriverManager().install()); driver = webdriver.Chrome(service=s, options=options)
            logging.info("Selenium Chrome драйверът е стартиран успешно с webdriver_manager.")
        except ImportError:
            logging.warning("webdriver_manager не е инсталиран. 'pip install webdriver-manager'. Опит за PATH.")
            driver = webdriver.Chrome(service=Service(), options=options); logging.info("Selenium Chrome драйверът е стартиран (PATH).")
        except Exception as e_driver: logging.critical(f"Неуспешно стартиране на Chrome драйвер: {e_driver}."); return
        olx_url = "https://www.olx.bg/ads/"; driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT) 
        try:
            driver.get(olx_url); WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-cy="l-card"]')))
            logging.info("Обявите в OLX се заредиха (поне контейнерът)."); time.sleep(random.uniform(2,4)) 
        except TimeoutException: logging.critical(f"OLX ({olx_url}) не се зареди ({PAGE_LOAD_TIMEOUT} сек)."); return
        except Exception as e: logging.critical(f"Грешка при зареждане на OLX: {e}."); return
        processed_olx_links_this_run = set()
        ad_cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-cy="l-card"]')
        links = list(set(a.get_attribute('href') for card in ad_cards for a in [card.find_element(By.TAG_NAME, 'a')] if a.get_attribute('href') and a.get_attribute('href').startswith('http')))
        logging.info(f"Намерени {len(links)} уникални обяви в OLX на първа страница.")
        for link_idx, link in enumerate(links):
            if link in processed_olx_links_this_run: logging.debug(f"Обявата '{link}' вече е обработена."); continue
            logging.info(f"Обработка на OLX обява ({link_idx + 1}/{len(links)}): {link}"); processed_olx_links_this_run.add(link)
            try:
                driver.get(link)
                try: WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body"))); logging.debug(f"Body зареден за {link}.")
                except TimeoutException: logging.warning(f"Body не се зареди за {link}."); continue
                time.sleep(random.uniform(0.5, 1.5)) 
                olx_title = "Няма заглавие"
                title_selectors = [
                    'h1[data-cy="adPageAdTitle"]',
                    'h1[data-testid="ad-title"]',
                    'h1.css-1soizd2',
                    'h4.css-10ofhqw',
                    'h1',
                    'h2',
                    'h3',
                    'h4',
                    '[data-cy="adPageAdTitle"]',
                    '[data-testid="ad-title"]',
                    '.css-1soizd2',
                    '.css-10ofhqw'
                ]

                # Списък с фрази, които показват грешка или проблем
                error_phrases = [
                    "има проблем",
                    "ще го решим",
                    "грешка",
                    "error",
                    "проблем",
                    "не може да се зареди",
                    "не е намерено",
                    "не съществува",
                    "невалидна",
                    "невалиден",
                    "невалидно"
                ]

                for selector in title_selectors:
                    try:
                        title_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for title_element in title_elements:
                            olx_title_candidate = title_element.text.strip()
                            
                            # Проверка дали заглавието е валидно
                            if (olx_title_candidate and 
                                len(olx_title_candidate) > 3 and 
                                not any(error_phrase in olx_title_candidate.lower() for error_phrase in error_phrases)):
                                
                                # Проверка дали елементът е видим
                                if title_element.is_displayed():
                                    olx_title = olx_title_candidate
                                    logging.info(f"Заглавие с '{selector}': {olx_title}")
                                    break
                        
                        if olx_title != "Няма заглавие":
                            break
                    except Exception as e:
                        logging.debug(f"Селектор за заглавие '{selector}' не е намерен за {link}: {str(e)}")

                if olx_title == "Няма заглавие" or any(error_phrase in olx_title.lower() for error_phrase in error_phrases):
                    logging.warning(f"Не може да се извлече валидно заглавие за {link}.")
                    time.sleep(random.uniform(1.0, 2.0))
                    continue
                price_olx = None
                price_selectors = ['h3.css-fqcbii', 'div[data-testid="adPagePrice"] strong', '[data-testid="ad-price"] strong', 'div[data-cy="adPagePrice"] div > strong', 'h3.css-12vqlj3']
                for selector in price_selectors:
                    try:
                        price_element = WebDriverWait(driver, SHORT_ELEMENT_WAIT).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                        price_text = price_element.text.strip(); price_match = re.search(r'([\d\s,.]+)', price_text) 
                        if price_match:
                            price_str_cleaned = price_match.group(1).replace(' ', '').replace(',', '.')
                            if price_str_cleaned: price_olx = float(price_str_cleaned)
                            if price_olx is not None: logging.info(f"Цена с '{selector}': {price_olx}"); break 
                    except: logging.debug(f"Селектор за цена '{selector}' не е намерен за {link}.")
                if olx_title == "Няма заглавие" and price_olx is None: logging.warning(f"Нито заглавие, нито цена за {link}."); time.sleep(random.uniform(1.0, 2.0)); continue
                if price_olx is None: logging.info(f"Пропускане '{olx_title}' без цена."); time.sleep(random.uniform(1.0, 2.0)); continue

                # Извличане на допълнителна информация
                category = None
                location = None
                
                try:
                    # Опит за извличане на категория
                    category_element = driver.find_element(By.CSS_SELECTOR, 'a[data-cy="adPageBreadcrumb"]')
                    if category_element:
                        category = category_element.text.strip()
                except: pass

                try:
                    # Опит за извличане на локация
                    location_element = driver.find_element(By.CSS_SELECTOR, 'p[data-testid="location-date"]')
                    if location_element:
                        location_text = location_element.text.strip()
                        # Премахваме "Обновено..." частта
                        location = location_text.split(' - ')[0].strip()
                        logging.info(f"Намерена локация: {location}")
                except Exception as e:
                    logging.debug(f"Не може да се извлече локация: {e}")
                    location = None

                logging.info(f"OLX Data: Title='{olx_title}', Price={price_olx}, Location='{location}'")
                filler_words_for_search = [
                    "продавам", "чисто", "нови", "нова", "ново", "перфектна", "перфектно", "перфектен", "състояние", "добро", "запазен", "запазена", "запазено", "спешно", "изгодно",
                    "уникален", "уникална", "уникално", "оригинален", "оригинална", "оригинално", "комплект", "както", "вижда", "снимките", "без", "забележки", "забележка",
                    "цена", "договаряне", "коментар", "възможен", "възможно", "само", "лично", "предаване", "за", "на", "и", "с", "в", "от", "до", "по", "при", "със", "качество", "качествено",
                    "1бр", "2бр", "3бр", "бр", "броя", "много", "спешна", "оферта", "намаление", "разпродажба", "dual", "sim", "ram", "5g", "4g", "lte", "смартфон", "телефон", "мобилен",
                    "wifi", "bluetooth", "nfc", "gps", "oled", "amoled", "lcd", "plus", "pro", "max", "mini", "ultra", "lite", "fe", "цвят", "черен", "бял", "сив", "син", "зелен", "червен", "жълт", "розов", "лилав", "оранжев", "кафяв",
                    "златист", "сребърен", "графит", "тъмносин", "светлосин", "тъмнозелен", "светлозелен", "black", "white", "gray", "grey", "blue", "green", "red", "yellow", "pink", "purple", "orange", "brown",
                    "gold", "silver", "graphite", "spacegray", "midnight", "starlight", "sierra", "alpine", "размер", "голям", "малък", "среден", "xl", "l", "m", "s", "xs", "xxl",
                    "версия", "издание", "глобална", "европейска", "международна", "внос", "вносител", "разопакован", "мострен", "мостра", "тестов", "тестова", "разопакована",
                    "модел", "година", "нов модел", "стар модел", "г", "инча", "mah", "вата", "w", "v", "волта", "ah", "ампера"
                ]
                storage_pattern = r'^\d+(gb|mb|tb)$' 
                olx_title_for_search_words = []
                for word_original in olx_title.split(): 
                    word_lower_cleaned = re.sub(r'[^\w\s-]', '', word_original.lower()) 
                    is_filler = word_lower_cleaned in filler_words_for_search; is_storage = bool(re.match(storage_pattern, word_lower_cleaned))
                    if word_lower_cleaned and not is_filler and not is_storage and len(word_lower_cleaned) > 1: olx_title_for_search_words.append(word_original) 
                product_name_for_emag_search = " ".join(olx_title_for_search_words)
                if not product_name_for_emag_search.strip(): 
                    logging.warning(f"Заглавието '{olx_title}' остана празно след филтри. Ползваме оригиналното."); product_name_for_emag_search = olx_title
                logging.info(f"За търсене в eMAG: '{product_name_for_emag_search}'")
                
                # Филтър 1: Минимален брой думи
                if len(product_name_for_emag_search.split()) < MIN_WORDS_FOR_EMAG_SEARCH:
                    logging.info(f"Почистеното OLX заглавие '{product_name_for_emag_search}' има по-малко от {MIN_WORDS_FOR_EMAG_SEARCH} думи. Пропускане.")
                    time.sleep(random.uniform(1.0, 2.0)); continue
                
                emag_price, emag_product_link, emag_product_title, emag_image_url = get_emag_data(product_name_for_emag_search)
                if emag_price is None or emag_product_title is None or emag_product_title == "Няма заглавие в eMAG": 
                    logging.info(f"Няма валидни данни от eMAG за '{product_name_for_emag_search}'."); time.sleep(random.uniform(1.5, 2.5)); continue 
                
                # Филтър 2: Проверка за липсващи думи
                olx_words_for_comparison = get_words_from_title(product_name_for_emag_search) 
                emag_words_for_comparison = get_words_from_title(emag_product_title)
                missing_from_emag_count = 0
                if olx_words_for_comparison and emag_words_for_comparison: 
                    for word in olx_words_for_comparison: 
                        if word not in emag_words_for_comparison:
                            is_very_similar = any(fuzz.ratio(word, emag_word) > 85 for emag_word in emag_words_for_comparison)
                            if not is_very_similar: missing_from_emag_count += 1; logging.debug(f"Дума '{word}' липсва/не е сходна в '{emag_product_title}'.")
                logging.info(f"Проверка думи: {missing_from_emag_count} липсващи от OLX в eMAG (праг: {MAX_MISSING_WORDS_THRESHOLD}).")
                if missing_from_emag_count > MAX_MISSING_WORDS_THRESHOLD:
                    logging.info(f"'{olx_title}' пропуснат поради {missing_from_emag_count} липсващи думи в eMAG."); time.sleep(random.uniform(1.0, 2.0)); continue
                
                # Филтър 3: Сходство на заглавията (оригинално OLX с eMAG)
                title_similarity_score = calculate_fuzzy_similarity(olx_title, emag_product_title) 
                logging.info(f"Сходство оригинални заглавия: {title_similarity_score}% (праг: {TITLE_SIMILARITY_THRESHOLD}%)")
                if title_similarity_score < TITLE_SIMILARITY_THRESHOLD:
                    logging.info(f"Недостатъчно сходство на оригинални заглавия ({title_similarity_score}%) за '{olx_title}'. Пропускане преди проверка за отстъпка/AI.")
                    time.sleep(random.uniform(1.0, 2.0)); continue

                # Филтър 4: Проверка за отстъпка (ПРЕДИ AI)
                if not (price_olx <= emag_price * (1 - DISCOUNT_THRESHOLD)):
                    logging.info(f"OLX цена ({price_olx:.2f} лв.) не е достатъчно ниска спрямо eMAG ({emag_price:.2f} лв.) за отстъпка от {DISCOUNT_THRESHOLD*100}%. Пропускане преди AI.")
                    time.sleep(random.uniform(1.0, 2.0)); continue
                
                # Филтър 5: AI Проверка за съвпадение на продуктите (само ако цената е добра)
                products_match_ai = True 
                if GOOGLE_AI_API_KEY and product_name_for_emag_search.strip() and emag_product_title != "Няма заглавие в eMAG": 
                    products_match_ai = are_products_a_match_ai(product_name_for_emag_search, emag_product_title)
                    if not products_match_ai:
                        logging.info(f"AI прецени, че продуктите '{product_name_for_emag_search}' и '{emag_product_title}' не съвпадат (въпреки добрата цена). Пропускане.")
                        time.sleep(random.uniform(1.0,2.0)); continue
                
                # Ако всички проверки са минали, изпращаме съобщение
                logging.info(f"СЪВПАДЕНИЕ (след всички филтри, вкл. AI={products_match_ai}): OLX: {price_olx:.2f} лв. | eMAG: {emag_price:.2f} лв. | OLX: {olx_title} | eMAG: {emag_product_title}")
                discount_percentage = (1 - (price_olx / emag_price)) * 100 if emag_price > 0 else 100
                message = (f"🟢 **OLX оферта с ~{discount_percentage:.0f}% по-ниска цена!**\n<b>{olx_title}</b>\nOLX: <b>{price_olx:.2f} лв.</b>\neMAG: {emag_price:.2f} лв. ({emag_product_title})\nOLX: {link}\neMAG: {emag_product_link if emag_product_link else 'Няма'}")
                
                # Запазване в базата данни
                save_offer_to_db(
                    title=olx_title,
                    price=price_olx,
                    olx_link=link,
                    emag_price=emag_price,
                    emag_link=emag_product_link,
                    discount_percentage=discount_percentage,
                    category=category,
                    location=location,
                    image_url=emag_image_url,  # Използваме само eMAG картинката
                    emag_image_url=emag_image_url
                )
                
                # Изпращане в Telegram
                send_telegram_message(message)
                
                time.sleep(random.uniform(3.5, 7.0)) 
            except TimeoutException: logging.warning(f"Таймаут ({PAGE_LOAD_TIMEOUT}s) за {link}.");
            except WebDriverException as e: logging.error(f"WebDriver грешка за {link}: {e.msg}.")
            except Exception as e: logging.error(f"Грешка за {link}: {e}", exc_info=True)
            finally: time.sleep(random.uniform(2.0, 3.5)) 
    except Exception as e: logging.critical(f"Критична грешка в run_scraper_job: {e}", exc_info=True)
    finally:
        if driver: driver.quit(); logging.info("Selenium Chrome драйверът е затворен.")
    logging.info("--- Задача за скрапинг приключи ---")