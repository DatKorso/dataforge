"""Тест для проверки размера групп в алгоритме similarity matching"""
from dataforge.similarity_matching import search_similar_matches
from dataforge.similarity_config import SimilarityScoringConfig
import os

# Читаем wb_sku из тестового файла
with open("docs/wb_sku_for_test.txt") as f:
    wb_skus = [line.strip() for line in f if line.strip()]

print(f"Загружено {len(wb_skus)} wb_sku из файла")
print(f"Первые 5: {wb_skus[:5]}")

# Настраиваем конфиг с новыми оптимальными значениями
cfg = SimilarityScoringConfig(
    min_score_threshold=300.0,
    max_candidates_per_seed=30,
    max_group_size=10,  # Ограничиваем размер группы
)

# Получаем токены из переменных окружения или streamlit secrets
md_token = os.environ.get("MOTHERDUCK_TOKEN")
md_database = os.environ.get("MOTHERDUCK_DATABASE", "dataforge")

if not md_token:
    try:
        # Пробуем загрузить из secrets через dataforge.secrets
        from dataforge.secrets import load_secrets
        secrets = load_secrets()
        md_token = secrets.get("md_token")
        md_database = secrets.get("md_database", "dataforge")
        if md_token:
            print("✅ Токены загружены из .streamlit/secrets.toml")
    except Exception as e:
        print(f"⚠️  Не удалось загрузить из secrets: {e}")
        
if not md_token:
    print("⚠️  MOTHERDUCK_TOKEN не установлен. Используйте: export MOTHERDUCK_TOKEN=...")
    print("   Или настройте .streamlit/secrets.toml")
    exit(1)

print("\n🔍 Запускаем search_similar_matches с новыми оптимальными параметрами...")
df_result = search_similar_matches(
    wb_skus,
    config=cfg,
    md_token=md_token,
    md_database=md_database,
)

if df_result.empty:
    print("❌ Результаты пустые")
    exit(0)

print(f"\n📊 Получено {len(df_result)} строк результата")
print(f"Уникальных wb_sku: {df_result['wb_sku'].nunique()}")
print(f"Уникальных oz_sku: {df_result['oz_sku'].nunique()}")

# Анализируем группы
if 'group_number' in df_result.columns:
    group_sizes = df_result.groupby('group_number')['wb_sku'].nunique()
    print(f"\n📈 Статистика по группам:")
    print(f"Всего групп: {len(group_sizes)}")
    print(f"Размеры групп (уникальных wb_sku):")
    print(group_sizes.sort_values(ascending=False).head(10))
    
    max_group = group_sizes.max()
    max_group_num = group_sizes.idxmax()
    print(f"\n⚠️  Самая большая группа: #{max_group_num} с {max_group} уникальными wb_sku")
    
    if cfg.max_group_size and max_group > cfg.max_group_size:
        print(f"❌ ПРОБЛЕМА: Размер группы {max_group} превышает max_group_size={cfg.max_group_size}")
        print(f"   Ожидалось: не более {cfg.max_group_size}")
        
        # Показываем wb_sku из самой большой группы
        big_group = df_result[df_result['group_number'] == max_group_num]
        print(f"\n   WB SKU в большой группе (первые 20):")
        unique_wb = big_group['wb_sku'].unique()[:20]
        for wb in unique_wb:
            print(f"     - {wb}")
    else:
        print(f"✅ Размер группы в пределах ожидаемого (max_group_size={cfg.max_group_size})")
else:
    print("⚠️  Колонка group_number отсутствует")

# Сохраняем результаты для анализа
df_result.to_csv("test_similarity_groups_output.csv", index=False)
print(f"\n💾 Результаты сохранены в test_similarity_groups_output.csv")
