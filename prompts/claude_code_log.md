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
