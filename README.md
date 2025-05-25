# OLX Сравнител

Модерно уеб приложение за сравняване на цени между OLX и eMAG, с възможност за търсене и филтриране на оферти.

## Функционалности

- Автоматично сканиране на OLX за изгодни оферти
- Сравнение с цените в eMAG
- Изпращане на известия в Telegram
- Модерен уеб интерфейс с търсене и филтриране
- Сортиране по различни критерии
- Пагинация на резултатите
- Категоризация на офертите
- Показване на процент отстъпка
- Директни линкове към OLX и eMAG

## Изисквания

- Python 3.8+
- Chrome браузър (за Selenium)
- Telegram бот токен
- Google AI API ключ (опционално)

## Инсталация

1. Клонирайте репозиторито:
```bash
git clone https://github.com/yourusername/olx-comparator.git
cd olx-comparator
```

2. Създайте виртуална среда и активирайте я:
```bash
python -m venv venv
source venv/bin/activate  # За Linux/Mac
venv\Scripts\activate     # За Windows
```

3. Инсталирайте зависимостите:
```bash
pip install -r requirements.txt
```

4. Копирайте `config.ini.example` в `config.ini` и попълнете вашите данни:
```ini
[TELEGRAM]
BOT_TOKEN = your_telegram_bot_token
CHAT_ID = your_telegram_chat_id

[SETTINGS]
MIN_EMAG_PRICE = 50
DISCOUNT_THRESHOLD = 0.4
TITLE_SIMILARITY_THRESHOLD = 60
MAX_MISSING_WORDS_THRESHOLD = 3
MIN_WORDS_FOR_EMAG_SEARCH = 3
PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT_TIMEOUT = 20
SHORT_ELEMENT_WAIT = 5

[GOOGLE_AI]
API_KEY = your_google_ai_api_key
```

## Стартиране

1. Стартирайте уеб приложението:
```bash
python app.py
```

2. Отворете браузъра и навигирайте до:
```
http://localhost:5000
```

## Използване

1. **Търсене на оферти**:
   - Използвайте полето за търсене за филтриране по заглавие
   - Филтрирайте по категория, цена и минимална отстъпка
   - Сортирайте по различни критерии

2. **Преглед на оферти**:
   - Всяка оферта показва цената в OLX и eMAG
   - Процентът отстъпка е видим в горния десен ъгъл
   - Директни линкове към OLX и eMAG офертите

3. **Автоматично обновяване**:
   - Офертите се обновяват автоматично на всеки 30 минути
   - Можете да обновите ръчно с бутона "Обнови"

## Конфигурация

Можете да промените следните настройки в `config.ini`:

- `MIN_EMAG_PRICE`: Минимална цена в eMAG за сравнение
- `DISCOUNT_THRESHOLD`: Минимален процент отстъпка за известие
- `TITLE_SIMILARITY_THRESHOLD`: Праг за сходство на заглавията
- `PAGE_LOAD_TIMEOUT`: Таймаут за зареждане на страници
- И други...

## Лиценз

MIT License 