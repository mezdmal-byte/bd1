import pandas as pd
import sys
import sqlite3

def find_header_row(df, keywords):
    """
    Ищем строку, которая выглядит как заголовок.
    Возвращает индекс строки или None.
    """
    key_lower = [k.lower() for k in keywords]
    for idx, row in df.head(20).iterrows():
        row_str = ' '.join(str(val).lower() for val in row if pd.notna(val))
        matches = sum(1 for k in key_lower if k in row_str)
        if matches >= 4:  # минимум 4 совпадения — это почти наверняка заголовок
            return idx
    return None

def import_1s_smart(file_path, db_path='assets.db'):
    try:
        # Читаем весь файл как строки
        df = pd.read_excel(file_path, dtype=str, engine='openpyxl', header=None)

        # Ключевые слова для поиска строки заголовков
        header_keywords = [
            'инвентарный номер', 'заводской номер', 'основное средство',
            'дата принятия', 'состояние', 'текущее местонахождение',
            'стоимость первоначальная'
        ]

        header_idx = find_header_row(df, header_keywords)
        if header_idx is None:
            raise ValueError(
                "Не удалось найти строку с заголовками.\n"
                "Проверьте первые 20 строк файла — там должны быть слова вроде 'Инвентарный номер', 'Состояние' и т.д.\n"
                f"Первые строки:\n{df.head(10).to_string()}"
            )

        print(f"Найдена строка заголовков на позиции {header_idx + 1} (индекс {header_idx})")

        # Устанавливаем заголовки из найденной строки
        headers = df.iloc[header_idx]
        df = df.iloc[header_idx + 1:]  # данные начинаются со следующей строки
        df.columns = headers.str.strip().str.replace('\n', ' ').str.replace('\r', '')

        # Ищем нужные колонки
        mapping = {}
        for col in df.columns:
            col_lower = str(col).lower()
            if 'инвентарный номер' in col_lower:
                mapping['inventory_number'] = col
            elif 'заводской номер' in col_lower or 'номер лицензии' in col_lower:
                mapping['serial_number'] = col
            elif 'основное средство' in col_lower or 'наименование' in col_lower:
                mapping['name'] = col
            elif 'дата принятия' in col_lower:
                mapping['acquisition_date'] = col
            elif 'стоимость первоначальная' in col_lower or 'первоначальная стоимость' in col_lower:
                mapping['initial_cost'] = col
            elif 'состояние' in col_lower:
                mapping['accounting_status'] = col
            elif 'текущее местонахождение' in col_lower or 'местонахождение' in col_lower:
                mapping['location'] = col

        # Обязательные
        required = ['inventory_number', 'name', 'accounting_status']
        missing = [k for k in required if k not in mapping]
        if missing:
            raise ValueError(f"Не найдены обязательные колонки: {missing}\nДоступные: {list(df.columns)}")

        print("Найденные колонки:")
        for k, v in mapping.items():
            print(f"{k:18} ← {v}")

        # Фильтруем строки с инв. номером
        inv_col = mapping['inventory_number']
        valid_df = df[
            df[inv_col].notna() &
            (df[inv_col] != '') &
            ~df[inv_col].str.contains('Итого|Всего|Ответственный', na=False, case=False)
        ].copy()

        # Очистка
        valid_df[inv_col] = valid_df[inv_col].str.strip()
        valid_df[mapping['name']] = valid_df[mapping['name']].str.strip()
        valid_df[mapping['accounting_status']] = valid_df[mapping['accounting_status']].str.strip()
        if 'location' in mapping:
            valid_df['location'] = valid_df[mapping['location']].str.strip().fillna('')
        if 'serial_number' in mapping:
            valid_df[mapping['serial_number']] = valid_df[mapping['serial_number']].str.strip().fillna('')

        # Стоимость → float
        if 'initial_cost' in mapping:
            cost_col = mapping['initial_cost']
            valid_df[cost_col] = pd.to_numeric(
                valid_df[cost_col].str.replace(' ', '').str.replace(',', '.'),
                errors='coerce'
            )

        # SQL
        sql_statements = []
        for _, row in valid_df.iterrows():
            inv = str(row[inv_col]).replace("'", "''")
            ser = str(row.get(mapping.get('serial_number', ''), '')).replace("'", "''")
            name = str(row[mapping['name']]).replace("'", "''")
            date = str(row.get(mapping.get('acquisition_date', 'NULL'), 'NULL'))
            cost = row.get(mapping.get('initial_cost'), 'NULL')
            if pd.isna(cost):
                cost = 'NULL'
            else:
                cost = f"{float(cost):.2f}"
            status = str(row[mapping['accounting_status']]).replace("'", "''")
            loc = str(row.get('location', '')).replace("'", "''")

            sql = (
                f"INSERT OR REPLACE INTO assets "
                f"(inventory_number, serial_number, name, acquisition_date, initial_cost, accounting_status, location) "
                f"VALUES ('{inv}', '{ser}', '{name}', '{date}', {cost}, '{status}', '{loc}');"
            )
            sql_statements.append(sql)

        # Сохраняем
        sql_file = 'import_assets_final.sql'
        with open(sql_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sql_statements))

        print(f"\nГотово! Сгенерировано {len(sql_statements)} записей.")
        print(f"SQL сохранён в {sql_file}")
        print("Первые 3:")
        print('\n'.join(sql_statements[:3]))

        # Вставка в базу
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        inserted = 0
        for sql in sql_statements:
            try:
                cursor.execute(sql)
                inserted += 1
            except Exception as e:
                print(f"Ошибка вставки: {e}")
        conn.commit()
        conn.close()
        print(f"Вставлено {inserted} записей в базу {db_path}")

    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Запуск: python import_1s_smart.py \"путь_к_файлу.xlsx\"")
    else:
        import_1s_smart(sys.argv[1])