import urllib.request

# Проверяем фильтр по ID объекта
response = urllib.request.urlopen('http://127.0.0.1:5000/history?asset_id=2641')
html = response.read().decode('utf-8')

print("Проверка фильтра по ID объекта:")
if 'value="2641"' in html:
    print("Фильтр ID объекта установлен в 2641")

# Проверяем фильтры по датам
response2 = urllib.request.urlopen('http://127.0.0.1:5000/history?date_from=2026-02-04&date_to=2026-02-04')
html2 = response2.read().decode('utf-8')

print("\nПроверка фильтров по датам:")
if 'value="2026-02-04"' in html2:
    print("Фильтры дат установлены корректно")

# Проверяем комбинированные фильтры
response3 = urllib.request.urlopen('http://127.0.0.1:5000/history?asset_id=2641&date_from=2026-02-04')
html3 = response3.read().decode('utf-8')

print("\nПроверка комбинированных фильтров:")
if 'value="2641"' in html3 and 'value="2026-02-04"' in html3:
    print("Комбинированные фильтры работают")

print("\nПроверка ссылок на объекты:")
if 'href="/asset/2641"' in html:
    print("Ссылка на объект 2641 есть в таблице")
