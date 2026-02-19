import urllib.request
import urllib.parse
import os

# Шаг 1: Загрузка файла для сопоставления
url = 'http://127.0.0.1:5000/import'

csv_content = """inventory_number,name,acquisition_date,initial_cost,wear_percent,quantity,accounting_status,category
2641,Тестовый компьютер,2024-01-01,50000.00,10,1,Введено в эксплуатацию,Техника"""

with open('test_mapping.csv', 'w', encoding='utf-8') as f:
    f.write(csv_content)

# Загрузка файла
with open('test_mapping.csv', 'rb') as f:
    file_data = f.read()

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}'
}

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test_mapping.csv"\r\n'
    f'Content-Type: text/csv\r\n\r\n'
    f'{file_data.decode("utf-8")}\r\n'
    f'--{boundary}--\r\n'
)

try:
    req = urllib.request.Request(url, body.encode('utf-8'), headers=headers)
    with urllib.request.urlopen(req) as response:
        print(f"Шаг 1 - Статус: {response.status}")
        result = response.read().decode('utf-8')
        
        if 'Сопоставление колонок' in result:
            print("✅ Страница сопоставления открыта")
            
            # Ищем форму сопоставления
            if 'name="mapping"' in result:
                print("✅ Форма сопоставления найдена")
                
                # Шаг 2: Подтверждение сопоставления
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
                
                # Формируем данные для POST
                encoded_data = urllib.parse.urlencode(mapping_data)
                headers2 = {'Content-Type': 'application/x-www-form-urlencoded'}
                
                req2 = urllib.request.Request(url, encoded_data.encode('utf-8'), headers=headers2)
                with urllib.request.urlopen(req2) as response2:
                    print(f"Шаг 2 - Статус: {response2.status}")
                    result2 = response2.read().decode('utf-8')
                    
                    if 'Импорт успешен' in result2:
                        print("✅ Импорт успешен!")
                    elif 'Ошибка при импорте' in result2:
                        print("❌ Ошибка импорта")
                    else:
                        print(f"Результат: {result2[:200]}...")
            else:
                print("❌ Форма сопоставления НЕ найдена")
        else:
            print(f"❌ Страница сопоставления НЕ открыта")
            
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    if os.path.exists('test_mapping.csv'):
        os.remove('test_mapping.csv')
