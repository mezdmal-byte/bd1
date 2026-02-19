import pandas as pd
import sys
import sqlite3
from datetime import datetime
import re

def find_header_row(file_path, max_rows=50):
    """
    Автоматически находит строку с заголовком таблицы.
    Ищет строку, содержащую ключевые слова заголовков.
    """
    # Ключевые слова, которые должны быть в заголовке
    header_keywords = [
        'инвентарный номер',
        'основное средство',
        'наименование',
        'заводской номер',
        'дата принятия',
        'стоимость',
        'состояние',
        'местонахождение'
    ]
    
    # Читаем первые строки без заголовка
    for skip in range(max_rows):
        try:
            df = pd.read_excel(file_path, header=None, nrows=1, skiprows=skip, engine='openpyxl')
            if df.empty:
                continue
            
            # Получаем строку как список строк
            row_values = []
            for col in df.columns:
                val = df.iloc[0][col]
                if pd.notna(val):
                    row_str = str(val).strip().lower()
                    row_values.append(row_str)
            
            # Проверяем, содержит ли строка ключевые слова
            found_keywords = 0
            for keyword in header_keywords:
                for val in row_values:
                    if keyword in val:
                        found_keywords += 1
                        break
            
            # Если найдено минимум 3 ключевых слова - это заголовок
            if found_keywords >= 3:
                print(f"✓ Найдена строка заголовка: строка {skip + 1} (индекс {skip})")
                return skip
        except Exception as e:
            continue
    
    # Если не нашли автоматически, возвращаем None
    print("Не удалось автоматически найти заголовок. Попробуйте указать вручную.")
    return None

def parse_date(date_str):
    """
    Парсит дату из различных форматов.
    Возвращает строку в формате YYYY-MM-DD или NULL.
    """
    if pd.isna(date_str) or date_str == '' or str(date_str).lower() == 'nan':
        return None
    
    date_str = str(date_str).strip()
    
    # Формат DD.MM.YYYY
    if re.match(r'^\d{1,2}\.\d{1,2}\.\d{4}$', date_str):
        try:
            dt = datetime.strptime(date_str, '%d.%m.%Y')
            return dt.strftime('%Y-%m-%d')
        except:
            pass
    
    # Формат YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    
    return None

