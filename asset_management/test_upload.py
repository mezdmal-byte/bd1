import requests
import os

# Тест загрузки файла
url = 'http://127.0.0.1:5000/inventory_import'

# Подготовка файла
files = {'file': ('test_sample.csv', open('test_sample.csv', 'rb'), 'text/csv')}

try:
    response = requests.post(url, files=files)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.text[:200]}...")
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    if os.path.exists('test_sample.csv'):
        os.remove('test_sample.csv')
