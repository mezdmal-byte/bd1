import sqlite3

conn = sqlite3.connect('assets.db')
cursor = conn.cursor()

# Проверяем количество объектов
cursor.execute('SELECT COUNT(*) FROM assets')
print('Assets count:', cursor.fetchone()[0])

# Показываем первые 3 объекта
cursor.execute('SELECT id, inventory_number, name FROM assets LIMIT 3')
print('Sample assets:')
for row in cursor.fetchall():
    print(f'ID: {row[0]}, Inv: {row[1]}, Name: {row[2]}')

# Проверяем историю изменений
cursor.execute('SELECT COUNT(*) FROM change_history')
print('Change history count:', cursor.fetchone()[0])

conn.close()
