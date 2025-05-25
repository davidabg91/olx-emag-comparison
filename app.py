from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime
import json
from olx_scraper import run_scraper_job
import threading
import schedule
import time
from models import db, Offer
import logging
import sys
import atexit
import requests

# Конфигурация на логването
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

app = Flask(__name__)
CORS(app)

# Конфигурация на базата данни
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///offers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Създаване на базата данни
with app.app_context():
    db.create_all()

# Заключване за предотвратяване на паралелно изпълнение
scraper_lock = threading.Lock()
is_scraper_running = False
scraper_started = False  # Нова променлива за проследяване на стартирането

def run_scraper_with_lock():
    global is_scraper_running, scraper_started
    if not scraper_lock.acquire(blocking=False):
        logging.warning("Скрапинг задачата вече се изпълнява. Пропускане.")
        return
    
    try:
        is_scraper_running = True
        logging.info("Стартиране на скрапинг задача...")
        run_scraper_job()
    except Exception as e:
        logging.error(f"Грешка при изпълнение на скрапинг задача: {e}")
    finally:
        is_scraper_running = False
        scraper_lock.release()
        logging.info("Скрапинг задачата приключи.")

def run_scheduler():
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logging.error(f"Грешка в планировчика: {e}")
            time.sleep(5)  # Пауза при грешка

# Планиране на скрапинг задачата
schedule.every(5).minutes.do(run_scraper_with_lock)

# Добавяме keep-alive функционалност
def keep_alive():
    while True:
        try:
            response = requests.get("https://olx-emag-comparison.onrender.com/")
            logging.info(f"Keep-alive request sent. Status: {response.status_code}")
            time.sleep(60)  # 1 минута
        except Exception as e:
            logging.error(f"Keep-alive request failed: {e}")
            time.sleep(30)  # 30 секунди при грешка

# Стартиране на keep-alive в отделна нишка
keep_alive_thread = threading.Thread(target=keep_alive)
keep_alive_thread.daemon = True
keep_alive_thread.start()

# Стартиране на планировчика в отделна нишка
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.daemon = True
scheduler_thread.start()

# Стартираме скрапера веднага след стартиране на планировчика
threading.Thread(target=run_scraper_with_lock, daemon=True).start()

# Регистриране на функция за почистване при изход
def cleanup():
    if is_scraper_running:
        logging.info("Изчакване на текущата скрапинг задача да приключи...")
        scraper_lock.acquire()
        scraper_lock.release()

atexit.register(cleanup)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/offers')
def get_offers():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        min_discount = request.args.get('min_discount', type=float)
        category = request.args.get('category')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')

        query = Offer.query

        if search and search.strip():
            query = query.filter(Offer.title.ilike(f'%{search}%'))
        if min_price is not None:
            query = query.filter(Offer.price >= min_price)
        if max_price is not None:
            query = query.filter(Offer.price <= max_price)
        if min_discount is not None:
            query = query.filter(Offer.discount_percentage >= min_discount)
        if category:
            query = query.filter(Offer.category == category)

        # Сортиране
        if sort_by == 'price':
            query = query.order_by(Offer.price.desc() if sort_order == 'desc' else Offer.price.asc())
        elif sort_by == 'discount':
            query = query.order_by(Offer.discount_percentage.desc() if sort_order == 'desc' else Offer.discount_percentage.asc())
        else:  # created_at
            query = query.order_by(Offer.created_at.desc() if sort_order == 'desc' else Offer.created_at.asc())

        pagination = query.paginate(page=page, per_page=per_page)
        
        offers_data = [offer.to_dict() for offer in pagination.items]
        logging.info(f"Върнати оферти: {len(offers_data)}")
        for offer in offers_data:
            logging.info(f"Оферта: {offer['title']}, Image URL: {offer.get('image_url', 'Няма URL')}")
        
        return jsonify({
            'offers': offers_data,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
    except Exception as e:
        logging.error(f"Грешка при извличане на оферти: {e}")
        return jsonify({'error': 'Възникна грешка при извличане на оферти'}), 500

@app.route('/api/categories')
def get_categories():
    try:
        categories = db.session.query(Offer.category).distinct().all()
        return jsonify([category[0] for category in categories if category[0]])
    except Exception as e:
        logging.error(f"Грешка при извличане на категории: {e}")
        return jsonify({'error': 'Възникна грешка при извличане на категории'}), 500

@app.route('/api/status')
def status():
    try:
        logging.info("Стартиране на скрапинг задача...")
        logging.info(f"CHROME_BIN: {os.environ.get('CHROME_BIN')}")
        logging.info(f"CHROMEDRIVER_PATH: {os.environ.get('CHROMEDRIVER_PATH')}")
        logging.info(f"PATH: {os.environ.get('PATH')}")
        logging.info("Проверка на файловете:")
        try:
            import subprocess
            chrome_bin = os.environ.get('CHROME_BIN', '/opt/chrome/google-chrome')
            chromedriver_path = os.environ.get('CHROMEDRIVER_PATH', '/opt/chrome/chromedriver')
            logging.info(f"Проверка на Chrome: {subprocess.check_output([chrome_bin, '--version']).decode()}")
            logging.info(f"Проверка на ChromeDriver: {subprocess.check_output([chromedriver_path, '--version']).decode()}")
        except Exception as e:
            logging.error(f"Грешка при проверка на файловете: {e}")
        
        if not scraper_lock.acquire(blocking=False):
            logging.warning("Скрапинг задачата вече се изпълнява. Пропускане.")
            return jsonify({"status": "warning", "message": "Скрапинг задачата вече се изпълнява"})
        
        try:
            thread = threading.Thread(target=run_scraper_job)
            thread.daemon = True
            thread.start()
            return jsonify({"status": "success", "message": "Скрапинг задачата е стартирана"})
        finally:
            scraper_lock.release()
    except Exception as e:
        logging.error(f"Грешка при стартиране на скрапинг задачата: {e}")
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    def signal_handler(signum, frame):
        logging.info("Получен сигнал за спиране. Изчакване на текущите задачи да приключат...")
        if is_scraper_running:
            logging.info("Изчакване на скрапинг задачата да приключи...")
            scraper_lock.acquire()
            scraper_lock.release()
        logging.info("Сървърът спира...")
        os._exit(0)

    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    with app.app_context():
        db.create_all()
    
    # Стартиране на скрапинга в отделна нишка
    scraper_thread = threading.Thread(target=run_scraper_with_lock)
    scraper_thread.daemon = True
    scraper_thread.start()
    
    # Стартиране на сървъра с публичен хост
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 