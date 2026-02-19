import urllib.request

def test_page(url, name, expected):
    try:
        response = urllib.request.urlopen(url)
        html = response.read().decode('utf-8')
        
        if expected in html:
            print(f"+ {name}: работает")
            return True
        else:
            print(f"- {name}: проблема")
            return False
    except Exception as e:
        print(f"- {name}: ошибка {e}")
        return False

print("=== БЫСТРАЯ ПРОВЕРКА ===\n")

# Тесты
tests = [
    ("http://127.0.0.1:5000/", "Главная страница", "Система учета"),
    ("http://127.0.0.1:5000/assets", "Бух отчетность", "Бух отчетность"),
    ("http://127.0.0.1:5000/inventory_import", "Импорт факта", "Импорт фактической инвентаризации"),
    ("http://127.0.0.1:5000/history", "История изменений", "История изменений всех объектов"),
    ("http://127.0.0.1:5000/inventory", "Инвентаризация", "Инвентаризация"),
    ("http://127.0.0.1:5000/facts", "Факт", "Факт (инвентаризация)")
]

results = []
for url, name, expected in tests:
    results.append(test_page(url, name, expected))

print(f"\n=== РЕЗУЛЬТАТ ===")
print(f"Работает: {sum(results)}/{len(results)}")
print(f"Статус: {'✅ ВСЕ РАБОТАЕТ' if all(results) else '❌ ЕСТЬ ПРОБЛЕМЫ'}")
