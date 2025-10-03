from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ColumnSpec:
    """Specification for mapping an input column to a DB column.

    - `source`: header name in the uploaded file
    - `target`: column name in the database
    - `required`: whether the field is required in the batch
    - `transform`: optional transformer key to apply (from transformers.TRANSFORMERS)
    """

    source: str
    target: str
    required: bool = False
    transform: str | None = None


@dataclass(frozen=True)
class ReportSpec:
    """Pluggable report configuration.

    The goal is to make adding new reports trivial by defining a new spec.
    """

    id: str
    name: str
    description: str
    table: str
    allowed_extensions: list[str]
    default_encoding: str = "utf-8"
    delimiter: str | None = None  # None -> auto-detect for CSV
    header_row: int = 0
    columns: list[ColumnSpec] = field(default_factory=list)
    unique_fields_in_batch: list[str] = field(default_factory=list)
    computed_fields: dict[str, Callable[[dict[str, Any]], Any]] = field(default_factory=dict)
    multi_file: bool = False
    assembler: str | None = None  # id of assembler when multi_file



def _extract_primary_barcode(record: dict[str, Any], prefer_last: bool) -> str | None:
    """Pick first or last barcode from normalized record value."""
    raw = record.get("barcodes")
    if not raw:
        return None

    values: list[Any]
    if isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        try:
            decoded = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            if isinstance(raw, str):
                values = [part.strip() for part in raw.split(';')]
            else:
                return None
        else:
            if isinstance(decoded, list):
                values = decoded
            else:
                values = [decoded]

        cleaned = [str(item).strip() for item in values if str(item).strip()]
        if not cleaned:
            return None
        return cleaned[-1] if prefer_last else cleaned[0]


def _primary_barcode_first(record: dict[str, Any]) -> str | None:
    return _extract_primary_barcode(record, prefer_last=False)


def _primary_barcode_last(record: dict[str, Any]) -> str | None:
    return _extract_primary_barcode(record, prefer_last=True)


