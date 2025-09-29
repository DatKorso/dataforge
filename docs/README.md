# DataFox Documentation

This directory contains technical specifications and documentation for the DataFox dashboard project.

## 📁 Documentation Structure

### Technical Specifications (ТЗ)
Technical requirements documents for data import functionality:

- **[TZ_oz_products_import.md](TZ_oz_products_import.md)** - Ozon products import specification
- **[TZ_oz_orders_import.md](TZ_oz_orders_import.md)** - Ozon orders import specification  
- **[TZ_oz_prices_import.md](TZ_oz_prices_import.md)** - Ozon prices import specification
- **[TZ_wb_products_import.md](TZ_wb_products_import.md)** - Wildberries products import specification
- **[TZ_wb_prices_import.md](TZ_wb_prices_import.md)** - Wildberries prices import specification
- **[TZ_punta_table_import.md](TZ_punta_table_import.md)** - Punta table import specification

### Sample Data Files
Located in `files_examples/` directory:

#### Ozon Data Samples
- `oz_products.csv` - Sample Ozon products data
- `oz_orders.csv` - Sample Ozon orders data  
- `oz_prices.xlsx` - Sample Ozon prices data

#### Wildberries Data Samples
- `wb_prices.xlsx` - Sample Wildberries prices data
- `wb_products/` - Directory with Wildberries product samples
  - `07.08.2025_06.29_Общие характеристики одним файлом_1.xlsx`
  - `07.08.2025_06.29_Общие характеристики одним файлом_2.xlsx`

#### Punta Data Samples
- `punta_test.xlsx` - Sample Punta table data

## 🔍 Documentation Quick Reference

### Implementation Status

| Marketplace | Products | Orders | Prices | Status |
|-------------|----------|--------|--------|---------|
| **Ozon** | ✅ Implemented | ✅ Implemented | 📋 Spec only | 2/3 Complete |
| **Wildberries** | 📋 Spec only | - | 📋 Spec only | 0/2 Complete |
| **Punta** | 📋 Spec only | - | - | 0/1 Complete |

### Field Mapping Overview

- **Ozon Products**: 47 fields with comprehensive validation
- **Ozon Orders**: 43 fields with status normalization  
- **Ozon Prices**: Planned implementation
- **Wildberries Products**: Multi-sheet Excel processing
- **Wildberries Prices**: Price comparison functionality
- **Punta Tables**: Custom table structure

### Punta Collections
- Collections are managed in a dedicated table `punta_collections` with fields:
  - `collection` (TEXT, primary key)
  - `priority` (INTEGER)
  - `active` (BOOLEAN, reserved for future use)

- Import flow (Files → Punta):
  - Select an existing collection from the dropdown or create a new one.
  - The app replaces data only for the selected collection (partitioned by `collection`).
  - Current collection priority is shown as a hint.

- Managing order (Pages → 🗂 Коллекции):
  - Reorder collections via drag‑and‑drop (uses `streamlit-sortables`) and click “Save order”.
  - If the component is unavailable, edit numeric priorities in the table and save; priorities will be normalized to 1..n.

## 📝 Reading the Specifications

Each technical specification document follows this structure:

1. **Цель (Goal)** - Purpose and objectives
2. **Формат данных (Data Format)** - Input file formats
3. **Структура файла (File Structure)** - Expected columns and data types
4. **Маппинг полей (Field Mapping)** - CSV columns to database fields
5. **Правила обработки данных (Data Processing Rules)** - Validation and cleaning rules
6. **Схема таблицы (Table Schema)** - Database table structure
7. **Примеры данных (Data Examples)** - Sample data formats

## 🛠️ Using the Documentation

### For Developers
1. Review the appropriate TZ document for requirements
2. Check sample data files for format understanding
3. Implement following the field mapping specifications
4. Use the validation rules for data cleaning

### For Data Analysts
1. Use sample files as templates for data preparation
2. Reference field mapping for understanding data flow
3. Check validation rules for data quality requirements

### For Project Managers
1. Review implementation status table for progress tracking
2. Use specifications for requirement validation
3. Reference for scope and complexity estimation

## 🔗 Related Documentation

- **[../PROJECT_INDEX.md](../PROJECT_INDEX.md)** - Complete project documentation index
- **[../README.md](../README.md)** - Main project README
- **[../CLAUDE.md](../CLAUDE.md)** - Claude Code integration guide
- **[../README_SUPABASE_SETUP.md](../README_SUPABASE_SETUP.md)** - Supabase setup guide

---

*For complete project documentation, see [PROJECT_INDEX.md](../PROJECT_INDEX.md)*
