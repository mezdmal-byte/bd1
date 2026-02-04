import pandas as pd

# путь к твоему файлу, можно скопировать тот, что ты загружал
file_path = 'input.xlsx'

# читаем файл как есть
df = pd.read_excel(file_path, header=None, dtype=str)

# выводим первые 30 строк
for i in range(30):
    print(f"\n=== Строка {i} ===")
    print(list(df.iloc[i].values))
