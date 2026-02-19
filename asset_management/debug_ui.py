import urllib.request

def check_ui_pages():
    print("=== ПРОВЕРКА UI СТРАНИЦ ===\n")
    
    # Проверка импорта факта
    try:
        response = urllib.request.urlopen('http://127.0.0.1:5000/inventory_import')
        html = response.read().decode('utf-8')
        
        print("1. Импорт факта:")
        if 'Импорт фактической инвентаризации' in html:
            print("  + Заголовок найден")
        else:
            print("  - Заголовок НЕ найден")
            
        if 'form method="post"' in html:
            print("  + Форма POST найдена")
        else:
            print("  - Форма POST НЕ найдена")
            
        if 'fileInput' in html:
            print("  + Поле файла найдено")
        else:
            print("  - Поле файла НЕ найдено")
            
        if 'Загрузить и обработать' in html:
            print("  + Кнопка отправки найдена")
        else:
            print("  - Кнопка отправки НЕ найдена")
            
        if 'handleFileSelect' in html:
            print("  + JavaScript найден")
        else:
            print("  - JavaScript НЕ найден")
            
    except Exception as e:
        print(f"1. Импорт факта: ошибка {e}")
    
    # Проверка импорта бух
    try:
        response = urllib.request.urlopen('http://127.0.0.1:5000/assets')
        html = response.read().decode('utf-8')
        
        print("\n2. Импорт бух:")
        if 'Загрузить таблицу из 1С' in html:
            print("  + Заголовок найден")
        else:
            print("  - Заголовок НЕ найден")
            
        if 'action="/import"' in html:
            print("  + Форма с action=/import найдена")
        else:
            print("  - Форма с action=/import НЕ найдена")
            
        if 'fileInput' in html:
            print("  + Поле файла найдено")
        else:
            print("  - Поле файла НЕ найдено")
            
        if 'Выбрать файл' in html:
            print("  + Кнопка выбора найдена")
        else:
            print("  - Кнопка выбора НЕ найдена")
            
        if 'handleFileSelect' in html:
            print("  + JavaScript найден")
        else:
            print("  - JavaScript НЕ найден")
            
    except Exception as e:
        print(f"2. Импорт бух: ошибка {e}")
    
    # Проверка истории
    try:
        response = urllib.request.urlopen('http://127.0.0.1:5000/history')
        html = response.read().decode('utf-8')
        
        print("\n3. История изменений:")
        if 'История изменений всех объектов' in html:
            print("  + Заголовок найден")
        else:
            print("  - Заголовок НЕ найден")
            
        if 'name="asset_id"' in html:
            print("  + Фильтр ID объекта найден")
        else:
            print("  - Фильтр ID объекта НЕ найден")
            
        if 'Экспорт CSV' in html:
            print("  + Экспорт CSV найден")
        else:
            print("  - Экспорт CSV НЕ найден")
            
    except Exception as e:
        print(f"3. История: ошибка {e}")

check_ui_pages()
