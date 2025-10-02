from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st
from dataforge.matching import search_matches
from dataforge.matching_helpers import add_merge_fields
from dataforge.similarity_matching import search_similar_matches  # новый прямой импорт
from dataforge.ui import setup_page

setup_page(title="DataForge — Склейка OZ", icon="🧩")

DEFECT_PREFIX = "БракSH"


@dataclass
class MergeConfig:
    md_token: str | None = None
    md_database: str | None = None
    filter_no_defect: bool = True
    filter_unique_sizes: bool = True
    limit_per_input: int = 0
    selected_cols: list[str] = field(default_factory=lambda: [
        "group_number",
        "wb_sku",
        "oz_sku",
        "oz_vendor_code",
        "merge_code",
        "merge_color",
        "similarity_score",
    ])


def parse_input(text: str) -> list[str]:
    tokens = [t.strip() for t in text.replace(",", " ").split()]
    return [t for t in tokens if t]


st.title("🧩 Склейка карточек OZ")
st.caption("Связываем карточки OZ между собой по выбранному алгоритму (базовый: общий wb_sku).")


md_token = st.session_state.get("md_token") or st.secrets.get("md_token") if hasattr(st, "secrets") else None
md_database = st.session_state.get("md_database") or st.secrets.get("md_database") if hasattr(st, "secrets") else None

if not md_token:
    st.warning("MD токен не найден. Укажите его на странице Настройки.")


with st.form(key="oz_merge_form"):
    col1, col2 = st.columns([1, 1])
    with col1:
        merge_algo = st.selectbox(
            "Алгоритм объединения",
            options=[
                ("Объединить по общему WB артикулу", "wb_by_sku"),
                ("Объединить по похожим WB товарам", "wb_similarity"),
            ],
            format_func=lambda x: x[0] if isinstance(x, tuple) else x,
            key="oz_merge_algo",
        )

    with col2:
        st.number_input(
            "Лимит кандидатов (0 — без лимита)",
            min_value=0,
            max_value=10000,
            value=int(st.session_state.get("oz_merge_limit", 20)),
            key="oz_merge_limit",
        )

    # Дополнительные настройки для similarity
    with st.expander("Параметры алгоритма похожести (wb_similarity)"):
        st.number_input(
            "min_score_threshold",
            min_value=0.0,
            max_value=1000.0,
            value=float(st.session_state.get("oz_merge_min_score", 300.0)),
            key="oz_merge_min_score",
            help="Порог отсечения кандидатов по итоговому скору",
        )
        st.number_input(
            "max_candidates_per_seed",
            min_value=1,
            max_value=100,
            value=int(st.session_state.get("oz_merge_max_rec", 30)),
            key="oz_merge_max_rec",
            help="Максимум кандидатов на исходный WB SKU",
        )
        st.number_input(
            "max_group_size",
            min_value=0,
            max_value=500,
            value=int(st.session_state.get("oz_merge_max_group_size", 10)),
            key="oz_merge_max_group_size",
            help="Максимальный размер группы (0 = без ограничения). Большие компоненты будут разбиты на подгруппы.",
        )

    st.text_area(
        "Список WB SKU",
        value=st.session_state.get("oz_merge_input_text", ""),
        height=140,
        help="Вставьте список wb_sku через пробел или новую строку.",
        key="oz_merge_input_text",
    )

    st.checkbox("Без брака Озон", key="oz_merge_filter_no_defect", value=True, help="Исключить oz_vendor_code начинающиеся на БракSH")
    st.checkbox("Без дублей размеров", key="oz_merge_filter_unique_sizes", value=True, help="Оставлять по одному значению размера с наивысшим match_score")
    st.caption("⚠️ После изменения настроек нажмите 'Склеить' снова для применения изменений")
    st.write("---")
    st.markdown("**Параметры пакетной обработки (chunking)**")
    # calibrated defaults from autotune
    st.number_input("Размер батча (batch_size)", min_value=1, max_value=5000, value=int(st.session_state.get("oz_merge_batch_size", 1000)), key="oz_merge_batch_size")
    st.write(f"Лимит кандидатов на вход (limit_per_input): {int(st.session_state.get('oz_merge_limit', 20))}")
    st.info("Batch processing будет выполнять поиск партиями и обновлять результаты по мере получения данных.")

    submitted = st.form_submit_button("Склеить", type="primary")

