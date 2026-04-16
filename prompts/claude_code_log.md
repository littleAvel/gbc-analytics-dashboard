### Prompt #1
Контекст: выполняю тестовое задание AI Tools Specialist для e-commerce компании GBC. 
Стек: Python 3.12, RetailCRM API v5, Supabase, позже Vercel + Telegram.

В корне репо есть mock_orders.json с 50 тестовыми заказами. Нужно залить их в мой 
RetailCRM демо-аккаунт через REST API v5.

Задача: создай scripts/upload_to_crm.py который:

1. Читает mock_orders.json из корня репо
2. Валидирует структуру через pydantic модели (создай MockOrder для входа и 
   RetailCRMOrderPayload для отправки)
3. Преобразует каждый заказ в формат RetailCRM:
   - externalId = строка из исходного id (для идемпотентности)
   - firstName, phone, email из customer
   - items мапятся в массив items с initialPrice и quantity
   - status = "new" (или маппинг статусов если исходные отличаются)
   - createdAt в формате RetailCRM
4. Отправляет POST /api/v5/orders/create для каждого
   - Если заказ с таким externalId уже есть — использует /api/v5/orders/{externalId}/edit?by=externalId
   - Так обеспечивается идемпотентность при повторном запуске
5. Логирует: какой заказ, успех/ошибка, код ответа
6. Rate limiting: 100мс между запросами
7. В конце итоговая статистика: создано / обновлено / ошибок / время

Требования:
- httpx sync (не async, для 50 запросов не нужно)
- python-dotenv для креды из .env.local
- Type hints везде
- Обработка ошибок на каждом запросе — одна ошибка не валит весь процесс
- Логирование через стандартный logging, не print

Формат запроса к RetailCRM:
POST https://{subdomain}.retailcrm.ru/api/v5/orders/create
Параметры в теле как form-urlencoded:
  apiKey={key}
  site={site_code}  # код магазина в RetailCRM, нужно выяснить
  order={json_string}  # заказ как JSON-строка

Документация: https://docs.retailcrm.ru/Developers/API/APIVersions/APIv5

Перед генерацией кода:
1. Посмотри реальную структуру mock_orders.json (он в корне репо)
2. Уточни маппинг полей
3. Скажи какой site code использовать — я посмотрю в настройках RetailCRM

Выдай сначала план (структуру модулей и функций), потом код.

---

### Prompt #2
Вот справочники моего RetailCRM:

orderTypes: только "main"
orderMethods: phone, shopping-cart, one-click, landing-page, offline, app, live-chat, messenger и др.
statuses: new, complete, cancel-other, assembling, delivering и др.

В mock_orders.json используются:
- orderType: "eshop-individual" → замени на "main"
- orderMethod: посмотри что в mock_orders и замапь на ближайший существующий. 
  Если нет подходящего — ставь "shopping-cart" по умолчанию
- status: посмотри что в mock_orders и замапь. Если нет совпадения — ставь "new"

Обнови STATUS_MAP и добавь ORDER_METHOD_MAP в upload_to_crm.py.

---

### Prompt #3
При повторном запуске все 50 заказов падают с 400 "Order already exists", 
но скрипт не переходит к edit. 

Проблема в upsert_order(): условие для дубликата проверяет status_code == 460 
и "externalId" в ошибке, но RetailCRM возвращает 400 и текст "Order already exists".

Исправь: если errorMsg содержит "already exists" — делай edit по externalId.

---

### Prompt #4
Контекст: тестовое задание AI Tools Specialist для GBC. 
Шаг 1 выполнен — 50 заказов загружены в RetailCRM. 
Шаг 2 — таблица orders создана в Supabase.

Сейчас нужен скрипт который:
1. Забирает заказы из RetailCRM API v5 (GET /api/v5/orders)
2. Upsert каждого в Supabase (по retailcrm_id — если есть, обновить; если нет, вставить)
3. Если total_sum > 50000 — отправить уведомление в Telegram

Создай scripts/sync_to_supabase.py:

Логика:
- Запросить GET /api/v5/orders с параметром limit=100 (у нас 50, хватит одной страницы)
- Для каждого заказа:
  - Извлечь: id (это retailcrm_id), externalId, firstName, lastName, 
    phone, email, totalSumm, status, orderType, orderMethod, 
    delivery.address.city, createdAt
  - Сохранить полный объект в raw_data как jsonb
  - Upsert в Supabase таблицу orders (on_conflict retailcrm_id)
  - Если totalSumm > 50000 и заказ новый (не был в Supabase раньше) — 
    отправить Telegram-алерт

Telegram-алерт:
- POST https://api.telegram.org/bot{TOKEN}/sendMessage
- Формат сообщения:
  🔔 Новый крупный заказ
  Сумма: {sum} ₸
  Клиент: {firstName} {lastName}
  Статус: {status}
  ID: {retailcrm_id}

Стек:
- httpx для запросов к RetailCRM и Telegram
- supabase-py для записи в Supabase
- python-dotenv для переменных из .env.local
- logging, не print

Переменные окружения (уже есть в .env.local):
- RETAILCRM_URL, RETAILCRM_API_KEY, RETAILCRM_SITE
- SUPABASE_URL, SUPABASE_SERVICE_KEY (использовать service key для записи!)
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Требования:
- Идемпотентность: повторный запуск не создаёт дубли в Supabase
- Telegram-алерт только для НОВЫХ заказов > 50000 (не при повторном sync)
- В конце: статистика — вставлено / обновлено / алертов отправлено
- Type hints, обработка ошибок на каждом заказе

Выдай план, потом код.

---

### Prompt #5

Контекст: тестовое задание AI Tools Specialist для GBC (e-commerce, бренд Tomyris).
В Supabase таблица orders с 50 заказами. Нужен дашборд.

Создай Next.js 14 приложение в папке dashboard/:

Стек:
- Next.js 14 + TypeScript + App Router
- Tailwind CSS
- Recharts для графиков
- @supabase/supabase-js для чтения данных

Страница одна — главная, на ней:

1. Заголовок "GBC Orders Dashboard"

2. Три KPI-карточки в ряд:
   - Всего заказов (количество)
   - Общая сумма (₸)
   - Средний чек (₸)

3. График 1: количество заказов по дням (BarChart)

4. График 2: сумма заказов по дням (LineChart)

5. Таблица последних 10 заказов: дата, клиент, сумма, статус, город

Подключение к Supabase:
- Через серверный компонент (не useEffect на клиенте!)
- Env переменные: NEXT_PUBLIC_SUPABASE_URL и NEXT_PUBLIC_SUPABASE_ANON_KEY
- Таблица orders, поля: id, retailcrm_id, first_name, last_name, 
  total_sum, status, city, created_at

Требования:
- Тёмная тема по умолчанию (фон #0a0a0a или Tailwind dark)
- Адаптивная вёрстка (mobile-friendly)
- ISR: revalidate = 60 секунд
- Числа форматировать с разделителями тысяч
- Обработка пустого состояния "Нет заказов"
- Минимализм — не перегружать UI

Не нужно:
- Авторизация
- Фильтры/поиск
- Роутинг (одна страница)
- Отдельные файлы CSS/JS — всё в одном

Структура:
dashboard/
  app/
    page.tsx
    layout.tsx
    globals.css
  components/
    KpiCards.tsx
    OrdersBarChart.tsx
    OrdersSumChart.tsx
    OrdersTable.tsx
  lib/
    supabase.ts
  package.json
  next.config.js
  tailwind.config.ts
  tsconfig.json

Выдай план, потом код. Код должен быть готов к запуску после npm install.

---


