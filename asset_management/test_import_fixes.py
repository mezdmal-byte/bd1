import urllib.request

def test_page(url, page_name, expected_content):
    try:
        response = urllib.request.urlopen(url)
        html = response.read().decode('utf-8')
        
        if expected_content in html:
            print(f"+ {page_name}: работает")
            return True
        else:
            print(f"- {page_name}: проблема с '{expected_content}'")
            return False
    except Exception as e:
        print(f"- {page_name}: ошибка {e}")
        return False

print("=== Тестирование исправлений импорта ===\n")

# Тест 1: Импорт факта
print("1. Умный импорт факта:")
test_page("http://127.0.0.1:5000/inventory_import", "Импорт факта", "Перетащите файл")

# Тест 2: Бух отчетность
print("\n2. Бух отчетность:")
test_page("http://127.0.0.1:5000/assets", "Бух отчетность", "Загрузить таблицу")

# Тест 3: История изменений
print("\n3. История изменений:")
test_page("http://127.0.0.1:5000/history", "История изменений", "Экспорт CSV")

print("\n=== Проверка завершена ===")