def import_1s_final(file_path, db_path='assets.db', header_row=None):
    """
    Импортирует данные из Excel файла от бухгалтерии в базу данных.
    
    Args:
        file_path: путь к Excel файлу
        db_path: путь к базе данных
        header_row: номер строки заголовка (начиная с 0). Если None - ищется автоматически.
    """
    try:
        # Автоматический поиск строки заголовка
        if header_row is None:
            header_row = find_header_row(file_path)
            if header_row is None:
                raise ValueError("Не удалось найти строку заголовка. Укажите вручную через параметр header_row.")
        
        print(f"Используется строка заголовка: {header_row + 1} (индекс {header_row})")
        
        # Читаем файл с найденной строкой заголовка
        df = pd.read_excel(file_path, header=header_row, dtype=str, engine='openpyxl', na_values=['', 'nan', 'NaN'])
        
        # Очищаем названия колонок
        df.columns = [str(col).strip().replace('\n', ' ').replace('\r', '') if pd.notna(col) else f'Unnamed_{i}' 
                     for i, col in enumerate(df.columns)]
        
        print(f"\nНайдено колонок: {len(df.columns)}")
        print("Колонки в файле:", list(df.columns))
        
        # Ищем колонки по частичному совпадению
        mapping = {}
        for col in df.columns:
            if not isinstance(col, str):
                continue
            col_lower = col.lower()
            
            if 'инвентарный номер' in col_lower:
                mapping['inventory_number'] = col
            elif 'заводской номер' in col_lower or 'номер лицензии' in col_lower:
                mapping['serial_number'] = col
            elif 'основное средство' in col_lower or 'наименование' in col_lower:
                mapping['name'] = col
            elif 'дата принятия' in col_lower or 'дата принятия к учету' in col_lower:
                mapping['acquisition_date'] = col
            elif 'стоимость первоначальная' in col_lower or 'первоначальная стоимость' in col_lower:
                mapping['initial_cost'] = col
            elif 'состояние' in col_lower and 'местонахождение' not in col_lower:
                mapping['accounting_status'] = col
            elif 'текущее местонахождение' in col_lower or 'местонахождение' in col_lower:
                mapping['location'] = col
        
        # Обязательные колонки
        required = ['inventory_number', 'name']
        missing = [k for k in required if k not in mapping]
        if missing:
            raise ValueError(f"Не найдены обязательные колонки: {missing}\nДоступные колонки: {list(df.columns)}")
        
        print("\nНайденные колонки:")
        for k, v in mapping.items():
            print(f"  {k:20} ← {v}")
        
        # Фильтруем строки с инв. номером и без служебных строк
        inv_col = mapping['inventory_number']
        valid_df = df[
            df[inv_col].notna() &
            (df[inv_col].astype(str).str.strip() != '') &
            ~df[inv_col].astype(str).str.contains('Итого|Всего|Ответственный|итого|всего', na=False, case=False)
        ].copy()
        
        print(f"\nНайдено валидных записей: {len(valid_df)}")
        
        if len(valid_df) == 0:
            raise ValueError("Не найдено ни одной валидной записи для импорта")
        
        # Очистка данных
        valid_df[inv_col] = valid_df[inv_col].astype(str).str.strip()
        valid_df[mapping['name']] = valid_df[mapping['name']].astype(str).str.strip()
        
        if 'accounting_status' in mapping:
            valid_df[mapping['accounting_status']] = valid_df[mapping['accounting_status']].astype(str).str.strip().fillna('')
        
        # Обработка стоимости
        if 'initial_cost' in mapping:
            cost_col = mapping['initial_cost']
            # Убираем пробелы и заменяем запятую на точку
            valid_df[cost_col] = valid_df[cost_col].astype(str).str.replace(' ', '', regex=False).str.replace(',', '.', regex=False)
            valid_df[cost_col] = pd.to_numeric(valid_df[cost_col], errors='coerce')
        
        # Подключение к базе
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем структуру таблицы assets
        cursor.execute("PRAGMA table_info(assets)")
        columns_info = cursor.fetchall()
        available_columns = [col[1] for col in columns_info]
        print(f"\nДоступные колонки в таблице assets: {available_columns}")
        
        inserted = 0
        updated = 0
        errors = []
        
        # Вставка данных
        for idx, row in valid_df.iterrows():
            try:
                inv = str(row[inv_col]).strip()
                if not inv or inv.lower() in ['nan', 'none', '']:
                    continue
                
                name = str(row[mapping['name']]).strip()
                if not name or name.lower() in ['nan', 'none', '']:
                    continue
                
                # Получаем значения полей
                acquisition_date = None
                if 'acquisition_date' in mapping:
                    date_val = row[mapping['acquisition_date']]
                    acquisition_date = parse_date(date_val)
                
                initial_cost = None
                if 'initial_cost' in mapping:
                    cost_val = row[mapping['initial_cost']]
                    if pd.notna(cost_val):
                        try:
                            initial_cost = float(cost_val)
                        except:
                            pass
                
                accounting_status = ''
                if 'accounting_status' in mapping:
                    status_val = row[mapping['accounting_status']]
                    if pd.notna(status_val):
                        accounting_status = str(status_val).strip()
                
                # Формируем SQL запрос только с существующими полями
                fields = ['inventory_number', 'name']
                values = [inv, name]
                placeholders = ['?', '?']
                
                if acquisition_date:
                    fields.append('acquisition_date')
                    values.append(acquisition_date)
                    placeholders.append('?')
                
                if initial_cost is not None:
                    fields.append('initial_cost')
                    values.append(initial_cost)
                    placeholders.append('?')
                
                if accounting_status:
                    fields.append('accounting_status')
                    values.append(accounting_status)
                    placeholders.append('?')
                
                # Проверяем, существует ли запись
                cursor.execute("SELECT id FROM assets WHERE inventory_number = ?", (inv,))
                existing = cursor.fetchone()
                
                if existing:
                    # Обновляем существующую запись
                    set_clause = ', '.join([f"{f} = ?" for f in fields if f != 'inventory_number'])
                    set_values = [v for f, v in zip(fields, values) if f != 'inventory_number']
                    set_values.append(inv)
                    
                    sql = f"UPDATE assets SET {set_clause} WHERE inventory_number = ?"
                    cursor.execute(sql, set_values)
                    updated += 1
                else:
                    # Вставляем новую запись
                    sql = f"INSERT INTO assets ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
                    cursor.execute(sql, values)
                    inserted += 1
                
                # Если есть серийный номер, сохраняем его в actual_assets
                if 'serial_number' in mapping:
                    serial_val = row[mapping['serial_number']]
                    # Проверяем, что значение валидное и не "б/н"
                    if pd.notna(serial_val):
                        serial_str = str(serial_val).strip()
                        serial_lower = serial_str.lower()
                        # Пропускаем пустые значения, "б/н", "nan" и т.д.
                        if serial_str and serial_lower not in ['nan', 'б/н', 'none', '', 'н/д', 'н.д.']:
                            serial_number = serial_str
                            # Получаем ID актива
                            cursor.execute("SELECT id FROM assets WHERE inventory_number = ?", (inv,))
                            asset_row = cursor.fetchone()
                            if asset_row:
                                asset_id = asset_row[0]
                                # Проверяем, есть ли уже запись в actual_assets
                                cursor.execute("SELECT id FROM actual_assets WHERE asset_id = ?", (asset_id,))
                                actual_row = cursor.fetchone()
                                if actual_row:
                                    cursor.execute("UPDATE actual_assets SET serial_number = ? WHERE asset_id = ?", 
                                                 (serial_number, asset_id))
                                else:
                                    cursor.execute("INSERT INTO actual_assets (asset_id, serial_number) VALUES (?, ?)", 
                                                 (asset_id, serial_number))
                
            except Exception as e:
                error_msg = f"Ошибка обработки строки {idx + header_row + 2}: {str(e)}"
                errors.append(error_msg)
                print(f"  ⚠ {error_msg}")
        
        conn.commit()
        conn.close()
        
        print(f"\n{'='*60}")
        print(f"Импорт завершен!")
        print(f"  Вставлено новых записей: {inserted}")
        print(f"  Обновлено записей: {updated}")
        print(f"  Ошибок: {len(errors)}")
        print(f"{'='*60}")
        
        if errors:
            print("\nОшибки:")
            for err in errors[:10]:  # Показываем первые 10 ошибок
                print(f"  - {err}")
            if len(errors) > 10:
                print(f"  ... и еще {len(errors) - 10} ошибок")

        # Возвращаем результат для использования в веб-приложении
        return {
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
        }
    
    except Exception as e:
        import traceback
        print(f"\n❌ Ошибка обработки файла: {e}")
        print(traceback.format_exc())
        raise

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование: python import_1s_final.py <путь_к_файлу.xlsx> [номер_строки_заголовка]")
        print("Пример: python import_1s_final.py new111.xlsx")
        print("Пример: python import_1s_final.py new111.xlsx 3")
        print("\nЕсли номер строки не указан, будет выполнен автоматический поиск.")
    else:
        file_path = sys.argv[1]
        header_row = None
        if len(sys.argv) >= 3:
            try:
                header_row = int(sys.argv[2]) - 1  # Пользователь указывает с 1, мы используем с 0
            except ValueError:
                print("⚠ Номер строки должен быть числом. Будет выполнен автоматический поиск.")
        
        import_1s_final(file_path, header_row=header_row)
