import pandas as pd
import sqlite3

# 1. Путь к Excel-файлу
file_path = '12121212.xlsx'  # или 'uploads/твой_файл.xlsx'

# 2. Читаем Excel без заголовка для поиска шапки
df_raw = pd.read_excel(file_path, header=None, dtype=str)
header_row = None
for idx in range(len(df_raw)):
    if 'Основное средство' in df_raw.iloc[idx].values:
        header_row = idx
        break

if header_row is None:
    raise ValueError("Не найдена строка с заголовком 'Основное средство'")

# 3. Перечитываем с правильным заголовком
df = pd.read_excel(file_path, header=header_row, dtype=str)

# 4. Фильтруем только реальные записи (не группировки и не итоги)
df = df[df['Инвентарный номер'].notna() & df['Основное средство'].notna()]

# 5. Маппинг колонок (с учётом Unnamed)
columns_map = {
    'Основное средство': 'name',
    'Инвентарный номер': 'inventory_number',
    'Дата принятия к учету': 'acquisition_date',
    'Unnamed: 17': 'initial_cost',  # Балансовая стоимость
    'Срок полезного использования': 'useful_life_months',
    'Износ, %': 'wear_percent',
    'Unnamed: 18': 'quantity',      # Количество
    'Состояние': 'accounting_status',
    'Текущее местонахождение': 'location'
}

# Оставляем только нужные колонки
df = df[list(columns_map.keys())].rename(columns=columns_map)

# 6. Приводим типы
df['initial_cost'] = df['initial_cost'].str.replace(' ', '').str.replace(',', '.').astype(float)
df['wear_percent'] = df['wear_percent'].replace('-', '0').str.replace(',', '.').astype(float)
df['quantity'] = df['quantity'].fillna(0).astype(int)
df['useful_life_months'] = df['useful_life_months'].replace('-', '0').fillna(0).astype(int)
df['acquisition_date'] = pd.to_datetime(df['acquisition_date'], dayfirst=True, errors='coerce')

# 7. Подключаемся к БД
conn = sqlite3.connect('assets.db')
cursor = conn.cursor()

# УДАЛИ ЭТУ СТРОКУ: df.to_sql('assets', conn, if_exists='replace', index=False)
# ЗАМЕНИ НА:
df[['name', 'inventory_number', 'acquisition_date', 'initial_cost',
    'useful_life_months', 'wear_percent', 'quantity', 'accounting_status']].to_sql(
    'assets', conn, if_exists='append', index=False
)

# 8. Добавляем местоположение в actual_assets
for _, row in df.iterrows():
    inv_num = row['inventory_number']
    location = row['location'] if pd.notna(row['location']) else None

    # Получаем id актива
    cursor.execute("SELECT id FROM assets WHERE inventory_number = ?", (inv_num,))
    result = cursor.fetchone()
    if result:
        asset_id = result[0]
        notes = f"Местоположение: {location}" if location else None
        cursor.execute("""
            INSERT OR REPLACE INTO actual_assets (asset_id, notes)
            VALUES (?, ?)
        """, (asset_id, notes))

conn.commit()
conn.close()

print(f"Импорт завершён! Загружено записей: {len(df)}")