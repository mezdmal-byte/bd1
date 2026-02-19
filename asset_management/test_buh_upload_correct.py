import urllib.request
import urllib.parse
import os

# Тест загрузки файла для бух отчетности
url = 'http://127.0.0.1:5000/import'

# Создаем тестовый Excel файл
csv_content = """inventory_number,name,acquisition_date,initial_cost,wear_percent,quantity,accounting_status,category
2641,Тестовый компьютер,2024-01-01,50000.00,10,1,Введено в эксплуатацию,Техника
2642,Тестовый монитор,2024-01-02,15000.00,5,1,Введено в эксплуатацию,Техника"""

with open('test_buh.csv', 'w', encoding='utf-8') as f:
    f.write(csv_content)

# Подготовка файла
with open('test_buh.csv', 'rb') as f:
    file_data = f.read()

# Создаем multipart/form-data
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}'
}

# Формируем тело запроса
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
            print("Импорт работает - страница сопоставления открыта")
        elif 'Импорт успешен' in result:
            print("Импорт успешен")
        elif 'Ошибка при импорте' in result:
            print("Ошибка импорта")
        else:
            print(f"Ответ: {result[:300]}...")
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    if os.path.exists('test_buh.csv'):
        os.remove('test_buh.csv')
