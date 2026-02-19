import urllib.request

try:
    response = urllib.request.urlopen('http://127.0.0.1:5000/assets')
    html = response.read().decode('utf-8')
    print('Страница бух отчетности загружается')
    
    if 'Бух отчетность' in html:
        print('Заголовок найден')
    else:
        print('Заголовок НЕ найден')
        
    if 'Загрузить таблицу' in html:
        print('Кнопка загрузки найдена')
    else:
        print('Кнопка загрузки НЕ найдена')
        
    if 'form method="post"' in html:
        print('Форма найдена')
    else:
        print('Форма НЕ найдена')
        
except Exception as e:
    print(f'Ошибка бух отчетности: {e}')
