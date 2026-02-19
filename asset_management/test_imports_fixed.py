import urllib.request
import urllib.parse
import os

print("=== ТЕСТ ИСПРАВЛЕННЫХ ИМПОРТОВ ===")

# Тест 1: Импорт бух отчетности
print("\n1. Тест импорта бух отчетности:")
csv_content = """inventory_number,name,acquisition_date,initial_cost,wear_percent
2641,Тестовый компьютер,2024-01-01,50000.00,10
2642,Тестовый монитор,2024-01-02,15000.00,5"""

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
    req = urllib.request.Request('http://127.0.0.1:5000/import', 
                                body.encode('utf-8'), 
                                headers=headers)
    
    with urllib.request.urlopen(req) as response:
        print(f"  Статус: {response.status}")
        result = response.read().decode('utf-8')
        
        if 'Сопоставление колонок' in result:
            print("  ✅ Страница сопоставления открыта")
        else:
            print("  ❌ Страница сопоставления НЕ открыта")
            
except Exception as e:
    print(f"  ❌ Ошибка: {e}")
finally:
    if os.path.exists('test_buh.csv'):
        os.remove('test_buh.csv')

# Тест 2: Импорт факта
print("\n2. Тест импорта факта:")
csv_content = """inventory_number,name,serial_number,condition_status,physical_label_status,location,notes
2641,Тестовый компьютер,12345,Исправно,Есть,Кабинет 101,Тестовая запись"""

with open('test_fact.csv', 'w', encoding='utf-8') as f:
    f.write(csv_content)

with open('test_fact.csv', 'rb') as f:
    file_data = f.read()

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test_fact.csv"\r\n'
    f'Content-Type: text/csv\r\n\r\n'
    f'{file_data.decode("utf-8")}\r\n'
    f'--{boundary}--\r\n'
)

try:
    req = urllib.request.Request('http://127.0.0.1:5000/inventory_import', 
                                body.encode('utf-8'), 
                                headers=headers)
    
    with urllib.request.urlopen(req) as response:
        print(f"  Статус: {response.status}")
        result = response.read().decode('utf-8')
        
        if 'Сопоставление колонок' in result:
            print("  ✅ Страница сопоставления открыта")
        else:
            print("  ❌ Страница сопоставления НЕ открыта")
            
except Exception as e:
    print(f"  ❌ Ошибка: {e}")
finally:
    if os.path.exists('test_fact.csv'):
        os.remove('test_fact.csv')

print("\n=== РЕЗУЛЬТАТЫ ===")
print("Оба импорта должны показывать страницу сопоставления колонок")
print("Если страницы не открываются - есть проблемы с кодом")
