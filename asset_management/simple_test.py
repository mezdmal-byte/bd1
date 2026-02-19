import urllib.request

def test_page(url, page_name, tests):
    try:
        response = urllib.request.urlopen(url)
        html = response.read().decode('utf-8')
        
        results = []
        for test_name, expected_content in tests:
            if expected_content in html:
                print(f"  + {test_name}")
                results.append(True)
            else:
                print(f"  - {test_name}")
                results.append(False)
        
        return all(results)
    except Exception as e:
        print(f"  X Ошибка загрузки: {e}")
        return False

print("=== КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ ===\n")

# Тест 1: Умный импорт факта
print("1. Умный импорт факта:")
success1 = test_page("http://127.0.0.1:5000/inventory_import", "Импорт факта", [
    ("Загрузка страницы", "Перетащите файл"),
    ("Форма загрузки", 'enctype="multipart/form-data"'),
    ("JavaScript", "handleFileSelect"),
    ("Кнопка выбора", "Выбрать файл")
])

# Тест 2: Бух отчетность и импорт Excel
print("\n2. Бух отчетность:")
success2 = test_page("http://127.0.0.1:5000/assets", "Бух отчетность", [
    ("Загрузка страницы", "Бух отчетность (1С)"),
    ("Форма загрузки", "Загрузить таблицу"),
    ("Поддержка форматов", ".xlsx"),
    ("Кнопка загрузки", "Выбрать файл")
])

# Тест 3: История изменений с фильтрами
print("\n3. История изменений:")
success3 = test_page("http://127.0.0.1:5000/history", "История изменений", [
    ("Загрузка страницы", "История изменений всех объектов"),
    ("Фильтры", "ID объекта"),
    ("Экспорт CSV", "Экспорт CSV"),
    ("Пагинация", "Предыдущая")
])

# Тест 4: Навигация
print("\n4. Навигация:")
try:
    response = urllib.request.urlopen('http://127.0.0.1:5000')
    html = response.read().decode('utf-8')
    
    nav_items = [
        ("Дашборд", "Дашборд"),
        ("Бух отчетность", "Бух отчетность"),
        ("Приход", "Приход"),
        ("Инвентаризация", "Инвентаризация"),
        ("Импорт факта", "Импорт факта"),
        ("Несоответствия", "Несоответствия"),
        ("Факт", "Факт"),
        ("История изменений", "История изменений")
    ]
    
    nav_success = True
    for item_name, item_content in nav_items:
        if item_content in html:
            print(f"  + {item_name}")
        else:
            print(f"  - {item_name}")
            nav_success = False
    
    success4 = nav_success
except Exception as e:
    print(f"  X Ошибка навигации: {e}")
    success4 = False

# Итоги
print(f"\n=== РЕЗУЛЬТАТЫ ===")
print(f"Импорт факта: {'OK' if success1 else 'ПРОБЛЕМЫ'}")
print(f"Бух отчетность: {'OK' if success2 else 'ПРОБЛЕМЫ'}")
print(f"История изменений: {'OK' if success3 else 'ПРОБЛЕМЫ'}")
print(f"Навигация: {'OK' if success4 else 'ПРОБЛЕМЫ'}")

overall = success1 and success2 and success3 and success4
print(f"\nОБЩИЙ СТАТУС: {'ВСЕ РАБОТАЕТ' if overall else 'ЕСТЬ ПРОБЛЕМЫ'}")
