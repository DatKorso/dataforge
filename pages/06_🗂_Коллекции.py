import streamlit as st

from dataforge.collections import (
    list_punta_collections,
    ensure_punta_collection,
    reorder_punta_collections,
)


st.title("🗂 Коллекции (Punta)")
st.caption("Управление списком коллекций и их порядком (приоритетом).")


def _sget(key: str) -> str | None:
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:
        return None


md_token = st.session_state.get("md_token") or _sget("md_token")
md_database = st.session_state.get("md_database") or _sget("md_database")


@st.cache_data(ttl=10)
def _load_colls(md_token: str | None, md_database: str | None):
    try:
        df = list_punta_collections(md_token=md_token, md_database=md_database)
    except Exception:
        df = None
    return df


def _refresh():
    _load_colls.clear()  # type: ignore[attr-defined]


# Create new collection
with st.expander("Создать коллекцию", expanded=False):
    new_name = st.text_input("Название коллекции", key="_new_coll_name")
    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("Создать") and new_name.strip():
            try:
                name, pr = ensure_punta_collection(
                    new_name.strip(), md_token=md_token, md_database=md_database
                )
                st.success(f"Создано: {name} (приоритет {pr})")
                _refresh()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Не удалось создать: {exc}")


df = _load_colls(md_token, md_database)
if df is None or df.empty:
    st.info("Коллекции не найдены. Создайте первую коллекцию выше.")
    st.stop()


st.subheader("Порядок коллекций")
names = df["collection"].astype(str).tolist()

new_order: list[str] | None = None

# Try drag-n-drop via streamlit-sortables, fallback to editor
used_drag = False
try:
    from streamlit_sortables import sort_items  # type: ignore

    st.caption("Перетащите коллекции для изменения порядка (drag‑n‑drop).")
    sorted_items = sort_items(names, direction="vertical", key="punta_collections_sort")
    if isinstance(sorted_items, list) and len(sorted_items) == len(names):
        new_order = [str(x) for x in sorted_items]
        used_drag = True
except Exception:
    used_drag = False

if not used_drag:
    st.caption(
        "Компонент drag‑n‑drop недоступен. Редактируйте приоритеты вручную и сохраните порядок."
    )
    editable = df[["collection", "priority"]].copy()
    editable = st.data_editor(
        editable,
        key="punta_coll_editor",
        hide_index=True,
        use_container_width=True,
    )
    # Sort by edited priority, then by name for stability
    editable = editable.sort_values(["priority", "collection"], ascending=[True, True])
    new_order = editable["collection"].astype(str).tolist()


col_save, col_refresh = st.columns([1, 1])
with col_save:
    if st.button("Сохранить порядок") and new_order:
        try:
            reorder_punta_collections(new_order, md_token=md_token, md_database=md_database)
            st.success("Порядок сохранён.")
            _refresh()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Не удалось сохранить: {exc}")
with col_refresh:
    if st.button("Обновить список"):
        _refresh()

