import urllib.request

try:
    response = urllib.request.urlopen('http://127.0.0.1:5000/inventory_import')
    html = response.read().decode('utf-8')
    print('Страница импорта факта загружается')
    
    if 'Импорт фактической инвентаризации' in html:
        print('Заголовок найден')
    else:
        print('Заголовок НЕ найден')
        
    if 'form method="post"' in html:
        print('Форма найдена')
    else:
        print('Форма НЕ найдена')
        
    if 'fileInput' in html:
        print('Поле файла найдено')
    else:
        print('Поле файла НЕ найдено')
        
except Exception as e:
    print(f'Ошибка импорта факта: {e}')
