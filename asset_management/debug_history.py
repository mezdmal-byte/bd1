import urllib.request

try:
    response = urllib.request.urlopen('http://127.0.0.1:5000/history')
    html = response.read().decode('utf-8')
    
    print("Статус: страница загружена")
    print("Длина HTML:", len(html))
    
    # Ищем конкретные элементы
    if 'История изменений всех объектов' in html:
        print("+ Заголовок найден")
    else:
        print("- Заголовок не найден")
    
    if 'Экспорт CSV' in html:
        print("+ Кнопка экспорта найдена")
    else:
        print("- Кнопка экспорта не найдена")
        
    if 'ID объекта' in html:
        print("+ Таблица найдена")
    else:
        print("- Таблица не найдена")
        
    # Ищем ошибки
    if 'error' in html.lower() or 'ошибка' in html.lower():
        print("! Есть ошибки в HTML")
        
    # Показываем первые 500 символов
    print("\nПервые 500 символов:")
    print(html[:500])
    
except Exception as e:
    print(f"Ошибка: {e}")
