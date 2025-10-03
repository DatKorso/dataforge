import toml
import os
from dataforge.attributes import (
	import_unique_values_from_punta,
	merge_with_existing_mappings,
	save_category_mappings,
	get_next_id_for_category,
	get_attributes_by_category,
)


def _load_secrets():
	md_token = os.environ.get("MOTHERDUCK_TOKEN")
	md_database = os.environ.get("MD_DATABASE")
	if md_token and md_database:
		return md_token, md_database
	try:
		s = toml.load(".streamlit/secrets.toml")
		return s.get("md_token"), s.get("md_database")
	except Exception:
		return md_token, md_database


md_token, md_database = _load_secrets()

cat = 'lining_material'
print('Importing unique values for', cat)
new_vals = import_unique_values_from_punta(cat, md_token=md_token, md_database=md_database)
print('Unique from punta:', len(new_vals))
existing = get_attributes_by_category(cat, md_token=md_token, md_database=md_database)
print('Existing before:', len(existing))
merged = merge_with_existing_mappings(cat, new_vals, md_token=md_token, md_database=md_database)
print('Merged total:', len(merged))
# Do not save by default; just test counts
added = len(merged) - len(existing)
print('Would add:', added)