if submitted:
    if not md_token:
        st.error("MD токен отсутствует. Укажите его на странице Настройки.")
        st.stop()

    text_value = st.session_state.get("oz_merge_input_text", "")
    values = parse_input(text_value)
    if not values:
        st.warning("Введите хотя бы один WB SKU.")
        st.stop()

    if len(values) > 500:
        st.info("Передано много значений; операция может занять время.")

    try:
        if merge_algo[1] == "wb_similarity":
            from dataforge.similarity_config import SimilarityScoringConfig
            max_group_size_val = int(st.session_state.get("oz_merge_max_group_size", 15))
            cfg = SimilarityScoringConfig(
                min_score_threshold=float(st.session_state.get("oz_merge_min_score", 50.0)),
                max_candidates_per_seed=int(st.session_state.get("oz_merge_max_rec", 10)),
                max_group_size=max_group_size_val if max_group_size_val > 0 else None,
            )
            
            # Batch processing with progress
            batch_size = int(st.session_state.get("oz_merge_batch_size", 1000))
            total = len(values)
            n_chunks = math.ceil(total / batch_size)
            
            st.session_state["oz_merge_result"] = pd.DataFrame()
            progress = st.progress(0)
            fetched = 0
            
            for idx in range(n_chunks):
                start = idx * batch_size
                end = min(start + batch_size, total)
                chunk = values[start:end]
                with st.spinner(f"Запрос партии {idx+1}/{n_chunks} ({start+1}-{end})..."):
                    df_chunk = search_similar_matches(
                        chunk,
                        config=cfg,
                        md_token=md_token,
                        md_database=md_database,
                    )
                
                if df_chunk is None or df_chunk.empty:
                    df_chunk = pd.DataFrame()
                
                # Apply defect filter per-chunk to reduce memory
                if st.session_state.get("oz_merge_filter_no_defect", True) and "oz_vendor_code" in df_chunk.columns:
                    starts_with_brak = df_chunk["oz_vendor_code"].fillna("").astype(str).str.startswith(DEFECT_PREFIX)
                    df_chunk = df_chunk.loc[~starts_with_brak]
                
                # Accumulate safely
                df_result = st.session_state.get("oz_merge_result")
                if df_result is None or (hasattr(df_result, "empty") and df_result.empty):
                    st.session_state["oz_merge_result"] = df_chunk.copy()
                else:
                    st.session_state["oz_merge_result"] = pd.concat([df_result, df_chunk], ignore_index=True, copy=False)
                
                fetched += len(chunk)
                # Update progress
                progress.progress(int((end / total) * 100))
            
            # Handle duplicate sizes
            df_similarity = st.session_state["oz_merge_result"]
            
            if st.session_state.get("oz_merge_filter_unique_sizes", True):
                # Remove duplicates completely - filter by wb_sku + size (not group_number)
                if not df_similarity.empty and 'oz_manufacturer_size' in df_similarity.columns and 'wb_sku' in df_similarity.columns:
                    mask_known_size = df_similarity['oz_manufacturer_size'].notna() & (df_similarity['oz_manufacturer_size'].astype(str).str.strip() != "")
                    df_known = df_similarity.loc[mask_known_size].copy()
                    df_unknown = df_similarity.loc[~mask_known_size].copy()
                    
                    if not df_known.empty:
                        df_known = df_known.sort_values(['match_score'], ascending=[False])
                        # Dedupe by wb_sku + size (not group_number + size)
                        df_known = df_known.drop_duplicates(subset=['wb_sku', 'oz_manufacturer_size'], keep='first')
                        df_similarity = pd.concat([df_known, df_unknown], axis=0, ignore_index=True)
                    
                    st.session_state["oz_merge_result"] = df_similarity
            # Note: If filter_unique_sizes is False, duplicates are already handled by add_merge_fields_for_similarity
            
            # Check for missing wb_sku
            df_similarity = st.session_state["oz_merge_result"]
            found_wb = {str(x) for x in df_similarity.get("wb_sku", [])} if not df_similarity.empty else set()
            missing = [v for v in values if v not in found_wb]
            st.session_state["oz_merge_missing_wb"] = missing
            
            # Fallback: запускаем базовый алгоритм для не найденных товаров
            if missing:
                st.info(f"📋 Не найдены похожие товары для {len(missing)} wb_sku. Запускаем базовый алгоритм для создания одиночных групп...")
                try:
                    with st.spinner(f"Обработка {len(missing)} товаров базовым алгоритмом..."):
                        df_fallback = search_matches(
                            missing,
                            input_type="wb_sku",
                            limit_per_input=None,
                            md_token=md_token,
                            md_database=md_database,
                        )
                        
                        if not df_fallback.empty:
                            # Apply defect filter
                            if st.session_state.get("oz_merge_filter_no_defect", True) and "oz_vendor_code" in df_fallback.columns:
                                starts_with_brak = df_fallback["oz_vendor_code"].fillna("").astype(str).str.startswith(DEFECT_PREFIX)
                                df_fallback = df_fallback.loc[~starts_with_brak]
                            
                            # Add merge fields first (before any deduplication)
                            if not df_fallback.empty and "oz_vendor_code" in df_fallback.columns:
                                df_fallback = add_merge_fields(df_fallback, wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")
                            
                            # Handle duplicates based on filter setting
                            if st.session_state.get("oz_merge_filter_unique_sizes", True) and not df_fallback.empty:
                                # Remove duplicates completely
                                from dataforge.matching_helpers import dedupe_sizes
                                df_fallback = dedupe_sizes(df_fallback, input_type="wb_sku")
                            elif not df_fallback.empty:
                                # Keep duplicates but mark them with 'D' prefix
                                from dataforge.matching_helpers import mark_duplicate_sizes
                                df_fallback = mark_duplicate_sizes(
                                    df_fallback,
                                    primary_prefix="B",
                                    duplicate_prefix="D",
                                    grouping_column="wb_sku"
                                )
                            
                            if not df_fallback.empty and "group_number" in df_fallback.columns:
                                if "group_number" in df_similarity.columns and not df_similarity.empty:
                                    max_existing = df_similarity["group_number"].max()
                                    max_existing_group = int(max_existing) if pd.notna(max_existing) else 0
                                else:
                                    max_existing_group = 0
                                df_fallback["group_number"] = df_fallback["group_number"] + max_existing_group
                            
                            # Add similarity_score column (0 for fallback items)
                            if "similarity_score" not in df_fallback.columns:
                                df_fallback["similarity_score"] = 0.0
                            
                            # Merge with main results
                            st.session_state["oz_merge_result"] = pd.concat([df_similarity, df_fallback], ignore_index=True)
                            st.success(f"✅ Добавлено {len(df_fallback)} строк из базового алгоритма")
                            
                            # Note: No need for final dedupe/mark after merging for similarity algorithm
                            # Both similarity and fallback items already have proper duplicate marking
                except Exception as e:
                    st.error(f"❌ Ошибка при выполнении fallback алгоритма: {e}")
                    # Продолжаем с результатами similarity, не прерывая работу
                
                # Update missing list after fallback
                df_final = st.session_state["oz_merge_result"]
                found_wb_final = {str(x) for x in df_final.get("wb_sku", [])} if not df_final.empty else set()
                missing_final = [v for v in values if v not in found_wb_final]
                st.session_state["oz_merge_missing_wb"] = missing_final
                
                if missing_final:
                    st.warning(f"⚠️ Не найдены в wb_products даже после базового алгоритма: {', '.join(missing_final[:50])}{' ...' if len(missing_final)>50 else ''}")
        else:
            # Batch processing with progress
            batch_size = int(st.session_state.get("oz_merge_batch_size", 1000))
            limit_per_input = int(st.session_state.get("oz_merge_limit", 20))
            total = len(values)
            n_chunks = math.ceil(total / batch_size)

            st.session_state["oz_merge_result"] = pd.DataFrame()
            progress = st.progress(0)
            fetched = 0

            for idx in range(n_chunks):
                start = idx * batch_size
                end = min(start + batch_size, total)
                chunk = values[start:end]
                with st.spinner(f"Запрос партии {idx+1}/{n_chunks} ({start+1}-{end})..."):
                    df_chunk = search_matches(
                        chunk,
                        input_type="wb_sku",
                        limit_per_input=(None if limit_per_input <= 0 else limit_per_input),
                        md_token=md_token,
                        md_database=md_database,
                    )

                if df_chunk is None or df_chunk.empty:
                    df_chunk = pd.DataFrame()

                # Apply defect filter per-chunk to reduce memory
                if st.session_state.get("oz_merge_filter_no_defect", True) and "oz_vendor_code" in df_chunk.columns:
                    starts_with_brak = df_chunk["oz_vendor_code"].fillna("").astype(str).str.startswith(DEFECT_PREFIX)
                    df_chunk = df_chunk.loc[~starts_with_brak]

                # Add merge fields to the chunk
                if not df_chunk.empty and "oz_vendor_code" in df_chunk.columns:
                    df_chunk = add_merge_fields(df_chunk, wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")

                # accumulate safely
                df_result = st.session_state.get("oz_merge_result")
                if df_result is None or (hasattr(df_result, "empty") and df_result.empty):
                    st.session_state["oz_merge_result"] = df_chunk.copy()
                else:
                    st.session_state["oz_merge_result"] = pd.concat([df_result, df_chunk], ignore_index=True, copy=False)

                fetched += len(chunk)
                # Update progress
                progress.progress(int((end / total) * 100))

                        # Final dedupe sizes similar to existing page
            filter_unique = st.session_state.get("oz_merge_filter_unique_sizes", True)
            
            if filter_unique and not st.session_state["oz_merge_result"].empty:
                from dataforge.matching_helpers import dedupe_sizes

                st.session_state["oz_merge_result"] = dedupe_sizes(st.session_state["oz_merge_result"], input_type="wb_sku")
                
                # Ensure merge fields present after dedupe
                if not st.session_state["oz_merge_result"].empty:
                    st.session_state["oz_merge_result"] = add_merge_fields(st.session_state["oz_merge_result"], wb_sku_col="wb_sku", oz_vendor_col="oz_vendor_code")
            elif not st.session_state["oz_merge_result"].empty:
                # Keep duplicates but mark them with 'D' prefix (primary uses 'B' for basic algorithm)
                from dataforge.matching_helpers import mark_duplicate_sizes
                
                df_result = st.session_state["oz_merge_result"]
                
                # IMPORTANT: Recalculate group_number based on merge_code after merging all chunks
                # because each chunk had its own group numbering
                unique_merge_codes = sorted(df_result["merge_code"].unique())
                merge_code_to_group = {code: idx + 1 for idx, code in enumerate(unique_merge_codes)}
                df_result["group_number"] = df_result["merge_code"].map(merge_code_to_group)
                
                # For basic algorithm, use wb_sku as grouping column to find duplicates within same wb_sku
                df_result = mark_duplicate_sizes(
                    df_result,
                    primary_prefix="B",
                    duplicate_prefix="D",
                    grouping_column="wb_sku"  # Group by wb_sku instead of group_number
                )
                
                st.session_state["oz_merge_result"] = df_result
                st.session_state["oz_merge_result"] = df_result
                # Note: merge_code is already set by mark_duplicate_sizes, don't call add_merge_fields

            # collect invalid oz_vendor_code rows for highlighting
            df = st.session_state["oz_merge_result"]
            if "oz_vendor_code" in df.columns:
                invalid_mask = ~df["oz_vendor_code"].astype(str).str.contains("-", regex=False)
                st.session_state["oz_merge_invalid_oz_vendor"] = df.loc[invalid_mask]
            else:
                st.session_state["oz_merge_invalid_oz_vendor"] = pd.DataFrame()
    except Exception as exc:
        st.error("Ошибка при поиске/обработке: ")
        st.exception(exc)

df_show: pd.DataFrame = st.session_state.get("oz_merge_result", pd.DataFrame())

if df_show.empty:
    st.info("Результаты будут показаны здесь после нажатия 'Склеить'.")
    st.stop()

cols_default = [
    "group_number",
    "wb_sku",
    "oz_sku",
    "oz_vendor_code",
    "merge_code",
    "merge_color",
    "match_score",
    "similarity_score",
]

cols_to_show = [c for c in st.session_state.get("oz_merge_selected_cols", cols_default) if c in df_show.columns]
if not cols_to_show:
    cols_to_show = [c for c in cols_default if c in df_show.columns]

st.subheader("Результаты склейки OZ")
st.dataframe(df_show[cols_to_show], width="stretch", height=600)

csv_buf = io.StringIO()
df_show[cols_to_show].to_csv(csv_buf, index=False)
st.download_button(
    "Скачать CSV",
    data=csv_buf.getvalue().encode("utf-8"),
    file_name="oz_merge.csv",
    mime="text/csv",
)
