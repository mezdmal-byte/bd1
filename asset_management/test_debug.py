import urllib.request
import urllib.parse
import os

print("=== ТЕСТ С ОТЛАДКОЙ ===")

# Создаем тестовый файл
csv_content = """inventory_number,name,serial_number,condition_status,physical_label_status,location,notes
2641,Тестовый компьютер,12345,Исправно,Есть,Кабинет 101,Тестовая запись"""

with open('test_fact.csv', 'w', encoding='utf-8') as f:
    f.write(csv_content)

# Отправляем файл
with open('test_fact.csv', 'rb') as f:
    file_data = f.read()

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

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
        print(f"Статус: {response.status}")
        result = response.read().decode('utf-8')
        
        if 'Сопоставление колонок' in result:
            print("Страница сопоставления открыта")
        else:
            print("Страница сопоставления НЕ открыта")
            print("Ответ:", result[:200])
            
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    if os.path.exists('test_fact.csv'):
        os.remove('test_fact.csv')

print("\nПроверьте логи сервера в консоли для отладки")
