import requests
from bs4 import BeautifulSoup

# Проверяем основную вкладку
response = requests.get('http://127.0.0.1:5000/asset/2641')
soup = BeautifulSoup(response.text, 'html.parser')

# Проверяем наличие вкладок
tabs = soup.find_all(class_='tab')
print(f"Найдено вкладок: {len(tabs)}")
for tab in tabs:
    print(f"- {tab.text.strip()}")

# Проверяем активную вкладку
active_tab = soup.find(class_='tab active')
if active_tab:
    print(f"Активная вкладка: {active_tab.text.strip()}")

# Проверяем наличие контента вкладок
main_content = soup.find(id='main-tab')
history_content = soup.find(id='history-tab')

print(f"Основной контент найден: {bool(main_content)}")
print(f"Контент истории найден: {bool(history_content)}")

if main_content:
    print(f"Основной контент активен: {'active' in main_content.get('class', [])}")
if history_content:
    print(f"Контент истории активен: {'active' in history_content.get('class', [])}")
