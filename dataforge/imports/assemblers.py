from __future__ import annotations

from io import BytesIO
from typing import Any, Iterable, List

import pandas as pd


def _clean_df(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    if key_col in df.columns:
        df = df[df[key_col].notna()]
        # Drop rows where key is empty after strip
        df = df[df[key_col].astype(str).str.strip() != ""]
    # Strip surrounding spaces in headers
    df.columns = [str(c).strip() for c in df.columns]
    return df


def assemble_ozon_products_full(files: Iterable[Any]) -> pd.DataFrame:
    """Assemble data across multiple XLSX files and sheets into one DataFrame.

    Sheets:
    - "Шаблон" (base)
    - "Озон.Видео"
    - "Озон.Видеообложка"

    Join key: "Артикул*"
    """
    base_parts: List[pd.DataFrame] = []
    video_parts: List[pd.DataFrame] = []
    cover_parts: List[pd.DataFrame] = []

    base_cols_keep = [
        "Артикул*",
        "Название товара",
        "Цена, руб.*",
        "Цена до скидки, руб.",
        "НДС, %*",
        "Штрихкод (Серийный номер / EAN)",
        "Вес в упаковке, г*",
        "Ширина упаковки, мм*",
        "Высота упаковки, мм*",
        "Длина упаковки, мм*",
        "Ссылка на главное фото*",
        "Ссылки на дополнительные фото",
        "Артикул фото",
        "Бренд в одежде и обуви*",
        "Объединить на одной карточке*",
        "Цвет товара*",
        "Российский размер*",
        "Название цвета",
        "Размер производителя",
        "Тип*",
        "Пол*",
        "Сезон",
        "Название группы",
        "Ошибка",
        "Предупреждение",
    ]

    video_cols_keep = [
        "Артикул*",
        "Озон.Видео: название",
        "Озон.Видео: ссылка",
        "Озон.Видео: товары на видео",
    ]

    cover_cols_keep = [
        "Артикул*",
        "Озон.Видеообложка: ссылка",
    ]

    for f in files:
        # Streamlit UploadedFile supports getvalue(); use BytesIO to allow multiple reads
        raw = f.getvalue() if hasattr(f, "getvalue") else f.read()
        bio = BytesIO(raw)

        try:
            base = pd.read_excel(bio, sheet_name="Шаблон", header=1, engine="openpyxl")
        except Exception as e1:
            # Retry with default sheet (some files may vary)
            try:
                bio.seek(0)
                base = pd.read_excel(bio, header=1, engine="openpyxl")
            except Exception as e2:
                name = getattr(f, "name", "")
                if str(name).lower().endswith(".xls"):
                    raise ValueError(
                        f"Файл {name} в формате .xls не поддерживается. Сохраните его как .xlsx."
                    ) from e2
                raise
        base = _clean_df(base, "Артикул*")
        base = base[[c for c in base_cols_keep if c in base.columns]]
        base["source_file"] = getattr(f, "name", "")
        base_parts.append(base)

        bio.seek(0)
        try:
            video = pd.read_excel(bio, sheet_name="Озон.Видео", header=1, engine="openpyxl")
            video = _clean_df(video, "Артикул*")
            video = video[[c for c in video_cols_keep if c in video.columns]]
            video_parts.append(video)
        except Exception:
            pass

        bio.seek(0)
        try:
            cover = pd.read_excel(
                bio, sheet_name="Озон.Видеообложка", header=1, engine="openpyxl"
            )
            cover = _clean_df(cover, "Артикул*")
            cover = cover[[c for c in cover_cols_keep if c in cover.columns]]
            cover_parts.append(cover)
        except Exception:
            pass

    base_df = pd.concat(base_parts, ignore_index=True) if base_parts else pd.DataFrame()
    video_df = pd.concat(video_parts, ignore_index=True) if video_parts else pd.DataFrame()
    cover_df = pd.concat(cover_parts, ignore_index=True) if cover_parts else pd.DataFrame()

    if not base_df.empty and not video_df.empty:
        base_df = base_df.merge(video_df, on="Артикул*", how="left")
    if not base_df.empty and not cover_df.empty:
        base_df = base_df.merge(cover_df, on="Артикул*", how="left")

    return base_df


def assemble_wb_products(files: Iterable[Any]) -> pd.DataFrame:
    """Assemble WB products from multiple Excel files, sheet 'Товары'.

    - Headers at row 3 (header=2)
    - Data starts at row 5; rows with empty 'Артикул продавца' dropped
    - Add source_file column
    """
    parts: List[pd.DataFrame] = []
    keep_cols = [
        "Группа",
        "Артикул продавца",
        "Артикул WB",
        "Наименование",
        "Категория продавца",
        "Бренд",
        "Описание",
        "Фото",
        "Видео",
        "Пол",
        "Цвет",
        "Баркод",
        "Размер",
        "Рос. размер",
        "Вес с упаковкой",
        "Высота упаковки",
        "Длина упаковки",
        "Ширина упаковки",
        "ТНВЭД",
        "Рейтинг",
        "Ярлыки",
        "Ставка НДС",
    ]

    for f in files:
        raw = f.getvalue() if hasattr(f, "getvalue") else f.read()
        bio = BytesIO(raw)
        try:
            df = pd.read_excel(bio, sheet_name="Товары", header=2, engine="openpyxl")
        except Exception:
            name = getattr(f, "name", "")
            if str(name).lower().endswith(".xls"):
                raise ValueError(
                    f"Файл {name} в формате .xls не поддерживается. Сохраните его как .xlsx."
                )
            raise
        # cleanup
        df.columns = [str(c).strip() for c in df.columns]
        if "Артикул продавца" in df.columns:
            df = df[df["Артикул продавца"].notna()]
            df = df[df["Артикул продавца"].astype(str).str.strip() != ""]
        df = df[[c for c in keep_cols if c in df.columns]]
        df["source_file"] = getattr(f, "name", "")
        parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def assemble_wb_prices(files: Iterable[Any]) -> pd.DataFrame:
    """Read WB prices from 'Отчет - цены и скидки на товары' (first row headers)."""
    parts: List[pd.DataFrame] = []
    for f in files:
        raw = f.getvalue() if hasattr(f, "getvalue") else f.read()
        bio = BytesIO(raw)
        try:
            df = pd.read_excel(bio, sheet_name="Отчет - цены и скидки на товары", header=0, engine="openpyxl")
        except Exception:
            name = getattr(f, "name", "")
            if str(name).lower().endswith(".xls"):
                raise ValueError(
                    f"Файл {name} в формате .xls не поддерживается. Сохраните его как .xlsx."
                )
            raise
        df.columns = [str(c).strip() for c in df.columns]
        parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
