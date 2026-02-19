import urllib.request

def test_page(url, page_name, expected_content):
    try:
        response = urllib.request.urlopen(url)
        html = response.read().decode('utf-8')
        
        if expected_content in html:
            print(f"✅ {page_name}: работает")
            return True
        else:
            print(f"❌ {page_name}: контент не найден")
            return False
    except Exception as e:
        print(f"❌ {page_name}: ошибка {e}")
        return False

print("=== Тестирование новых функций ===\n")

# Тест 1: Улучшенная страница /history
print("1. Улучшенная история изменений:")
test_page("http://127.0.0.1:5000/history", "История изменений", "Экспорт CSV")
test_page("http://127.0.0.1:5000/history?export=csv", "Экспорт CSV", "ID объекта")

# Тест 2: Гибкий импорт /import
print("\n2. Гибкий импорт Excel:")
test_page("http://127.0.0.1:5000/import", "Импорт Excel", "Загрузить таблицу")

# Тест 3: Умный импорт факта /inventory_import
print("\n3. Умный импорт факта:")
test_page("http://127.0.0.1:5000/inventory_import", "Импорт факта", "Перетащите файл")

# Тест 4: Навигация
print("\n4. Проверка навигации:")
response = urllib.request.urlopen('http://127.0.0.1:5000')
html = response.read().decode('utf-8')

if 'Импорт факта' in html:
    print("✅ Навигация: ссылка 'Импорт факта' добавлена")
else:
    print("❌ Навигация: ссылка 'Импорт факта' не найдена")

if 'История изменений' in html:
    print("✅ Навигация: ссылка 'История изменений' добавлена")
else:
    print("❌ Навигация: ссылка 'История изменений' не найдена")

print("\n=== Проверка завершена ===")
