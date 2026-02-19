import urllib.request
import urllib.parse
import os

# Тест загрузки файла
url = 'http://127.0.0.1:5000/inventory_import'

# Подготовка файла
with open('test_sample.csv', 'rb') as f:
    file_data = f.read()

# Создаем multipart/form-data
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}'
}

# Формируем тело запроса
body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test_sample.csv"\r\n'
    f'Content-Type: text/csv\r\n\r\n'
    f'{file_data.decode("utf-8")}\r\n'
    f'--{boundary}--\r\n'
)

try:
    req = urllib.request.Request(url, body.encode('utf-8'), headers=headers)
    with urllib.request.urlopen(req) as response:
        print(f"Статус: {response.status}")
        print(f"Ответ: {response.read().decode('utf-8')[:200]}...")
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    if os.path.exists('test_sample.csv'):
        os.remove('test_sample.csv')
