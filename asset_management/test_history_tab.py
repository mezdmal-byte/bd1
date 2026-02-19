import urllib.request

# Проверяем вкладку истории
response = urllib.request.urlopen('http://127.0.0.1:5000/asset/2641?tab=history')
html = response.read().decode('utf-8')

print("Проверка вкладки истории:")
if 'id="history-tab"' in html:
    print("Контент истории найден")
if 'id="main-tab"' in html:
    print("Основной контент найден")
if 'tab-content active' in html:
    print("Активный контент найден")

# Проверяем, что история активна
if 'id="history-tab"' in html and 'tab-content active' in html:
    history_pos = html.find('id="history-tab"')
    active_pos = html.find('tab-content active', history_pos)
    if active_pos != -1 and active_pos < history_pos + 500:  # в пределах 500 символов
        print("Вкладка истории активна!")
    else:
        print("Вкладка истории неактивна")

# Проверяем наличие таблицы с историей
if 'История изменений объекта' in html:
    print("Заголовок истории найден")
if 'Поле' in html and 'Было' in html and 'Стало' in html:
    print("Таблица истории найдена")
