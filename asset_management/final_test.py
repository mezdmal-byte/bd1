import urllib.request

def test_page(url, page_name, expected_content):
    try:
        response = urllib.request.urlopen(url)
        html = response.read().decode('utf-8')
        
        if expected_content in html:
            print(f"+ {page_name}: работает")
            return True
        else:
            print(f"- {page_name}: проблема")
            return False
    except Exception as e:
        print(f"- {page_name}: ошибка {e}")
        return False

print("=== ИТОГОВОЕ ТЕСТИРОВАНИЕ ===\n")

# Тест 1: История изменений
print("1. История изменений:")
test_page("http://127.0.0.1:5000/history", "История изменений", "Экспорт CSV")
test_page("http://127.0.0.1:5000/history?asset_id=2641", "Фильтр по ID", "2641")
test_page("http://127.0.0.1:5000/history?field_changed=serial_number", "Фильтр по полю", "serial_number")

# Тест 2: Импорт факта
print("\n2. Умный импорт факта:")
test_page("http://127.0.0.1:5000/inventory_import", "Импорт факта", "Перетащите файл")

# Тест 3: Бух отчетность и импорт
print("\n3. Бух отчетность:")
test_page("http://127.0.0.1:5000/assets", "Бух отчетность", "Загрузить таблицу")

# Тест 4: Навигация
print("\n4. Навигация:")
response = urllib.request.urlopen('http://127.0.0.1:5000')
html = response.read().decode('utf-8')

nav_items = ['Импорт факта', 'История изменений', 'Бух отчетность', 'Дашборд']
for item in nav_items:
    if item in html:
        print(f"+ Навигация: {item}")
    else:
        print(f"- Навигация: {item} не найдена")

print("\n=== ГОТОВО! ===")
