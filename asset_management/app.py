from flask import Flask, render_template_string, request, redirect, url_for, flash
import sqlite3
import pandas as pd
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DATABASE = 'assets.db'

# Фильтр для форматирования цены
@app.template_filter('currency')
def currency_filter(value):
    if value is None or value == '':
        return "—"
    try:
        return f"{float(value):,.2f} ₽"
    except:
        return "—"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # Делаем путь к schema.sql независимым от текущей директории
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = f.read()
        conn = get_db()
        conn.executescript(schema)
        conn.commit()
        conn.close()


# Всегда применяем схему при старте, чтобы создать недостающие таблицы
init_db()

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Учет основных средств</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
            background: #f5f5f5; 
            font-size: 14px;
            line-height: 1.4;
            color: #2c3e50;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 16px; }
        header { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; 
            padding: 20px 24px; 
            margin-bottom: 16px; 
            border-radius: 10px; 
        }
        header h1 { font-size: 24px; margin-bottom: 6px; }
        header p { opacity: 0.9; font-size: 13px; }
        nav { 
            background: white; 
            padding: 10px 12px; 
            border-radius: 8px; 
            margin-bottom: 16px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.06); 
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        nav a { 
            text-decoration: none; 
            color: #2c3e50; 
            padding: 8px 14px; 
            border-radius: 6px; 
            display: inline-block; 
            font-weight: 500; 
            font-size: 13px;
            transition: all 0.2s; 
        }
        nav a:hover { background: #667eea; color: white; transform: translateY(-1px); }
        nav a.active { background: #667eea; color: white; }
        .card { 
            background: white; 
            padding: 18px 20px; 
            border-radius: 10px; 
            margin-bottom: 16px; 
            box-shadow: 0 2px 6px rgba(0,0,0,0.06); 
        }
        .stats { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 16px; 
            margin-bottom: 18px; 
        }
        .stat-box { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; 
            padding: 18px; 
            border-radius: 10px; 
            box-shadow: 0 4px 10px rgba(102,126,234,0.25); 
        }
        .stat-box.green { 
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); 
            box-shadow: 0 4px 10px rgba(17,153,142,0.25); 
        }
        .stat-box h3 { 
            font-size: 12px; 
            opacity: 0.9; 
            margin-bottom: 8px; 
            text-transform: uppercase; 
            letter-spacing: 0.5px; 
        }
        .stat-box .number { font-size: 28px; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #e0e0e0; }
        th { background: #f8f9fa; font-weight: 600; color: #2c3e50; position: sticky; top: 0; z-index: 1; }
        tr:hover { background: #f8f9fa; }
        .btn { 
            padding: 8px 16px; 
            border: none; 
            border-radius: 6px; 
            cursor: pointer; 
            text-decoration: none; 
            display: inline-block; 
            font-size: 13px; 
            font-weight: 500; 
            transition: all 0.2s; 
            background: #e9ecef;
            color: #2c3e50;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-primary:hover { background: #5568d3; transform: translateY(-1px); box-shadow: 0 3px 8px rgba(102,126,234,0.3); }
        .btn:hover { filter: brightness(0.97); }
        .search-box { 
            padding: 8px 10px; 
            border: 1px solid #d0d7de; 
            border-radius: 6px; 
            width: 260px; 
            max-width: 100%;
            margin-bottom: 8px; 
            font-size: 13px; 
            background: #fff;
        }
        .search-box:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 2px rgba(102,126,234,0.15); }
        .filter-group { 
            margin-bottom: 14px; 
            display: flex; 
            gap: 10px; 
            align-items: center; 
            flex-wrap: wrap; 
        }
        .upload-area { 
            border: 2px dashed #ddd; 
            padding: 30px; 
            text-align: center; 
            border-radius: 10px; 
            background: #fafafa; 
            transition: all 0.2s; 
        }
        .upload-area:hover { border-color: #667eea; background: #f0f4ff; }
        .upload-area input[type="file"] { display: none; }
        .upload-label { 
            cursor: pointer; 
            display: inline-block; 
            padding: 10px 20px; 
            background: #667eea; 
            color: white; 
            border-radius: 6px; 
            font-weight: 500; 
            font-size: 13px;
            transition: all 0.2s; 
        }
        .upload-label:hover { background: #5568d3; transform: translateY(-1px); }
        .flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-weight: 500; font-size: 13px; }
        .flash-success { background: #d4edda; color: #155724; border-left: 4px solid #28a745; }
        .flash-error { background: #f8d7da; color: #721c24; border-left: 4px solid #dc3545; }
        .table-container { overflow-x: auto; max-height: 560px; border-radius: 6px; }
        .empty-state { text-align: center; padding: 40px 20px; color: #999; }
        .empty-state-icon { font-size: 52px; margin-bottom: 16px; }
        @media (max-width: 900px) {
            header { padding: 16px 14px; }
            .card { padding: 14px 12px; }
            nav { padding: 8px 8px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏛️ Система учета основных средств</h1>
            <p>Управление оборудованием и мебелью института</p>
        </header>

        <nav>
            <a href="/" class="{{ 'active' if page == 'dashboard' }}">📊 Дашборд</a>
            <a href="/assets" class="{{ 'active' if page == 'assets' }}">📦 Бух отчетность</a>
            <a href="/incoming" class="{{ 'active' if page == 'incoming' }}">🧾 Приход</a>
            <a href="/inventory" class="{{ 'active' if page == 'inventory' }}">📋 Инвентаризация</a>
            <a href="/discrepancies" class="{{ 'active' if page == 'discrepancies' }}">⚠️ Несоответствия</a>
            <a href="/facts" class="{{ 'active' if page == 'facts' }}">📋 Факт</a>
        </nav>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>

    <script>
        function selectFile() {
            document.getElementById('fileInput').click();
        }

        function handleFileSelect(input) {
            if (input.files && input.files[0]) {
                document.getElementById('fileName').textContent = input.files[0].name;
                document.getElementById('uploadForm').submit();
            }
        }
    </script>
</body>
</html>
"""

def compute_discrepancies_row(asset_row, actual_row):
    results = []
    # Состояние: бухгалтерия "Введено в эксплуатацию", фактически != Исправно
    if actual_row:
        if actual_row['condition_status'] and asset_row['accounting_status'] == 'Введено в эксплуатацию' and actual_row['condition_status'] != 'Исправно':
            results.append(('CONDITION', 'Состояние', 'Введено', actual_row['condition_status'], 'MEDIUM'))
        # Наклейка
        if actual_row['physical_label_status'] and actual_row['physical_label_status'] != 'Есть':
            results.append(('LABEL', 'Инв. наклейка', 'Есть', actual_row['physical_label_status'], 'HIGH'))
        # Серийник
        if not (actual_row['serial_number'] and actual_row['serial_number'].strip()):
            results.append(('SERIAL', 'Серийный номер', 'Есть', 'Отсутствует', 'MEDIUM'))
    # Местоположение: если есть учетное (в notes) и фактическое поле пустое — не сравниваем, т.к. у нас одно поле
    # Дубликат инв. номера будет найден отдельным запросом, здесь пропускаем
    return results


@app.route('/')
def dashboard():
    conn = get_db()

    total_assets = conn.execute('SELECT COUNT(*) as cnt FROM assets').fetchone()['cnt']
    total_cost = conn.execute('SELECT SUM(initial_cost) as total FROM assets').fetchone()['total'] or 0

    recent_assets = conn.execute('''
        SELECT a.*, aa.notes as location_notes
        FROM assets a
        LEFT JOIN actual_assets aa ON a.id = aa.asset_id
        ORDER BY a.created_at DESC 
        LIMIT 10
    ''').fetchall()

    conn.close()

    # Форматируем данные для отображения
    assets_display = []
    for asset in recent_assets:
        assets_display.append({
            'id': asset['id'],
            'inventory_number': asset['inventory_number'] or '—',
            'name': asset['name'],
            'location': asset['location_notes'] or '—',
            'date': asset['acquisition_date'] or '—',
            'cost': asset['initial_cost'],
            'wear': f"{asset['wear_percent']}" if asset['wear_percent'] else '—'
        })

    content = """
    {% block content %}
        <div class="stats">
            <div class="stat-box blue">
                <h3>Всего объектов</h3>
                <div class="number">""" + str(total_assets) + """</div>
            </div>
            <div class="stat-box green">
                <h3>Общая стоимость</h3>
                <div class="number">{{ total_cost|currency }}</div>
            </div>
        </div>

        {% if assets_display %}
        <div class="card">
            <h2>📋 Последние загруженные объекты</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Инв. номер</th>
                            <th>Наименование</th>
                            <th>Местонахождение</th>
                            <th>Дата принятия</th>
                            <th>Стоимость</th>
                            <th>Износ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for asset in assets_display %}
                        <tr>
                            <td>{{ asset.inventory_number }}</td>
                            <td>{{ asset.name }}</td>
                            <td><small>{{ asset.location }}</small></td>
                            <td>{{ asset.date }}</td>
                            <td>{{ asset.cost|currency }}</td>
                            <td>{{ asset.wear }}%</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% else %}
        <div class="card">
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <h3>Данных пока нет</h3>
                <p style="margin-top: 10px;">Загрузите таблицу из бухгалтерии через раздел "Загрузить таблицу"</p>
                <a href="/import" class="btn btn-primary" style="margin-top: 20px;">📤 Загрузить таблицу</a>
            </div>
        </div>
        {% endif %}
    {% endblock %}
    """

    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='dashboard',
                                  assets_display=assets_display,
                                  total_cost=total_cost)


@app.route('/assets')
def assets_list():
    conn = get_db()

    search = request.args.get('search', '')
    selected_room = request.args.get('room', '').strip()
    selected_kind = request.args.get('kind', '').strip()  # Техника / Мебель (вычисляется эвристикой)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # Доступные колонки для отображения в таблице
    # key -> ('Человекочитаемый заголовок', optional width)
    available_columns = [
        ('inventory_number', 'Инв. номер', '120px'),
        ('serial_number', 'Заводской номер', '160px'),
        ('name', 'Наименование', None),
        ('category', 'Категория', '120px'),
        ('okof_code', 'ОКОФ', '110px'),
        ('acquisition_date', 'Дата принятия', '120px'),
        ('accounting_status', 'Состояние (бух)', '150px'),
        ('initial_cost', 'Стоимость', '120px'),
        ('quantity', 'Кол-во', '80px'),
        ('useful_life_months', 'Срок (мес.)', '100px'),
        ('wear_percent', 'Износ %', '90px'),
        ('location', 'Местонахождение', '220px'),
        ('created_at', 'Создано', '140px'),
        ('updated_at', 'Обновлено', '140px'),
    ]

    query = '''
        SELECT 
            a.*, 
            aa.notes as location_notes, 
            aa.serial_number as serial_number,
            (SELECT COUNT(*) FROM incoming_goods ig WHERE ig.assigned_asset_id = a.id) as incoming_count,
            (SELECT GROUP_CONCAT(ig.item_name, ', ')
               FROM incoming_goods ig
               WHERE ig.assigned_asset_id = a.id) as incoming_names
        FROM assets a
        LEFT JOIN actual_assets aa ON a.id = aa.asset_id
        WHERE 1=1
    '''
    params = []

    if search:
        # Глобальный частичный поиск по нескольким полям
        query += '''
            AND (
                a.name LIKE ?
                OR a.inventory_number LIKE ?
                OR IFNULL(a.okof_code, '') LIKE ?
                OR IFNULL(a.accounting_status, '') LIKE ?
                OR IFNULL(a.acquisition_date, '') LIKE ?
                OR EXISTS (
                    SELECT 1 FROM incoming_goods ig
                    WHERE ig.assigned_asset_id = a.id AND ig.item_name LIKE ?
                )
            )
        '''
        like = f'%{search}%'
        params.extend([like, like, like, like, like, like])

    if selected_room:
        # Фильтрация по кабинету: парсим из aa.notes, формат "Местоположение: <комната>"
        query += ' AND IFNULL(aa.notes, \'\') LIKE ?'
        params.append(f'%Местоположение: {selected_room}%')

    if date_from:
        # Сравнение по дате принятия (включительно)
        query += ' AND date(a.acquisition_date) >= date(?)'
        params.append(date_from)

    if date_to:
        query += ' AND date(a.acquisition_date) <= date(?)'
        params.append(date_to)

    query += ' ORDER BY a.id DESC'

    assets_raw = conn.execute(query, params).fetchall()

    # Форматируем для отображения
    assets_display = []
    # Эвристика определения "Техника" / "Мебель" по названию (если не задано в БД)
    def derive_kind(name_value):
        if not name_value:
            return None
        name_lower = name_value.lower()
        tech_keywords = [
            'компьютер', 'пк', 'моноблок', 'монитор', 'принтер', 'мфу', 'сканер',
            'ксерокс', 'ноутбук', 'планшет', 'сервер', 'свитч', 'маршрутизатор',
            'роутер', 'телефон', 'телевизор', 'тв', 'проектор', ' ups', 'ИБП',
            'модем', 'камера', 'видеонаблюдени', 'кондиционер', 'системный блок',
            'мышь', 'клавиатура', 'акустика', 'колонки'
        ]
        furniture_keywords = [
            'стол', 'стул', 'кресло', 'шкаф', 'тумб', 'диван', 'банкетка',
            'полка', 'вешалка', 'кровать', 'комод', 'стеллаж', 'скамья'
        ]
        if any(k in name_lower for k in tech_keywords):
            return 'Техника'
        if any(k in name_lower for k in furniture_keywords):
            return 'Мебель'
        return None

    for asset in assets_raw:
        # Парсим местонахождение из notes
        location_notes = asset['location_notes'] or '—'
        if location_notes and location_notes.startswith('Местоположение: '):
            parsed_location = location_notes[15:]
        else:
            parsed_location = location_notes or '—'

        # Приоритет — сохранённое в БД значение category; иначе пытаемся определить по названию
        derived_kind = asset['category'] if asset['category'] else derive_kind(asset['name'])

        assets_display.append({
            'id': asset['id'],
            'inventory_number': asset['inventory_number'] or '—',
            'serial_number': asset['serial_number'] if 'serial_number' in asset.keys() else (None),
            'name': asset['name'],
            'incoming_names': asset['incoming_names'] if 'incoming_names' in asset.keys() else None,
            'category': asset['category'] or '—',
            'okof_code': asset['okof_code'] or '—',
            'acquisition_date': asset['acquisition_date'] or '—',
            'accounting_status': asset['accounting_status'] or '—',
            'initial_cost': asset['initial_cost'],
            'quantity': asset['quantity'] or 1,
            'useful_life_months': asset['useful_life_months'] if asset['useful_life_months'] is not None else '—',
            'wear_percent': f"{asset['wear_percent']}" if asset['wear_percent'] is not None else '—',
            'location': parsed_location,
            'created_at': asset['created_at'] or '—',
            'updated_at': asset['updated_at'] or '—',
            '_kind': derived_kind,
            '_chips': [],
            '_incoming_count': asset['incoming_count'] if 'incoming_count' in asset.keys() else 0
        })

    # Применяем фильтр по эвристическому "Типу" (Техника / Мебель), если выбран
    if selected_kind in ('Техника', 'Мебель'):
        assets_display = [a for a in assets_display if a.get('_kind') == selected_kind]

    # Значения для фильтров
    # Кабинеты: извлекаем уникальные из notes
    rooms = set()
    notes_rows = conn.execute('SELECT notes FROM actual_assets WHERE notes IS NOT NULL AND notes LIKE "Местоположение:%"').fetchall()
    for r in notes_rows:
        text = r['notes']
        if text.startswith('Местоположение: '):
            rooms.add(text[15:].strip())
    room_options = sorted([r for r in rooms if r])

    conn.close()

    # Добавляем чипы-несоответствия (минимальный набор)
    for item in assets_display:
        # Нет серийного номера
        if not item.get('serial_number'):
            item['_chips'].append(('SERIAL', '№', '#dc3545'))
        # Высокий износ > 90%
        try:
            wear_str = item.get('wear_percent')
            wear_val = None
            if isinstance(wear_str, str) and wear_str != '—':
                wear_val = float(wear_str.replace(',', '.'))
            elif isinstance(wear_str, (int, float)):
                wear_val = float(wear_str)
            if wear_val is not None and wear_val > 90:
                item['_chips'].append(('WEAR', 'И', '#ffc107'))
        except:
            pass
        # Есть назначенный приход
        try:
            cnt = item.get('_incoming_count') or 0
            if isinstance(cnt, (int, float)) and cnt > 0:
                item['_chips'].append(('INCOMING', f'П:{int(cnt)}', '#17a2b8'))
        except:
            pass

    content = """
    {% block content %}
        <div class="card">
            <h2>📦 Бух отчетность (1С)</h2>

            <div class="card" style="padding: 18px; margin-top: 12px; background:#f8f9fa;">
                <div style="font-weight:600; color:#2c3e50; margin-bottom:6px;">Загрузить таблицу из 1С</div>
                <p style="margin: 0 0 12px 0; color:#666; font-size: 13px;">
                    Файл отчета “Ведомость остатков ОС, НМА, НПА” (.xlsx/.xls). При загрузке бухгалтерская база обновится.
                </p>
                <form method="post" action="/import" enctype="multipart/form-data" id="uploadForm" style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <input type="file" name="file" id="fileInput" accept=".xlsx,.xls" required onchange="handleFileSelect(this)" class="search-box" style="width: 420px; margin-bottom:0;">
                    <button type="button" class="btn btn-primary" onclick="selectFile()">📤 Выбрать файл</button>
                    <span id="fileName" style="color:#666; font-size: 13px;"></span>
                </form>
            </div>

            <div class="filter-group">
                <form method="get" style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <input type="text" name="search" class="search-box" placeholder="Поиск по всем полям..." 
                           value="{{ request.args.get('search', '') }}">

                    <select name="room" class="search-box" style="height: 44px; width: 240px;">
                        <option value="">Кабинет: все</option>
                        {% for r in room_options %}
                            <option value="{{ r }}" {% if request.args.get('room','') == r %}selected{% endif %}>{{ r }}</option>
                        {% endfor %}
                    </select>

                    <select name="kind" class="search-box" style="height: 44px; width: 180px;">
                        <option value="">Тип: все</option>
                        <option value="Техника" {% if request.args.get('kind','') == 'Техника' %}selected{% endif %}>Техника</option>
                        <option value="Мебель" {% if request.args.get('kind','') == 'Мебель' %}selected{% endif %}>Мебель</option>
                    </select>

                    <div style="display:flex; gap:8px; align-items:center;">
                        <label style="font-size:13px; color:#2c3e50;">Дата принятия:</label>
                        <input type="date" name="date_from" class="search-box" style="height:44px; width: 160px;" value="{{ request.args.get('date_from','') }}">
                        <span style="color:#666;">—</span>
                        <input type="date" name="date_to" class="search-box" style="height:44px; width: 160px;" value="{{ request.args.get('date_to','') }}">
                    </div>

                    <button type="submit" class="btn btn-primary">🔍 Найти</button>
                    <a href="{{ url_for('assets_export', search=request.args.get('search',''), room=request.args.get('room',''), kind=request.args.get('kind',''), date_from=request.args.get('date_from',''), date_to=request.args.get('date_to','')) }}" class="btn">⬇️ Экспорт CSV</a>
                    <a href="/assets" class="btn">Сбросить</a>
                </form>
            </div>

            <!-- Настройка колонок -->
            <div class="card" style="padding: 15px; margin-top: 10px;">
                <div style="font-weight:600; margin-bottom: 8px; color:#2c3e50;">Отображаемые колонки</div>
                <div id="columnsToggle" style="display:flex; gap: 12px; flex-wrap: wrap;">
                    {% for key, label, width in available_columns %}
                        <label style="display:flex; align-items:center; gap:6px; font-size: 13px;">
                            <input type="checkbox" class="col-toggle" data-col="{{ key }}">
                            {{ label }}
                        </label>
                    {% endfor %}
                </div>
            </div>

            {% if assets_display %}
            <div class="table-container">
                <table id="assetsTable">
                    <thead>
                        <tr>
                            {% for key, label, width in available_columns %}
                                <th data-col="{{ key }}" {% if width %}style="width: {{ width }};"{% endif %}>{{ label }}</th>
                            {% endfor %}
                            <th style="width: 100px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for asset in assets_display %}
                        <tr>
                            <td data-col="inventory_number"><a href="{{ url_for('asset_detail', asset_id=asset.id) }}" style="color: #667eea; font-weight: 500;"><small>{{ asset.inventory_number }}</small></a></td>
                            <td data-col="serial_number"><small>{{ asset.serial_number or '—' }}</small></td>
                            <td data-col="name">
                                {{ asset.name }}
                                {% if asset._chips and asset._chips|length > 0 %}
                                    <span style="margin-left:6px;">
                                        {% for code, label, color in asset._chips %}
                                            <span title="{{ code }}" style="display:inline-block; padding:2px 6px; border-radius:10px; font-size:11px; color:#fff; background: {{ color }}; margin-right:4px;">
                                                {{ label }}
                                            </span>
                                        {% endfor %}
                                    </span>
                                {% endif %}
                                {% if asset.incoming_names %}
                                    <div style="margin-top:4px; color:#666; font-size:12px;">
                                        <em>Приход:</em> {{ asset.incoming_names }}
                                    </div>
                                {% endif %}
                            </td>
                            <td data-col="category"><small>{{ asset.category }}</small></td>
                            <td data-col="okof_code"><small>{{ asset.okof_code }}</small></td>
                            <td data-col="acquisition_date"><small>{{ asset.acquisition_date }}</small></td>
                            <td data-col="accounting_status"><small>{{ asset.accounting_status }}</small></td>
                            <td data-col="initial_cost" style="text-align: right;"><strong>{{ asset.initial_cost|currency }}</strong></td>
                            <td data-col="quantity" style="text-align: center;">{{ asset.quantity }}</td>
                            <td data-col="useful_life_months" style="text-align: right;">{{ asset.useful_life_months }}</td>
                            <td data-col="wear_percent" style="text-align: right;">{{ asset.wear_percent }}%</td>
                            <td data-col="location"><small>{{ asset.location }}</small></td>
                            <td data-col="created_at"><small>{{ asset.created_at }}</small></td>
                            <td data-col="updated_at"><small>{{ asset.updated_at }}</small></td>
                            <td style="text-align: center;">
                                <a href="{{ url_for('asset_detail', asset_id=asset.id) }}" 
                                   class="btn" 
                                   style="padding: 6px 12px; font-size: 12px; background: #667eea; color: white;">
                                   Открыть
                                </a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <p style="margin-top: 15px; color: #666; font-size: 13px;">Показано записей: {{ assets_display|length }}</p>
            {% else %}
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <p>Ничего не найдено</p>
            </div>
            {% endif %}
        </div>
        <script>
            (function() {
                const STORAGE_KEY = 'visibleColumns';
                const allCols = {{ available_columns|tojson }};
                const toggles = document.querySelectorAll('.col-toggle');
                const table = document.getElementById('assetsTable');

                function getSaved() {
                    try {
                        const raw = localStorage.getItem(STORAGE_KEY);
                        if (!raw) return null;
                        const parsed = JSON.parse(raw);
                        if (Array.isArray(parsed)) return parsed;
                        return null;
                    } catch { return null; }
                }
                function save(list) {
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
                }
                function applyVisibility(visible) {
                    const visibleSet = new Set(visible);
                    // Toggle headers
                    allCols.forEach(([key]) => {
                        const th = table.querySelector('thead th[data-col="'+key+'"]');
                        if (th) th.style.display = visibleSet.has(key) ? '' : 'none';
                    });
                    // Toggle body cells
                    table.querySelectorAll('tbody tr').forEach(tr => {
                        allCols.forEach(([key]) => {
                            const td = tr.querySelector('td[data-col="'+key+'"]');
                            if (td) td.style.display = visibleSet.has(key) ? '' : 'none';
                        });
                    });
                    // Sync checkboxes
                    toggles.forEach(cb => {
                        cb.checked = visibleSet.has(cb.dataset.col);
                    });
                }
                // Init default visible columns (inventory_number, name, location, acquisition_date, accounting_status, initial_cost, quantity, wear_percent)
                const defaultVisible = ['inventory_number','serial_number','name','location','acquisition_date','accounting_status','initial_cost','quantity','wear_percent'];
                const saved = getSaved() || defaultVisible;
                // Initialize checkboxes
                toggles.forEach(cb => {
                    cb.addEventListener('change', () => {
                        const key = cb.dataset.col;
                        let next = saved.slice();
                        if (cb.checked) {
                            if (!next.includes(key)) next.push(key);
                        } else {
                            next = next.filter(k => k !== key);
                            // safeguard: always keep at least one column
                            if (next.length === 0) next = defaultVisible.slice(0,1);
                        }
                        save(next);
                        applyVisibility(next);
                    });
                });
                // Apply on load
                applyVisibility(saved);
            })();
        </script>
    {% endblock %}
    """

    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='assets',
                                  assets_display=assets_display,
                                  room_options=room_options,
                                  available_columns=available_columns)

@app.route('/assets/export')
def assets_export():
    # Экспорт текущего набора фильтров в CSV
    import csv
    from io import StringIO
    conn = get_db()
    search = request.args.get('search', '')
    selected_room = request.args.get('room', '').strip()
    selected_kind = request.args.get('kind', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = '''
        SELECT a.*, aa.notes as location_notes, aa.serial_number as serial_number
        FROM assets a
        LEFT JOIN actual_assets aa ON a.id = aa.asset_id
        WHERE 1=1
    '''
    params = []
    if search:
        query += '''
            AND (
                a.name LIKE ?
                OR a.inventory_number LIKE ?
                OR IFNULL(a.okof_code, '') LIKE ?
                OR IFNULL(a.accounting_status, '') LIKE ?
                OR IFNULL(a.acquisition_date, '') LIKE ?
                OR EXISTS (
                    SELECT 1 FROM incoming_goods ig
                    WHERE ig.assigned_asset_id = a.id AND ig.item_name LIKE ?
                )
            )
        '''
        like = f'%{search}%'
        params.extend([like, like, like, like, like, like])
    if selected_room:
        query += ' AND IFNULL(aa.notes, \'\') LIKE ?'
        params.append(f'%Местоположение: {selected_room}%')
    if date_from:
        query += ' AND date(a.acquisition_date) >= date(?)'
        params.append(date_from)
    if date_to:
        query += ' AND date(a.acquisition_date) <= date(?)'
        params.append(date_to)
    query += ' ORDER BY a.id DESC'

    rows = conn.execute(query, params).fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si, delimiter=';')
    cw.writerow(['Инв. номер','Заводской номер','Наименование','Тип','ОКОФ','Дата принятия','Состояние (бух)','Стоимость','Кол-во','Срок (мес.)','Износ %','Местонахождение'])
    for r in rows:
        location_notes = r['location_notes'] or ''
        if location_notes.startswith('Местоположение: '):
            loc = location_notes[15:]
        else:
            loc = location_notes
        cw.writerow([
            r['inventory_number'] or '',
            r['serial_number'] or '',
            r['name'] or '',
            r['category'] or '',
            r['okof_code'] or '',
            r['acquisition_date'] or '',
            r['accounting_status'] or '',
            r['initial_cost'] or '',
            r['quantity'] or '',
            r['useful_life_months'] or '',
            r['wear_percent'] or '',
            loc or ''
        ])
    output = si.getvalue().encode('utf-8-sig')
    from flask import Response
    return Response(output, mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': 'attachment; filename=assets_export.csv'
    })

@app.route('/facts')
def facts_list():
    conn = get_db()
    search = request.args.get('search','').strip()
    query = '''
        SELECT f.*, a.inventory_number as a_inv, a.name as a_name
        FROM fact_inventory f
        LEFT JOIN assets a ON a.id = f.matched_asset_id
        WHERE 1=1
    '''
    params = []
    if search:
        query += '''
            AND (
                IFNULL(f.inventory_number,'') LIKE ?
                OR IFNULL(f.name,'') LIKE ?
                OR IFNULL(f.serial_number,'') LIKE ?
                OR IFNULL(f.location,'') LIKE ?
            )
        '''
        like = f'%{search}%'
        params.extend([like, like, like, like])
    query += ' ORDER BY COALESCE(f.observed_date, f.created_at) DESC, f.id DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()

    content = """
    {% block content %}
        <div class="card">
            <h2>📋 Факт (инвентаризация)</h2>
            <div class="filter-group">
                <form method="get" style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <input type="text" name="search" class="search-box" placeholder="Поиск по факту (инв., серийник, локация, имя)" value="{{ request.args.get('search','') }}">
                    <a class="btn" href="/facts">Сбросить</a>
                </form>
            </div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:120px;">Инв. номер</th>
                            <th>Наименование</th>
                            <th style="width:160px;">Серийный номер</th>
                            <th style="width:200px;">Местоположение</th>
                            <th style="width:120px;">Состояние</th>
                            <th style="width:120px;">Наклейка</th>
                            <th style="width:110px;">Дата</th>
                            <th style="width:140px;">Связь с бух.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for f in rows %}
                        <tr>
                            <td><small>{{ f['inventory_number'] or '—' }}</small></td>
                            <td>{{ f['name'] or '—' }}</td>
                            <td><small>{{ f['serial_number'] or '—' }}</small></td>
                            <td><small>{{ f['location'] or '—' }}</small></td>
                            <td><small>{{ f['condition_status'] or '—' }}</small></td>
                            <td><small>{{ f['physical_label_status'] or '—' }}</small></td>
                            <td><small>{{ f['observed_date'] or f['created_at'] }}</small></td>
                            <td>
                                {% if f['a_inv'] %}
                                    <a href="{{ url_for('asset_detail', asset_id=f['matched_asset_id']) }}" style="color:#667eea;">{{ f['a_inv'] }}</a>
                                {% else %}
                                    <span style="color:#999;">не сопоставлено</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    {% endblock %}
    """
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='facts',
                                  rows=rows)

@app.route('/admin/cleanup', methods=['GET','POST'])
def admin_cleanup():
    q = request.values.get('q', 'слон').strip()
    do_incoming = request.values.get('incoming', '1') == '1'
    do_facts = request.values.get('facts', '1') == '1'
    do_assets = request.values.get('assets', '0') == '1'
    deleted = {'incoming': 0, 'facts': 0, 'assets': 0}
    if request.method == 'POST':
        conn = get_db()
        try:
            if do_incoming:
                cur = conn.execute("DELETE FROM incoming_goods WHERE item_name LIKE ?", (f'%{q}%',))
                deleted['incoming'] = cur.rowcount if cur.rowcount is not None else 0
            if do_facts:
                cur = conn.execute("DELETE FROM fact_inventory WHERE IFNULL(name,'') LIKE ? OR IFNULL(inventory_number,'') LIKE ? OR IFNULL(serial_number,'') LIKE ?", (f'%{q}%', f'%{q}%', f'%{q}%',))
                deleted['facts'] = cur.rowcount if cur.rowcount is not None else 0
            if do_assets:
                cur = conn.execute("DELETE FROM assets WHERE name LIKE ?", (f'%{q}%',))
                deleted['assets'] = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
        finally:
            conn.close()
        flash(f"Удалено: приход {deleted['incoming']}, факт {deleted['facts']}, бухгалтерия {deleted['assets']}", 'success')
        return redirect(url_for('admin_cleanup', q=q, incoming='1' if do_incoming else '0', facts='1' if do_facts else '0', assets='1' if do_assets else '0'))

    content = """
    {% block content %}
        <div class="card">
            <h2>🧹 Очистка тестовых данных</h2>
            <form method="post" style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <input type="text" name="q" class="search-box" value="{{ request.args.get('q','слон') }}" placeholder="Ключевое слово">
                <label style="display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" name="incoming" value="1" {% if request.args.get('incoming','1')=='1' %}checked{% endif %}> Приход
                </label>
                <label style="display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" name="facts" value="1" {% if request.args.get('facts','1')=='1' %}checked{% endif %}> Факт
                </label>
                <label style="display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" name="assets" value="1" {% if request.args.get('assets','0')=='1' %}checked{% endif %}> Бухгалтерия (осторожно)
                </label>
                <button class="btn btn-primary" type="submit">Удалить</button>
                <a class="btn" href="/facts">К факту</a>
                <a class="btn" href="/incoming">К приходу</a>
            </form>
            <p style="margin-top:10px; color:#666; font-size:13px;">Подбор по LIKE. По умолчанию бухучет не трогаем.</p>
        </div>
    {% endblock %}
    """
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='admin')
@app.route('/inventory', methods=['GET', 'POST'])
def inventory_import():
    # Импорт фактической инвентаризации из Excel/CSV в actual_assets
    if request.method == 'POST':
        # Ветвление: ручной ввод или файл
        if request.form.get('manual_mode') == '1':
            inv = (request.form.get('inventory_number') or '').strip()
            if not inv:
                flash('Укажите инвентарный номер', 'error')
                return redirect(request.url)
            conn = get_db()
            asset = conn.execute('SELECT id FROM assets WHERE inventory_number = ?', (inv,)).fetchone()
            if not asset:
                conn.close()
                flash('Объект с таким инв. номером не найден', 'error')
                return redirect(request.url)
            serial_number = (request.form.get('serial_number') or '').strip() or None
            condition_status = (request.form.get('condition_status') or '').strip() or None
            physical_label_status = (request.form.get('physical_label_status') or '').strip() or None
            location_text = (request.form.get('location') or '').strip() or None
            notes = (request.form.get('notes') or '').strip() or None
            compiled_notes = None
            if location_text:
                compiled_notes = f"Местоположение: {location_text}"
                if notes:
                    compiled_notes = f"{compiled_notes}; {notes}"
            else:
                compiled_notes = notes
            # Пишем в fact_inventory; одно наблюдение = одна запись (можно несколько по одному инв. номеру)
            conn.execute('''
                INSERT INTO fact_inventory
                (inventory_number, name, serial_number, condition_status, physical_label_status, location, notes, source, observed_date, matched_asset_id)
                VALUES (?, NULL, ?, ?, ?, ?, ?, 'manual', date('now'), ?)
            ''', (inv, serial_number, condition_status, physical_label_status, location_text, compiled_notes, asset['id']))
            conn.commit()
            conn.close()
            flash('Фактические данные сохранены', 'success')
            return redirect(url_for('discrepancies_page'))
        # Иначе — загрузка файла
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        try:
            if filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(temp_path, dtype=str)
            else:
                # CSV бывает с разными разделителями и кодировками; плюс иногда встречаются "кривые" строки.
                # Сначала пробуем автоопределение разделителя и несколько кодировок.
                read_errors = []
                df = None
                encodings_to_try = ['utf-8-sig', 'cp1251', 'windows-1251', 'latin1']
                for enc in encodings_to_try:
                    try:
                        df = pd.read_csv(
                            temp_path,
                            dtype=str,
                            sep=None,              # autodetect delimiter
                            engine='python',
                            encoding=enc,
                            on_bad_lines='skip'    # не падать на строках с лишними разделителями
                        )
                        break
                    except Exception as e1:
                        read_errors.append(f"encoding={enc}: {e1}")
                        df = None
                if df is None:
                    for enc in encodings_to_try:
                        for sep_try in (';', ',', '\t'):
                            try:
                                df = pd.read_csv(
                                    temp_path,
                                    dtype=str,
                                    sep=sep_try,
                                    engine='python',
                                    encoding=enc,
                                    on_bad_lines='skip'
                                )
                                break
                            except Exception as e2:
                                read_errors.append(f"encoding={enc}, sep={sep_try}: {e2}")
                                df = None
                        if df is not None:
                            break
                if df is None:
                    raise ValueError(
                        "Не удалось прочитать CSV (скорее всего нестандартная кодировка/разделитель). "
                        "Попробуйте сохранить как CSV UTF-8 или Windows-1251 с разделителем ';' или ','. "
                        "Детали: " + " | ".join(read_errors[:6])
                    )
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            flash(f'Не удалось прочитать файл: {e}', 'error')
            return redirect(request.url)

        # Ожидаемые колонки (минимум): Инвентарный номер, Серийный номер, Местоположение, Состояние, Инв. наклейка, Комментарий
        # Попробуем гибкое сопоставление по частичным названиям
        def find_col(possible, columns):
            for p in possible:
                for c in columns:
                    if str(c).strip().lower() == p:
                        return c
            return None

        cols = {c: c for c in df.columns}
        lower = {str(c).strip().lower(): c for c in df.columns}
        inv_col = find_col(['инвентарный номер', 'инв. номер', 'inventory_number'], lower) or 'Инвентарный номер'
        ser_col = find_col(['серийный номер', 'serial', 'serial_number'], lower)
        loc_col = find_col(['местоположение', 'кабинет', 'location'], lower)
        cond_col = find_col(['состояние', 'condition_status', 'сост'], lower)
        label_col = find_col(['инв. наклейка', 'наклейка', 'label', 'physical_label_status'], lower)
        note_col = find_col(['комментарий', 'примечание', 'notes'], lower)

        missing = []
        inserted = 0
        matched_assets = 0
        conn = get_db()
        try:
            for _, row in df.iterrows():
                inv = (row.get(inv_col) if inv_col in row else None) if isinstance(row, dict) else row[inv_col] if inv_col in df.columns else None
                if not inv or str(inv).strip() == '' or str(inv).strip().lower() == 'nan':
                    continue
                inv = str(inv).strip()
                asset = conn.execute('SELECT id FROM assets WHERE inventory_number = ?', (inv,)).fetchone()
                if asset:
                    matched_assets += 1
                serial_number = str(row.get(ser_col)).strip() if ser_col and pd.notna(row.get(ser_col)) else None
                condition_status = str(row.get(cond_col)).strip() if cond_col and pd.notna(row.get(cond_col)) else None
                physical_label_status = str(row.get(label_col)).strip() if label_col and pd.notna(row.get(label_col)) else None
                location_text = str(row.get(loc_col)).strip() if loc_col and pd.notna(row.get(loc_col)) else None
                notes = str(row.get(note_col)).strip() if note_col and pd.notna(row.get(note_col)) else None
                # Собираем notes как Местоположение: <...> + комментарий
                compiled_notes = None
                if location_text:
                    compiled_notes = f"Местоположение: {location_text}"
                    if notes:
                        compiled_notes = f"{compiled_notes}; {notes}"
                else:
                    compiled_notes = notes

                conn.execute('''
                    INSERT INTO fact_inventory
                    (inventory_number, name, serial_number, condition_status, physical_label_status, location, notes, source, observed_date, matched_asset_id)
                    VALUES (?, NULL, ?, ?, ?, ?, ?, 'import', date('now'), ?)
                ''', (inv, serial_number, condition_status, physical_label_status, location_text, compiled_notes, asset['id'] if asset else None))
                inserted += 1
            conn.commit()
        finally:
            conn.close()
            if os.path.exists(temp_path):
                os.remove(temp_path)

        msg = f"Импорт инвентаризации: записей: {inserted}, сопоставлено с бух. объектами: {matched_assets}"
        flash(msg, 'success')
        return redirect(url_for('discrepancies_page'))

    # GET форма
    content = """
    {% block content %}
        <div class="card">
            <h2>📋 Импорт инвентаризации (факт)</h2>
            <p style="margin:10px 0 16px 0; color:#666;">Загрузите Excel/CSV с колонками: <em>Инвентарный номер</em> (обязательно), <em>Серийный номер</em>, <em>Местоположение</em>, <em>Состояние</em>, <em>Инв. наклейка</em>, <em>Комментарий</em>.</p>
            <form method="post" enctype="multipart/form-data" id="uploadForm">
                <div class="upload-area" onclick="selectFile()">
                    <p style="font-size: 64px; margin-bottom: 15px;">File</p>
                    <input type="file" name="file" id="fileInput" accept=".xlsx,.xls,.csv" required 
                           onchange="handleFileSelect(this)">
                    <label for="fileInput" class="upload-label">
                        Выбрать файл
                    </label>
                    <p id="fileName" style="margin-top: 15px; color: #666; font-size: 14px;"></p>
                    <p style="margin-top: 10px; color: #999; font-size: 12px;">или перетащите файл сюда</p>
                </div>
            </form>
        </div>
        <div class="card">
            <h3 style="margin-bottom:8px;">Быстрый ручной ввод (одна запись)</h3>
            <form method="post" style="display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px;">
                <input type="hidden" name="manual_mode" value="1">
                <div>
                    <label>Инвентарный номер*</label>
                    <input type="text" name="inventory_number" class="search-box" required placeholder="например: 004006426">
                </div>
                <div>
                    <label>Серийный номер</label>
                    <input type="text" name="serial_number" class="search-box">
                </div>
                <div>
                    <label>Состояние</label>
                    <select name="condition_status" class="search-box" style="height:44px;">
                        <option value="">—</option>
                        <option value="Исправно">Исправно</option>
                        <option value="Сломано">Сломано</option>
                        <option value="Утеряно">Утеряно</option>
                        <option value="На ремонте">На ремонте</option>
                    </select>
                </div>
                <div>
                    <label>Инв. наклейка</label>
                    <select name="physical_label_status" class="search-box" style="height:44px;">
                        <option value="">—</option>
                        <option value="Есть">Есть</option>
                        <option value="Стерта">Стерта</option>
                        <option value="Нет">Нет</option>
                    </select>
                </div>
                <div>
                    <label>Местоположение</label>
                    <input type="text" name="location" class="search-box" placeholder="например: 33-12">
                </div>
                <div style="grid-column: 1 / -1;">
                    <label>Комментарий</label>
                    <input type="text" name="notes" class="search-box">
                </div>
                <div style="grid-column: 1 / -1;">
                    <button class="btn btn-primary" type="submit">Сохранить</button>
                </div>
            </form>
        </div>
    {% endblock %}
    """
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='inventory')

@app.route('/discrepancies')
def discrepancies_page():
    # Выводим расхождения между assets (бух) и fact_inventory (факт)
    conn = get_db()
    rows = conn.execute('''
        SELECT 
            a.id as asset_id, a.inventory_number as a_inv, a.name as a_name, a.accounting_status as a_acc_status,
            f.id as fact_id, f.inventory_number as f_inv, f.name as f_name, f.serial_number as f_serial,
            f.condition_status as f_condition, f.physical_label_status as f_label, f.location as f_location,
            f.observed_date as f_date
        FROM assets a
        LEFT JOIN fact_inventory f
          ON (f.inventory_number IS NOT NULL AND f.inventory_number = a.inventory_number)
        ORDER BY a.id DESC
    ''').fetchall()
    # Факты без бух-объекта
    orphan_facts = conn.execute('''
        SELECT f.*
        FROM fact_inventory f
        LEFT JOIN assets a ON a.inventory_number = f.inventory_number
        WHERE a.id IS NULL
        ORDER BY f.id DESC
    ''').fetchall()
    conn.close()

    items = []
    for r in rows:
        mismatches = []
        if r['f_inv'] is None:
            mismatches.append(('NOT_FOUND', 'Нет факта'))
        else:
            # простые правила
            if r['a_acc_status'] == 'Введено в эксплуатацию' and (r['f_condition'] and r['f_condition'] != 'Исправно'):
                mismatches.append(('COND', f"Сост: {r['f_condition']}"))
            if r['f_label'] and r['f_label'] != 'Есть':
                mismatches.append(('LABEL', f"Наклейка: {r['f_label']}"))
            if r['f_serial'] in (None, '', '—'):
                mismatches.append(('SERIAL', 'Нет серийника'))
        items.append({
            'asset_id': r['asset_id'],
            'inventory_number': r['a_inv'] or '—',
            'name': r['a_name'],
            'location_fact': r['f_location'] or '—',
            'serial_number': r['f_serial'] or '—',
            'observed_date': r['f_date'] or '—',
            'mismatches': mismatches
        })

    content = """
    {% block content %}
        <div class="card">
            <h2>⚠️ Несоответствия</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:120px;">Инв. номер</th>
                            <th>Наименование</th>
                            <th style="width:220px;">Факт. местоположение</th>
                            <th style="width:160px;">Серийный номер</th>
                            <th style="width:240px;">Проблемы</th>
                            <th style="width:100px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for it in items %}
                        <tr>
                            <td><small>{{ it.inventory_number }}</small></td>
                            <td>{{ it.name }}</td>
                            <td><small>{{ it.location_fact }}</small></td>
                            <td><small>{{ it.serial_number }}</small></td>
                            <td>
                                {% if it.mismatches and it.mismatches|length>0 %}
                                    {% for code, label in it.mismatches %}
                                        <span style="display:inline-block; padding:2px 6px; border-radius:10px; font-size:12px; color:#fff; background: {% if code=='NOT_FOUND' %}#dc3545{% elif code=='LABEL' %}#fd7e14{% elif code=='COND' %}#ffc107{% else %}#6c757d{% endif %}; margin-right:4px; margin-bottom:4px;">
                                            {{ label }}
                                        </span>
                                    {% endfor %}
                                {% else %}
                                    <span style="color:#28a745;">OK</span>
                                {% endif %}
                            </td>
                            <td style="text-align:center;">
                                <a class="btn" href="{{ url_for('asset_detail', asset_id=it.asset_id) }}" style="padding:6px 10px; font-size:12px; background:#667eea; color:#fff;">Открыть</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h3 style="margin-bottom:10px;">Факты без записи в бухгалтерии</h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:120px;">Инв. номер</th>
                            <th>Наименование (факт)</th>
                            <th style="width:200px;">Местоположение</th>
                            <th style="width:140px;">Серийный номер</th>
                            <th style="width:110px;">Дата факта</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for f in orphan_facts %}
                        <tr>
                            <td><small>{{ f['inventory_number'] or '—' }}</small></td>
                            <td>{{ f['name'] or '—' }}</td>
                            <td><small>{{ f['location'] or '—' }}</small></td>
                            <td><small>{{ f['serial_number'] or '—' }}</small></td>
                            <td><small>{{ f['observed_date'] or '—' }}</small></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    {% endblock %}
    """
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='discrepancies',
                                  items=items,
                                  orphan_facts=orphan_facts)

@app.route('/incoming', methods=['GET', 'POST'])
def incoming_list():
    conn = get_db()
    if request.method == 'POST':
        arrival_date = request.form.get('arrival_date') or datetime.now().date().isoformat()
        item_name = request.form.get('item_name', '').strip()
        quantity = int(request.form.get('quantity', '1') or '1')
        supplier = request.form.get('supplier', '').strip() or None
        document_number = request.form.get('document_number', '').strip() or None
        category = request.form.get('category', '').strip() or None
        temporary_storage_location = request.form.get('temporary_storage_location', '').strip() or None
        notes = request.form.get('notes', '').strip() or None

        if not item_name:
            flash('Укажите наименование позиции прихода', 'error')
        else:
            conn.execute('''
                INSERT INTO incoming_goods
                (arrival_date, item_name, quantity, supplier, document_number, category, temporary_storage_location, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            ''', (arrival_date, item_name, quantity, supplier, document_number, category, temporary_storage_location, notes))
            conn.commit()
            flash('Позиция прихода добавлена', 'success')
    # Список
    rows = conn.execute('''
        SELECT ig.*, a.inventory_number as assigned_inventory
        FROM incoming_goods ig
        LEFT JOIN assets a ON ig.assigned_asset_id = a.id
        ORDER BY ig.arrival_date DESC, ig.id DESC
    ''').fetchall()
    conn.close()

    content = """
    {% block content %}
        <div class="card">
            <h2>🧾 Приход</h2>
            <form method="post" style="display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; margin-top: 15px;">
                <div>
                    <label>Дата прихода</label>
                    <input type="date" name="arrival_date" class="search-box" style="width:100%;">
                </div>
                <div style="grid-column: span 2;">
                    <label>Наименование</label>
                    <input type="text" name="item_name" class="search-box" style="width:100%;" placeholder="Что пришло?">
                </div>
                <div>
                    <label>Кол-во</label>
                    <input type="number" name="quantity" class="search-box" style="width:100%;" value="1" min="1">
                </div>
                <div>
                    <label>Поставщик</label>
                    <input type="text" name="supplier" class="search-box" style="width:100%;">
                </div>
                <div>
                    <label>Документ №</label>
                    <input type="text" name="document_number" class="search-box" style="width:100%;">
                </div>
                <div>
                    <label>Категория</label>
                    <select name="category" class="search-box" style="width:100%; height:44px;">
                        <option value="">Не задано</option>
                        <option value="Техника">Техника</option>
                        <option value="Мебель">Мебель</option>
                    </select>
                </div>
                <div>
                    <label>Временное хранение</label>
                    <input type="text" name="temporary_storage_location" class="search-box" style="width:100%;" placeholder="Склад/кабинет">
                </div>
                <div style="grid-column: 1 / -1;">
                    <label>Примечание</label>
                    <input type="text" name="notes" class="search-box" style="width:100%;">
                </div>
                <div style="grid-column: 1 / -1; display:flex; gap:8px;">
                    <button type="submit" class="btn btn-primary">➕ Добавить</button>
                </div>
            </form>
        </div>

        <div class="card">
            <h3 style="margin-bottom: 8px;">Список прихода</h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:110px;">Дата</th>
                            <th>Наименование</th>
                            <th style="width:80px;">Кол-во</th>
                            <th style="width:140px;">Категория</th>
                            <th style="width:180px;">Поставщик</th>
                            <th style="width:140px;">Документ</th>
                            <th style="width:160px;">Хранение</th>
                            <th style="width:120px;">Статус</th>
                            <th style="width:140px;">Назначено</th>
                            <th style="width:120px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in rows %}
                        <tr>
                            <td><small>{{ r['arrival_date'] or '' }}</small></td>
                            <td>{{ r['item_name'] }}</td>
                            <td style="text-align:center;">{{ r['quantity'] }}</td>
                            <td><small>{{ r['category'] or '—' }}</small></td>
                            <td><small>{{ r['supplier'] or '—' }}</small></td>
                            <td><small>{{ r['document_number'] or '—' }}</small></td>
                            <td><small>{{ r['temporary_storage_location'] or '—' }}</small></td>
                            <td><small>{{ r['status'] or 'PENDING' }}</small></td>
                            <td><small>{{ r['assigned_inventory'] or '—' }}</small></td>
                            <td>
                                <a class="btn" style="padding:6px 10px; font-size:12px; background:#667eea; color:#fff;"
                                   href="{{ url_for('incoming_assign', incoming_id=r['id']) }}">Назначить</a>
                                <a class="btn" style="padding:6px 10px; font-size:12px; background:#11998e; color:#fff; margin-left:6px;"
                                   href="{{ url_for('incoming_create_fact', incoming_id=r['id']) }}">Создать факт</a>
                                {% if r['assigned_inventory'] %}
                                <a class="btn" style="padding:6px 10px; font-size:12px; background:#dc3545; color:#fff; margin-left:6px;"
                                   href="{{ url_for('incoming_unassign', incoming_id=r['id']) }}">Отвязать</a>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    {% endblock %}
    """

    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='incoming',
                                  rows=rows)

@app.route('/incoming/assign/<int:incoming_id>', methods=['GET','POST'])
def incoming_assign(incoming_id: int):
    conn = get_db()
    row = conn.execute('SELECT * FROM incoming_goods WHERE id = ?', (incoming_id,)).fetchone()
    if not row:
        conn.close()
        flash('Позиция прихода не найдена', 'error')
        return redirect(url_for('incoming_list'))

    search_result = None
    if request.method == 'POST':
        inventory_number = (request.form.get('inventory_number') or '').strip()
        asset_id_str = (request.form.get('asset_id') or '').strip()
        target_asset = None
        if asset_id_str.isdigit():
            target_asset = conn.execute('SELECT id, inventory_number FROM assets WHERE id = ?', (int(asset_id_str),)).fetchone()
        elif inventory_number:
            target_asset = conn.execute('SELECT id, inventory_number FROM assets WHERE inventory_number = ?', (inventory_number,)).fetchone()
        if target_asset:
            conn.execute('UPDATE incoming_goods SET assigned_asset_id = ?, status = ? WHERE id = ?',
                         (target_asset['id'], 'ASSIGNED', incoming_id))
            conn.commit()
            conn.close()
            flash(f'Назначено на объект {target_asset["inventory_number"]}', 'success')
            return redirect(url_for('incoming_list'))
        else:
            # Попробуем показать несколько похожих
            if inventory_number:
                search_result = conn.execute('SELECT id, inventory_number, name FROM assets WHERE inventory_number LIKE ? ORDER BY id DESC LIMIT 10',
                                             (f'%{inventory_number}%',)).fetchall()
            flash('Объект не найден. Уточните инв. номер или ID.', 'error')

    conn.close()
    content = """
    {% block content %}
        <div class="card">
            <h2>Назначить позицию прихода #{{ row['id'] }}</h2>
            <p style="margin:8px 0 16px 0; color:#666;"><strong>{{ row['item_name'] }}</strong>, кол-во: {{ row['quantity'] }}, дата: {{ row['arrival_date'] or '—' }}</p>
            <form method="post" style="display:grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                    <label>Инвентарный номер</label>
                    <input type="text" name="inventory_number" class="search-box" placeholder="Например: 12345">
                </div>
                <div>
                    <label>ID объекта (альтернативно)</label>
                    <input type="number" name="asset_id" class="search-box" placeholder="ID из базы">
                </div>
                <div style="grid-column: 1 / -1; display:flex; gap:8px;">
                    <button class="btn btn-primary" type="submit">Назначить</button>
                    <a class="btn" href="{{ url_for('incoming_list') }}">Назад</a>
                </div>
            </form>
        </div>

        {% if search_result %}
        <div class="card">
            <h3>Похожие объекты</h3>
            <ul style="margin-left:18px;">
                {% for a in search_result %}
                    <li><strong>{{ a['inventory_number'] }}</strong> — {{ a['name'] }} (ID: {{ a['id'] }})</li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}
    {% endblock %}
    """
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
                                  page='incoming',
                                  row=row,
                                  search_result=search_result)

@app.route('/incoming/unassign/<int:incoming_id>')
def incoming_unassign(incoming_id: int):
    conn = get_db()
    exists = conn.execute('SELECT id FROM incoming_goods WHERE id = ?', (incoming_id,)).fetchone()
    if not exists:
        conn.close()
        flash('Позиция прихода не найдена', 'error')
        return redirect(url_for('incoming_list'))
    conn.execute('UPDATE incoming_goods SET assigned_asset_id = NULL, status = "PENDING" WHERE id = ?', (incoming_id,))
    conn.commit()
    conn.close()
    flash('Позиция прихода отвязана от объекта', 'success')
    return redirect(url_for('incoming_list'))

@app.route('/incoming/create_fact/<int:incoming_id>')
def incoming_create_fact(incoming_id: int):
    conn = get_db()
    row = conn.execute('SELECT * FROM incoming_goods WHERE id = ?', (incoming_id,)).fetchone()
    if not row:
        conn.close()
        flash('Позиция прихода не найдена', 'error')
        return redirect(url_for('incoming_list'))

    # Создаем запись ФАКТА на основе прихода (без изменения бухгалтерии)
    name = row['item_name'] or 'Новый объект (факт)'
    observed_date = row['arrival_date']
    # Сохраняем в fact_inventory, matched_asset_id не ставим (позже можно сопоставить вручную)
    conn.execute('''
        INSERT INTO fact_inventory
        (inventory_number, name, serial_number, condition_status, physical_label_status, location, notes, source, observed_date, matched_asset_id)
        VALUES (NULL, ?, NULL, NULL, NULL, ?, ?, 'incoming', ?, NULL)
    ''', (name, row['temporary_storage_location'], row['notes'], observed_date))

    # Обновляем статус прихода (не назначаем на бухгалтерский объект)
    conn.execute('UPDATE incoming_goods SET status = "FACT_RECORDED" WHERE id = ?', (incoming_id,))
    conn.commit()
    conn.close()
    flash('Создана запись в Факте на основе прихода', 'success')
    return redirect(url_for('facts_list'))


@app.route('/import', methods=['GET', 'POST'])
def import_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)

        if file and file.filename.endswith(('.xlsx', '.xls')):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                # ОЧИСТКА СТАРЫХ ДАННЫХ
                conn = get_db()
                conn.execute("DELETE FROM actual_assets;")
                conn.execute("DELETE FROM assets;")
                conn.commit()

                # Читаем Excel
                df_raw = pd.read_excel(filepath, header=None, dtype=str)
                header_row = None
                for idx in range(len(df_raw)):
                    if 'Основное средство' in df_raw.iloc[idx].values:
                        header_row = idx
                        break

                if header_row is None:
                    raise ValueError("Не найдена строка с заголовком 'Основное средство'")

                df = pd.read_excel(filepath, header=header_row, dtype=str)
                df = df[df['Инвентарный номер'].notna() & df['Основное средство'].notna()]

                columns_map = {
                    'Основное средство': 'name',
                    'Инвентарный номер': 'inventory_number',
                    'Дата принятия к учету': 'acquisition_date',
                    'Unnamed: 17': 'initial_cost',
                    'Срок полезного использования': 'useful_life_months',
                    'Износ, %': 'wear_percent',
                    'Unnamed: 18': 'quantity',
                    'Состояние': 'accounting_status',
                    'Текущее местонахождение': 'location'
                }

                df = df[list(columns_map.keys())].rename(columns=columns_map)

                # Приводим типы
                df['initial_cost'] = df['initial_cost'].str.replace(' ', '').str.replace(',', '.').astype(float)
                df['wear_percent'] = df['wear_percent'].replace('-', '0').str.replace(',', '.').astype(float)
                df['quantity'] = df['quantity'].fillna(0).astype(int)
                df['useful_life_months'] = df['useful_life_months'].replace('-', '0').fillna(0).astype(int)
                df['acquisition_date'] = pd.to_datetime(df['acquisition_date'], dayfirst=True, errors='coerce')

                # Вычисляем категорию (Техника/Мебель) по названию
                def derive_kind(name_value: str):
                    if not isinstance(name_value, str) or not name_value:
                        return None
                    name_lower = name_value.lower()
                    tech_keywords = [
                        'компьютер', 'пк', 'моноблок', 'монитор', 'принтер', 'мфу', 'сканер',
                        'ксерокс', 'ноутбук', 'планшет', 'сервер', 'свитч', 'маршрутизатор',
                        'роутер', 'телефон', 'телевизор', 'тв', 'проектор', ' ups', 'ибп',
                        'модем', 'камера', 'видеонаблюдени', 'кондиционер', 'системный блок',
                        'мышь', 'клавиатура', 'акустика', 'колонки'
                    ]
                    furniture_keywords = [
                        'стол', 'стул', 'кресло', 'шкаф', 'тумб', 'диван', 'банкетка',
                        'полка', 'вешалка', 'кровать', 'комод', 'стеллаж', 'скамья'
                    ]
                    if any(k in name_lower for k in tech_keywords):
                        return 'Техника'
                    if any(k in name_lower for k in furniture_keywords):
                        return 'Мебель'
                    return None

                df['category'] = df['name'].apply(derive_kind)

                # Вставляем в assets
                data_to_insert = df[['name', 'inventory_number', 'acquisition_date', 'initial_cost',
                                     'useful_life_months', 'wear_percent', 'quantity', 'accounting_status', 'category']]
                data_to_insert.to_sql('assets', conn, if_exists='append', index=False)

                # Вставляем местоположение
                for _, row in df.iterrows():
                    inv_num = row['inventory_number']
                    location = row['location'] if pd.notna(row['location']) else None
                    asset = conn.execute("SELECT id FROM assets WHERE inventory_number = ?", (inv_num,)).fetchone()
                    if asset:
                        notes = f"Местоположение: {location}" if location else None
                        conn.execute("INSERT OR REPLACE INTO actual_assets (asset_id, notes) VALUES (?, ?)",
                                     (asset[0], notes))

                conn.commit()
                conn.close()

                # Удаляем файл после импорта
                if os.path.exists(filepath):
                    os.remove(filepath)

                flash(f'Импорт успешен! Загружено: {len(df)} записей', 'success')
                return redirect(url_for('assets_list'))

            except Exception as e:
                flash(f'Ошибка при импорте: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(request.url)

    # GET: редиректим на бух-отчетность (форма загрузки теперь там)
    return redirect(url_for('assets_list'))


@app.route('/asset/<int:asset_id>', methods=['GET', 'POST'])
def asset_detail(asset_id):
    conn = get_db()

    # Получаем основной объект
    asset = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
    if not asset:
        flash('Объект не найден', 'error')
        return redirect(url_for('assets_list'))

    # Получаем фактическое состояние
    actual = conn.execute('SELECT * FROM actual_assets WHERE asset_id = ?', (asset_id,)).fetchone()

    if request.method == 'POST':
        location = request.form.get('location')
        serial_number = request.form.get('serial_number', '').strip() or None
        condition_status = request.form.get('condition_status')
        physical_label_status = request.form.get('physical_label_status')
        notes = request.form.get('notes', '').strip() or None
        new_category = request.form.get('category', '').strip() or None

        if actual:
            conn.execute('''
                UPDATE actual_assets 
                SET serial_number = ?, 
                    condition_status = ?, 
                    physical_label_status = ?, 
                    notes = ?, 
                    last_verified_date = date('now'),
                    verified_by = 'user'
                WHERE asset_id = ?
            ''', (serial_number, condition_status, physical_label_status, notes, asset_id))
        else:
            conn.execute('''
                INSERT INTO actual_assets 
                (asset_id, serial_number, condition_status, physical_label_status, notes, last_verified_date, verified_by)
                VALUES (?, ?, ?, ?, ?, date('now'), 'user')
            ''', (asset_id, serial_number, condition_status, physical_label_status, notes))

        # Обновляем категорию в assets, если поменялась
        if new_category is not None:
            conn.execute('UPDATE assets SET category = ? WHERE id = ?', (new_category, asset_id))

        conn.commit()
        flash('Фактическое состояние обновлено!', 'success')
        conn.close()
        return redirect(url_for('asset_detail', asset_id=asset_id))

    # Подготавливаем данные
    accounting_location = '—'
    if actual and actual['notes'] and actual['notes'].startswith('Местоположение: '):
        accounting_location = actual['notes'][15:]

    # Расхождения
    discrepancies = []
    if actual:
        if actual['condition_status'] != 'Исправно' and asset['accounting_status'] == 'Введено в эксплуатацию':
            discrepancies.append(('Состояние', 'Введено', actual['condition_status'], 'warning'))
        if actual['physical_label_status'] != 'Есть':
            discrepancies.append(('Инв. наклейка', 'Есть', actual['physical_label_status'], 'error'))
        if not actual['serial_number']:
            discrepancies.append(('Серийный номер', 'Есть', 'Отсутствует', 'warning'))

    # Расходники по объекту
    conn2 = get_db()
    consumables = conn2.execute('''
        SELECT * FROM equipment_consumables
        WHERE parent_asset_id = ?
        ORDER BY COALESCE(installation_date, '') DESC, id DESC
    ''', (asset_id,)).fetchall()
    # Приход, назначенный на объект
    assigned_incoming = conn2.execute('''
        SELECT arrival_date, item_name, quantity, supplier, document_number, notes
        FROM incoming_goods
        WHERE assigned_asset_id = ?
        ORDER BY COALESCE(arrival_date,'' ) DESC, id DESC
    ''', (asset_id,)).fetchall()
    conn2.close()

    conn.close()

    content = """
    {% block content %}
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2>Объект #{{ asset['inventory_number'] }}</h2>
                <a href="/assets" class="btn">Назад к списку</a>
            </div>

            <!-- Бухгалтерские данные -->
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h3 style="color: #2c3e50; margin-bottom: 15px;">Бухгалтерский учёт</h3>
                <table style="width: 100%; font-size: 14px;">
                    <tr><td style="width: 200px;"><strong>Наименование:</strong></td><td>{{ asset['name'] }}</td></tr>
                    <tr><td><strong>Инв. номер:</strong></td><td><code>{{ asset['inventory_number'] }}</code></td></tr>
                    <tr><td><strong>Дата принятия:</strong></td><td>{{ asset['acquisition_date'] or '—' }}</td></tr>
                    <tr><td><strong>Стоимость:</strong></td><td><strong>{{ asset['initial_cost']|currency }}</strong></td></tr>
                    <tr><td><strong>Износ:</strong></td><td>{{ asset['wear_percent'] or 0 }}%</td></tr>
                    <tr><td><strong>Местоположение (бух):</strong></td><td><em>{{ accounting_location }}</em></td></tr>
                </table>
            </div>

            <!-- Форма фактического состояния -->
            <form method="post">
                <h3 style="color: #2c3e50; margin-bottom: 15px;">Фактическое состояние (инвентаризация)</h3>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                    <div>
                        <label><strong>Где находится сейчас?</strong></label>
                        <input type="text" name="location" class="search-box" style="width: 100%; margin-top: 5px;"
                               value="{% if actual and actual['notes'] and ': ' in actual['notes'] %}{{ actual['notes'].split(': ', 1)[1] }}{% endif %}"
                               placeholder="Например: 33-12, склад, утилизирован">
                    </div>
                    <div>
                        <label><strong>Серийный номер</strong></label>
                        <input type="text" name="serial_number" class="search-box" style="width: 100%; margin-top: 5px;"
                               value="{{ actual['serial_number'] if actual else '' }}">
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                    <div>
                        <label><strong>Состояние</strong></label>
                        <select name="condition_status" class="search-box" style="width: 100%; margin-top: 5px; height: 44px;">
                            <option value="Исправно" {% if actual and actual['condition_status'] == 'Исправно' %}selected{% endif %}>Исправно</option>
                            <option value="Сломано" {% if actual and actual['condition_status'] == 'Сломано' %}selected{% endif %}>Сломано</option>
                            <option value="Утеряно" {% if actual and actual['condition_status'] == 'Утеряно' %}selected{% endif %}>Утеряно</option>
                            <option value="На ремонте" {% if actual and actual['condition_status'] == 'На ремонте' %}selected{% endif %}>На ремонте</option>
                        </select>
                    </div>
                    <div>
                        <label><strong>Инв. наклейка</strong></label>
                        <select name="physical_label_status" class="search-box" style="width: 100%; margin-top: 5px; height: 44px;">
                            <option value="Есть" {% if actual and actual['physical_label_status'] == 'Есть' %}selected{% endif %}>Есть</option>
                            <option value="Стерта" {% if actual and actual['physical_label_status'] == 'Стерта' %}selected{% endif %}>Стерта</option>
                            <option value="Нет" {% if actual and actual['physical_label_status'] == 'Нет' %}selected{% endif %}>Нет</option>
                        </select>
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                    <div>
                        <label><strong>Тип (категория)</strong></label>
                        <select name="category" class="search-box" style="width: 100%; margin-top: 5px; height: 44px;">
                            <option value="" {% if not asset['category'] %}selected{% endif %}>Не задано</option>
                            <option value="Техника" {% if asset['category'] == 'Техника' %}selected{% endif %}>Техника</option>
                            <option value="Мебель" {% if asset['category'] == 'Мебель' %}selected{% endif %}>Мебель</option>
                        </select>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label><strong>Комментарий</strong></label>
                    <textarea name="notes" class="search-box" style="width: 100%; height: 80px; margin-top: 5px; padding: 12px;"
                              placeholder="Дополнительная информация...">{{ actual['notes'] if actual else '' }}</textarea>
                </div>

                <button type="submit" class="btn btn-primary" style="padding: 12px 30px; font-size: 16px;">
                    Сохранить фактическое состояние
                </button>
            </form>

            <!-- Расходники (например, картриджи для принтеров) -->
            <div style="margin-top: 28px; background:#f8f9fa; padding:16px; border-radius:8px;">
                <h3 style="color:#2c3e50; margin-bottom: 10px;">Расходники</h3>
                {% if consumables and consumables|length > 0 %}
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:180px;">Тип</th>
                                <th>Модель</th>
                                <th style="width:140px;">Дата установки</th>
                                <th style="width:140px;">Установил</th>
                                <th style="width:120px;">Ресурс</th>
                                <th>Примечание</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for c in consumables %}
                            <tr>
                                <td><small>{{ c['consumable_type'] or '—' }}</small></td>
                                <td>{{ c['model'] or '—' }}</td>
                                <td><small>{{ c['installation_date'] or '—' }}</small></td>
                                <td><small>{{ c['installed_by'] or '—' }}</small></td>
                                <td style="text-align:right;"><small>{{ c['estimated_yield'] or '—' }}</small></td>
                                <td><small>{{ c['notes'] or '—' }}</small></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                    <p style="color:#666;">Пока нет записей о расходниках</p>
                {% endif %}

                <form method="post" action="{{ url_for('add_consumable', asset_id=asset['id']) }}" style="display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; margin-top:12px;">
                    <div>
                        <label>Тип</label>
                        <input type="text" name="consumable_type" class="search-box" placeholder="Картридж / Тонер / Фильтр ...">
                    </div>
                    <div>
                        <label>Модель</label>
                        <input type="text" name="model" class="search-box" placeholder="Например: CF283A">
                    </div>
                    <div>
                        <label>Дата установки</label>
                        <input type="date" name="installation_date" class="search-box">
                    </div>
                    <div>
                        <label>Кто поставил</label>
                        <input type="text" name="installed_by" class="search-box">
                    </div>
                    <div>
                        <label>Ресурс (стр.)</label>
                        <input type="number" name="estimated_yield" class="search-box" min="0">
                    </div>
                    <div style="grid-column: 1 / -1;">
                        <label>Примечание</label>
                        <input type="text" name="notes" class="search-box">
                    </div>
                    <div style="grid-column: 1 / -1;">
                        <button class="btn btn-primary" type="submit">➕ Добавить расходник</button>
                    </div>
                </form>
            </div>

            <!-- Назначенный приход -->
            <div style="margin-top: 28px; background:#f8f9fa; padding:16px; border-radius:8px;">
                <h3 style="color:#2c3e50; margin-bottom: 10px;">Приход, назначенный на этот объект</h3>
                {% if assigned_incoming and assigned_incoming|length > 0 %}
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:110px;">Дата</th>
                                <th>Наименование</th>
                                <th style="width:90px;">Кол-во</th>
                                <th style="width:180px;">Поставщик</th>
                                <th style="width:140px;">Документ</th>
                                <th>Примечание</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for g in assigned_incoming %}
                            <tr>
                                <td><small>{{ g['arrival_date'] or '—' }}</small></td>
                                <td>{{ g['item_name'] }}</td>
                                <td style="text-align:center;"><small>{{ g['quantity'] or '—' }}</small></td>
                                <td><small>{{ g['supplier'] or '—' }}</small></td>
                                <td><small>{{ g['document_number'] or '—' }}</small></td>
                                <td><small>{{ g['notes'] or '—' }}</small></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                    <p style="color:#666;">Пока нет назначенного прихода</p>
                {% endif %}
            </div>

            <!-- Расхождения -->
            {% if discrepancies %}
            <div style="margin-top: 30px; padding: 20px; background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 8px;">
                <h3 style="color: #856404; margin-bottom: 10px;">Расхождения с бухгалтерией</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    {% for label, expected, actual_val, severity in discrepancies %}
                    <li style="margin: 8px 0; color: {% if severity == 'error' %}#721c24{% else %}#856404{% endif %}">
                        <strong>{{ label }}:</strong> ожидалось <em>{{ expected }}</em> → найдено <strong>{{ actual_val }}</strong>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}
        </div>
    {% endblock %}
    """

    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
        page='assets',
        asset=asset,
        actual=actual,
        consumables=consumables,
        assigned_incoming=assigned_incoming,
        discrepancies=discrepancies,
        accounting_location=accounting_location
    )

@app.route('/asset/<int:asset_id>/consumables', methods=['POST'])
def add_consumable(asset_id: int):
    conn = get_db()
    # Проверим существование объекта
    exists = conn.execute('SELECT id FROM assets WHERE id = ?', (asset_id,)).fetchone()
    if not exists:
        conn.close()
        flash('Объект не найден', 'error')
        return redirect(url_for('assets_list'))
    consumable_type = (request.form.get('consumable_type') or '').strip() or None
    model = (request.form.get('model') or '').strip() or None
    installation_date = request.form.get('installation_date') or None
    installed_by = (request.form.get('installed_by') or '').strip() or None
    estimated_yield = request.form.get('estimated_yield') or None
    try:
        estimated_yield_val = int(estimated_yield) if estimated_yield not in (None, '',) else None
    except:
        estimated_yield_val = None
    notes = (request.form.get('notes') or '').strip() or None

    conn.execute('''
        INSERT INTO equipment_consumables
        (parent_asset_id, consumable_type, model, installation_date, installed_by, estimated_yield, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (asset_id, consumable_type, model, installation_date, installed_by, estimated_yield_val, notes))
    conn.commit()
    conn.close()
    flash('Расходник добавлен', 'success')
    return redirect(url_for('asset_detail', asset_id=asset_id))

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Запуск системы учета основных средств")
    print("=" * 60)
    print("\n📡 Сервер запущен на: http://127.0.0.1:5000")
    print("📖 Откройте эту ссылку в браузере\n")
    print("💾 База данных: assets.db")
    print("📁 Загруженные файлы: uploads/\n")
    print("⚠️  Для остановки нажмите Ctrl+C\n")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=5000)