from __future__ import annotations

import logging
from collections.abc import Iterable

import duckdb
import pandas as pd
from dataforge.matching import _ensure_connection, _matches_for_wb_skus, _table_exists  # type: ignore
from dataforge.similarity_config import SimilarityScoringConfig

logger = logging.getLogger(__name__)


def _split_large_component(
    component: set[int],
    pairs_df: pd.DataFrame,
    max_size: int,
) -> list[set[int]]:
    """Разбивает большой компонент на подгруппы с учетом скоринга.
    
    Использует жадный алгоритм:
    1. Берем элемент с максимальным суммарным скором связей
    2. Добавляем к нему наиболее связанные элементы до достижения max_size
    3. Повторяем для оставшихся элементов
    
    Args:
        component: Множество wb_sku для разбиения
        pairs_df: DataFrame с парами (seed_wb_sku, cand_wb_sku, final_score)
        max_size: Максимальный размер подгруппы
        
    Returns:
        Список подгрупп (множеств wb_sku)
    """
    if len(component) <= max_size:
        return [component]
    
    # Edge case: пустой компонент
    if not component:
        return []
    
    # Строим граф связей с весами (скорами)
    edges: dict[tuple[int, int], float] = {}
    for _, row in pairs_df.iterrows():
        a, b = int(row.seed_wb_sku), int(row.cand_wb_sku)
        if a in component and b in component:
            key = (min(a, b), max(a, b))
            edges[key] = max(edges.get(key, 0.0), float(row.final_score))
    
    # Считаем суммарный скор для каждого узла
    node_scores: dict[int, float] = dict.fromkeys(component, 0.0)
    for (a, b), score in edges.items():
        node_scores[a] += score
        node_scores[b] += score
    
    remaining = component.copy()
    subgroups: list[set[int]] = []
    
    while remaining:
        # Начинаем новую группу с узла с максимальным скором
        seed = max(remaining, key=lambda n: node_scores.get(n, 0.0))
        current_group = {seed}
        remaining.remove(seed)
        
        # Кэшируем связи текущей группы для оптимизации
        group_connections: dict[int, float] = {}
        for node in remaining:
            key = (min(seed, node), max(seed, node))
            group_connections[node] = edges.get(key, 0.0)
        
        # Добавляем наиболее связанные элементы
        while len(current_group) < max_size and remaining:
            # Находим узел с максимальной связью с текущей группой
            best_candidate = None
            best_score = -1.0
            
            for candidate in remaining:
                score_sum = group_connections.get(candidate, 0.0)
                
                if score_sum > best_score:
                    best_score = score_sum
                    best_candidate = candidate
            
            if best_candidate is None or best_score <= 0:
                # Нет больше связанных узлов, начинаем новую группу
                break
            
            current_group.add(best_candidate)
            remaining.remove(best_candidate)
            
            # Обновляем кэш для оставшихся узлов
            for node in remaining:
                key = (min(best_candidate, node), max(best_candidate, node))
                group_connections[node] = group_connections.get(node, 0.0) + edges.get(key, 0.0)
        
        subgroups.append(current_group)
    
    return subgroups


