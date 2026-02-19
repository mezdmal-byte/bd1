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
        print(f"- {page_name}: ошибка загрузки")
        return False

print("=== Тестирование исправлений ===\n")

# Тест 1: История с фильтрами
print("1. История изменений с фильтрами:")
test_page("http://127.0.0.1:5000/history", "История изменений", "Экспорт CSV")
test_page("http://127.0.0.1:5000/history?asset_id=2641", "История с фильтром", "2641")

# Тест 2: Импорт факта
print("\n2. Импорт фактической инвентаризации:")
test_page("http://127.0.0.1:5000/inventory_import", "Импорт факта", "Перетащите файл")

# Тест 3: Бух отчетность (импорт)
print("\n3. Бух отчетность:")
test_page("http://127.0.0.1:5000/assets", "Бух отчетность", "Загрузить таблицу")

print("\n=== Проверка завершена ===")