def get_registry() -> dict[str, ReportSpec]:
    """Return the registry of supported report specs.

    Currently includes: Ozon — Товары (ozon_products)
    """
    # Ozon Products spec
    # Mapping is based on docs/TZ_oz_products_import.md
    ozon_products = ReportSpec(
        id="ozon_products",
        name="Ozon — Товары",
        description=(
            "Импорт отчёта товаров Ozon (.csv/.xlsx). Автопоиск разделителя, "
            "очистка и валидация, загрузка в таблицу oz_products."
        ),
        table="oz_products",
        allowed_extensions=["csv", "xlsx"],
        default_encoding="utf-8",
        delimiter=None,  # auto for CSV
        header_row=0,
        columns=[
            ColumnSpec("Артикул", "oz_vendor_code", required=True, transform="string_clean"),
            ColumnSpec("Ozon Product ID", "oz_product_id", required=True, transform="int_strict"),
            ColumnSpec("SKU", "oz_sku", required=True, transform="int_strict"),
            ColumnSpec("Barcode", "barcode-primary", required=False, transform="string_clean"),
            ColumnSpec("Название товара", "product_name", required=True, transform="string_clean"),
            ColumnSpec("Бренд", "brand", required=False, transform="brand_title"),
            ColumnSpec("Статус товара", "product_status", required=False, transform="string_clean"),
            ColumnSpec("Метки", "tags", required=False, transform="string_clean"),
            ColumnSpec("Отзывы", "reviews_count", required=False, transform="int_relaxed"),
            ColumnSpec("Рейтинг", "rating", required=False, transform="rating"),
            ColumnSpec("Видимость на Ozon", "visibility_status", required=False, transform="string_clean"),
            ColumnSpec("Причины скрытия", "hide_reasons", required=False, transform="string_clean"),
            ColumnSpec(
                "Доступно к продаже по схеме FBO, шт.", "fbo_available", required=False, transform="int_relaxed"
            ),
            ColumnSpec("Зарезервировано, шт", "reserved_qty", required=False, transform="int_relaxed"),
            ColumnSpec(
                "Текущая цена с учетом скидки, ₽", "current_price", required=False, transform="price"
            ),
            ColumnSpec(
                "Цена до скидки (перечеркнутая цена), ₽", "original_price", required=False, transform="price"
            ),
            ColumnSpec("Цена Premium, ₽", "premium_price", required=False, transform="price"),
            ColumnSpec("Рыночная цена, ₽", "market_price", required=False, transform="price"),
            ColumnSpec("Размер НДС, %", "vat_rate", required=False, transform="percent_str"),
        ],
        unique_fields_in_batch=["oz_vendor_code", "oz_product_id", "oz_sku"],
        computed_fields={
            "discount_percent": lambda row: (
                None
                if row.get("original_price") in (None, 0, "") or row.get("current_price") in (None, "")
                else (
                    None
                    if float(row["original_price"]) == 0
                    else max(
                        0.0,
                        min(
                            100.0,
                            (float(row["original_price"]) - float(row["current_price"]))
                            / float(row["original_price"])
                            * 100.0,
                        ),
                    )
                )
            )
        },
    )

    # Ozon Orders spec (based on docs/TZ_oz_orders_import.md)
    ozon_orders = ReportSpec(
        id="ozon_orders",
        name="Ozon — Заказы",
        description=(
            "Импорт отчёта заказов Ozon (.csv). Включает парсинг дат, цен, валют и контроль уникальности отправлений."
        ),
        table="oz_orders",
        allowed_extensions=["csv"],
        default_encoding="utf-8",
        delimiter=";",
        header_row=0,
        columns=[
            ColumnSpec("Номер заказа", "order_number", required=True, transform="string_clean"),
            ColumnSpec("Номер отправления", "shipment_number", required=True, transform="string_clean"),
            ColumnSpec("Принят в обработку", "processing_date", required=False, transform="timestamp"),
            ColumnSpec("Дата отгрузки", "shipment_date", required=False, transform="timestamp"),
            ColumnSpec("Статус", "status", required=False, transform="string_clean"),
            ColumnSpec("Дата доставки", "delivery_date", required=False, transform="timestamp"),
            ColumnSpec(
                "Фактическая дата передачи в доставку",
                "actual_delivery_transfer_date",
                required=False,
                transform="timestamp",
            ),
            ColumnSpec("Сумма отправления", "shipment_amount", required=False, transform="money2"),
            ColumnSpec(
                "Код валюты отправления", "shipment_currency_code", required=False, transform="upper3"
            ),
            ColumnSpec("Наименование товара", "product_name", required=False, transform="string_clean"),
            ColumnSpec("OZON id", "oz_product_id", required=True, transform="int_strict"),
            ColumnSpec("Артикул", "oz_vendor_code", required=False, transform="string_clean"),
            ColumnSpec("Ваша цена", "your_product_cost", required=False, transform="money2"),
            ColumnSpec("Код валюты товара", "product_currency_code", required=False, transform="upper3"),
            ColumnSpec(
                "Стоимость товара для покупателя", "customer_product_cost", required=False, transform="money2"
            ),
            ColumnSpec("Код валюты покупателя", "customer_currency_code", required=False, transform="upper3"),
            ColumnSpec("Количество", "quantity", required=False, transform="int_relaxed"),
            ColumnSpec("Стоимость доставки", "delivery_cost", required=False, transform="money2"),
            ColumnSpec("Связанные отправления", "related_shipments", required=False, transform="string_clean"),
            ColumnSpec("Выкуп товара", "product_buyout", required=False, transform="string_clean"),
            ColumnSpec(
                "Цена товара до скидок", "price_before_discount", required=False, transform="money2"
            ),
            ColumnSpec("Скидка %", "discount_percent", required=False, transform="percent_str"),
            ColumnSpec("Скидка руб", "discount_amount", required=False, transform="money2"),
            ColumnSpec("Акции", "promotions", required=False, transform="string_clean"),
        ],
        unique_fields_in_batch=["shipment_number"],
        computed_fields={},
    )

    # Ozon Products Full (.xlsx multi-file, multi-sheet)
    ozon_products_full = ReportSpec(
        id="ozon_products_full",
        name="Ozon — Товары (полный)",
        description=(
            "Импорт полного шаблона товаров Ozon из нескольких XLSX файлов: "
            "сбор данных с листов 'Шаблон', 'Озон.Видео', 'Озон.Видеообложка'"
        ),
        table="oz_products_full",
        allowed_extensions=["xlsx", "xls"],
        default_encoding="utf-8",
        delimiter=None,
        header_row=1,  # заголовки во 2-й строке (0-based)
        columns=[
            # Base sheet (Шаблон)
            ColumnSpec("Артикул*", "oz_vendor_code", required=True, transform="string_clean"),
            ColumnSpec("Название товара", "product_name", required=False, transform="string_clean"),
            ColumnSpec("Цена, руб.*", "price", required=False, transform="money2"),
            ColumnSpec(
                "Цена до скидки, руб.", "price_before_discount", required=False, transform="money2"
            ),
            ColumnSpec("НДС, %*", "vat_percent", required=False, transform="percent_int"),
            ColumnSpec(
                "Штрихкод (Серийный номер / EAN)", "barcodes", required=False, transform="barcodes_json"
            ),
            ColumnSpec("Вес в упаковке, г*", "weight_grams", required=False, transform="int_relaxed"),
            ColumnSpec("Ширина упаковки, мм*", "package_width_mm", required=False, transform="int_relaxed"),
            ColumnSpec("Высота упаковки, мм*", "package_height_mm", required=False, transform="int_relaxed"),
            ColumnSpec("Длина упаковки, мм*", "package_length_mm", required=False, transform="int_relaxed"),
            ColumnSpec("Ссылка на главное фото*", "main_photo_url", required=False, transform="string_clean"),
            ColumnSpec(
                "Ссылки на дополнительные фото", "additional_photos_urls", required=False, transform="urls_json"
            ),
            ColumnSpec("Артикул фото", "photo_article", required=False, transform="string_clean"),
            ColumnSpec("Бренд в одежде и обуви*", "brand", required=False, transform="brand_title"),
            ColumnSpec("Объединить на одной карточке*", "group_on_card", required=False, transform="string_clean"),
            ColumnSpec("Цвет товара*", "color", required=False, transform="string_clean"),
            ColumnSpec("Российский размер*", "russian_size", required=False, transform="string_clean"),
            ColumnSpec("Название цвета", "color_name", required=False, transform="string_clean"),
            ColumnSpec("Размер производителя", "manufacturer_size", required=False, transform="string_clean"),
            ColumnSpec("Тип*", "product_type", required=False, transform="string_clean"),
            ColumnSpec("Пол*", "gender", required=False, transform="string_clean"),
            ColumnSpec("Сезон", "season", required=False, transform="string_clean"),
            ColumnSpec("Название группы", "group_name", required=False, transform="string_clean"),
            ColumnSpec("Ошибка", "error_message", required=False, transform="string_clean"),
            ColumnSpec("Предупреждение", "warning_message", required=False, transform="string_clean"),

            # Video sheet
            ColumnSpec("Озон.Видео: название", "video_name", required=False, transform="string_clean"),
            ColumnSpec("Озон.Видео: ссылка", "video_url", required=False, transform="string_clean"),
            ColumnSpec("Озон.Видео: товары на видео", "video_products", required=False, transform="string_clean"),

            # Cover sheet
            ColumnSpec(
                "Озон.Видеообложка: ссылка", "video_cover_url", required=False, transform="string_clean"
            ),

            # Assembler appends source_file; import date computed
            ColumnSpec("source_file", "source_file", required=False, transform="string_clean"),
        ],
        unique_fields_in_batch=["oz_vendor_code", "primary_barcode"],
        computed_fields={
            "primary_barcode": _primary_barcode_last,
            "import_date": lambda r: pd.Timestamp.utcnow(),
        },
        multi_file=True,
        assembler="ozon_products_full",
    )

    # WB Products (multi-file, sheet 'Товары')
    wb_products = ReportSpec(
        id="wb_products",
        name="WB — Товары",
        description=(
            "Импорт товаров Wildberries из нескольких XLSX файлов (лист 'Товары')."
        ),
        table="wb_products",
        allowed_extensions=["xlsx", "xls"],
        default_encoding="utf-8",
        delimiter=None,
        header_row=2,
        columns=[
            ColumnSpec("Группа", "group_id", required=False, transform="int_relaxed"),
            ColumnSpec("Артикул продавца", "wb_article", required=True, transform="string_clean"),
            ColumnSpec("Артикул WB", "wb_sku", required=True, transform="int_strict"),
            ColumnSpec("Наименование", "product_name", required=False, transform="string_clean"),
            ColumnSpec("Категория продавца", "seller_category", required=False, transform="string_clean"),
            ColumnSpec("Бренд", "brand", required=False, transform="brand_title"),
            ColumnSpec("Описание", "description", required=False, transform="string_clean"),
            ColumnSpec("Фото", "photos", required=False, transform="urls_json"),
            ColumnSpec("Видео", "video_url", required=False, transform="string_clean"),
            ColumnSpec("Пол", "gender", required=False, transform="string_clean"),
            ColumnSpec("Цвет", "color", required=False, transform="lower_clean"),
            ColumnSpec("Баркод", "barcodes", required=False, transform="barcodes_json"),
            ColumnSpec("Размер", "size", required=False, transform="size_first2"),
            ColumnSpec("Рос. размер", "russian_size", required=False, transform="string_clean"),
            ColumnSpec("Вес с упаковкой", "weight_kg", required=False, transform="decimal3"),
            ColumnSpec("Высота упаковки", "package_height_cm", required=False, transform="decimal2"),
            ColumnSpec("Длина упаковки", "package_length_cm", required=False, transform="decimal2"),
            ColumnSpec("Ширина упаковки", "package_width_cm", required=False, transform="decimal2"),
            ColumnSpec("ТНВЭД", "tnved_code", required=False, transform="string_clean"),
            ColumnSpec("Рейтинг", "card_rating", required=False, transform="rating10"),
            ColumnSpec("Ярлыки", "labels", required=False, transform="string_clean"),
            ColumnSpec("Ставка НДС", "vat_rate", required=False, transform="string_clean"),
            ColumnSpec("source_file", "source_file", required=False, transform="string_clean"),
        ],
        unique_fields_in_batch=["wb_sku", "size", "primary_barcode"],
        computed_fields={
            "primary_barcode": _primary_barcode_last,
            "package_volume_cm3": lambda r: (
                None
                if r.get("package_height_cm") in (None, "")
                or r.get("package_length_cm") in (None, "")
                or r.get("package_width_cm") in (None, "")
                else float(r["package_height_cm"]) * float(r["package_length_cm"]) * float(r["package_width_cm"])  # noqa: E501
            ),
        },
        multi_file=True,
        assembler="wb_products",
    )

    # WB Prices (single file, sheet 'Отчет - цены и скидки на товары')
    wb_prices = ReportSpec(
        id="wb_prices",
        name="WB — Цены",
        description=(
            "Импорт цен и скидок Wildberries из XLSX (лист 'Отчет - цены и скидки на товары')."
        ),
        table="wb_prices",
        allowed_extensions=["xlsx", "xls"],
        default_encoding="utf-8",
        delimiter=None,
        header_row=0,
        columns=[
            ColumnSpec("Бренд", "brand", required=False, transform="brand_title"),
            ColumnSpec("Категория", "category", required=False, transform="title_clean"),
            ColumnSpec("Артикул WB", "wb_sku", required=True, transform="string_clean"),
            ColumnSpec("Артикул продавца", "wb_vendor_code", required=False, transform="string_clean"),
            ColumnSpec("Последний баркод", "barcode_primary", required=False, transform="digits_only"),
            ColumnSpec("Остатки WB", "wb_stock", required=False, transform="int_relaxed"),
            ColumnSpec("Текущая цена", "current_price", required=False, transform="price"),
            ColumnSpec("Текущая скидка", "current_discount", required=False, transform="percent_str"),
        ],
        unique_fields_in_batch=["wb_sku"],
        computed_fields={
            # Если остаток пустой в отчёте, сохраняем 0
            "wb_stock": lambda r: (0 if r.get("wb_stock") in (None, "") else r.get("wb_stock")),
        },
        multi_file=False,
        assembler="wb_prices",
    )

    # Punta barcodes (single file, sheet 'Sheet')
    punta_barcodes = ReportSpec(
        id="punta_barcodes",
        name="Punta — Штрихкоды",
        description=(
            "Импорт Excel с данными по штрихкодам Punta. Перед загрузкой пользователь "
            "должен указать значение 'Коллекция'; перед вставкой все записи этой коллекции "
            "в таблице будут удалены."
        ),
        table="punta_barcodes",
        allowed_extensions=["xlsx", "xls"],
        default_encoding="utf-8",
        delimiter=None,
        header_row=0,  # заголовки в первой строке
        columns=[
            # 'Коллекция' подставляется из интерфейса, но допускаем наличие колонки в файле
            ColumnSpec("Коллекция", "collection", required=True, transform="string_clean"),
            ColumnSpec("Артикул", "pn_article", required=True, transform="string_clean"),
            ColumnSpec("Вид товара", "product_type", required=False, transform="string_clean"),
            ColumnSpec("Внешний код", "external_code", required=True, transform="code_text"),
            ColumnSpec("Размер", "size", required=False, transform="string_clean"),
            ColumnSpec("Штрихкод", "barcode", required=False, transform="digits_only"),
            ColumnSpec("ТН ВЭД", "tn_ved", required=False, transform="code_text"),
        ],
        unique_fields_in_batch=["pn_article", "size", "external_code", "barcode"],
        computed_fields={},
        multi_file=False,
        assembler=None,
    )

    # Punta products (single file)
    punta_products = ReportSpec(
        id="punta_products",
        name="Punta — Товары",
        description=(
            "Импорт Excel с данными по товарам Punta. Перед загрузкой пользователь "
            "должен указать значение 'Коллекция'; перед вставкой все записи этой коллекции "
            "в таблице будут удалены."
        ),
        table="punta_products",
        allowed_extensions=["xlsx", "xls"],
        default_encoding="utf-8",
        delimiter=None,
        header_row=0,
        columns=[
            ColumnSpec("Коллекция", "collection", required=True, transform="string_clean"),
            ColumnSpec("Уникальный идентификатор", "un-id", required=True, transform="code_text"),
            ColumnSpec("Статус обработки", "status", required=False, transform="string_clean"),
            ColumnSpec("Оптовый покупатель", "buyer", required=False, transform="string_clean"),
            ColumnSpec("Артикул", "pn_article", required=False, transform="string_clean"),
            ColumnSpec("Группировочный код", "group_code", required=False, transform="code_text"),
            ColumnSpec("Код оригинальной модели", "original_code", required=False, transform="code_text"),
            ColumnSpec("Внешний код", "external_code_list", required=False, transform="paragraphs_json"),
            ColumnSpec("Себестоимость (п), USD", "cost_usd", required=False, transform="decimal2"),
            # New mappings requested
            ColumnSpec("Вид товара", "product_type", required=False, transform="string_clean"),
            ColumnSpec("Пол (факт)", "gender_actual", required=False, transform="string_clean"),
            ColumnSpec("Конструкция верха", "upper_construction_1", required=False, transform="string_clean"),
            ColumnSpec("Конструкция верха 2", "upper_construction_2", required=False, transform="string_clean"),
            ColumnSpec("Поставка", "shipment_batch", required=False, transform="string_clean"),
            ColumnSpec("Поставка BEST", "shipment_best", required=False, transform="string_clean"),
            ColumnSpec("Материал верха", "upper_material", required=False, transform="string_clean"),
            ColumnSpec("Материал подкладки", "lining_material", required=False, transform="string_clean"),
            ColumnSpec("Материал подошвы", "outsole_material", required=False, transform="string_clean"),
            ColumnSpec("Материал стельки", "insole_material", required=False, transform="string_clean"),
            ColumnSpec("Сезон", "season", required=False, transform="string_clean"),
            ColumnSpec("Каблук", "heel_presence", required=False, transform="string_clean"),
            ColumnSpec("Каблук (тип)", "heel_type_general", required=False, transform="string_clean"),
            ColumnSpec("Торговая марка", "brand", required=False, transform="brand_title"),
            ColumnSpec("Размерная шкала", "size_scale", required=False, transform="string_clean"),
            ColumnSpec("Ростовка", "size_run", required=False, transform="string_clean"),
            ColumnSpec("Кол-во (п)", "quantity_pairs", required=False, transform="int_relaxed"),
            ColumnSpec("Цвет (основной)", "color_primary", required=False, transform="string_clean"),
            ColumnSpec("Новая колодка", "last_new", required=False, transform="string_clean"),
            ColumnSpec("Колодка MEGA", "last_mega", required=False, transform="string_clean"),
            ColumnSpec("Колодка BEST", "last_best", required=False, transform="string_clean"),
            ColumnSpec("№ заказа", "order_number", required=False, transform="string_clean"),
            ColumnSpec("Статус заказа", "order_status", required=False, transform="string_clean"),
            ColumnSpec("Статус приемки", "acceptance_status", required=False, transform="string_clean"),
            ColumnSpec("Статус отгрузки", "shipment_status", required=False, transform="string_clean"),
            ColumnSpec("№ инвойса", "invoice_number", required=False, transform="string_clean"),
            ColumnSpec("№ контейнера", "container_number", required=False, transform="string_clean"),
            ColumnSpec("Вид застежки", "fastening_type", required=False, transform="string_clean"),
            ColumnSpec("Вид каблука", "heel_type", required=False, transform="string_clean"),
            ColumnSpec("WB: Высота подошвы, см", "wb_platform_height_cm", required=False, transform="decimal2"),
            ColumnSpec("WB: Высота каблука, см", "wb_heel_height_cm", required=False, transform="decimal2"),
            ColumnSpec("WB: Высота голенища, см", "wb_shaft_height_cm", required=False, transform="decimal2"),
            ColumnSpec("СМ:ХТС", "sm_khts_code", required=False, transform="string_clean"),
            ColumnSpec("Прошивка подошвы", "outsole_stitching", required=False, transform="string_clean"),
            ColumnSpec("Ярлык", "label_tag", required=False, transform="string_clean"),
            ColumnSpec("Фишки", "features", required=False, transform="string_clean"),
            ColumnSpec("Комментарии MP-TRADE", "comments_mp_trade", required=False, transform="string_clean"),
            ColumnSpec("Высота каблука (пяточная часть), мм", "heel_height_mm", required=False, transform="int_relaxed"),
            ColumnSpec("Высота подошвы (пучки), мм", "forefoot_platform_height_mm", required=False, transform="int_relaxed"),
            ColumnSpec("Метод крепления подошвы", "outsole_attachment_method", required=False, transform="string_clean"),
            ColumnSpec("Ширина, мм (КО)", "width_mm_ko", required=False, transform="int_relaxed"),
            ColumnSpec("Высота, мм (КО)", "height_mm_ko", required=False, transform="int_relaxed"),
        ],
        unique_fields_in_batch=["un-id"],
        computed_fields={},
        multi_file=False,
        assembler=None,
    )

    # Punta Google (dynamic schema from Google Sheets CSV)
    punta_google = ReportSpec(
        id="punta_google",
        name="Punta — Google",
        description=(
            "Загрузка из Google Sheets по ссылке (без API). 1-я строка — заголовки, "
            "2-я строка пропускается, с 3-й строки — данные. Схема таблицы динамически "
            "соответствует заголовкам. Все поля — текст."
        ),
        table="punta_google",
        allowed_extensions=[],  # uploader не используется
        default_encoding="utf-8",
        delimiter=None,
        header_row=0,
        columns=[],
        unique_fields_in_batch=[],
        computed_fields={},
        multi_file=False,
        assembler=None,
    )

    return {
        ozon_products.id: ozon_products,
        ozon_orders.id: ozon_orders,
        ozon_products_full.id: ozon_products_full,
        wb_products.id: wb_products,
        wb_prices.id: wb_prices,
        punta_barcodes.id: punta_barcodes,
        punta_products.id: punta_products,
        punta_google.id: punta_google,
    }
