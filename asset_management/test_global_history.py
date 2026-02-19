import urllib.request

# Проверяем глобальную историю
response = urllib.request.urlopen('http://127.0.0.1:5000/history')
html = response.read().decode('utf-8')

print("Проверка глобальной истории изменений:")
if 'История изменений всех объектов' in html:
    print("Заголовок страницы найден")
if 'ID объекта' in html and 'Тип объекта' in html:
    print("Таблица с колонками найдена")
if 'filter-group' in html:
    print("Фильтры найдены")
if 'asset_id' in html:
    print("Фильтр по ID объекта найден")
if 'date_from' in html and 'date_to' in html:
    print("Фильтры по датам найдены")

# Проверяем наличие данных
if 'Показано записей:' in html:
    print("Данные в таблице есть")
else:
    print("Данных в таблице нет или пусто")

print("\nПроверка навигации:")
if 'active' in html and 'history' in html:
    print("Вкладка истории активна в меню")

# Проверяем ссылку на объект
if 'href="/asset/' in html:
    print("Ссылки на объекты в таблице есть")
