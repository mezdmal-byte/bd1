import urllib.request
import urllib.parse
import os

def test_browser_simulation():
    print("=== ТЕСТИРОВАНИЕ КАК В БРАУЗЕРЕ ===\n")
    
    # Тест 1: Импорт факта - проверка формы
    print("1. Импорт факта:")
    try:
        # Сначала получаем страницу
        response = urllib.request.urlopen('http://127.0.0.1:5000/inventory_import')
        html = response.read().decode('utf-8')
        
        # Проверяем наличие формы
        if 'enctype="multipart/form-data"' in html:
            print("  + Форма multipart/form-data найдена")
        else:
            print("  - Форма multipart/form-data НЕ найдена")
            
        # Создаем тестовый файл
        csv_content = """inventory_number,name,serial_number,condition_status,physical_label_status,location,notes
2641,Тестовый компьютер,12345,Исправно,Есть,Кабинет 101,Тестовая запись"""
        
        with open('test_fact.csv', 'w', encoding='utf-8') as f:
            f.write(csv_content)
        
        # Отправляем файл как в браузере
        with open('test_fact.csv', 'rb') as f:
            file_data = f.read()
        
        # Создаем multipart/form-data как браузер
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="test_fact.csv"\r\n'
            f'Content-Type: text/csv\r\n\r\n'
            f'{file_data.decode("utf-8")}\r\n'
            f'--{boundary}--\r\n'
        )
        
        req = urllib.request.Request('http://127.0.0.1:5000/inventory_import', 
                                    body.encode('utf-8'), 
                                    headers=headers)
        
        with urllib.request.urlopen(req) as response:
            print(f"  + Статус: {response.status}")
            result = response.read().decode('utf-8')
            
            if 'Сопоставление колонок' in result:
                print("  + Страница сопоставления открыта")
                
                # Теперь подтверждаем импорт
                mapping_data = {
                    'confirm_import': '1',
                    'map_inventory_number': 'inventory_number',
                    'map_name': 'name',
                    'map_serial_number': 'serial_number',
                    'map_condition_status': 'condition_status',
                    'map_physical_label_status': 'physical_label_status',
                    'map_location': 'location',
                    'map_notes': 'notes'
                }
                
                encoded_data = urllib.parse.urlencode(mapping_data)
                headers2 = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                req2 = urllib.request.Request('http://127.0.0.1:5000/inventory_import',
                                             encoded_data.encode('utf-8'),
                                             headers=headers2)
                
                with urllib.request.urlopen(req2) as response2:
                    print(f"  + Статус импорта: {response2.status}")
                    result2 = response2.read().decode('utf-8')
                    
                    if 'Импорт завершен' in result2:
                        print("  + Импорт успешен!")
                        return True
                    elif 'Ошибка при импорте' in result2:
                        print("  - Ошибка импорта")
                    else:
                        print(f"  ? Неизвестный результат: {len(result2)} символов")
            else:
                print("  - Страница сопоставления НЕ открыта")
                
    except Exception as e:
        print(f"  - Ошибка: {e}")
        return False
    finally:
        if os.path.exists('test_fact.csv'):
            os.remove('test_fact.csv')
    
    return False

# Запуск теста
result = test_browser_simulation()

if result:
    print("\n✅ Импорт работает!")
else:
    print("\n❌ Проблемы с импортом")
    print("\nВозможные причины:")
    print("1. JavaScript в браузере блокирует отправку")
    print("2. Файл не выбран или пустой")
    print("3. Ошибка в обработке формы")
    print("\nРекомендации:")
    print("- Откройте http://127.0.0.1:5000/inventory_import в браузере")
    print("- Выберите файл и нажмите кнопку")
    print("- Проверьте консоль браузера на ошибки")
