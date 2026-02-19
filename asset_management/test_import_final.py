import urllib.request
import urllib.parse
import os

def test_import_fact():
    print("=== ТЕСТ ИМПОРТА ФАКТА ===")
    
    url = 'http://127.0.0.1:5000/inventory_import'
    
    csv_content = """inventory_number,name,serial_number,condition_status,physical_label_status,location,notes
2641,Тестовый компьютер,12345,Исправно,Есть,Кабинет 101,Тестовая запись
2642,Тестовый монитор,67890,Исправно,Есть,Кабинет 102,Еще одна запись"""

    with open('test_fact.csv', 'w', encoding='utf-8') as f:
        f.write(csv_content)

    with open('test_fact.csv', 'rb') as f:
        file_data = f.read()

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="test_fact.csv"\r\n'
        f'Content-Type: text/csv\r\n\r\n'
        f'{file_data.decode("utf-8")}\r\n'
        f'--{boundary}--\r\n'
    )

    try:
        req = urllib.request.Request(url, body.encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req) as response:
            print(f"Статус: {response.status}")
            result = response.read().decode('utf-8')
            
            if 'Сопоставление колонок' in result:
                print("Страница сопоставления открыта")
                
                mapping_data = {
                    'confirm_import': '1',
                    'map_inventory_number': 'inventory_number',
                    'map_name': 'name',
                    'map_serial_number': 'serial_number',
                    'map_condition_status': 'condition_status',
                    'map_physical_label_status': 'physical_label_status',
                    'map_location': 'location',
                    'map_notes': 'notes'
                }
                
                encoded_data = urllib.parse.urlencode(mapping_data)
                headers2 = {'Content-Type': 'application/x-www-form-urlencoded'}
                
                req2 = urllib.request.Request(url, encoded_data.encode('utf-8'), headers=headers2)
                with urllib.request.urlopen(req2) as response2:
                    print(f"Статус импорта: {response2.status}")
                    result2 = response2.read().decode('utf-8')
                    
                    if 'Импорт завершен' in result2:
                        print("Импорт факта успешен!")
                        return True
                    else:
                        print(f"Результат: {len(result2)} символов")
                        return False
            else:
                print("Страница сопоставления НЕ открыта")
                return False
                
    except Exception as e:
        print(f"Ошибка: {e}")
        return False
    finally:
        if os.path.exists('test_fact.csv'):
            os.remove('test_fact.csv')

def test_import_buh():
    print("\n=== ТЕСТ ИМПОРТА БУХ ===")
    
    url = 'http://127.0.0.1:5000/import'
    
    csv_content = """inventory_number,name,acquisition_date,initial_cost,wear_percent,quantity,accounting_status,category
2641,Тестовый компьютер,2024-01-01,50000.00,10,1,Введено в эксплуатацию,Техника"""

    with open('test_buh.csv', 'w', encoding='utf-8') as f:
        f.write(csv_content)

    with open('test_buh.csv', 'rb') as f:
        file_data = f.read()

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="test_buh.csv"\r\n'
        f'Content-Type: text/csv\r\n\r\n'
        f'{file_data.decode("utf-8")}\r\n'
        f'--{boundary}--\r\n'
    )

    try:
        req = urllib.request.Request(url, body.encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req) as response:
            print(f"Статус: {response.status}")
            result = response.read().decode('utf-8')
            
            if 'Сопоставление колонок' in result:
                print("Страница сопоставления открыта")
                
                mapping_data = {
                    'mapping': '1',
                    'map_inventory_number': 'inventory_number',
                    'map_name': 'name',
                    'map_acquisition_date': 'acquisition_date',
                    'map_initial_cost': 'initial_cost',
                    'map_wear_percent': 'wear_percent',
                    'map_quantity': 'quantity',
                    'map_accounting_status': 'accounting_status',
                    'map_category': 'category',
                    'clear_data': 'on'
                }
                
                encoded_data = urllib.parse.urlencode(mapping_data)
                headers2 = {'Content-Type': 'application/x-www-form-urlencoded'}
                
                req2 = urllib.request.Request(url, encoded_data.encode('utf-8'), headers=headers2)
                with urllib.request.urlopen(req2) as response2:
                    print(f"Статус импорта: {response2.status}")
                    result2 = response2.read().decode('utf-8')
                    
                    if 'Импорт успешен' in result2:
                        print("Импорт бух успешен!")
                        return True
                    else:
                        print(f"Результат: {len(result2)} символов")
                        return False
            else:
                print("Страница сопоставления НЕ открыта")
                return False
                
    except Exception as e:
        print(f"Ошибка: {e}")
        return False
    finally:
        if os.path.exists('test_buh.csv'):
            os.remove('test_buh.csv')

# Запуск тестов
fact_result = test_import_fact()
buh_result = test_import_buh()

print(f"\n=== ИТОГИ ===")
print(f"Импорт факта: {'УСПЕШНО' if fact_result else 'ПРОБЛЕМА'}")
print(f"Импорт бух: {'УСПЕШНО' if buh_result else 'ПРОБЛЕМА'}")

if fact_result and buh_result:
    print("\nОБА ИМПОРТА РАБОТАЮТ!")
    print("Теперь проверьте в браузере:")
    print("- http://127.0.0.1:5000/inventory_import - импорт факта")
    print("- http://127.0.0.1:5000/assets - импорт бух")
else:
    print("\nЕСТЬ ПРОБЛЕМЫ С ИМПОРТОМ")
