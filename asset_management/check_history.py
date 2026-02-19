import sqlite3

conn = sqlite3.connect('assets.db')
cursor = conn.cursor()

# Проверяем историю изменений
cursor.execute('''
    SELECT entity_type, entity_id, field_changed, old_value, new_value, reason, changed_at 
    FROM change_history 
    ORDER BY changed_at DESC 
    LIMIT 10
''')

history = cursor.fetchall()
if history:
    print('Recent changes:')
    for row in history:
        print(f'{row[6]} - {row[0]} ID:{row[1]} - {row[2]}: "{row[3]}" -> "{row[4]}" ({row[5]})')
else:
    print('No changes found in history')

cursor.execute('SELECT COUNT(*) FROM change_history')
print(f'Total changes: {cursor.fetchone()[0]}')

conn.close()
