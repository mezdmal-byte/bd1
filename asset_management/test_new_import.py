import urllib.request
import urllib.parse
import os

print("=== ТЕСТ НОВОГО ИМПОРТА ===")

# Создаем тестовый файл
csv_content = """inventory_number,name,acquisition_date,initial_cost,wear_percent
2641,Тестовый компьютер,2024-01-01,50000.00,10
2642,Тестовый монитор,2024-01-02,15000.00,5"""

with open('test_import.csv', 'w', encoding='utf-8') as f:
    f.write(csv_content)

# Отправляем файл
with open('test_import.csv', 'rb') as f:
    file_data = f.read()

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test_import.csv"\r\n'
    f'Content-Type: text/csv\r\n\r\n'
    f'{file_data.decode("utf-8")}\r\n'
    f'--{boundary}--\r\n'
)

try:
    req = urllib.request.Request('http://127.0.0.1:5000/import', 
                                body.encode('utf-8'), 
                                headers=headers)
    
    with urllib.request.urlopen(req) as response:
        print(f"Статус: {response.status}")
        result = response.read().decode('utf-8')
        
        if 'Сопоставление колонок' in result:
            print("Страница сопоставления открыта")
            
            # Теперь подтверждаем импорт
            mapping_data = {
                'confirm_import': '1',
                'filename': 'test_import.csv',
                'map_inventory_number': 'inventory_number',
                'map_name': 'name',
                'map_acquisition_date': 'acquisition_date',
                'map_initial_cost': 'initial_cost',
                'map_wear_percent': 'wear_percent'
            }
            
            encoded_data = urllib.parse.urlencode(mapping_data)
            headers2 = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            req2 = urllib.request.Request('http://127.0.0.1:5000/import',
                                         encoded_data.encode('utf-8'),
                                         headers=headers2)
            
            with urllib.request.urlopen(req2) as response2:
                print(f"Статус импорта: {response2.status}")
                result2 = response2.read().decode('utf-8')
                
                if 'Импортировано' in result2:
                    print("Импорт успешен!")
                else:
                    print(f"Результат: {len(result2)} символов")
        else:
            print("Страница сопоставления НЕ открыта")
            print("Ответ:", result[:200])
            
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    if os.path.exists('test_import.csv'):
        os.remove('test_import.csv')

print("\nТеперь проверьте в браузере:")
print("1. http://127.0.0.1:5000/import - страница загрузки")
print("2. Загрузите тестовый файл")
print("3. Проверьте, появляется ли предпросмотр и сопоставление")