def search_similar_matches(
    wb_skus: Iterable[str | int],
    *,
    config: SimilarityScoringConfig | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Algorithm wb_similarity (see design notes).

    Returns DataFrame with columns: wb_sku, oz_sku, oz_vendor_code, oz_manufacturer_size, merge_code, merge_color, match_score.
    """
    cfg = config or SimilarityScoringConfig()
    cfg.validate()

    wb_list: list[str] = [str(s).strip() for s in wb_skus if str(s).strip()]
    if not wb_list:
        return pd.DataFrame()

    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)

    df_in = pd.DataFrame({"seed_wb_sku": wb_list})
    local_con.register("seed_input", df_in)

    if not _table_exists(local_con, "wb_products"):
        raise ValueError("wb_products missing for wb_similarity")

    punta_exists = _table_exists(local_con, "punta_google")

    pg_cols = "" if not punta_exists else """
        , pg_seed.season AS seed_season, pg_cand.season AS cand_season
        , pg_seed.color AS seed_color, pg_cand.color AS cand_color
        , pg_seed.lacing_type AS seed_fastener, pg_cand.lacing_type AS cand_fastener
        , pg_seed.material_short AS seed_material, pg_cand.material_short AS cand_material
        , pg_seed.mega_last AS seed_mega_last, pg_cand.mega_last AS cand_mega_last
        , pg_seed.best_last AS seed_best_last, pg_cand.best_last AS cand_best_last
        , pg_seed.new_last AS seed_new_last, pg_cand.new_last AS cand_new_last
        , pg_seed.model_name AS seed_model_name, pg_cand.model_name AS cand_model_name
    """

    scoring_columns = "" if not punta_exists else f"""
        , CASE
            WHEN seed_season IS NOT NULL AND cand_season IS NOT NULL THEN
                CASE WHEN seed_season = cand_season THEN {cfg.season_match_bonus}
                     ELSE {cfg.season_mismatch_penalty}
                END
              ELSE 0 END AS season_score
        , CASE WHEN seed_color IS NOT NULL AND seed_color = cand_color THEN {cfg.color_match_bonus} ELSE 0 END AS color_score
        , CASE WHEN seed_material IS NOT NULL AND seed_material = cand_material THEN {cfg.material_match_bonus} ELSE 0 END AS material_score
        , CASE WHEN seed_fastener IS NOT NULL AND seed_fastener = cand_fastener THEN {cfg.fastener_match_bonus} ELSE 0 END AS fastener_score
        , CASE
            WHEN seed_mega_last IS NOT NULL AND seed_mega_last <> '' AND seed_mega_last = cand_mega_last THEN {cfg.mega_last_bonus}
            WHEN seed_best_last IS NOT NULL AND seed_best_last <> '' AND seed_best_last = cand_best_last THEN {cfg.best_last_bonus}
            WHEN seed_new_last IS NOT NULL AND seed_new_last <> '' AND seed_new_last = cand_new_last THEN {cfg.new_last_bonus}
            ELSE 0 END AS last_score
        , CASE WHEN seed_model_name IS NOT NULL AND seed_model_name <> '' AND seed_model_name = cand_model_name THEN {cfg.model_match_bonus} ELSE 0 END AS model_score
    """

    score_aggregation = "" if not punta_exists else f"""
        , ({cfg.base_score} + season_score + color_score + material_score + fastener_score + last_score + model_score) AS raw_score
        , CASE WHEN last_score = 0 THEN CAST(({cfg.base_score} + season_score + color_score + material_score + fastener_score + last_score + model_score) * {cfg.no_last_penalty_multiplier} AS DOUBLE)
               ELSE ({cfg.base_score} + season_score + color_score + material_score + fastener_score + last_score + model_score)
          END AS adjusted_score
        , LEAST({cfg.max_score}, adjusted_score) AS final_score
    """

    if not punta_exists:
        score_aggregation = f", {cfg.base_score} AS raw_score, {cfg.base_score} AS adjusted_score, {cfg.base_score} AS final_score"

    # Construct dynamic CTE parts for punta_google
    punta_ctes = ''
    punta_left_joins = ''
    material_filter = ''
    if punta_exists:
        punta_ctes = ", pg_seed AS (SELECT wb_sku, season, color, lacing_type, material_short, mega_last, best_last, new_last, model_name FROM punta_google), pg_cand AS (SELECT wb_sku, season, color, lacing_type, material_short, mega_last, best_last, new_last, model_name FROM punta_google)"
        punta_left_joins = "LEFT JOIN pg_seed ON pg_seed.wb_sku = s.seed_wb_sku LEFT JOIN pg_cand ON pg_cand.wb_sku = c.cand_wb_sku"
        # ТРЕБОВАНИЕ: material_short должен точно совпадать, иначе товар не является кандидатом
        material_filter = "WHERE (pg_seed.material_short IS NULL OR pg_cand.material_short IS NULL OR pg_seed.material_short = pg_cand.material_short)"

    sql = f"""
    WITH seed AS (
        SELECT DISTINCT CAST(seed_wb_sku AS UBIGINT) AS seed_wb_sku
        FROM seed_input
        WHERE seed_wb_sku ~ '^[0-9]+'
    ),
    seed_enriched AS (
        SELECT s.seed_wb_sku, wp.seller_category, wp.gender
        FROM seed s
        LEFT JOIN wb_products wp ON wp.wb_sku = s.seed_wb_sku
        WHERE wp.wb_sku IS NOT NULL
    ),
    candidates AS (
        SELECT c.wb_sku AS cand_wb_sku, c.seller_category, c.gender, s.seed_wb_sku
        FROM wb_products c
        JOIN seed_enriched s ON s.seller_category = c.seller_category AND s.gender = c.gender
        WHERE c.wb_sku <> s.seed_wb_sku
    )
    {punta_ctes}
    , pairs AS (
        SELECT
            s.seed_wb_sku,
            c.cand_wb_sku
            {pg_cols}
        FROM candidates c
        JOIN seed_enriched s ON s.seed_wb_sku = c.seed_wb_sku
        {punta_left_joins}
        {material_filter}
    )
    , scored AS (
        SELECT *
            {scoring_columns}
            {score_aggregation}
        FROM pairs
    )
    , filtered AS (
        SELECT * FROM scored WHERE final_score >= {cfg.min_score_threshold}
    )
    , deduped AS (
        SELECT seed_wb_sku, cand_wb_sku, MAX(final_score) AS final_score
        FROM filtered
        GROUP BY seed_wb_sku, cand_wb_sku
    )
    , ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY seed_wb_sku ORDER BY final_score DESC, cand_wb_sku) AS rn
        FROM deduped
    )
    SELECT * FROM ranked
    WHERE rn <= {cfg.max_candidates_per_seed}
    ORDER BY seed_wb_sku, final_score DESC, cand_wb_sku
    """

    df_pairs = local_con.execute(sql).fetch_df()
    if df_pairs.empty:
        return pd.DataFrame(columns=["wb_sku", "oz_sku", "oz_vendor_code", "merge_code", "merge_color", "match_score", "similarity_score"])

    # Store similarity scores for each wb_sku (candidates)
    similarity_scores: dict[int, float] = {}
    for _, r in df_pairs.iterrows():
        try:
            wb = int(r.cand_wb_sku)
            similarity_scores[wb] = float(r.final_score)
        except Exception:
            pass
    
    # For seed wb_sku (input values), assign a high reference score (e.g., base_score or max observed)
    # This indicates they are the reference items
    seed_wb_skus = {int(x) for x in df_pairs.seed_wb_sku.unique()}
    for seed_wb in seed_wb_skus:
        if seed_wb not in similarity_scores:
            # Use the maximum score they were matched with, or a default
            matching_scores = df_pairs[df_pairs['seed_wb_sku'] == seed_wb]['final_score']
            similarity_scores[seed_wb] = float(matching_scores.max()) if not matching_scores.empty else float(cfg.base_score)

    # Build connectivity components (union-find simple)
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    seen_seeds: set[int] = set()
    for _, r in df_pairs.iterrows():
        a, b = int(r.seed_wb_sku), int(r.cand_wb_sku)
        seen_seeds.add(a)
        seen_seeds.add(b)
        union(a, b)
    # Добавим одиночных seed (без кандидатов) чтобы формировать корректные merge_code
    for s in (int(x) for x in df_pairs.seed_wb_sku.unique()):
        parent.setdefault(s, s)
    comp_map: dict[int, set[int]] = {}
    for k in list(parent.keys()):
        root = find(k)
        comp_map.setdefault(root, set()).add(k)
    components = list(comp_map.values())

    # Разбиваем большие компоненты, если указан max_group_size
    if cfg.max_group_size is not None:
        split_components = []
        large_components_count = 0
        for comp in components:
            if len(comp) > cfg.max_group_size:
                large_components_count += 1
                subgroups = _split_large_component(comp, df_pairs, cfg.max_group_size)
                logger.info(f"Split large component of size {len(comp)} into {len(subgroups)} subgroups")
                split_components.extend(subgroups)
            else:
                split_components.append(comp)
        if large_components_count > 0:
            logger.info(f"Split {large_components_count} large components, total groups: {len(components)} -> {len(split_components)}")
        components = split_components

    mapping: dict[int, tuple[str, str]] = {}
    merge_code_to_group: dict[str, int] = {}
    group_num = 1
    for comp in components:
        # В компоненте могут появиться только cand/seed; min определяет общий merge_code
        min_wb = min(comp)
        group_hex = format(min_wb, "X")
        merge_code = "C-" + group_hex
        merge_code_to_group[merge_code] = group_num
        for wb in comp:
            mapping[wb] = (merge_code, group_hex)
        group_num += 1

    all_wb = sorted({int(x) for x in df_pairs.seed_wb_sku.tolist()} | {int(x) for x in df_pairs.cand_wb_sku.tolist()})
    df_matches = _matches_for_wb_skus([str(x) for x in all_wb], limit_per_input=None, con=local_con, md_token=md_token, md_database=md_database)
    if df_matches.empty:
        return pd.DataFrame(columns=["group_number", "wb_sku", "oz_sku", "oz_vendor_code", "oz_manufacturer_size", "merge_code", "merge_color", "match_score", "similarity_score"])

    def extract_color(oz_vendor_code: str | None) -> str:
        if not oz_vendor_code:
            return ""
        parts = str(oz_vendor_code).split("-")
        return parts[1].strip() if len(parts) >= 3 else ""

    rows = []
    for _, r in df_matches.iterrows():
        try:
            wb = int(r.wb_sku)
        except Exception:
            continue
        merge_code, group_hex = mapping.get(wb, ("C-" + format(wb, "X"), format(wb, "X")))
        # If merge_code not in mapping, it's an isolated wb_sku, assign next group number
        if merge_code not in merge_code_to_group:
            merge_code_to_group[merge_code] = group_num
            group_num += 1
        group_number = merge_code_to_group[merge_code]
        color_mid = extract_color(r.get("oz_vendor_code"))
        merge_color = f"{color_mid}; {format(wb, 'X')}" if color_mid else format(wb, 'X')
        rows.append({
            "group_number": group_number,
            "wb_sku": r.get("wb_sku"),
            "oz_sku": r.get("oz_sku"),
            "oz_vendor_code": r.get("oz_vendor_code"),
            "oz_manufacturer_size": r.get("oz_manufacturer_size"),
            "merge_code": merge_code,
            "merge_color": merge_color,
            "match_score": int(r.get("match_score") or 0),
            "similarity_score": similarity_scores.get(wb, 0.0),
        })
    out = pd.DataFrame(rows)
    # Deduplicate OZ sizes: keep best score for (wb_sku, oz_sku, oz_manufacturer_size)
    if not out.empty and "oz_manufacturer_size" in out.columns:
        out = out.sort_values(["match_score"], ascending=[False])
        out = out.drop_duplicates(subset=["wb_sku", "oz_sku", "oz_manufacturer_size"], keep="first")
    return out


def search_similar_matches_debug(
    wb_skus: Iterable[str | int],
    *,
    config: SimilarityScoringConfig | None = None,
    md_token: str | None = None,
    md_database: str | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Debug variant returning the final dataframe plus stage row counts.

    Stage keys: candidates, pairs, scored, filtered, ranked, matches_rows.
    """
    cfg = config or SimilarityScoringConfig()
    cfg.validate()
    wb_list: list[str] = [str(s).strip() for s in wb_skus if str(s).strip()]
    if not wb_list:
        return pd.DataFrame(), {}
    local_con = _ensure_connection(con, md_token=md_token, md_database=md_database)
    local_con.register("seed_input", pd.DataFrame({"seed_wb_sku": wb_list}))
    punta_exists = _table_exists(local_con, "punta_google")
    # Reuse core SQL but wrap counts
    # We replicate simplified logic (without re-writing entire function) by querying intermediate CTE results.
    # To avoid duplicating large SQL, we run the same assembly and then extract counts using subqueries.
    # For transparency we call main function for final output.
    df_final = search_similar_matches(wb_list, config=cfg, md_token=md_token, md_database=md_database, con=local_con)
    stats: dict[str, int] = {}
    # candidates count
    cand_row = local_con.execute(
        """
        WITH seed AS (
            SELECT DISTINCT CAST(seed_wb_sku AS UBIGINT) AS seed_wb_sku
            FROM seed_input WHERE seed_wb_sku ~ '^[0-9]+'
        ),
        seed_enriched AS (
            SELECT s.seed_wb_sku, wp.seller_category, wp.gender
            FROM seed s
            LEFT JOIN wb_products wp ON wp.wb_sku = s.seed_wb_sku
            WHERE wp.wb_sku IS NOT NULL
        ),
        candidates AS (
            SELECT c.wb_sku AS cand_wb_sku, c.seller_category, c.gender, s.seed_wb_sku
            FROM wb_products c
            JOIN seed_enriched s ON s.seller_category = c.seller_category AND s.gender = c.gender
            WHERE c.wb_sku <> s.seed_wb_sku
        )
        SELECT COUNT(*) AS cnt FROM candidates
        """
    ).fetchone()
    stats["candidates"] = int(cand_row[0]) if cand_row else 0
    # pairs (after joins with punta if exists)
    if punta_exists:
        pair_row = local_con.execute(
            """
            WITH seed AS (
                SELECT DISTINCT CAST(seed_wb_sku AS UBIGINT) AS seed_wb_sku
                FROM seed_input WHERE seed_wb_sku ~ '^[0-9]+'
            ),
            seed_enriched AS (
                SELECT s.seed_wb_sku, wp.seller_category, wp.gender
                FROM seed s
                LEFT JOIN wb_products wp ON wp.wb_sku = s.seed_wb_sku
                WHERE wp.wb_sku IS NOT NULL
            ),
            candidates AS (
                SELECT c.wb_sku AS cand_wb_sku, c.seller_category, c.gender, s.seed_wb_sku
                FROM wb_products c
                JOIN seed_enriched s ON s.seller_category = c.seller_category AND s.gender = c.gender
                WHERE c.wb_sku <> s.seed_wb_sku
            ),
            pg_seed AS (
                SELECT wb_sku, season, color, lacing_type, material_short, mega_last, best_last, new_last, model_name
                FROM punta_google
            ),
            pg_cand AS (
                SELECT wb_sku, season, color, lacing_type, material_short, mega_last, best_last, new_last, model_name
                FROM punta_google
            )
            SELECT COUNT(*) AS cnt
            FROM candidates c
            JOIN seed_enriched s ON s.seed_wb_sku = c.seed_wb_sku
            LEFT JOIN pg_seed ON pg_seed.wb_sku = s.seed_wb_sku
            LEFT JOIN pg_cand ON pg_cand.wb_sku = c.cand_wb_sku
            WHERE (pg_seed.material_short IS NULL OR pg_cand.material_short IS NULL OR pg_seed.material_short = pg_cand.material_short)
            """
        ).fetchone()
        stats["pairs"] = int(pair_row[0]) if pair_row else 0
    else:
        stats["pairs"] = stats["candidates"]
    # ranked approx = number of unique candidate pairs after threshold; recompute via original df_final groups
    stats["matches_rows"] = len(df_final)
    return df_final, stats
