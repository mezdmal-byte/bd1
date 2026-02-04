import pandas as pd

# Укажи путь к своему файлу
filepath = 'uploads/12121212.xlsx'  # Замени на реальное имя

# Читаем без заголовка
df = pd.read_excel(filepath, header=None, dtype=str)

print("=" * 60)
print("ПЕРВЫЕ 10 СТРОК ФАЙЛА:")
print("=" * 60)
print(df.head(10))

print("\n" + "=" * 60)
print("ПОИСК СТРОКИ С ШАПКОЙ:")
print("=" * 60)

# Ищем шапку
for idx in range(min(15, len(df))):
    row_values = df.iloc[idx].values
    if 'Основное средство' in row_values:
        print(f"✅ Найдена шапка на строке {idx}")
        print(f"Колонки: {list(df.iloc[idx])}")

        # Перечитываем с правильным заголовком
        df_with_header = pd.read_excel(filepath, header=idx, dtype=str)
        print(f"\nВсего колонок: {len(df_with_header.columns)}")
        print(f"Названия колонок:\n{list(df_with_header.columns)}")

        print(f"\nПервые 5 строк данных:")
        print(df_with_header.head(5))
        break
else:
    print("❌ Не найдена строка с 'Основное средство'")