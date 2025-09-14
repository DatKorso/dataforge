# Связи таблиц БД (первичная схема)

Документ описывает базовые связи между ключевыми таблицами данных Ozon и Wildberries, используемыми в дашборде. Ниже приведены логические связи, целевое назначение связок и примеры SQL‑запросов для объединения данных.

## Сводка связей

- Ozon: `oz_products` ⇄ `oz_products_full` по полю `oz_vendor_code`.
- Ozon: `oz_orders` ⇄ `oz_products` по полям `oz_product_id` и/или `oz_vendor_code`.
- Wildberries: `wb_products` ⇄ `wb_prices` по полю `wb_sku`; дополнительно по `wb_vendor_code` (если поле присутствует в `wb_products`).

## Визуальная схема (ERD)

```mermaid
erDiagram
    OZ_PRODUCTS {
        BIGINT oz_product_id
        VARCHAR oz_vendor_code
        BIGINT oz_sku
    }
    OZ_PRODUCTS_FULL {
        VARCHAR oz_vendor_code
        -- прочие атрибуты карточки
    }
    OZ_ORDERS {
        BIGINT oz_product_id
        VARCHAR oz_vendor_code
        -- атрибуты заказа
    }
    WB_PRODUCTS {
        BIGINT wb_sku
        VARCHAR primary_barcode
        -- прочие атрибуты карточки
    }
    WB_PRICES {
        VARCHAR wb_sku
        VARCHAR wb_vendor_code
        -- ценовые атрибуты
    }

    OZ_PRODUCTS ||--|| OZ_PRODUCTS_FULL : "oz_vendor_code"
    OZ_PRODUCTS ||--o{ OZ_ORDERS : "oz_product_id / oz_vendor_code"

    WB_PRODUCTS ||--o{ WB_PRICES : "wb_sku"
    %% Доп. связь через wb_vendor_code — если столбец есть в products
```

Примечания по кардинальности:
- `oz_products` → `oz_orders`: как правило 1:N (одна карточка — много строк заказов).
- `oz_products` ↔ `oz_products_full`: 1:1 или 1:N (зависит от уникальности `oz_vendor_code` в файлах выгрузки; в схеме БД явного PK нет).
- `wb_products` → `wb_prices`: 1:1 или 1:N в зависимости от того, как формируется прайс (по `wb_sku`).

## Назначение связок

- `oz_products` ⇄ `oz_products_full` — обогащение карточек товара расширенными атрибутами (характеристики, фото, размеры и т. п.) по единому артикулу `oz_vendor_code`.
- `oz_orders` ⇄ `oz_products` — привязка строк заказов к карточкам товаров для аналитики продаж, остатков и цен.
- `wb_products` ⇄ `wb_prices` — сопоставление карточек с их текущими/актуальными ценами.

## Индексация (для производительности)

Текущая схема БД содержит индексы по ключевым полям связей:
- `oz_products`: индексы по `oz_product_id`, `oz_sku`, `oz_vendor_code`, `"barcode-primary"`.
- `oz_orders`: индексы по `oz_product_id`, `oz_vendor_code`.
- `oz_products_full`: индексы по `oz_vendor_code`, `primary_barcode`.
- `wb_products`: индексы по `wb_sku`, `primary_barcode`.
- `wb_prices`: индексы по `wb_sku`, `barcode_primary`.

## Примеры SQL‑объединений

### Ozon: карточки + расширенные атрибуты
```sql
SELECT p.*, pf.*
FROM oz_products AS p
LEFT JOIN oz_products_full AS pf
  ON pf.oz_vendor_code = p.oz_vendor_code;
```

### Ozon: заказы + карточки
```sql
SELECT o.*, p.*
FROM oz_orders AS o
LEFT JOIN oz_products AS p
  ON p.oz_product_id = o.oz_product_id
  -- Доп. страховка на случай дубликатов/несостыковок ID
  AND p.oz_vendor_code = o.oz_vendor_code;
```

### Wildberries: карточки + цены
```sql
SELECT wp.*, pr.*
FROM wb_products AS wp
LEFT JOIN wb_prices AS pr
  ON pr.wb_sku = wp.wb_sku
  -- Если в products появится wb_vendor_code, можно добавить второе условие
  -- AND pr.wb_vendor_code = wp.wb_vendor_code
;
```

## Правила и валидация данных

- Поля связей не должны быть пустыми: `oz_vendor_code`, `oz_product_id`, `wb_sku`.
- Возможны дубликаты в исходных выгрузках; рекомендуется:
  - использовать агрегаты при аналитике (например, `GROUP BY oz_product_id`),
  - проверять уникальность ключей перед загрузкой в витрины.
- Для Wildberries `wb_vendor_code` в текущей схеме присутствует в `wb_prices`, а в `wb_products` — отсутствует; базовая связь выполняется по `wb_sku`.

## Расширение документа

По мере внедрения новых таблиц (цены Ozon, остатки, поставки и т. п.) данный документ будет дополнен новыми связями и деталями по кардинальности, а также ссылками на бизнес‑процессы (цепочки загрузки и использования данных в отчётах).

---

Последнее обновление: автогенерация ассистентом.
