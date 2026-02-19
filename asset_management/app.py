from flask import Flask, render_template_string, request, redirect, url_for, flash, Response
import sqlite3
import pandas as pd
from datetime import datetime
import os
import shutil
import re
from werkzeug.utils import secure_filename
from import_1s_final import import_1s_final

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['BACKUP_FOLDER'] = 'backups'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)

DATABASE = 'assets.db'

# ============================================================
# Вспомогательные функции
# ============================================================

def log_change(conn, entity_type, entity_id, field, old_val, new_val, reason=None):
    conn.execute('''
        INSERT INTO change_history
        (entity_type, entity_id, field_changed, old_value, new_value, changed_by, reason)
        VALUES (?, ?, ?, ?, ?, 'user', ?)
    ''', (entity_type, entity_id, field, old_val, new_val, reason))
    conn.commit()


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
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = f.read()
        conn = get_db()
        conn.executescript(schema)
        conn.commit()
        conn.close()
    # Миграции: добавить недостающие поля если их нет
    conn = get_db()
    migrations = [
        ('fact_inventory', 'ip_address', 'VARCHAR(45)'),
        ('actual_assets', 'ip_address', 'VARCHAR(45)'),
        ('actual_assets', 'location', 'TEXT'),
        ('equipment_consumables', 'current_usage', 'INTEGER DEFAULT 0'),
        ('inventory_consumables', 'asset_name', 'TEXT'),
        ('inventory_consumables', 'asset_id', 'INTEGER'),
    ]
    for tbl, col, col_def in migrations:
        try:
            conn.execute(f'SELECT {col} FROM {tbl} LIMIT 1')
        except:
            try:
                conn.execute(f'ALTER TABLE {tbl} ADD COLUMN {col} {col_def}')
                conn.commit()
            except:
                pass
    # Таблицы склада и совместимости (если нет — создаются из schema при первом запуске)
    for sql in [
        '''CREATE TABLE IF NOT EXISTS inventory_consumables (
            id INTEGER PRIMARY KEY AUTOINCREMENT, consumable_type VARCHAR(50), model VARCHAR(100),
            quantity INTEGER DEFAULT 0, location TEXT, notes TEXT, asset_name TEXT, asset_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE SET NULL)''',
        '''CREATE TABLE IF NOT EXISTS compatible_consumables (
            id INTEGER PRIMARY KEY AUTOINCREMENT, asset_model TEXT NOT NULL, consumable_model TEXT NOT NULL,
            UNIQUE(asset_model, consumable_model))''',
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except:
            pass
    conn.close()


init_db()


def read_file_to_df(filepath, filename):
    """Универсальное чтение Excel/CSV в DataFrame."""
    if filename.lower().endswith('.csv'):
        for enc in ['utf-8-sig', 'cp1251', 'windows-1251', 'latin1']:
            try:
                return pd.read_csv(filepath, dtype=str, sep=None, engine='python',
                                   encoding=enc, on_bad_lines='skip')
            except:
                continue
        raise ValueError("Не удалось прочитать CSV")
    else:
        return pd.read_excel(filepath, header=0, dtype=str)


def smart_fact_mapping(columns):
    """Автосопоставление колонок файла факта с полями БД."""
    rules = {
        'inventory_number': ['инвентарный', 'инв'],
        'name': ['наименование', 'название', 'основное средство'],
        'serial_number': ['серийный', 'заводской'],
        'condition_status': ['состояние'],
        # physical_label_status убрана из шаблона факта (не нужна обходчику)
        'location': ['местоположение', 'кабинет', 'location', 'комната'],
        'ip_address': ['ip', 'адрес', 'address'],
        'notes': ['примечание', 'комментарий', 'notes'],
    }
    mapping = {}
    for col in columns:
        cl = str(col).lower().strip()
        best = 'ignore'
        for field, kws in rules.items():
            if any(k in cl for k in kws):
                best = field
                break
        mapping[col] = best
    return mapping


def fuzzy_match_asset_name(search_name, conn):
    """Нечеткое сопоставление имени устройства с активами в БД.
    Возвращает список совпадений с оценкой похожести (asset_id, name, score).
    """
    if not search_name or not search_name.strip():
        return []
    
    search_lower = search_name.lower().strip()
    search_words = [w for w in search_lower.split() if len(w) > 2]
    
    # Получаем все устройства (МФУ, проекторы, принтеры)
    assets = conn.execute('''
        SELECT id, name, category FROM assets
        WHERE (LOWER(name) LIKE '%мфу%' OR LOWER(name) LIKE '%принтер%' 
               OR LOWER(name) LIKE '%проектор%' OR LOWER(name) LIKE '%projector%'
               OR category IN ('МФУ', 'Принтер', 'Проектор'))
        ORDER BY name
    ''').fetchall()
    
    matches = []
    for asset in assets:
        asset_name = asset['name'] or ''
        asset_lower = asset_name.lower()
        
        # Точное совпадение (без учета регистра)
        if search_lower == asset_lower:
            matches.append((asset['id'], asset_name, 100))
            continue
        
        # Полное вхождение
        if search_lower in asset_lower or asset_lower in search_lower:
            matches.append((asset['id'], asset_name, 90))
            continue
        
        # Подсчет совпадающих слов
        asset_words = [w for w in asset_lower.split() if len(w) > 2]
        common_words = set(search_words) & set(asset_words)
        
        if common_words:
            # Оценка на основе количества общих слов
            score = min(80, len(common_words) * 20)
            # Бонус если ключевые слова совпадают (мфу, принтер, проектор)
            key_words = ['мфу', 'принтер', 'проектор', 'projector', 'printer', 'mfp']
            if any(kw in search_lower and kw in asset_lower for kw in key_words):
                score += 10
            matches.append((asset['id'], asset_name, score))
    
    # Сортируем по score (по убыванию) и возвращаем топ-5
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[:5]


# ============================================================
# Базовый шаблон
# ============================================================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Учет основных средств</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css" rel="stylesheet" type="text/css" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        body { 
            background: #f9fafb;
            min-height: 100vh;
        }
        .card { 
            background: white;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
            border: 1px solid #e5e7eb;
            border-radius: 12px;
        }
        .btn { 
            border-radius: 10px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-weight: 600;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .btn-primary { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
        }
        .btn-primary:hover { 
            opacity: 0.9;
        }
        .btn-danger { 
            background: #dc3545;
            color: white;
            border: none;
        }
        .btn-danger:hover {
            background: #c82333;
        }
        .btn-success { 
            background: #28a745;
            color: white;
            border: none;
        }
        .btn-success:hover {
            background: #218838;
        }
        .search-box {
            padding: 10px 14px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.2s ease;
            background: white;
        }
        .search-box:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .search-box:hover {
            border-color: #d1d5db;
        }
        .badge-red { 
            background: #dc3545;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-orange { 
            background: #fd7e14;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-yellow { 
            background: #ffc107;
            color: #333;
            border: none;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-green { 
            background: #28a745;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-blue { 
            background: #17a2b8;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-gray { 
            background: #6c757d;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .flash-success { 
            background: #d4edda;
            border-left: 4px solid #28a745;
            border-radius: 8px;
            padding: 12px 16px;
            color: #155724;
        }
        .flash-error { 
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            border-radius: 8px;
            padding: 12px 16px;
            color: #721c24;
        }
        .flash-warning { 
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            border-radius: 8px;
            padding: 12px 16px;
            color: #856404;
        }
        .table-container { 
            overflow-x: auto;
            border-radius: 8px;
            background: white;
            border: 1px solid #e5e7eb;
        }
        table { width: 100%; border-collapse: separate; border-spacing: 0; }
        th { 
            background: #f9fafb;
            font-weight: 600;
            color: #374151;
            padding: 12px 16px;
            text-align: left;
            border-bottom: 2px solid #e5e7eb;
            position: sticky;
            top: 0;
            z-index: 10;
            font-size: 12px;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }
        th.text-center {
            text-align: center;
        }
        td { 
            padding: 12px 16px;
            border-bottom: 1px solid #f3f4f6;
            font-size: 14px;
            color: #4b5563;
        }
        tr:hover { 
            background: #f8f9fa;
            transition: background-color 0.15s ease;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .form-group label {
            font-size: 13px;
            font-weight: 600;
            color: #374151;
            margin-bottom: 4px;
        }
        .form-input {
            width: 100%;
            padding: 10px 14px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.2s ease;
            background: white;
        }
        .form-input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .form-input:hover {
            border-color: #d1d5db;
        }
        .form-select {
            width: 100%;
            padding: 10px 14px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            background: white;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .form-select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .form-select[multiple] {
            padding: 8px;
            overflow-y: auto;
            cursor: default;
        }
        .form-select[multiple] option {
            padding: 6px 10px;
            margin: 2px 0;
            border-radius: 4px;
            cursor: pointer;
        }
        .form-select[multiple] option:hover {
            background-color: #f3f4f6;
        }
        .form-select[multiple] option:checked {
            background-color: #667eea;
            color: white;
        }
        .form-textarea {
            width: 100%;
            padding: 10px 14px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
            font-family: inherit;
            resize: vertical;
            min-height: 80px;
            transition: all 0.2s ease;
        }
        .form-textarea:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .stat-box {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
            border: 1px solid #e5e7eb;
            transition: all 0.2s ease;
        }
        .stat-box:hover {
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
        }
        .stat-box h3 {
            font-size: 0.875rem;
            font-weight: 600;
            color: #6b7280;
            margin-bottom: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .stat-box .number {
            font-size: 2rem;
            font-weight: 700;
            color: #111827;
        }
        .stat-box.green .number {
            color: #059669;
        }
        .stat-box.orange .number {
            color: #ea580c;
        }
        .stat-box.red .number {
            color: #dc2626;
        }
        .empty-state {
            text-align: center;
            padding: 3rem 1rem;
        }
        .empty-state-icon {
            font-size: 4rem;
            margin-bottom: 1rem;
        }
        .empty-state h3 {
            font-size: 1.25rem;
            font-weight: 600;
            color: #374151;
            margin-bottom: 0.5rem;
        }
        .empty-state p {
            color: #6b7280;
            font-size: 0.875rem;
        }
    </style>
</head>
<body>
    <div class="min-h-screen bg-gray-50">
        <header class="bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900 text-white shadow-2xl relative overflow-hidden">
            <div class="absolute inset-0 bg-black opacity-10"></div>
            <div class="absolute inset-0" style="background-image: radial-gradient(circle at 20% 50%, rgba(255,255,255,0.1) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,0.1) 0%, transparent 50%);"></div>
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 relative z-10">
                <h1 class="text-4xl font-bold mb-2 tracking-tight">Система учёта основных средств</h1>
                <p class="text-purple-100 text-base">Управление оборудованием и мебелью</p>
            </div>
        </header>

        <nav class="bg-white/80 backdrop-blur-md shadow-lg border-b border-gray-200/50 sticky top-0 z-50">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex flex-wrap gap-2 py-4">
                    <a href="/" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'dashboard' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Дашборд</a>
                    <a href="/assets" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'assets' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Бух отчетность</a>
                    <a href="/facts" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'facts' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Факт</a>
                    <a href="/discrepancies" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'discrepancies' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Сверка</a>
                    <a href="/incoming" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'incoming' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Приход</a>
                    <a href="/reports" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'reports' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Отчёты</a>
                    <a href="/consumables" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'consumables' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Расходники</a>
                    <a href="/history" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'history' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">История</a>
                    <a href="/admin" class="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 {{ 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/50' if page == 'admin' else 'text-gray-700 hover:bg-gray-100 hover:shadow-md' }}">Админ</a>
                </div>
            </div>
        </nav>

        <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash flash-{{ category }} mb-4">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}

            {% block content %}{% endblock %}
        </main>
    </div>

    <script>
        function selectFile(inputId) {
            document.getElementById(inputId || 'fileInput').click();
        }
        function handleFileSelect(input, formId) {
            if (input.files && input.files[0]) {
                var nameEl = input.parentElement.querySelector('.file-name');
                if (nameEl) nameEl.textContent = input.files[0].name;
                if (formId) {
                    var form = document.getElementById(formId);
                    if (form) form.submit();
                }
            }
        }
    </script>
</body>
</html>
"""


def render(content, **kwargs):
    """Обёртка для render_template_string с BASE_TEMPLATE."""
    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content),
        **kwargs
    )


# ============================================================
# ДАШБОРД
# ============================================================

@app.route('/')
def dashboard():
    conn = get_db()
    total_assets = conn.execute('SELECT COUNT(*) as cnt FROM assets').fetchone()['cnt']
    total_cost = conn.execute('SELECT SUM(initial_cost) as total FROM assets').fetchone()['total'] or 0
    total_facts = conn.execute('SELECT COUNT(*) as cnt FROM fact_inventory').fetchone()['cnt']

    # Счётчик несоответствий
    not_found_count = 0
    if total_facts > 0:
        not_found_count = conn.execute('''
            SELECT COUNT(*) as cnt FROM assets a
            WHERE NOT EXISTS (
                SELECT 1 FROM fact_inventory f WHERE f.inventory_number = a.inventory_number
            )
        ''').fetchone()['cnt']

    recent_assets = conn.execute('''
        SELECT a.*, aa.notes as location_notes
        FROM assets a LEFT JOIN actual_assets aa ON a.id = aa.asset_id
        ORDER BY a.created_at DESC LIMIT 10
    ''').fetchall()
    conn.close()

    assets_display = []
    for a in recent_assets:
        assets_display.append({
            'id': a['id'],
            'inventory_number': a['inventory_number'] or '—',
            'name': a['name'],
            'location': a['location_notes'] or '—',
            'date': a['acquisition_date'] or '—',
            'cost': a['initial_cost'],
        })

    content = """
    {% block content %}
        <div class="stats">
            <div class="stat-box">
                <h3>Объектов в бухгалтерии</h3>
                <div class="number">""" + str(total_assets) + """</div>
            </div>
            <div class="stat-box green">
                <h3>Общая стоимость</h3>
                <div class="number">{{ total_cost|currency }}</div>
            </div>
            <div class="stat-box orange">
                <h3>Записей факта</h3>
                <div class="number">""" + str(total_facts) + """</div>
            </div>
            <div class="stat-box red">
                <h3>Не найдено при сверке</h3>
                <div class="number">""" + str(not_found_count) + """</div>
            </div>
        </div>

        {% if assets_display %}
        <div class="card p-6">
            <h2 class="text-2xl font-bold text-gray-900 mb-6">Последние объекты (бухгалтерия)</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:140px;">Инв. номер</th>
                            <th>Наименование</th>
                            <th style="width:200px;">Местонахождение</th>
                            <th style="width:140px;">Дата принятия</th>
                            <th style="width:150px;" class="text-right">Стоимость</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for a in assets_display %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td>
                                <a href="/asset/{{ a.id }}" class="text-blue-600 hover:text-blue-800 hover:underline font-mono text-xs">{{ a.inventory_number }}</a>
                            </td>
                            <td class="font-medium text-gray-900">{{ a.name }}</td>
                            <td class="text-sm text-gray-600">{{ a.location }}</td>
                            <td class="text-sm text-gray-600">{{ a.date }}</td>
                            <td class="text-right font-semibold text-gray-900">{{ a.cost|currency }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% else %}
        <div class="card p-6">
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <h3>Данных пока нет</h3>
                <p>Загрузите таблицу из бухгалтерии через раздел «Бух отчетность»</p>
            </div>
        </div>
        {% endif %}
    {% endblock %}
    """
    return render(content, page='dashboard', assets_display=assets_display, total_cost=total_cost)


# ============================================================
# БУХ ОТЧЁТНОСТЬ
# ============================================================

@app.route('/assets')
def assets_list():
    conn = get_db()
    search = request.args.get('search', '')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    location_filter = request.args.getlist('location')  # Множественный выбор
    category_filter = request.args.getlist('category')  # Множественный выбор

    # Получаем список уникальных местоположений (только номера кабинетов)
    try:
        # Сначала берем из поля location
        locations_raw = conn.execute('''
            SELECT DISTINCT location as loc
            FROM actual_assets 
            WHERE location IS NOT NULL AND location != '' AND location NOT LIKE '%,%'
        ''').fetchall()
        locations_set = set()
        for loc in locations_raw:
            if loc['loc']:
                # Извлекаем номер кабинета (формат типа "33-12", "2-04" и т.д.)
                loc_str = loc['loc'].strip()
                # Если это просто номер кабинета (содержит цифры и дефис/тире), добавляем
                if any(c.isdigit() for c in loc_str) and ('-' in loc_str or '—' in loc_str or len(loc_str) <= 10):
                    locations_set.add(loc_str)
        
        # Также проверяем notes для извлечения кабинетов
        notes_raw = conn.execute('''
            SELECT DISTINCT notes
            FROM actual_assets 
            WHERE notes IS NOT NULL AND notes != ''
        ''').fetchall()
        for note in notes_raw:
            if note['notes']:
                # Ищем паттерны типа "33-12", "2-04", "кабинет 101" и т.д.
                text = note['notes']
                # Паттерн для номеров кабинетов: цифры-цифры или просто номер
                matches = re.findall(r'\b(\d+[-—]\d+|\d+-\d+|\d{1,3})\b', text)
                for match in matches:
                    if len(match) <= 10:  # Ограничиваем длину
                        locations_set.add(match)
        
        locations_list = sorted(list(locations_set))
    except Exception as e:
        locations_list = []

    # Категории: Техника и Мебель (стандартные для фильтрации)
    categories_list = ['Техника', 'Мебель']

    available_columns = [
        ('inventory_number', 'Инвентарный номер', '140px'),
        ('name', 'Основное средство', None),
        ('serial_number', 'Заводской номер', '180px'),
        ('acquisition_date', 'Дата принятия к учету', '150px'),
        ('accounting_status', 'Состояние', '160px'),
        ('location', 'Текущее местонахождение', '260px'),
        ('initial_cost', 'Стоимость первоначальная', '160px'),
    ]

    query = '''
        SELECT a.*,
               aa.notes as location_notes,
               aa.location as actual_location,
               aa.serial_number as serial_number
        FROM assets a
        LEFT JOIN actual_assets aa ON a.id = aa.asset_id
        WHERE 1=1
    '''
    params = []
    if search:
        query += '''
            AND (a.name LIKE ? OR a.inventory_number LIKE ?
                 OR IFNULL(a.accounting_status,'') LIKE ?
                 OR IFNULL(a.acquisition_date,'') LIKE ?)
        '''
        like = f'%{search}%'
        params.extend([like, like, like, like])
    if date_from:
        query += ' AND date(a.acquisition_date) >= date(?)'
        params.append(date_from)
    if date_to:
        query += ' AND date(a.acquisition_date) <= date(?)'
        params.append(date_to)
    if location_filter:
        location_conditions = []
        for loc in location_filter:
            if loc:  # Проверка на пустое значение
                location_conditions.append('(aa.location = ? OR aa.location LIKE ? OR aa.notes LIKE ? OR aa.notes LIKE ?)')
                params.extend([loc, f'%{loc}%', f'%{loc}%', f'Местоположение: {loc}%'])
        if location_conditions:
            query += ' AND (' + ' OR '.join(location_conditions) + ')'
    if category_filter:
        # Определяем категорию по названию или по категории из БД
        category_conditions = []
        for cat in category_filter:
            if cat == 'Техника':
                # Ключевые слова для техники
                category_conditions.append('''(LOWER(a.name) LIKE '%принтер%' OR LOWER(a.name) LIKE '%компьютер%' 
                    OR LOWER(a.name) LIKE '%ноутбук%' OR LOWER(a.name) LIKE '%монитор%' 
                    OR LOWER(a.name) LIKE '%проектор%' OR LOWER(a.name) LIKE '%мфу%'
                    OR LOWER(a.name) LIKE '%сканер%' OR LOWER(a.name) LIKE '%планшет%'
                    OR LOWER(a.name) LIKE '%сервер%' OR LOWER(a.name) LIKE '%роутер%'
                    OR LOWER(a.name) LIKE '%свитч%' OR LOWER(a.name) LIKE '%ups%'
                    OR a.category = 'Техника' OR a.category LIKE '%техника%')''')
            elif cat == 'Мебель':
                # Ключевые слова для мебели
                category_conditions.append('''(LOWER(a.name) LIKE '%стол%' OR LOWER(a.name) LIKE '%стул%' 
                    OR LOWER(a.name) LIKE '%шкаф%' OR LOWER(a.name) LIKE '%полка%'
                    OR LOWER(a.name) LIKE '%кресло%' OR LOWER(a.name) LIKE '%диван%'
                    OR LOWER(a.name) LIKE '%тумба%' OR LOWER(a.name) LIKE '%стеллаж%'
                    OR LOWER(a.name) LIKE '%стелаж%' OR a.category = 'Мебель' OR a.category LIKE '%мебель%')''')
        if category_conditions:
            query += ' AND (' + ' OR '.join(category_conditions) + ')'
    query += ' ORDER BY a.id DESC'
    try:
        assets_raw = conn.execute(query, params).fetchall()
    except Exception as e:
        flash(f'Ошибка выполнения запроса: {str(e)}', 'error')
        assets_raw = []
    conn.close()

    assets_display = []
    for a in assets_raw:
        actual_loc = a['actual_location'] if 'actual_location' in a.keys() else None
        location_notes = a['location_notes'] if 'location_notes' in a.keys() else None
        loc = actual_loc or location_notes or '—'
        if isinstance(loc, str) and loc.startswith('Местоположение: '):
            loc = loc[16:]
        assets_display.append({
            'id': a['id'],
            'inventory_number': a['inventory_number'] or '—',
            'serial_number': a['serial_number'] if 'serial_number' in a.keys() else None,
            'name': a['name'],
            'acquisition_date': a['acquisition_date'] or '—',
            'accounting_status': a['accounting_status'] or '—',
            'initial_cost': a['initial_cost'],
            'location': loc,
            'category': a['category'] if 'category' in a.keys() else '—',
        })

    content = """
    {% block content %}
        <div class="card p-6 mb-6">
            <h2 class="text-2xl font-bold text-gray-900 mb-6">Бух отчетность (1С)</h2>

            <div class="bg-gray-50 rounded-lg p-5 mb-6 border border-gray-200">
                <div class="font-semibold text-gray-800 mb-2">Загрузить таблицу из 1С</div>
                <p class="text-sm text-gray-600 mb-4">
                    Файл «Ведомость остатков ОС, НМА, НПА» (.xlsx/.xls). Строка заголовка определяется автоматически.
                </p>
                <form method="post" action="/import_1s_auto" enctype="multipart/form-data" id="importForm" class="flex gap-3 items-end">
                    <div class="form-group flex-1">
                        <label for="fileInput" class="text-sm font-semibold text-gray-700 mb-2 block">Выберите файл</label>
                        <input type="file" name="file" id="fileInput" accept=".xlsx,.xls" required
                               onchange="handleFileSelect(this, 'importForm')" class="form-input">
                    </div>
                    <button type="button" class="btn btn-primary px-6 py-2.5 whitespace-nowrap" onclick="selectFile('fileInput')">Выбрать файл (автоимпорт)</button>
                </form>
            </div>

            <form method="get" class="space-y-4 mb-6">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="form-group">
                        <label for="assets_search" class="text-sm font-semibold text-gray-700 mb-2 block">Поиск</label>
                        <input type="text" id="assets_search" name="search" class="form-input" placeholder="Поиск..." value="{{ request.args.get('search','') }}">
                    </div>
                    <div class="form-group">
                        <label for="date_from" class="text-sm font-semibold text-gray-700 mb-2 block">Дата от</label>
                        <input type="date" id="date_from" name="date_from" class="form-input" value="{{ request.args.get('date_from','') }}">
                    </div>
                    <div class="form-group">
                        <label for="date_to" class="text-sm font-semibold text-gray-700 mb-2 block">Дата до</label>
                        <input type="date" id="date_to" name="date_to" class="form-input" value="{{ request.args.get('date_to','') }}">
                    </div>
                </div>
                
                <!-- Фильтры по категории и местоположению -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <div>
                        <label for="category_filter" class="text-sm font-semibold text-gray-700 mb-2 block">
                            Категория 
                            {% if request.args.getlist('category') %}
                            <span class="text-blue-600 font-normal">(выбрано: {{ request.args.getlist('category')|length }})</span>
                            {% endif %}
                        </label>
                        <select id="category_filter" name="category" multiple size="3" class="form-select w-full border-2 border-gray-300 rounded-lg p-2 bg-white text-sm" style="min-height: 80px;">
                            {% for cat in categories_list %}
                            <option value="{{ cat }}" {% if cat in request.args.getlist('category') %}selected{% endif %}>{{ cat }}</option>
                            {% endfor %}
                        </select>
                        <p class="text-xs text-gray-500 mt-1">Удерживайте Ctrl (Cmd на Mac) для выбора нескольких</p>
                    </div>
                    <div>
                        <label for="location_filter" class="text-sm font-semibold text-gray-700 mb-2 block">
                            Местоположение (кабинет)
                            {% if request.args.getlist('location') %}
                            <span class="text-blue-600 font-normal">(выбрано: {{ request.args.getlist('location')|length }})</span>
                            {% endif %}
                        </label>
                        <select id="location_filter" name="location" multiple size="8" class="form-select w-full border-2 border-gray-300 rounded-lg p-2 bg-white text-sm" style="min-height: 200px;">
                            {% if locations_list %}
                                {% for loc in locations_list %}
                                <option value="{{ loc }}" {% if loc in request.args.getlist('location') %}selected{% endif %}>{{ loc }}</option>
                                {% endfor %}
                            {% else %}
                                <option disabled>Местоположения не найдены</option>
                            {% endif %}
                        </select>
                        <p class="text-xs text-gray-500 mt-1">Удерживайте Ctrl (Cmd на Mac) для выбора нескольких</p>
                    </div>
                </div>
                
                <div class="flex gap-3">
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Найти</button>
                    <a href="/assets/export?search={{ request.args.get('search','') }}&date_from={{ request.args.get('date_from','') }}&date_to={{ request.args.get('date_to','') }}" class="btn px-6 py-2.5">Экспорт CSV</a>
                    <a href="/assets" class="btn px-6 py-2.5">Сбросить</a>
                </div>
            </form>

            <!-- Активные фильтры -->
            {% if request.args.getlist('category') or request.args.getlist('location') or request.args.get('search') %}
            <div class="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-semibold text-gray-700">Активные фильтры:</span>
                    {% if request.args.get('search') %}
                    <span class="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-medium">
                        Поиск: "{{ request.args.get('search') }}"
                    </span>
                    {% endif %}
                    {% for cat in request.args.getlist('category') %}
                    <span class="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-medium">
                        Категория: {{ cat }}
                    </span>
                    {% endfor %}
                    {% for loc in request.args.getlist('location') %}
                    <span class="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
                        Кабинет: {{ loc }}
                    </span>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            <!-- Настройка колонок -->
            <div class="card p-4 mb-6 bg-gray-50 border border-gray-200">
                <div class="font-semibold text-gray-800 mb-3">Отображаемые колонки</div>
                <div id="columnsToggle" class="flex flex-wrap gap-4">
                    {% for key, label, width in available_columns %}
                        <label class="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                            <input type="checkbox" class="col-toggle w-4 h-4 text-blue-600" data-col="{{ key }}"> 
                            <span>{{ label }}</span>
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
                                <th data-col="{{ key }}" {% if width %}style="width:{{ width }};"{% endif %}>{{ label }}</th>
                            {% endfor %}
                            <th style="width:100px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for asset in assets_display %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td data-col="inventory_number">
                                <a href="/asset/{{ asset.id }}" class="text-blue-600 hover:text-blue-800 hover:underline font-mono text-xs">
                                    {{ asset.inventory_number }}
                                </a>
                            </td>
                            <td data-col="name" class="font-medium text-gray-900">{{ asset.name }}</td>
                            <td data-col="serial_number" class="text-sm text-gray-600">{{ asset.serial_number or '—' }}</td>
                            <td data-col="acquisition_date" class="text-sm text-gray-600">{{ asset.acquisition_date }}</td>
                            <td data-col="accounting_status" class="text-sm text-gray-600">{{ asset.accounting_status }}</td>
                            <td data-col="location" class="text-sm text-gray-600">{{ asset.location }}</td>
                            <td data-col="initial_cost" class="text-right font-semibold text-gray-900">{{ asset.initial_cost|currency }}</td>
                            <td class="text-center">
                                <a href="/asset/{{ asset.id }}" class="btn btn-primary text-xs px-3 py-1.5">Открыть</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <p class="text-sm text-gray-600 mt-4">Показано: <span class="font-semibold">{{ assets_display|length }}</span></p>
            {% else %}
            <div class="text-center py-12">
                <div class="text-5xl mb-4">🔍</div>
                <p class="text-gray-500 text-lg font-semibold">Ничего не найдено</p>
            </div>
            {% endif %}
        </div>
        <script>
            (function() {
                const STORAGE_KEY = 'visibleColumns_assets_v3';
                const allCols = {{ available_columns|tojson }};
                const toggles = document.querySelectorAll('.col-toggle');
                const table = document.getElementById('assetsTable');
                if (!table) return;
                const allKeys = new Set(allCols.map(([k]) => k));
                function getSaved() {
                    try { const r = localStorage.getItem(STORAGE_KEY); return r ? JSON.parse(r) : null; } catch { return null; }
                }
                function save(l) { localStorage.setItem(STORAGE_KEY, JSON.stringify(l)); }
                function apply(vis) {
                    const s = new Set(vis);
                    allCols.forEach(([k]) => {
                        const th = table.querySelector('thead th[data-col="'+k+'"]');
                        if (th) th.style.display = s.has(k) ? '' : 'none';
                    });
                    table.querySelectorAll('tbody tr').forEach(tr => {
                        allCols.forEach(([k]) => {
                            const td = tr.querySelector('td[data-col="'+k+'"]');
                            if (td) td.style.display = s.has(k) ? '' : 'none';
                        });
                    });
                    toggles.forEach(cb => { cb.checked = s.has(cb.dataset.col); });
                }
                const def = ['inventory_number','name','serial_number','acquisition_date','accounting_status','location','initial_cost'];
                let saved = (getSaved() || def).filter(k => allKeys.has(k));
                if (!saved.length) saved = def.slice();
                toggles.forEach(cb => {
                    cb.addEventListener('change', () => {
                        let cur = (getSaved() || def).filter(k => allKeys.has(k));
                        if (cb.checked) { if (!cur.includes(cb.dataset.col)) cur.push(cb.dataset.col); }
                        else { cur = cur.filter(k => k !== cb.dataset.col); if (!cur.length) cur = def.slice(0,1); }
                        save(cur); apply(cur);
                    });
                });
                apply(saved);
            })();
        </script>
    {% endblock %}
    """
    return render(content, page='assets', assets_display=assets_display, available_columns=available_columns,
                  locations_list=locations_list, categories_list=categories_list)


@app.route('/assets/export')
def assets_export():
    import csv
    from io import StringIO
    conn = get_db()
    search = request.args.get('search', '')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    query = '''
        SELECT a.*, aa.serial_number as serial_number
        FROM assets a LEFT JOIN actual_assets aa ON a.id = aa.asset_id
        WHERE 1=1
    '''
    params = []
    if search:
        like = f'%{search}%'
        query += ' AND (a.name LIKE ? OR a.inventory_number LIKE ?)'
        params.extend([like, like])
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
    cw.writerow(['Инвентарный номер', 'Основное средство', 'Заводской номер',
                 'Дата принятия к учету', 'Состояние', 'Стоимость первоначальная'])
    for r in rows:
        cw.writerow([r['inventory_number'] or '', r['name'] or '', r['serial_number'] or '',
                     r['acquisition_date'] or '', r['accounting_status'] or '', r['initial_cost'] or ''])
    output = si.getvalue().encode('utf-8-sig')
    return Response(output, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=assets_export.csv'})


@app.route('/import_1s_auto', methods=['GET', 'POST'])
def import_1s_auto():
    if request.method == 'POST':
        if 'file' not in request.files or request.files['file'].filename == '':
            flash('Файл не выбран', 'error')
            return redirect(url_for('assets_list'))
        file = request.files['file']
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            result = import_1s_final(filepath, db_path=DATABASE)
            inserted = result.get("inserted", 0)
            updated = result.get("updated", 0)
            errors = result.get("errors", [])
            if errors:
                flash(f'Автоимпорт: новых {inserted}, обновлено {updated}, ошибок {len(errors)}.', 'warning')
            else:
                flash(f'Автоимпорт: новых {inserted}, обновлено {updated}.', 'success')
        except Exception as e:
            flash(f'Ошибка автоимпорта: {e}', 'error')
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
        return redirect(url_for('assets_list'))
    return redirect(url_for('assets_list'))


# ============================================================
# ФАКТ (инвентаризация) — просмотр + ручной ввод + импорт Excel + шаблон
# ============================================================

@app.route('/facts', methods=['GET', 'POST'])
def facts_list():
    if request.method == 'POST':
        action = request.form.get('action', '')

        # --- Ручной ввод ---
        if action == 'manual_add':
            inv = (request.form.get('inventory_number') or '').strip()
            name = (request.form.get('name') or '').strip()
            serial_number = (request.form.get('serial_number') or '').strip() or None
            condition_status = (request.form.get('condition_status') or '').strip() or None
            location = (request.form.get('location') or '').strip() or None
            ip_address = (request.form.get('ip_address') or '').strip() or None
            notes = (request.form.get('notes') or '').strip() or None

            if not name:
                flash('Укажите название', 'error')
                return redirect(url_for('facts_list'))

            conn = get_db()
            matched_id = None
            if inv:
                asset = conn.execute('SELECT id FROM assets WHERE inventory_number = ?', (inv,)).fetchone()
                if asset:
                    matched_id = asset['id']

            conn.execute('''
                INSERT INTO fact_inventory
                (inventory_number, name, serial_number, condition_status,
                 location, ip_address, notes, source, observed_date, matched_asset_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', date('now'), ?)
            ''', (inv or None, name, serial_number, condition_status,
                  location, ip_address, notes, matched_id))
            conn.commit()
            conn.close()
            flash('Запись факта добавлена', 'success')
            return redirect(url_for('facts_list'))

        # --- Импорт из Excel/CSV ---
        if action == 'import_file':
            if 'file' not in request.files or request.files['file'].filename == '':
                flash('Файл не выбран', 'error')
                return redirect(url_for('facts_list'))
            file = request.files['file']
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                df = read_file_to_df(filepath, filename)
                df = df.dropna(how='all').reset_index(drop=True)
                df.columns = [str(c).strip() for c in df.columns]
            except Exception as e:
                flash(f'Ошибка чтения файла: {e}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(url_for('facts_list'))

            mapping = smart_fact_mapping(df.columns)
            preview = df.head(5).to_dict(orient='records')

            content = """
            {% block content %}
                <div class="card p-6">
                    <div class="flex items-center justify-between mb-6">
                        <h2 class="text-2xl font-bold text-gray-900">Сопоставление колонок (факт)</h2>
                        <a href="/facts" class="btn px-4 py-2">Отмена</a>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-4 mb-6 border border-gray-200">
                        <p class="text-sm text-gray-600"><span class="font-semibold">Файл:</span> <span class="font-mono text-gray-900">{{ filename }}</span></p>
                        <p class="text-sm text-gray-600 mt-1"><span class="font-semibold">Строк:</span> <span class="font-bold text-gray-900">{{ total_rows }}</span></p>
                    </div>
                    <form method="post" class="space-y-6">
                        <input type="hidden" name="action" value="confirm_import">
                        <input type="hidden" name="filename" value="{{ filename }}">
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th style="width:200px;">Колонка в файле</th>
                                        <th>Пример</th>
                                        <th style="width:250px;">Сопоставить с</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for col in columns %}
                                    <tr class="hover:bg-gray-50 transition-colors duration-150">
                                        <td class="font-semibold text-gray-900">{{ col }}</td>
                                        <td class="text-sm text-gray-600 font-mono">{{ preview[0][col] if preview and col in preview[0] else '—' }}</td>
                                        <td>
                                            <select name="map_{{ col }}" class="form-select">
                                                <option value="ignore">Игнорировать</option>
                                                <option value="inventory_number" {% if mapping[col]=='inventory_number' %}selected{% endif %}>Инв. номер</option>
                                                <option value="name" {% if mapping[col]=='name' %}selected{% endif %}>Наименование</option>
                                                <option value="serial_number" {% if mapping[col]=='serial_number' %}selected{% endif %}>Серийный номер</option>
                                                <option value="condition_status" {% if mapping[col]=='condition_status' %}selected{% endif %}>Состояние</option>
                                                <option value="location" {% if mapping[col]=='location' %}selected{% endif %}>Местоположение</option>
                                                <option value="ip_address" {% if mapping[col]=='ip_address' %}selected{% endif %}>IP-адрес</option>
                                                <option value="notes" {% if mapping[col]=='notes' %}selected{% endif %}>Примечание</option>
                                            </select>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        <div class="flex gap-3">
                            <button type="submit" class="btn btn-primary px-6 py-2.5">Импортировать в факт</button>
                        </div>
                    </form>
                </div>
            {% endblock %}
            """
            return render(content, page='facts', filename=filename, columns=list(df.columns),
                          preview=preview, mapping=mapping, total_rows=len(df))

        # --- Подтверждение импорта ---
        if action == 'confirm_import':
            filename = request.form.get('filename', '')
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
            if not os.path.exists(filepath):
                flash('Файл не найден', 'error')
                return redirect(url_for('facts_list'))
            try:
                df = read_file_to_df(filepath, filename)
                df = df.dropna(how='all').reset_index(drop=True)
                df.columns = [str(c).strip() for c in df.columns]
            except Exception as e:
                flash(f'Ошибка чтения: {e}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(url_for('facts_list'))

            mapping = {}
            for col in df.columns:
                mapping[col] = request.form.get(f'map_{col}', 'ignore')

            conn = get_db()
            added = 0
            try:
                for _, row in df.iterrows():
                    record = {}
                    for col, field in mapping.items():
                        if field != 'ignore' and pd.notna(row.get(col)):
                            v = str(row[col]).strip()
                            if v.lower() not in ('nan', 'none', ''):
                                record[field] = v
                    if record.get('inventory_number') or record.get('name'):
                        matched_id = None
                        if record.get('inventory_number'):
                            asset = conn.execute('SELECT id FROM assets WHERE inventory_number = ?',
                                                 (record['inventory_number'],)).fetchone()
                            if asset:
                                matched_id = asset['id']
                        conn.execute('''
                            INSERT INTO fact_inventory
                            (inventory_number, name, serial_number, condition_status,
                             location, ip_address, notes, source, observed_date, matched_asset_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 'import', date('now'), ?)
                        ''', (record.get('inventory_number'), record.get('name'), record.get('serial_number'),
                              record.get('condition_status'),
                              record.get('location'), record.get('ip_address'), record.get('notes'), matched_id))
                        added += 1
                conn.commit()
            finally:
                conn.close()
                if os.path.exists(filepath):
                    os.remove(filepath)
            flash(f'Импорт факта: добавлено {added} записей', 'success')
            return redirect(url_for('facts_list'))

    # --- GET: список факта ---
    conn = get_db()
    search = request.args.get('search', '').strip()
    location_filter = request.args.getlist('location')  # Множественный выбор
    category_filter = request.args.getlist('category')  # Множественный выбор

    # Получаем список уникальных местоположений из факта (только номера кабинетов)
    try:
        locations_raw = conn.execute('''
            SELECT DISTINCT location 
            FROM fact_inventory 
            WHERE location IS NOT NULL AND location != ''
            ORDER BY location
        ''').fetchall()
        locations_set = set()
        for loc in locations_raw:
            if loc['location']:
                loc_str = loc['location'].strip()
                # Если это просто номер кабинета (содержит цифры и дефис/тире), добавляем
                if any(c.isdigit() for c in loc_str) and ('-' in loc_str or '—' in loc_str or len(loc_str) <= 10):
                    locations_set.add(loc_str)
                # Также ищем паттерны номеров кабинетов в тексте
                matches = re.findall(r'\b(\d+[-—]\d+|\d+-\d+|\d{1,3})\b', loc_str)
                for match in matches:
                    if len(match) <= 10:
                        locations_set.add(match)
        locations_list = sorted(list(locations_set))
    except:
        locations_list = []

    # Определяем категории по названиям (Техника/Мебель)
    # Для факта определяем категорию по ключевым словам в названии
    categories_list = ['Техника', 'Мебель']

    query = '''
        SELECT f.*, a.inventory_number as a_inv, a.name as a_name, a.category as asset_category
        FROM fact_inventory f
        LEFT JOIN assets a ON a.id = f.matched_asset_id
        WHERE 1=1
    '''
    params = []
    if search:
        like = f'%{search}%'
        query += ''' AND (IFNULL(f.inventory_number,'') LIKE ? OR IFNULL(f.name,'') LIKE ?
                         OR IFNULL(f.serial_number,'') LIKE ? OR IFNULL(f.location,'') LIKE ?) '''
        params.extend([like, like, like, like])
    if location_filter:
        placeholders = ','.join(['?' for _ in location_filter])
        query += f' AND f.location IN ({placeholders})'
        params.extend(location_filter)
    if category_filter:
        # Определяем категорию по названию или по категории из связанного актива
        category_conditions = []
        for cat in category_filter:
            if cat == 'Техника':
                # Ключевые слова для техники
                category_conditions.append('''(LOWER(f.name) LIKE '%принтер%' OR LOWER(f.name) LIKE '%компьютер%' 
                    OR LOWER(f.name) LIKE '%ноутбук%' OR LOWER(f.name) LIKE '%монитор%' 
                    OR LOWER(f.name) LIKE '%проектор%' OR LOWER(f.name) LIKE '%мфу%'
                    OR LOWER(f.name) LIKE '%сканер%' OR LOWER(f.name) LIKE '%планшет%'
                    OR a.category = 'Техника')''')
            elif cat == 'Мебель':
                # Ключевые слова для мебели
                category_conditions.append('''(LOWER(f.name) LIKE '%стол%' OR LOWER(f.name) LIKE '%стул%' 
                    OR LOWER(f.name) LIKE '%шкаф%' OR LOWER(f.name) LIKE '%полка%'
                    OR LOWER(f.name) LIKE '%кресло%' OR LOWER(f.name) LIKE '%диван%'
                    OR LOWER(f.name) LIKE '%тумба%' OR a.category = 'Мебель')''')
        if category_conditions:
            query += ' AND (' + ' OR '.join(category_conditions) + ')'
    query += ' ORDER BY COALESCE(f.observed_date, f.created_at) DESC, f.id DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()

    content = """
    {% block content %}
        <div class="card p-6 mb-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-900">Факт (инвентаризация)</h2>
                <a href="/facts/template" class="btn btn-success px-4 py-2">Скачать шаблон Excel</a>
            </div>

            <form method="get" class="space-y-4 mb-6">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="form-group">
                        <label for="facts_search" class="text-sm font-semibold text-gray-700 mb-2 block">Поиск</label>
                        <input type="text" id="facts_search" name="search" class="form-input" placeholder="Поиск (инв., серийник, локация, имя)" value="{{ request.args.get('search','') }}">
                    </div>
                    <div class="form-group md:col-span-2">
                        <div class="flex gap-3">
                            <button type="submit" class="btn btn-primary px-6 py-2.5 whitespace-nowrap">Найти</button>
                            <a href="/facts" class="btn px-6 py-2.5 whitespace-nowrap">Сбросить</a>
                        </div>
                    </div>
                </div>
                
                <!-- Фильтры по категории и местоположению -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <div>
                        <label for="facts_category_filter" class="text-sm font-semibold text-gray-700 mb-2 block">
                            Категория 
                            {% if request.args.getlist('category') %}
                            <span class="text-blue-600 font-normal">(выбрано: {{ request.args.getlist('category')|length }})</span>
                            {% endif %}
                        </label>
                        <select id="facts_category_filter" name="category" multiple size="3" class="form-select w-full border-2 border-gray-300 rounded-lg p-2 bg-white text-sm" style="min-height: 80px;">
                            {% for cat in categories_list %}
                            <option value="{{ cat }}" {% if cat in request.args.getlist('category') %}selected{% endif %}>{{ cat }}</option>
                            {% endfor %}
                        </select>
                        <p class="text-xs text-gray-500 mt-1">Удерживайте Ctrl (Cmd на Mac) для выбора нескольких</p>
                    </div>
                    <div>
                        <label for="facts_location_filter" class="text-sm font-semibold text-gray-700 mb-2 block">
                            Местоположение (кабинет)
                            {% if request.args.getlist('location') %}
                            <span class="text-blue-600 font-normal">(выбрано: {{ request.args.getlist('location')|length }})</span>
                            {% endif %}
                        </label>
                        <select id="facts_location_filter" name="location" multiple size="8" class="form-select w-full border-2 border-gray-300 rounded-lg p-2 bg-white text-sm" style="min-height: 200px;">
                            {% if locations_list %}
                                {% for loc in locations_list %}
                                <option value="{{ loc }}" {% if loc in request.args.getlist('location') %}selected{% endif %}>{{ loc }}</option>
                                {% endfor %}
                            {% else %}
                                <option disabled>Местоположения не найдены</option>
                            {% endif %}
                        </select>
                        <p class="text-xs text-gray-500 mt-1">Удерживайте Ctrl (Cmd на Mac) для выбора нескольких</p>
                    </div>
                </div>
            </form>

            <!-- Активные фильтры -->
            {% if request.args.getlist('category') or request.args.getlist('location') or request.args.get('search') %}
            <div class="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-semibold text-gray-700">Активные фильтры:</span>
                    {% if request.args.get('search') %}
                    <span class="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-medium">
                        Поиск: "{{ request.args.get('search') }}"
                    </span>
                    {% endif %}
                    {% for cat in request.args.getlist('category') %}
                    <span class="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-medium">
                        Категория: {{ cat }}
                    </span>
                    {% endfor %}
                    {% for loc in request.args.getlist('location') %}
                    <span class="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
                        Кабинет: {{ loc }}
                    </span>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:120px;">Инв. номер</th>
                            <th>Наименование</th>
                            <th style="width:140px;">Серийный номер</th>
                            <th style="width:110px;">Состояние</th>
                            <th style="width:150px;">Местоположение</th>
                            <th style="width:110px;">IP</th>
                            <th style="width:100px;">Дата</th>
                            <th style="width:120px;">Связь с бух.</th>
                            <th style="width:100px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for f in rows %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td class="font-mono text-xs text-gray-700">{{ f['inventory_number'] or '—' }}</td>
                            <td class="font-medium text-gray-900">{{ f['name'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ f['serial_number'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ f['condition_status'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ f['location'] or '—' }}</td>
                            <td class="font-mono text-xs text-gray-600">{{ f['ip_address'] or '—' }}</td>
                            <td class="text-sm text-gray-500">{{ f['observed_date'] or f['created_at'][:10] }}</td>
                            <td>
                                {% if f['a_inv'] %}
                                    <a href="/asset/{{ f['matched_asset_id'] }}" class="text-blue-600 hover:text-blue-800 hover:underline font-medium">{{ f['a_inv'] }}</a>
                                {% else %}
                                    <span class="text-gray-400">—</span>
                                {% endif %}
                            </td>
                            <td>
                                <a href="/fact/{{ f['id'] }}/edit" class="btn btn-primary text-xs px-3 py-1.5">Ред.</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <p class="text-sm text-gray-600 mt-4">Всего записей: <span class="font-semibold">{{ rows|length }}</span></p>
        </div>

        <!-- Разделитель и переход к формам -->
        <div class="my-8 flex items-center justify-center">
            <div class="flex-1 border-t border-gray-300"></div>
            <a href="#forms-section" class="mx-4 px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:opacity-90 transition-opacity duration-200 text-sm font-semibold shadow-lg shadow-blue-500/50">
                ↓ Перейти к формам ввода ↓
            </a>
            <div class="flex-1 border-t border-gray-300"></div>
        </div>

        <!-- Ручной ввод -->
        <div id="forms-section" class="card p-6 mb-6 scroll-mt-8">
            <h3 class="text-xl font-bold text-gray-900 mb-5">Добавить запись факта</h3>
            <form method="post" class="space-y-5">
                <input type="hidden" name="action" value="manual_add">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    <div class="form-group">
                        <label for="fact_inventory_number">Инвентарный номер</label>
                        <input type="text" id="fact_inventory_number" name="inventory_number" class="form-input" placeholder="004006426">
                    </div>
                    <div class="form-group md:col-span-2">
                        <label for="fact_name">Название <span class="text-red-500">*</span></label>
                        <input type="text" id="fact_name" name="name" class="form-input" required placeholder="Что видит обходчик">
                    </div>
                    <div class="form-group">
                        <label for="fact_serial_number">Серийный номер</label>
                        <input type="text" id="fact_serial_number" name="serial_number" class="form-input" placeholder="с шильдика или б/н">
                    </div>
                    <div class="form-group">
                        <label for="fact_condition_status">Состояние</label>
                        <select id="fact_condition_status" name="condition_status" class="form-select">
                            <option value="">—</option>
                            <option value="Исправно">Исправно</option>
                            <option value="Сломано">Сломано</option>
                            <option value="Утеряно">Утеряно</option>
                            <option value="На ремонте">На ремонте</option>
                            <option value="Списано">Списано</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="fact_location">Местоположение (кабинет)</label>
                        <input type="text" id="fact_location" name="location" class="form-input" placeholder="33-12">
                    </div>
                    <div class="form-group">
                        <label for="fact_ip_address">IP-адрес</label>
                        <input type="text" id="fact_ip_address" name="ip_address" class="form-input" placeholder="192.168.1.10">
                    </div>
                    <div class="form-group md:col-span-3">
                        <label for="fact_notes">Примечание</label>
                        <textarea id="fact_notes" name="notes" class="form-textarea" placeholder="Дополнительная информация"></textarea>
                    </div>
                </div>
                <div class="flex gap-3">
                    <button class="btn btn-primary px-6 py-2.5" type="submit">Добавить запись</button>
                </div>
            </form>
        </div>

        <!-- Импорт из файла -->
        <div class="card p-6">
            <h3 class="text-xl font-bold text-gray-900 mb-4">Импорт факта из Excel/CSV</h3>
            <form method="post" enctype="multipart/form-data" class="flex gap-3 items-end">
                <input type="hidden" name="action" value="import_file">
                <div class="form-group flex-1">
                    <label for="fact_file">Выберите файл</label>
                    <input type="file" id="fact_file" name="file" accept=".xlsx,.xls,.csv" required class="form-input">
                </div>
                <button type="submit" class="btn btn-primary px-6 py-2.5 whitespace-nowrap">Загрузить и сопоставить</button>
            </form>
        </div>
    {% endblock %}
    """
    return render(content, page='facts', rows=rows, locations_list=locations_list, categories_list=categories_list)


@app.route('/facts/template')
def facts_template():
    """Скачать шаблон Excel для заполнения факта."""
    df = pd.DataFrame(columns=[
        'Инвентарный номер', 'Название', 'Серийный номер',
        'Состояние', 'Местоположение', 'IP-адрес', 'Примечание'
    ])
    # Пример строки
    df.loc[0] = ['004006426', 'Принтер HP LaserJet', 'VNB3Y12345', 'Исправно', '33-12', '192.168.1.50', '']
    df.loc[1] = ['', 'Стол ученический', 'б/н', 'Исправно', '33-07', '', 'Без инв. номера на бирке']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'shablon_fact.xlsx')
    df.to_excel(filepath, index=False)
    with open(filepath, 'rb') as f:
        data = f.read()
    os.remove(filepath)
    return Response(data, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename=shablon_fact.xlsx'})


@app.route('/fact/<int:fact_id>/edit', methods=['GET', 'POST'])
def fact_edit(fact_id):
    conn = get_db()
    fact = conn.execute('SELECT * FROM fact_inventory WHERE id = ?', (fact_id,)).fetchone()
    if not fact:
        conn.close()
        flash('Запись не найдена', 'error')
        return redirect(url_for('facts_list'))

    if request.method == 'POST':
        fields = ['inventory_number', 'name', 'serial_number', 'condition_status',
                   'location', 'ip_address', 'notes']
        updates = {}
        for f in fields:
            new_val = (request.form.get(f) or '').strip() or None
            old_val = fact[f]
            if new_val != old_val:
                updates[f] = new_val
                log_change(conn, 'fact_inventory', fact_id, f, old_val, new_val, 'Редактирование факта')

        if updates:
            set_clause = ', '.join([f"{k} = ?" for k in updates])
            conn.execute(f"UPDATE fact_inventory SET {set_clause} WHERE id = ?",
                         list(updates.values()) + [fact_id])
            # Обновляем matched_asset_id если инв. номер изменился
            inv = updates.get('inventory_number', fact['inventory_number'])
            if inv:
                asset = conn.execute('SELECT id FROM assets WHERE inventory_number = ?', (inv,)).fetchone()
                conn.execute('UPDATE fact_inventory SET matched_asset_id = ? WHERE id = ?',
                             (asset['id'] if asset else None, fact_id))
            conn.commit()
            flash('Запись факта обновлена', 'success')
        else:
            flash('Изменений нет', 'warning')
        conn.close()
        return redirect(url_for('facts_list'))

    conn.close()
    content = """
    {% block content %}
        <div class="card p-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-900">Редактирование записи факта #{{ fact['id'] }}</h2>
                <a href="/facts" class="btn px-4 py-2">← Назад</a>
            </div>
            <form method="post" class="space-y-5">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    <div class="form-group">
                        <label for="edit_inventory_number">Инвентарный номер</label>
                        <input type="text" id="edit_inventory_number" name="inventory_number" class="form-input" value="{{ fact['inventory_number'] or '' }}">
                    </div>
                    <div class="form-group md:col-span-2">
                        <label for="edit_name">Наименование</label>
                        <input type="text" id="edit_name" name="name" class="form-input" value="{{ fact['name'] or '' }}">
                    </div>
                    <div class="form-group">
                        <label for="edit_serial_number">Серийный номер</label>
                        <input type="text" id="edit_serial_number" name="serial_number" class="form-input" value="{{ fact['serial_number'] or '' }}">
                    </div>
                    <div class="form-group">
                        <label for="edit_condition_status">Состояние</label>
                        <select id="edit_condition_status" name="condition_status" class="form-select">
                            <option value="">—</option>
                            {% for s in ['Исправно','Сломано','Утеряно','На ремонте','Списано'] %}
                                <option value="{{ s }}" {% if fact['condition_status'] == s %}selected{% endif %}>{{ s }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="edit_location">Местоположение</label>
                        <input type="text" id="edit_location" name="location" class="form-input" value="{{ fact['location'] or '' }}">
                    </div>
                    <div class="form-group">
                        <label for="edit_ip_address">IP-адрес</label>
                        <input type="text" id="edit_ip_address" name="ip_address" class="form-input" value="{{ fact['ip_address'] or '' }}">
                    </div>
                    <div class="form-group md:col-span-3">
                        <label for="edit_notes">Примечание</label>
                        <textarea id="edit_notes" name="notes" class="form-textarea">{{ fact['notes'] or '' }}</textarea>
                    </div>
                </div>
                <div class="flex gap-3">
                    <button class="btn btn-primary px-6 py-2.5" type="submit">Сохранить</button>
                    <a href="/facts" class="btn px-6 py-2.5">Отмена</a>
                </div>
            </form>
        </div>
    {% endblock %}
    """
    return render(content, page='facts', fact=fact)


# ============================================================
# СВЕРКА (несоответствия)
# ============================================================

@app.route('/discrepancies')
def discrepancies_page():
    flt = request.args.get('filter', '').strip()
    conn = get_db()

    rows = conn.execute('''
        SELECT
            a.id as asset_id, a.inventory_number as a_inv, a.name as a_name,
            a.accounting_status as a_status,
            f.id as f_id, f.inventory_number as f_inv,
            f.serial_number as f_serial, f.condition_status as f_condition,
            f.location as f_location, f.observed_date as f_date
        FROM assets a
        LEFT JOIN (
            SELECT fi.* FROM fact_inventory fi
            INNER JOIN (
                SELECT inventory_number, MAX(id) as max_id
                FROM fact_inventory WHERE inventory_number IS NOT NULL
                GROUP BY inventory_number
            ) latest ON fi.id = latest.max_id
        ) f ON f.inventory_number = a.inventory_number
        ORDER BY a.id DESC
    ''').fetchall()

    orphan_facts = conn.execute('''
        SELECT f.* FROM fact_inventory f
        LEFT JOIN assets a ON a.inventory_number = f.inventory_number
        WHERE a.id IS NULL AND f.inventory_number IS NOT NULL
        ORDER BY f.id DESC
    ''').fetchall()
    conn.close()

    all_items = []
    for r in rows:
        mismatches = []
        if r['f_inv'] is None:
            mismatches.append(('NOT_FOUND', 'Нет данных факта'))
        else:
            if r['f_condition'] and r['f_condition'] not in ('Исправно', ''):
                mismatches.append(('COND', f"Состояние: {r['f_condition']}"))
            if not r['f_serial'] or r['f_serial'].strip() == '':
                mismatches.append(('SERIAL', 'Нет серийника'))
        all_items.append({
            'asset_id': r['asset_id'], 'fact_id': r['f_id'],
            'inventory_number': r['a_inv'] or '—', 'name': r['a_name'],
            'location_fact': r['f_location'] or '—', 'serial_fact': r['f_serial'] or '—',
            'observed_date': r['f_date'] or '—', 'mismatches': mismatches
        })

    cnt_ok = sum(1 for it in all_items if not it['mismatches'])
    cnt_nf = sum(1 for it in all_items if any(c == 'NOT_FOUND' for c, _ in it['mismatches']))
    cnt_mm = sum(1 for it in all_items if it['mismatches'] and not any(c == 'NOT_FOUND' for c, _ in it['mismatches']))
    cnt_or = len(orphan_facts)

    if flt == 'ok':
        shown = [it for it in all_items if not it['mismatches']]
        title = 'Совпадающие объекты'
    elif flt == 'no_fact':
        shown = [it for it in all_items if any(c == 'NOT_FOUND' for c, _ in it['mismatches'])]
        title = 'Нет данных факта'
    elif flt == 'mismatch':
        shown = [it for it in all_items if it['mismatches'] and not any(c == 'NOT_FOUND' for c, _ in it['mismatches'])]
        title = 'Есть расхождения'
    elif flt == 'orphan':
        shown = []
        title = 'Лишнее в факте'
    else:
        shown = [it for it in all_items if it['mismatches']]
        title = 'Сверка: бухгалтерия vs факт'

    content = """
    {% block content %}
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div class="bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl shadow-lg hover:shadow-xl transition-shadow duration-200 cursor-pointer" role="button" tabindex="0" data-href="/discrepancies?filter=ok" onclick="window.location.href=this.getAttribute('data-href')" onkeydown="if(event.key==='Enter')window.location.href=this.getAttribute('data-href')">
                <div class="p-6 text-white">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-xs font-bold uppercase tracking-wider opacity-90">Совпадают</h3>
                        <div class="bg-white/20 rounded-lg p-2">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                        </div>
                    </div>
                    <div class="text-4xl font-bold mb-2">{{ cnt_ok }}</div>
                    <div class="text-sm opacity-90">Все записи совпадают</div>
                </div>
            </div>

            <div class="bg-gradient-to-br from-red-500 to-rose-600 rounded-xl shadow-lg hover:shadow-xl transition-shadow duration-200 cursor-pointer" role="button" tabindex="0" data-href="/discrepancies?filter=no_fact" onclick="window.location.href=this.getAttribute('data-href')" onkeydown="if(event.key==='Enter')window.location.href=this.getAttribute('data-href')">
                <div class="p-6 text-white">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-xs font-bold uppercase tracking-wider opacity-90">Нет данных факта</h3>
                        <div class="bg-white/20 rounded-lg p-2">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                            </svg>
                        </div>
                    </div>
                    <div class="text-4xl font-bold mb-2">{{ cnt_nf }}</div>
                    <div class="text-sm opacity-90">Требуют внимания</div>
                </div>
            </div>

            <div class="bg-gradient-to-br from-orange-500 to-amber-600 rounded-xl shadow-lg hover:shadow-xl transition-shadow duration-200 cursor-pointer" role="button" tabindex="0" data-href="/discrepancies?filter=mismatch" onclick="window.location.href=this.getAttribute('data-href')" onkeydown="if(event.key==='Enter')window.location.href=this.getAttribute('data-href')">
                <div class="p-6 text-white">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-xs font-bold uppercase tracking-wider opacity-90">Есть расхождения</h3>
                        <div class="bg-white/20 rounded-lg p-2">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                            </svg>
                        </div>
                    </div>
                    <div class="text-4xl font-bold mb-2">{{ cnt_mm }}</div>
                    <div class="text-sm opacity-90">Нужна проверка</div>
                </div>
            </div>

            <div class="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg hover:shadow-xl transition-shadow duration-200 cursor-pointer" role="button" tabindex="0" data-href="/discrepancies?filter=orphan" onclick="window.location.href=this.getAttribute('data-href')" onkeydown="if(event.key==='Enter')window.location.href=this.getAttribute('data-href')">
                <div class="p-6 text-white">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-xs font-bold uppercase tracking-wider opacity-90">Лишнее в факте</h3>
                        <div class="bg-white/20 rounded-lg p-2">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                            </svg>
                        </div>
                    </div>
                    <div class="text-4xl font-bold mb-2">{{ cnt_or }}</div>
                    <div class="text-sm opacity-90">Не найдены в бух.</div>
                </div>
            </div>
        </div>

        <div class="card p-5 mb-6">
            <p class="text-sm text-gray-600 mb-3 font-semibold"><strong class="text-gray-800">Перейти к списку:</strong></p>
            <div class="flex flex-wrap gap-2">
                <a href="/discrepancies?filter=ok" class="px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-lg hover:opacity-90 transition-opacity duration-200 text-sm font-semibold">Совпадают ({{ cnt_ok }})</a>
                <a href="/discrepancies?filter=no_fact" class="px-4 py-2 bg-gradient-to-r from-red-500 to-rose-600 text-white rounded-lg hover:opacity-90 transition-opacity duration-200 text-sm font-semibold">Нет данных факта ({{ cnt_nf }})</a>
                <a href="/discrepancies?filter=mismatch" class="px-4 py-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white rounded-lg hover:opacity-90 transition-opacity duration-200 text-sm font-semibold">Расхождения ({{ cnt_mm }})</a>
                <a href="/discrepancies?filter=orphan" class="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:opacity-90 transition-opacity duration-200 text-sm font-semibold">Лишнее в факте ({{ cnt_or }})</a>
            </div>
        </div>

        {% if flt %}
        <div class="mb-6">
            <a href="/discrepancies" class="inline-flex items-center px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 rounded-lg transition-colors duration-200 text-sm font-semibold shadow-sm border border-gray-200">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path>
                </svg>
                Показать всё
            </a>
        </div>
        {% endif %}

        {% if flt != 'orphan' %}
        <div class="card p-6">
            <h2 class="text-2xl font-bold text-gray-900 mb-4">{{ title }}</h2>
            {% if shown %}
            <p class="text-sm text-gray-600 mb-4">Показано: <span class="font-semibold text-gray-900">{{ shown|length }}</span></p>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th class="w-[120px]">Инв. номер</th>
                            <th>Наименование (бух)</th>
                            <th class="w-[180px]">Факт. местоположение</th>
                            <th class="w-[140px]">Серийный (факт)</th>
                            <th class="w-[100px]">Дата факта</th>
                            <th class="w-[220px]">Проблемы</th>
                            <th class="w-[160px]">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for it in shown %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td class="font-mono text-xs text-gray-700">{{ it.inventory_number }}</td>
                            <td class="font-medium text-gray-900">{{ it.name }}</td>
                            <td class="text-sm text-gray-600">{{ it.location_fact }}</td>
                            <td class="text-sm text-gray-600">{{ it.serial_fact }}</td>
                            <td class="text-sm text-gray-500">{{ it.observed_date }}</td>
                            <td>
                                {% if it.mismatches %}
                                    <div class="flex flex-wrap gap-2">
                                        {% for code, label in it.mismatches %}
                                            <span class="badge {% if code=='NOT_FOUND' %}badge-red{% elif code=='COND' %}badge-yellow{% else %}badge-gray{% endif %}">{{ label }}</span>
                                        {% endfor %}
                                    </div>
                                {% else %}
                                    <span class="badge badge-green">OK</span>
                                {% endif %}
                            </td>
                            <td>
                                <div class="flex gap-2">
                                    {% if it.fact_id %}
                                    <a class="btn btn-primary text-xs px-3 py-1.5" href="/discrepancies/compare/{{ it.asset_id }}/{{ it.fact_id }}">Сравнить</a>
                                    {% endif %}
                                    <a class="btn bg-gray-600 hover:bg-gray-700 text-white text-xs px-3 py-1.5" href="/asset/{{ it.asset_id }}">Открыть</a>
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="text-center py-12">
                <p class="text-gray-500">Нет записей в этой категории</p>
            </div>
            {% endif %}
        </div>
        {% endif %}

        {% if flt == 'orphan' or (not flt and orphan_facts) %}
        <div class="card p-6">
            <h3 class="text-xl font-bold text-gray-900 mb-4">Факты без записи в бухгалтерии (лишнее): <span class="text-indigo-600">{{ orphan_facts|length }}</span></h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th class="w-[120px]">Инв. номер</th>
                            <th>Наименование</th>
                            <th class="w-[150px]">Местоположение</th>
                            <th class="w-[120px]">Серийный</th>
                            <th class="w-[100px]">Дата</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for f in orphan_facts %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td class="font-mono text-xs text-gray-700">{{ f['inventory_number'] or '—' }}</td>
                            <td class="font-medium text-gray-900">{{ f['name'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ f['location'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ f['serial_number'] or '—' }}</td>
                            <td class="text-sm text-gray-500">{{ f['observed_date'] or '—' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
    {% endblock %}
    """
    return render(content, page='discrepancies', shown=shown, orphan_facts=orphan_facts,
                  flt=flt, title=title, cnt_ok=cnt_ok, cnt_nf=cnt_nf, cnt_mm=cnt_mm, cnt_or=cnt_or)


@app.route('/discrepancies/compare/<int:asset_id>/<int:fact_id>')
def discrepancy_compare(asset_id, fact_id):
    conn = get_db()
    asset = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
    fact = conn.execute('SELECT * FROM fact_inventory WHERE id = ?', (fact_id,)).fetchone()
    actual = conn.execute('SELECT * FROM actual_assets WHERE asset_id = ?', (asset_id,)).fetchone()
    conn.close()
    if not asset or not fact:
        flash('Объект или факт не найден', 'error')
        return redirect(url_for('discrepancies_page'))

    loc_buh = '—'
    if actual and actual['notes']:
        n = actual['notes']
        loc_buh = n.replace('Местоположение: ', '').strip() if 'Местоположение:' in n else n

    fd = dict(fact)
    actual_d = dict(actual) if actual else {}
    fields = [
        ('Состояние', actual_d.get('condition_status') or '—', fd.get('condition_status') or '—'),
        ('Местоположение', loc_buh, fd.get('location') or '—'),
        ('Серийный номер', actual_d.get('serial_number') or '—', fd.get('serial_number') or '—'),
        ('IP-адрес', actual_d.get('ip_address') or '—', fd.get('ip_address') or '—'),
    ]

    content = """
    {% block content %}
        <div class="card p-6">
            <div class="flex items-center justify-between mb-6">
                <div>
                    <h2 class="text-2xl font-bold text-gray-900">Сравнение</h2>
                    <p class="text-sm text-gray-600 mt-1">Инв. номер: <span class="font-mono font-semibold">{{ asset['inventory_number'] }}</span></p>
                    <p class="text-sm text-gray-600">Наименование: <span class="font-semibold">{{ asset['name'] }}</span></p>
                </div>
                <a href="/discrepancies" class="btn px-4 py-2">← Назад к сверке</a>
            </div>
            <div class="table-container mb-6">
                <table>
                    <thead>
                        <tr>
                            <th style="width:200px;">Поле</th>
                            <th>Бухгалтерия</th>
                            <th>Факт</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for label, buh, fval in fields %}
                        <tr class="{% if buh != fval and buh != '—' and fval != '—' %}bg-yellow-50{% else %}hover:bg-gray-50{% endif %} transition-colors duration-150">
                            <td class="font-semibold text-gray-900">{{ label }}</td>
                            <td class="text-sm text-gray-700">{{ buh }}</td>
                            <td class="text-sm {% if buh != fval and buh != '—' and fval != '—' %}text-red-600 font-bold{% else %}text-gray-700{% endif %}">{{ fval }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <div class="flex gap-3">
                <form method="post" action="/discrepancies/merge/{{ asset_id }}/{{ fact_id }}" class="inline">
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Слить факт → бухгалтерию</button>
                </form>
                <a href="/asset/{{ asset_id }}" class="btn px-6 py-2.5">Открыть карточку</a>
                <a href="/discrepancies" class="btn px-6 py-2.5">Отмена</a>
            </div>
        </div>
    {% endblock %}
    """
    return render(content, page='discrepancies', asset=dict(asset), fields=fields,
                  asset_id=asset_id, fact_id=fact_id)


@app.route('/discrepancies/merge/<int:asset_id>/<int:fact_id>', methods=['POST'])
def discrepancy_merge(asset_id, fact_id):
    conn = get_db()
    asset = conn.execute('SELECT id FROM assets WHERE id = ?', (asset_id,)).fetchone()
    fact = conn.execute('SELECT * FROM fact_inventory WHERE id = ?', (fact_id,)).fetchone()
    if not asset or not fact:
        conn.close()
        flash('Не найдено', 'error')
        return redirect(url_for('discrepancies_page'))
    fd = dict(fact)
    loc = fd.get('location') or ''
    notes = f"Местоположение: {loc}" if loc else None
    ip_addr = fd.get('ip_address') or None
    actual = conn.execute('SELECT id FROM actual_assets WHERE asset_id = ?', (asset_id,)).fetchone()
    try:
        if actual:
            conn.execute('''UPDATE actual_assets SET serial_number=?, condition_status=?,
                            notes=?, last_verified_date=date('now'), verified_by='merge', ip_address=? WHERE asset_id=?''',
                         (fd.get('serial_number'), fd.get('condition_status') or 'Исправно', notes, ip_addr, asset_id))
        else:
            conn.execute('''INSERT INTO actual_assets (asset_id, serial_number, condition_status,
                            notes, last_verified_date, verified_by, ip_address) VALUES (?,?,?,?,date('now'),'merge',?)''',
                         (asset_id, fd.get('serial_number'), fd.get('condition_status') or 'Исправно', notes, ip_addr))
    except Exception:
        if actual:
            conn.execute('''UPDATE actual_assets SET serial_number=?, condition_status=?,
                            notes=?, last_verified_date=date('now'), verified_by='merge' WHERE asset_id=?''',
                         (fd.get('serial_number'), fd.get('condition_status') or 'Исправно', notes, asset_id))
        else:
            conn.execute('''INSERT INTO actual_assets (asset_id, serial_number, condition_status,
                            notes, last_verified_date, verified_by) VALUES (?,?,?,?,date('now'),'merge')''',
                         (asset_id, fd.get('serial_number'), fd.get('condition_status') or 'Исправно', notes))
    log_change(conn, 'actual_asset', asset_id, 'merge', None, f'Из факта #{fact_id}', 'Слияние факт→бух')
    conn.commit()
    conn.close()
    flash('Данные из факта перенесены в бухгалтерию', 'success')
    return redirect(url_for('discrepancy_compare', asset_id=asset_id, fact_id=fact_id))


# ============================================================
# ПРИХОД
# ============================================================

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
            flash('Укажите наименование', 'error')
        else:
            conn.execute('''
                INSERT INTO incoming_goods
                (arrival_date, item_name, quantity, supplier, document_number, category, temporary_storage_location, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            ''', (arrival_date, item_name, quantity, supplier, document_number, category, temporary_storage_location, notes))
            conn.commit()
            log_change(conn, 'incoming', 0, 'add', None, item_name, f'Приход: {item_name}')
            flash('Позиция прихода добавлена', 'success')

    rows = conn.execute('''
        SELECT ig.*, a.inventory_number as assigned_inventory
        FROM incoming_goods ig
        LEFT JOIN assets a ON ig.assigned_asset_id = a.id
        ORDER BY ig.arrival_date DESC, ig.id DESC
    ''').fetchall()
    conn.close()

    content = """
    {% block content %}
        <div class="card p-6 mb-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-900">Приход</h2>
                <a href="/incoming/export" class="btn btn-success px-4 py-2">Экспорт Excel (для бухгалтерии)</a>
            </div>
            <form method="post" class="space-y-6">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    <div class="form-group">
                        <label for="arrival_date">Дата прихода</label>
                        <input type="date" id="arrival_date" name="arrival_date" class="form-input" required>
                    </div>
                    <div class="form-group md:col-span-2">
                        <label for="item_name">Наименование <span class="text-red-500">*</span></label>
                        <input type="text" id="item_name" name="item_name" class="form-input" placeholder="Что пришло?" required>
                    </div>
                    <div class="form-group">
                        <label for="quantity">Количество</label>
                        <input type="number" id="quantity" name="quantity" class="form-input" value="1" min="1">
                    </div>
                    <div class="form-group">
                        <label for="supplier">Поставщик</label>
                        <input type="text" id="supplier" name="supplier" class="form-input" placeholder="Название поставщика">
                    </div>
                    <div class="form-group">
                        <label for="document_number">Документ №</label>
                        <input type="text" id="document_number" name="document_number" class="form-input" placeholder="Номер документа">
                    </div>
                    <div class="form-group">
                        <label for="category">Категория</label>
                        <select id="category" name="category" class="form-select">
                            <option value="">—</option>
                            <option value="Техника">Техника</option>
                            <option value="Мебель">Мебель</option>
                            <option value="Расходники">Расходники</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="temporary_storage_location">Временное хранение</label>
                        <input type="text" id="temporary_storage_location" name="temporary_storage_location" class="form-input" placeholder="Склад/кабинет">
                    </div>
                    <div class="form-group md:col-span-3">
                        <label for="notes">Примечание</label>
                        <textarea id="notes" name="notes" class="form-textarea" placeholder="Дополнительная информация"></textarea>
                    </div>
                </div>
                <div class="flex gap-3">
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Добавить</button>
                </div>
            </form>
        </div>

        <div class="card p-6">
            <h3 class="text-xl font-bold text-gray-900 mb-4">Список прихода</h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:100px;">Дата</th>
                            <th>Наименование</th>
                            <th style="width:70px;" class="text-center">Кол</th>
                            <th style="width:110px;">Категория</th>
                            <th style="width:150px;">Поставщик</th>
                            <th style="width:120px;">Документ</th>
                            <th style="width:120px;">Хранение</th>
                            <th style="width:110px;">Статус</th>
                            <th style="width:120px;">Назначено</th>
                            <th style="width:200px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in rows %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td class="text-sm text-gray-600">{{ r['arrival_date'] or '—' }}</td>
                            <td class="font-medium text-gray-900">{{ r['item_name'] }}</td>
                            <td class="text-center text-gray-700 font-semibold">{{ r['quantity'] }}</td>
                            <td class="text-sm text-gray-600">{{ r['category'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['supplier'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['document_number'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['temporary_storage_location'] or '—' }}</td>
                            <td>
                                <span class="badge {% if r['status'] == 'PENDING' %}badge-yellow{% elif r['status'] == 'ASSIGNED' %}badge-green{% else %}badge-gray{% endif %} text-xs">
                                    {{ r['status'] or 'PENDING' }}
                                </span>
                            </td>
                            <td class="text-sm text-gray-600">{{ r['assigned_inventory'] or '—' }}</td>
                            <td>
                                <div class="flex gap-2">
                                    <a class="btn btn-primary text-xs px-3 py-1.5" href="/incoming/assign/{{ r['id'] }}">Назначить</a>
                                    {% if r['assigned_inventory'] %}
                                    <a class="btn btn-danger text-xs px-3 py-1.5" href="/incoming/unassign/{{ r['id'] }}">Отвязать</a>
                                    {% endif %}
                                </div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% if rows %}
            <p class="text-sm text-gray-600 mt-4">Всего записей: <span class="font-semibold">{{ rows|length }}</span></p>
            {% endif %}
        </div>
    {% endblock %}
    """
    return render(content, page='incoming', rows=rows)


@app.route('/incoming/export')
def incoming_export():
    conn = get_db()
    rows = conn.execute('''
        SELECT ig.*, a.inventory_number as assigned_inventory
        FROM incoming_goods ig LEFT JOIN assets a ON ig.assigned_asset_id = a.id
        ORDER BY ig.arrival_date DESC
    ''').fetchall()
    conn.close()
    data = []
    for r in rows:
        data.append({
            'Дата': r['arrival_date'] or '',
            'Наименование': r['item_name'],
            'Кол-во': r['quantity'],
            'Поставщик': r['supplier'] or '',
            'Документ №': r['document_number'] or '',
            'Категория': r['category'] or '',
            'Хранение': r['temporary_storage_location'] or '',
            'Статус': r['status'] or '',
            'Назначено на': r['assigned_inventory'] or '',
            'Примечание': r['notes'] or '',
        })
    df = pd.DataFrame(data)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'incoming_export.xlsx')
    df.to_excel(filepath, index=False)
    with open(filepath, 'rb') as f:
        content = f.read()
    os.remove(filepath)
    return Response(content, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename=incoming_export.xlsx'})


@app.route('/incoming/assign/<int:incoming_id>', methods=['GET', 'POST'])
def incoming_assign(incoming_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM incoming_goods WHERE id = ?', (incoming_id,)).fetchone()
    if not row:
        conn.close()
        flash('Не найдено', 'error')
        return redirect(url_for('incoming_list'))
    search_result = None
    if request.method == 'POST':
        inv = (request.form.get('inventory_number') or '').strip()
        target = None
        if inv:
            target = conn.execute('SELECT id, inventory_number FROM assets WHERE inventory_number = ?', (inv,)).fetchone()
        if target:
            conn.execute('UPDATE incoming_goods SET assigned_asset_id = ?, status = ? WHERE id = ?',
                         (target['id'], 'ASSIGNED', incoming_id))
            conn.commit()
            conn.close()
            flash(f'Назначено на {target["inventory_number"]}', 'success')
            return redirect(url_for('incoming_list'))
        else:
            if inv:
                search_result = conn.execute('SELECT id, inventory_number, name FROM assets WHERE inventory_number LIKE ? LIMIT 10',
                                             (f'%{inv}%',)).fetchall()
            flash('Объект не найден', 'error')
    conn.close()
    content = """
    {% block content %}
        <div class="card p-6 mb-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-900">Назначить приход #{{ row['id'] }}</h2>
                <a class="btn px-4 py-2" href="/incoming">← Назад</a>
            </div>
            <div class="bg-gray-50 rounded-lg p-4 mb-6 border border-gray-200">
                <p class="text-gray-700"><span class="font-semibold">Наименование:</span> <span class="font-bold text-gray-900">{{ row['item_name'] }}</span></p>
                <p class="text-gray-700 mt-1"><span class="font-semibold">Количество:</span> <span class="font-bold text-gray-900">{{ row['quantity'] }}</span></p>
            </div>
            <form method="post" class="space-y-5">
                <div class="form-group">
                    <label for="assign_inventory_number">Инвентарный номер</label>
                    <input type="text" id="assign_inventory_number" name="inventory_number" class="form-input" placeholder="Введите инвентарный номер">
                </div>
                <div class="flex gap-3">
                    <button class="btn btn-primary px-6 py-2.5" type="submit">Назначить</button>
                </div>
            </form>
        </div>
        {% if search_result %}
        <div class="card p-6">
            <h3 class="text-lg font-bold text-gray-900 mb-4">Похожие объекты</h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:150px;">Инв. номер</th>
                            <th>Наименование</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for a in search_result %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td class="font-mono text-sm text-blue-600 font-semibold">{{ a['inventory_number'] }}</td>
                            <td class="text-sm text-gray-900">{{ a['name'] }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
    {% endblock %}
    """
    return render(content, page='incoming', row=row, search_result=search_result)


@app.route('/incoming/unassign/<int:incoming_id>')
def incoming_unassign(incoming_id):
    conn = get_db()
    conn.execute('UPDATE incoming_goods SET assigned_asset_id = NULL, status = "PENDING" WHERE id = ?', (incoming_id,))
    conn.commit()
    conn.close()
    flash('Отвязано', 'success')
    return redirect(url_for('incoming_list'))


# ============================================================
# ДЕТАЛЬНАЯ СТРАНИЦА ОБЪЕКТА
# ============================================================

@app.route('/asset/<int:asset_id>', methods=['GET', 'POST'])
def asset_detail(asset_id):
    conn = get_db()
    active_tab = request.args.get('tab', 'main')
    asset = conn.execute('SELECT * FROM assets WHERE id = ?', (asset_id,)).fetchone()
    if not asset:
        flash('Объект не найден', 'error')
        return redirect(url_for('assets_list'))
    actual = conn.execute('SELECT * FROM actual_assets WHERE asset_id = ?', (asset_id,)).fetchone()

    if request.method == 'POST':
        serial_number = request.form.get('serial_number', '').strip() or None
        condition_status = request.form.get('condition_status')
        notes = request.form.get('notes', '').strip() or None
        new_category = request.form.get('category', '').strip() or None

        old_data = conn.execute('SELECT serial_number, condition_status FROM actual_assets WHERE asset_id = ?', (asset_id,)).fetchone()
        old_serial = old_data['serial_number'] if old_data else None
        old_cond = old_data['condition_status'] if old_data else None

        if actual:
            conn.execute('''UPDATE actual_assets SET serial_number=?, condition_status=?,
                            notes=?, last_verified_date=date('now'), verified_by='user' WHERE asset_id=?''',
                         (serial_number, condition_status, notes, asset_id))
        else:
            conn.execute('''INSERT INTO actual_assets (asset_id, serial_number, condition_status,
                            notes, last_verified_date, verified_by) VALUES (?,?,?,?,date('now'),'user')''',
                         (asset_id, serial_number, condition_status, notes))

        if new_category is not None:
            conn.execute('UPDATE assets SET category = ? WHERE id = ?', (new_category, asset_id))
        conn.commit()

        if old_serial != serial_number:
            log_change(conn, 'actual_asset', asset_id, 'serial_number', old_serial, serial_number, 'Изменён серийный номер')
        if old_cond != condition_status:
            log_change(conn, 'actual_asset', asset_id, 'condition_status', old_cond, condition_status, 'Изменено состояние')
        flash('Состояние обновлено', 'success')
        conn.close()
        return redirect(url_for('asset_detail', asset_id=asset_id))

    history = conn.execute('''SELECT * FROM change_history WHERE entity_id = ? AND entity_type = 'actual_asset'
                              ORDER BY changed_at DESC LIMIT 50''', (asset_id,)).fetchall()
    consumables = conn.execute('SELECT * FROM equipment_consumables WHERE parent_asset_id = ? ORDER BY installation_date DESC, id DESC',
                               (asset_id,)).fetchall()
    assigned_incoming = conn.execute('SELECT * FROM incoming_goods WHERE assigned_asset_id = ? ORDER BY arrival_date DESC',
                                     (asset_id,)).fetchall()
    conn.close()

    content = """
    {% block content %}
        <div class="card p-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-900">Объект #{{ asset['inventory_number'] }}</h2>
                <a href="/assets" class="btn px-4 py-2">← Назад к списку</a>
            </div>

            <div class="flex gap-2 border-b border-gray-200 mb-6">
                <a href="?tab=main" class="px-4 py-2 text-sm font-semibold transition-colors {% if active_tab=='main' %}text-blue-600 border-b-2 border-blue-600{% else %}text-gray-600 hover:text-gray-900{% endif %}">Основные данные</a>
                <a href="?tab=consumables" class="px-4 py-2 text-sm font-semibold transition-colors {% if active_tab=='consumables' %}text-blue-600 border-b-2 border-blue-600{% else %}text-gray-600 hover:text-gray-900{% endif %}">Расходники</a>
                <a href="?tab=history" class="px-4 py-2 text-sm font-semibold transition-colors {% if active_tab=='history' %}text-blue-600 border-b-2 border-blue-600{% else %}text-gray-600 hover:text-gray-900{% endif %}">История</a>
            </div>

            <!-- Основные данные -->
            <div class="tab-content {% if active_tab=='main' %}active{% endif %}">
                <div class="bg-gray-50 rounded-lg p-5 mb-6 border border-gray-200">
                    <h3 class="text-lg font-bold text-gray-900 mb-4">Бухгалтерский учёт</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div><span class="font-semibold text-gray-700">Наименование:</span> <span class="text-gray-900">{{ asset['name'] }}</span></div>
                        <div><span class="font-semibold text-gray-700">Инв. номер:</span> <code class="font-mono text-sm bg-white px-2 py-1 rounded border border-gray-300">{{ asset['inventory_number'] }}</code></div>
                        <div><span class="font-semibold text-gray-700">Дата принятия:</span> <span class="text-gray-900">{{ asset['acquisition_date'] or '—' }}</span></div>
                        <div><span class="font-semibold text-gray-700">Стоимость:</span> <span class="font-bold text-gray-900">{{ asset['initial_cost']|currency }}</span></div>
                        <div><span class="font-semibold text-gray-700">Состояние (бух):</span> <span class="text-gray-900">{{ asset['accounting_status'] or '—' }}</span></div>
                    </div>
                </div>

                <form method="post" class="space-y-5">
                    <h3 class="text-lg font-bold text-gray-900 mb-4">Фактическое состояние</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                        <div class="form-group">
                            <label for="asset_serial_number">Серийный номер</label>
                            <input type="text" id="asset_serial_number" name="serial_number" class="form-input" value="{{ actual['serial_number'] if actual else '' }}">
                        </div>
                        <div class="form-group">
                            <label for="asset_condition_status">Состояние</label>
                            <select id="asset_condition_status" name="condition_status" class="form-select">
                                {% for s in ['Исправно','Сломано','Утеряно','На ремонте','Списано'] %}
                                    <option value="{{ s }}" {% if actual and actual['condition_status']==s %}selected{% endif %}>{{ s }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="asset_category">Категория</label>
                            <select id="asset_category" name="category" class="form-select">
                                <option value="">—</option>
                                {% for s in ['Техника','Мебель'] %}
                                    <option value="{{ s }}" {% if asset['category']==s %}selected{% endif %}>{{ s }}</option>
                                {% endfor %}
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="asset_notes">Комментарий</label>
                        <textarea id="asset_notes" name="notes" class="form-textarea">{{ actual['notes'] if actual else '' }}</textarea>
                    </div>
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Сохранить</button>
                </form>

                {% if assigned_incoming %}
                <div class="mt-8 bg-gray-50 rounded-lg p-5 border border-gray-200">
                    <h3 class="text-lg font-bold text-gray-900 mb-4">Приход</h3>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Дата</th>
                                    <th>Наименование</th>
                                    <th class="text-center">Кол-во</th>
                                    <th>Поставщик</th>
                                    <th>Документ</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for g in assigned_incoming %}
                                <tr class="hover:bg-gray-50 transition-colors duration-150">
                                    <td class="text-sm text-gray-600">{{ g['arrival_date'] or '—' }}</td>
                                    <td class="font-medium text-gray-900">{{ g['item_name'] }}</td>
                                    <td class="text-center text-gray-700 font-semibold">{{ g['quantity'] }}</td>
                                    <td class="text-sm text-gray-600">{{ g['supplier'] or '—' }}</td>
                                    <td class="text-sm text-gray-600">{{ g['document_number'] or '—' }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
                {% endif %}
            </div>

            <!-- Расходники -->
            <div class="tab-content {% if active_tab=='consumables' %}active{% endif %}">
                {% if consumables %}
                <div class="table-container mb-6">
                    <table>
                        <thead>
                            <tr>
                                <th>Тип</th>
                                <th>Модель</th>
                                <th>Дата установки</th>
                                <th>Установил</th>
                                <th class="text-right">Ресурс</th>
                                <th>Примечание</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for c in consumables %}
                            <tr class="hover:bg-gray-50 transition-colors duration-150">
                                <td class="text-sm text-gray-700">{{ c['consumable_type'] or '—' }}</td>
                                <td class="text-sm text-gray-700">{{ c['model'] or '—' }}</td>
                                <td class="text-sm text-gray-600">{{ c['installation_date'] or '—' }}</td>
                                <td class="text-sm text-gray-600">{{ c['installed_by'] or '—' }}</td>
                                <td class="text-right text-gray-700 font-semibold">{{ c['estimated_yield'] or '—' }}</td>
                                <td class="text-sm text-gray-600">{{ c['notes'] or '—' }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-gray-500 mb-6">Нет записей о расходниках</p>
                {% endif %}
                <form method="post" action="/asset/{{ asset['id'] }}/consumables" class="space-y-5">
                    <h3 class="text-lg font-bold text-gray-900">Добавить расходник</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                        <div class="form-group">
                            <label for="cons_type">Тип</label>
                            <input type="text" id="cons_type" name="consumable_type" class="form-input" placeholder="Картридж / Лампа">
                        </div>
                        <div class="form-group">
                            <label for="cons_model">Модель</label>
                            <input type="text" id="cons_model" name="model" class="form-input" placeholder="CF283A">
                        </div>
                        <div class="form-group">
                            <label for="cons_date">Дата установки</label>
                            <input type="date" id="cons_date" name="installation_date" class="form-input">
                        </div>
                        <div class="form-group">
                            <label for="cons_by">Кто поставил</label>
                            <input type="text" id="cons_by" name="installed_by" class="form-input" placeholder="ФИО">
                        </div>
                        <div class="form-group">
                            <label for="cons_yield">Ресурс (стр.)</label>
                            <input type="number" id="cons_yield" name="estimated_yield" class="form-input" min="0" placeholder="0">
                        </div>
                        <div class="form-group md:col-span-3">
                            <label for="cons_notes">Примечание</label>
                            <textarea id="cons_notes" name="notes" class="form-textarea" placeholder="Дополнительная информация"></textarea>
                        </div>
                    </div>
                    <button class="btn btn-primary px-6 py-2.5" type="submit">Добавить расходник</button>
                </form>
            </div>

            <!-- История -->
            <div class="tab-content {% if active_tab=='history' %}active{% endif %}">
                {% if history %}
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Поле</th>
                                <th>Было</th>
                                <th>Стало</th>
                                <th>Когда</th>
                                <th>Кем</th>
                                <th>Причина</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for h in history %}
                            <tr class="hover:bg-gray-50 transition-colors duration-150">
                                <td class="font-semibold text-gray-900">{{ h['field_changed'] }}</td>
                                <td class="text-sm text-gray-600">{{ h['old_value'] or '—' }}</td>
                                <td class="text-sm text-gray-900 font-medium">{{ h['new_value'] or '—' }}</td>
                                <td class="text-sm text-gray-500">{{ h['changed_at'] }}</td>
                                <td class="text-sm text-gray-600">{{ h['changed_by'] }}</td>
                                <td class="text-sm text-gray-600">{{ h['reason'] or '—' }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-gray-500">Изменений пока нет</p>
                {% endif %}
            </div>
        </div>
    {% endblock %}
    """
    return render(content, page='assets', asset=asset, actual=actual, consumables=consumables,
                  assigned_incoming=assigned_incoming, history=history, active_tab=active_tab)


@app.route('/asset/<int:asset_id>/consumables', methods=['POST'])
def add_consumable(asset_id):
    conn = get_db()
    if not conn.execute('SELECT id FROM assets WHERE id = ?', (asset_id,)).fetchone():
        conn.close()
        flash('Объект не найден', 'error')
        return redirect(url_for('assets_list'))
    consumable_type = (request.form.get('consumable_type') or '').strip() or None
    model = (request.form.get('model') or '').strip() or None
    installation_date = request.form.get('installation_date') or None
    installed_by = (request.form.get('installed_by') or '').strip() or None
    estimated_yield = request.form.get('estimated_yield') or None
    try:
        estimated_yield = int(estimated_yield) if estimated_yield else None
    except:
        estimated_yield = None
    notes = (request.form.get('notes') or '').strip() or None
    conn.execute('''INSERT INTO equipment_consumables
                    (parent_asset_id, consumable_type, model, installation_date, installed_by, estimated_yield, notes)
                    VALUES (?,?,?,?,?,?,?)''',
                 (asset_id, consumable_type, model, installation_date, installed_by, estimated_yield, notes))
    conn.commit()
    conn.close()
    flash('Расходник добавлен', 'success')
    return redirect(url_for('asset_detail', asset_id=asset_id, tab='consumables'))


# ============================================================
# ОТЧЁТЫ
# ============================================================

@app.route('/reports')
def reports_page():
    conn = get_db()
    data_source = request.args.get('source', 'fact').strip()  # 'fact' или 'accounting'
    consumable_type_filter = request.args.get('consumable_type', '').strip()  # 'cartridge', 'lamp', или ''
    category_filter = request.args.get('category', '').strip()
    search = request.args.get('search', '').strip()

    if data_source == 'fact':
        # Данные из факта (fact_inventory)
        query = '''
            SELECT 
                f.id as fact_id, f.inventory_number, f.name, f.serial_number, 
                f.condition_status, f.location, f.ip_address,
                a.id as asset_id,
                (SELECT COUNT(*) FROM equipment_consumables ec 
                 JOIN assets a2 ON ec.parent_asset_id = a2.id 
                 WHERE a2.inventory_number = f.inventory_number) as consumable_count,
                (SELECT MAX(ec.installation_date) FROM equipment_consumables ec 
                 JOIN assets a2 ON ec.parent_asset_id = a2.id 
                 WHERE a2.inventory_number = f.inventory_number) as last_consumable_date,
                (SELECT ec.consumable_type FROM equipment_consumables ec 
                 JOIN assets a2 ON ec.parent_asset_id = a2.id 
                 WHERE a2.inventory_number = f.inventory_number 
                 ORDER BY ec.id DESC LIMIT 1) as last_cons_type,
                (SELECT ec.model FROM equipment_consumables ec 
                 JOIN assets a2 ON ec.parent_asset_id = a2.id 
                 WHERE a2.inventory_number = f.inventory_number 
                 ORDER BY ec.id DESC LIMIT 1) as last_cons_model
            FROM fact_inventory f
            LEFT JOIN assets a ON a.inventory_number = f.inventory_number
            WHERE f.id IN (
                SELECT MAX(id) FROM fact_inventory 
                WHERE inventory_number IS NOT NULL 
                GROUP BY inventory_number
            )
        '''
        params = []
        if category_filter:
            if category_filter == 'принтер_мфу':
                query += ' AND (LOWER(f.name) LIKE ? OR LOWER(f.name) LIKE ?)'
                params.extend(['%принтер%', '%мфу%'])
            else:
                query += ' AND LOWER(f.name) LIKE ?'
                params.append(f'%{category_filter.lower()}%')
        if search:
            like = f'%{search}%'
            query += ' AND (f.name LIKE ? OR f.inventory_number LIKE ? OR IFNULL(f.ip_address,"") LIKE ?)'
            params.extend([like, like, like])
        if consumable_type_filter == 'cartridge':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                JOIN assets a2 ON ec.parent_asset_id = a2.id 
                WHERE a2.inventory_number = f.inventory_number 
                AND LOWER(ec.consumable_type) LIKE '%картридж%'
            )'''
        elif consumable_type_filter == 'lamp':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                JOIN assets a2 ON ec.parent_asset_id = a2.id 
                WHERE a2.inventory_number = f.inventory_number 
                AND LOWER(ec.consumable_type) LIKE '%лампа%'
            )'''
        query += ' ORDER BY f.name'
        rows = conn.execute(query, params).fetchall()
        # Формируем данные в едином формате
        report_rows = []
        for r in rows:
            report_rows.append({
                'id': r['asset_id'] or r['fact_id'],
                'inventory_number': r['inventory_number'] or '—',
                'name': r['name'] or '—',
                'serial_number': r['serial_number'] or '—',
                'location': r['location'] or '—',
                'ip_address': r['ip_address'] or '—',
                'condition_status': r['condition_status'] or '—',
                'consumable_count': r['consumable_count'] or 0,
                'last_consumable_date': r['last_consumable_date'] or '—',
                'last_cons_type': r['last_cons_type'] or '—',
                'last_cons_model': r['last_cons_model'] or '—',
            })
    else:
        # Данные из бухгалтерии (assets + actual_assets)
        query = '''
            SELECT a.id, a.inventory_number, a.name, a.category, a.accounting_status,
                   aa.serial_number, aa.condition_status, aa.location,
                   (SELECT COUNT(*) FROM equipment_consumables ec WHERE ec.parent_asset_id = a.id) as consumable_count,
                   (SELECT MAX(ec.installation_date) FROM equipment_consumables ec WHERE ec.parent_asset_id = a.id) as last_consumable_date,
                   (SELECT ec.consumable_type FROM equipment_consumables ec WHERE ec.parent_asset_id = a.id ORDER BY ec.id DESC LIMIT 1) as last_cons_type,
                   (SELECT ec.model FROM equipment_consumables ec WHERE ec.parent_asset_id = a.id ORDER BY ec.id DESC LIMIT 1) as last_cons_model
            FROM assets a
            LEFT JOIN actual_assets aa ON a.id = aa.asset_id
            WHERE 1=1
        '''
        params = []
        if category_filter:
            if category_filter == 'принтер_мфу':
                query += ' AND (LOWER(a.name) LIKE ? OR LOWER(a.name) LIKE ?)'
                params.extend(['%принтер%', '%мфу%'])
            else:
                query += ' AND LOWER(a.name) LIKE ?'
                params.append(f'%{category_filter.lower()}%')
        if search:
            like = f'%{search}%'
            query += ' AND (a.name LIKE ? OR a.inventory_number LIKE ?)'
            params.extend([like, like])
        if consumable_type_filter == 'cartridge':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                WHERE ec.parent_asset_id = a.id 
                AND LOWER(ec.consumable_type) LIKE '%картридж%'
            )'''
        elif consumable_type_filter == 'lamp':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                WHERE ec.parent_asset_id = a.id 
                AND LOWER(ec.consumable_type) LIKE '%лампа%'
            )'''
        query += ' ORDER BY a.name'
        rows = conn.execute(query, params).fetchall()
        report_rows = []
        for r in rows:
            report_rows.append({
                'id': r['id'],
                'inventory_number': r['inventory_number'] or '—',
                'name': r['name'] or '—',
                'serial_number': r['serial_number'] or '—',
                'location': r['location'] or '—',
                'ip_address': '—',  # В бух нет IP
                'condition_status': r['condition_status'] or '—',
                'consumable_count': r['consumable_count'] or 0,
                'last_consumable_date': r['last_consumable_date'] or '—',
                'last_cons_type': r['last_cons_type'] or '—',
                'last_cons_model': r['last_cons_model'] or '—',
            })
    conn.close()

    content = """
    {% block content %}
        <div class="card p-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-900">Отчёты</h2>
                <a href="/reports/export?source={{ request.args.get('source','fact') }}&category={{ request.args.get('category','') }}&search={{ request.args.get('search','') }}&consumable_type={{ request.args.get('consumable_type','') }}" class="btn btn-success px-4 py-2">Экспорт Excel</a>
            </div>
            
            <form method="get" class="space-y-4 mb-6">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div class="form-group">
                        <label class="text-sm font-semibold text-gray-700 mb-2 block">Источник данных</label>
                        <div class="flex gap-4">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" name="source" value="fact" {% if request.args.get('source','fact')=='fact' %}checked{% endif %} class="w-4 h-4 text-blue-600">
                                <span class="text-sm text-gray-700">Факт</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" name="source" value="accounting" {% if request.args.get('source','fact')=='accounting' %}checked{% endif %} class="w-4 h-4 text-blue-600">
                                <span class="text-sm text-gray-700">Бухгалтерия</span>
                            </label>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="consumable_type" class="text-sm font-semibold text-gray-700 mb-2 block">Тип расходника</label>
                        <select id="consumable_type" name="consumable_type" class="form-select">
                            <option value="">Все расходники</option>
                            <option value="cartridge" {% if request.args.get('consumable_type','')=='cartridge' %}selected{% endif %}>Картриджи</option>
                            <option value="lamp" {% if request.args.get('consumable_type','')=='lamp' %}selected{% endif %}>Лампы</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="category" class="text-sm font-semibold text-gray-700 mb-2 block">Категория</label>
                        <select id="category" name="category" class="form-select">
                            <option value="">Все объекты</option>
                            <option value="принтер_мфу" {% if request.args.get('category','')=='принтер_мфу' %}selected{% endif %}>Принтеры и МФУ</option>
                            <option value="проектор" {% if request.args.get('category','')=='проектор' %}selected{% endif %}>Проекторы</option>
                            <option value="монитор" {% if request.args.get('category','')=='монитор' %}selected{% endif %}>Мониторы</option>
                            <option value="компьютер" {% if request.args.get('category','')=='компьютер' %}selected{% endif %}>Компьютеры</option>
                            <option value="ноутбук" {% if request.args.get('category','')=='ноутбук' %}selected{% endif %}>Ноутбуки</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="search" class="text-sm font-semibold text-gray-700 mb-2 block">Поиск</label>
                        <input type="text" id="search" name="search" class="form-input" placeholder="Поиск по имени, инв., IP..." value="{{ request.args.get('search','') }}">
                    </div>
                </div>
                <div class="flex gap-3">
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Показать</button>
                    <a href="/reports" class="btn px-6 py-2.5">Сбросить</a>
                </div>
            </form>

            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:120px;">Инв. номер</th>
                            <th>Наименование</th>
                            <th style="width:140px;">Серийный</th>
                            <th style="width:150px;">Местоположение</th>
                            <th style="width:110px;">IP</th>
                            <th style="width:110px;">Состояние</th>
                            <th style="width:120px;">Тип расходника</th>
                            <th style="width:120px;">Модель</th>
                            <th style="width:80px;" class="text-center">Расходн.</th>
                            <th style="width:120px;">Посл. замена</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in report_rows %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td>
                                <a href="/asset/{{ r['id'] }}" class="text-blue-600 hover:text-blue-800 hover:underline font-mono text-xs">{{ r['inventory_number'] }}</a>
                            </td>
                            <td class="font-medium text-gray-900">{{ r['name'] }}</td>
                            <td class="text-sm text-gray-600">{{ r['serial_number'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['location'] or '—' }}</td>
                            <td class="font-mono text-xs text-gray-600">{{ r['ip_address'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['condition_status'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['last_cons_type'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['last_cons_model'] or '—' }}</td>
                            <td class="text-center text-gray-700 font-semibold">{{ r['consumable_count'] or 0 }}</td>
                            <td class="text-sm text-gray-500">{{ r['last_consumable_date'] or '—' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <p class="text-sm text-gray-600 mt-4">Найдено: <span class="font-semibold">{{ report_rows|length }}</span> | Источник: <span class="font-semibold">{% if request.args.get('source','fact')=='fact' %}Факт{% else %}Бухгалтерия{% endif %}</span></p>
        </div>
    {% endblock %}
    """
    return render(content, page='reports', report_rows=report_rows)


@app.route('/reports/export')
def reports_export():
    conn = get_db()
    data_source = request.args.get('source', 'fact').strip()
    consumable_type_filter = request.args.get('consumable_type', '').strip()
    category_filter = request.args.get('category', '').strip()
    search = request.args.get('search', '').strip()

    if data_source == 'fact':
        query = '''
            SELECT 
                f.inventory_number, f.name, f.serial_number, f.condition_status,
                f.location, f.ip_address,
                (SELECT GROUP_CONCAT(ec.consumable_type || ' ' || IFNULL(ec.model,'') || ' (' || IFNULL(ec.installation_date,'?') || ')', '; ')
                 FROM equipment_consumables ec 
                 JOIN assets a2 ON ec.parent_asset_id = a2.id 
                 WHERE a2.inventory_number = f.inventory_number) as consumables_info
            FROM fact_inventory f
            WHERE f.id IN (
                SELECT MAX(id) FROM fact_inventory 
                WHERE inventory_number IS NOT NULL 
                GROUP BY inventory_number
            )
        '''
        params = []
        if category_filter:
            if category_filter == 'принтер_мфу':
                query += ' AND (LOWER(f.name) LIKE ? OR LOWER(f.name) LIKE ?)'
                params.extend(['%принтер%', '%мфу%'])
            else:
                query += ' AND LOWER(f.name) LIKE ?'
                params.append(f'%{category_filter.lower()}%')
        if search:
            like = f'%{search}%'
            query += ' AND (f.name LIKE ? OR f.inventory_number LIKE ?)'
            params.extend([like, like])
        if consumable_type_filter == 'cartridge':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                JOIN assets a2 ON ec.parent_asset_id = a2.id 
                WHERE a2.inventory_number = f.inventory_number 
                AND LOWER(ec.consumable_type) LIKE '%картридж%'
            )'''
        elif consumable_type_filter == 'lamp':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                JOIN assets a2 ON ec.parent_asset_id = a2.id 
                WHERE a2.inventory_number = f.inventory_number 
                AND LOWER(ec.consumable_type) LIKE '%лампа%'
            )'''
        query += ' ORDER BY f.name'
        rows = conn.execute(query, params).fetchall()
        data = []
        for r in rows:
            data.append({
                'Инв. номер': r['inventory_number'] or '',
                'Наименование': r['name'] or '',
                'Серийный': r['serial_number'] or '',
                'Состояние': r['condition_status'] or '',
                'Местоположение': r['location'] or '',
                'IP': r['ip_address'] or '',
                'Расходники': r['consumables_info'] or '',
            })
    else:
        query = '''
            SELECT a.inventory_number, a.name, aa.serial_number, aa.condition_status, aa.location,
                   (SELECT GROUP_CONCAT(ec.consumable_type || ' ' || IFNULL(ec.model,'') || ' (' || IFNULL(ec.installation_date,'?') || ')', '; ')
                    FROM equipment_consumables ec WHERE ec.parent_asset_id = a.id) as consumables_info
            FROM assets a
            LEFT JOIN actual_assets aa ON a.id = aa.asset_id
            WHERE 1=1
        '''
        params = []
        if category_filter:
            if category_filter == 'принтер_мфу':
                query += ' AND (LOWER(a.name) LIKE ? OR LOWER(a.name) LIKE ?)'
                params.extend(['%принтер%', '%мфу%'])
            else:
                query += ' AND LOWER(a.name) LIKE ?'
                params.append(f'%{category_filter.lower()}%')
        if search:
            like = f'%{search}%'
            query += ' AND (a.name LIKE ? OR a.inventory_number LIKE ?)'
            params.extend([like, like])
        if consumable_type_filter == 'cartridge':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                WHERE ec.parent_asset_id = a.id 
                AND LOWER(ec.consumable_type) LIKE '%картридж%'
            )'''
        elif consumable_type_filter == 'lamp':
            query += ''' AND EXISTS (
                SELECT 1 FROM equipment_consumables ec 
                WHERE ec.parent_asset_id = a.id 
                AND LOWER(ec.consumable_type) LIKE '%лампа%'
            )'''
        query += ' ORDER BY a.name'
        rows = conn.execute(query, params).fetchall()
        data = []
        for r in rows:
            data.append({
                'Инв. номер': r['inventory_number'] or '',
                'Наименование': r['name'] or '',
                'Серийный': r['serial_number'] or '',
                'Состояние': r['condition_status'] or '',
                'Местоположение': r['location'] or '',
                'IP': '',
                'Расходники': r['consumables_info'] or '',
            })
    conn.close()
    df = pd.DataFrame(data)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'report_export.xlsx')
    df.to_excel(filepath, index=False)
    with open(filepath, 'rb') as f:
        content = f.read()
    os.remove(filepath)
    source_label = 'fact' if data_source == 'fact' else 'accounting'
    type_label = consumable_type_filter or 'all'
    return Response(content, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename=report_{source_label}_{type_label}.xlsx'})


# ============================================================
# ИСТОРИЯ ИЗМЕНЕНИЙ
# ============================================================

@app.route('/history')
def history_page():
    conn = get_db()
    rows = conn.execute('''
        SELECT ch.*, a.inventory_number
        FROM change_history ch
        LEFT JOIN assets a ON ch.entity_id = a.id AND ch.entity_type IN ('actual_asset', 'asset')
        ORDER BY ch.changed_at DESC
        LIMIT 500
    ''').fetchall()
    conn.close()

    content = """
    {% block content %}
        <div class="card p-6">
            <h2 class="text-2xl font-bold text-gray-900 mb-6">История изменений</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:160px;">Дата</th>
                            <th style="width:100px;">Тип</th>
                            <th style="width:120px;">Инв. номер</th>
                            <th style="width:140px;">Поле</th>
                            <th>Было</th>
                            <th>Стало</th>
                            <th style="width:100px;">Кем</th>
                            <th>Причина</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in rows %}
                        <tr class="hover:bg-gray-50 transition-colors duration-150">
                            <td class="text-sm text-gray-500">{{ r['changed_at'] }}</td>
                            <td class="text-xs text-gray-600 font-mono">{{ r['entity_type'] }}</td>
                            <td class="text-sm text-gray-700 font-mono">{{ r['inventory_number'] or r['entity_id'] }}</td>
                            <td class="font-semibold text-gray-900">{{ r['field_changed'] }}</td>
                            <td class="text-sm text-gray-600">{{ r['old_value'] or '—' }}</td>
                            <td class="text-sm text-gray-900 font-medium">{{ r['new_value'] or '—' }}</td>
                            <td class="text-sm text-gray-600">{{ r['changed_by'] }}</td>
                            <td class="text-sm text-gray-600">{{ r['reason'] or '—' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% if rows %}
            <p class="text-sm text-gray-600 mt-4">Показано: <span class="font-semibold">{{ rows|length }}</span> записей</p>
            {% endif %}
        </div>
    {% endblock %}
    """
    return render(content, page='history', rows=rows)


# ============================================================
# АДМИНКА
# ============================================================

@app.route('/admin', methods=['GET', 'POST'])
def admin_page():
    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'backup':
            now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f'assets_backup_{now}.db'
            backup_path = os.path.join(app.config['BACKUP_FOLDER'], backup_name)
            try:
                shutil.copy2(DATABASE, backup_path)
                log_change(get_db(), 'system', 0, 'backup', None, backup_name, 'Ручной бэкап')
                flash(f'Бэкап создан: {backup_name}', 'success')
            except Exception as e:
                flash(f'Ошибка бэкапа: {e}', 'error')

        elif action == 'cleanup':
            q = (request.form.get('q') or '').strip()
            if q:
                conn = get_db()
                do_facts = request.form.get('clean_facts') == '1'
                do_incoming = request.form.get('clean_incoming') == '1'
                deleted = {'facts': 0, 'incoming': 0}
                if do_facts:
                    cur = conn.execute("DELETE FROM fact_inventory WHERE IFNULL(name,'') LIKE ? OR IFNULL(inventory_number,'') LIKE ?",
                                       (f'%{q}%', f'%{q}%'))
                    deleted['facts'] = cur.rowcount or 0
                if do_incoming:
                    cur = conn.execute("DELETE FROM incoming_goods WHERE item_name LIKE ?", (f'%{q}%',))
                    deleted['incoming'] = cur.rowcount or 0
                conn.commit()
                conn.close()
                flash(f"Удалено: факт {deleted['facts']}, приход {deleted['incoming']}", 'success')

    # Список бэкапов
    backups = []
    if os.path.exists(app.config['BACKUP_FOLDER']):
        for f in sorted(os.listdir(app.config['BACKUP_FOLDER']), reverse=True):
            if f.endswith('.db'):
                fp = os.path.join(app.config['BACKUP_FOLDER'], f)
                size = os.path.getsize(fp)
                backups.append({'name': f, 'size': f'{size / 1024 / 1024:.1f} МБ',
                               'date': datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M')})

    content = """
    {% block content %}
        <div class="card p-6 mb-6">
            <h2 class="text-2xl font-bold text-gray-900 mb-6">Администрирование</h2>

            <div class="mb-8">
                <h3 class="text-lg font-semibold text-gray-800 mb-2">Бэкап базы данных</h3>
                <p class="text-sm text-gray-600 mb-4">Создать копию assets.db. Рекомендуется делать перед импортом.</p>
                <form method="post" class="flex gap-3">
                    <input type="hidden" name="action" value="backup">
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Создать бэкап сейчас</button>
                </form>
            </div>

            {% if backups %}
            <div class="mb-6">
                <h3 class="text-lg font-semibold text-gray-800 mb-4">Список бэкапов</h3>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Файл</th>
                                <th style="width:120px;" class="text-center">Размер</th>
                                <th style="width:180px;">Дата</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for b in backups %}
                            <tr class="hover:bg-gray-50 transition-colors duration-150">
                                <td class="font-mono text-sm text-gray-700">{{ b.name }}</td>
                                <td class="text-center text-sm text-gray-600">{{ b.size }}</td>
                                <td class="text-sm text-gray-600">{{ b.date }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endif %}
        </div>

        <div class="card p-6">
            <h3 class="text-lg font-semibold text-gray-800 mb-2">Очистка данных</h3>
            <p class="text-sm text-gray-600 mb-4">Удаление записей по ключевому слову (LIKE-поиск). Бухгалтерию не трогаем.</p>
            <form method="post" class="space-y-4">
                <input type="hidden" name="action" value="cleanup">
                <div class="form-group">
                    <label for="cleanup_q" class="text-sm font-semibold text-gray-700 mb-2 block">Ключевое слово</label>
                    <input type="text" id="cleanup_q" name="q" class="form-input" placeholder="Введите ключевое слово для поиска">
                </div>
                <div class="flex gap-6 mb-4">
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="clean_facts" value="1" checked class="w-4 h-4 text-blue-600">
                        <span class="text-sm text-gray-700">Факт</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="clean_incoming" value="1" checked class="w-4 h-4 text-blue-600">
                        <span class="text-sm text-gray-700">Приход</span>
                    </label>
                </div>
                <button class="btn btn-danger px-6 py-2.5" type="submit">Удалить</button>
            </form>
        </div>
    {% endblock %}
    """
    return render(content, page='admin', backups=backups)


# ============================================================
# РАСХОДНИКИ
# ============================================================

@app.route('/consumables', methods=['GET', 'POST'])
def consumables_page():
    conn = get_db()
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'add_bulk':
            # Массовое добавление расходников
            bulk_data = request.form.get('bulk_data', '').strip()
            if bulk_data:
                lines = [line.strip() for line in bulk_data.split('\n') if line.strip()]
                added = 0
                errors = []
                
                for line in lines:
                    # Разделяем по табуляции или нескольким пробелам
                    parts = [p.strip() for p in line.split('\t') if p.strip()]
                    # Если нет табуляции, пробуем разделить по нескольким пробелам
                    if len(parts) == 1:
                        parts = [p.strip() for p in line.split('  ') if p.strip()]
                    if len(parts) < 1:
                        continue
                    
                    consumable_name = parts[0]
                    asset_name = parts[1] if len(parts) > 1 else ''
                    notes = parts[2] if len(parts) > 2 else ''
                    consumable_type = request.form.get('bulk_type', 'Картридж')
                    
                    # Нечеткое сопоставление устройства
                    asset_id = None
                    if asset_name:
                        matches = fuzzy_match_asset_name(asset_name, conn)
                        if matches:
                            asset_id = matches[0][0]  # Берем первое совпадение
                    
                    try:
                        conn.execute('''
                            INSERT INTO inventory_consumables 
                            (consumable_type, model, notes, asset_name, asset_id, quantity)
                            VALUES (?, ?, ?, ?, ?, 0)
                        ''', (consumable_type, consumable_name, notes, asset_name, asset_id))
                        added += 1
                    except Exception as e:
                        errors.append(f"{consumable_name}: {str(e)}")
                
                conn.commit()
                if added > 0:
                    flash(f'Добавлено расходников: {added}', 'success')
                if errors:
                    flash(f'Ошибки: {len(errors)}', 'warning')
        
        elif action == 'add_single':
            # Одиночное добавление
            consumable_type = request.form.get('consumable_type', 'Картридж')
            model = request.form.get('model', '').strip()
            asset_name = request.form.get('asset_name', '').strip()
            notes = request.form.get('notes', '').strip()
            quantity = int(request.form.get('quantity', '0') or '0')
            
            if not model:
                flash('Укажите название расходника', 'error')
            else:
                asset_id = None
                if asset_name:
                    matches = fuzzy_match_asset_name(asset_name, conn)
                    if matches:
                        asset_id = matches[0][0]
                
                conn.execute('''
                    INSERT INTO inventory_consumables 
                    (consumable_type, model, notes, asset_name, asset_id, quantity)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (consumable_type, model, notes, asset_name, asset_id, quantity))
                conn.commit()
                flash('Расходник добавлен', 'success')
        
        elif action == 'update_quantity':
            consumable_id = int(request.form.get('consumable_id', '0'))
            new_quantity = int(request.form.get('quantity', '0') or '0')
            conn.execute('UPDATE inventory_consumables SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                        (new_quantity, consumable_id))
            conn.commit()
            flash('Количество обновлено', 'success')
        
        elif action == 'delete':
            consumable_id = int(request.form.get('consumable_id', '0'))
            conn.execute('DELETE FROM inventory_consumables WHERE id=?', (consumable_id,))
            conn.commit()
            flash('Расходник удален', 'success')
    
    # Получаем все расходники с информацией об устройствах
    consumables = conn.execute('''
        SELECT 
            ic.id, ic.consumable_type, ic.model, ic.quantity, ic.notes, 
            ic.asset_name, ic.asset_id, ic.created_at,
            a.name as matched_asset_name, a.inventory_number as matched_inv_number
        FROM inventory_consumables ic
        LEFT JOIN assets a ON ic.asset_id = a.id
        ORDER BY ic.created_at DESC
    ''').fetchall()
    
    # Группируем по устройствам для отображения запасов
    assets_stock = {}
    for c in consumables:
        asset_id = c['asset_id']
        asset_name = c['matched_asset_name'] or c['asset_name'] or 'Не указано'
        
        # Используем строковый ключ для None (расходники без устройства)
        stock_key = str(asset_id) if asset_id else 'none'
        
        if stock_key not in assets_stock:
            assets_stock[stock_key] = {
                'asset_id': asset_id,
                'name': asset_name,
                'inv_number': c['matched_inv_number'],
                'cartridges': [],
                'lamps': [],
                'other': []
            }
        
        consumable_info = {
            'id': c['id'],
            'model': c['model'],
            'quantity': c['quantity'],
            'notes': c['notes'],
            'created_at': c['created_at']
        }
        
        cons_type = (c['consumable_type'] or '').lower()
        if 'картридж' in cons_type:
            assets_stock[stock_key]['cartridges'].append(consumable_info)
        elif 'лампа' in cons_type or 'проектор' in cons_type:
            assets_stock[stock_key]['lamps'].append(consumable_info)
        else:
            assets_stock[stock_key]['other'].append(consumable_info)
    
    # Преобразуем в список для удобной итерации в шаблоне
    assets_stock_list = [{'key': k, **v} for k, v in assets_stock.items()]
    
    conn.close()
    
    content = """
    {% block content %}
        <div class="card p-6 mb-6">
            <h2 class="text-2xl font-bold text-gray-900 mb-6">Управление расходниками</h2>
            
            <!-- Форма массового ввода -->
            <div class="mb-8 border-b border-gray-200 pb-6">
                <h3 class="text-lg font-semibold text-gray-800 mb-4">Массовый ввод (через табуляцию)</h3>
                <p class="text-sm text-gray-600 mb-4">
                    Формат: название расходника [TAB] имя МФУ/проектора [TAB] примечание<br>
                    Каждая строка - отдельный расходник. Имя устройства может быть неполным - система найдет похожее.
                </p>
                <form method="post" class="space-y-4">
                    <input type="hidden" name="action" value="add_bulk">
                    <div class="form-group">
                        <label for="bulk_type">Тип расходников</label>
                        <select id="bulk_type" name="bulk_type" class="form-select">
                            <option value="Картридж">Картридж</option>
                            <option value="Лампа проектора">Лампа проектора</option>
                            <option value="Другое">Другое</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="bulk_data">Данные (скопируйте из Excel/текста)</label>
                        <textarea id="bulk_data" name="bulk_data" class="form-textarea" rows="10" 
                                  placeholder="HP 85A&#10;МФУ кабинет 101&#10;HP 85A&#10;Принтер 205"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Добавить расходники</button>
                </form>
            </div>
            
            <!-- Форма одиночного ввода -->
            <div class="mb-8 border-b border-gray-200 pb-6">
                <h3 class="text-lg font-semibold text-gray-800 mb-4">Добавить один расходник</h3>
                <form method="post" class="space-y-4">
                    <input type="hidden" name="action" value="add_single">
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div class="form-group">
                            <label for="consumable_type">Тип</label>
                            <select id="consumable_type" name="consumable_type" class="form-select">
                                <option value="Картридж">Картридж</option>
                                <option value="Лампа проектора">Лампа проектора</option>
                                <option value="Другое">Другое</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="model">Название расходника <span class="text-red-500">*</span></label>
                            <input type="text" id="model" name="model" class="form-input" required placeholder="HP 85A">
                        </div>
                        <div class="form-group">
                            <label for="asset_name">Имя МФУ/проектора</label>
                            <input type="text" id="asset_name" name="asset_name" class="form-input" 
                                   placeholder="МФУ кабинет 101 (можно неполное)">
                        </div>
                        <div class="form-group">
                            <label for="quantity">Количество</label>
                            <input type="number" id="quantity" name="quantity" class="form-input" value="0" min="0">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="notes">Примечание</label>
                        <textarea id="notes" name="notes" class="form-textarea" rows="2"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary px-6 py-2.5">Добавить</button>
                </form>
            </div>
        </div>
        
        <!-- Запасы по устройствам -->
        <div class="card p-6 mb-6">
            <h3 class="text-xl font-bold text-gray-900 mb-4">Запасы по устройствам</h3>
            {% if assets_stock_list %}
                {% for stock_item in assets_stock_list %}
                {% set stock = stock_item %}
                <div class="mb-6 border border-gray-200 rounded-lg p-5 bg-gray-50">
                    <div class="flex items-center justify-between mb-4">
                        <div>
                            <h4 class="text-lg font-semibold text-gray-900">{{ stock.name }}</h4>
                            {% if stock.inv_number %}
                            <p class="text-sm text-gray-600">Инв. №: {{ stock.inv_number }}</p>
                            {% endif %}
                        </div>
                    </div>
                    
                    {% if stock.cartridges %}
                    <div class="mb-4">
                        <h5 class="font-semibold text-gray-700 mb-2">Картриджи:</h5>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Модель</th>
                                        <th style="width:100px;" class="text-center">Количество</th>
                                        <th>Примечание</th>
                                        <th style="width:150px;">Действия</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for cart in stock.cartridges %}
                                    <tr>
                                        <td class="font-medium">{{ cart.model }}</td>
                                        <td class="text-center font-semibold">{{ cart.quantity }}</td>
                                        <td class="text-sm text-gray-600">{{ cart.notes or '—' }}</td>
                                        <td>
                                            <form method="post" class="inline">
                                                <input type="hidden" name="action" value="update_quantity">
                                                <input type="hidden" name="consumable_id" value="{{ cart.id }}">
                                                <div class="flex gap-2">
                                                    <input type="number" name="quantity" value="{{ cart.quantity }}" 
                                                           class="form-input w-20 text-center" min="0">
                                                    <button type="submit" class="btn btn-primary text-xs px-2 py-1">✓</button>
                                                </div>
                                            </form>
                                            <form method="post" class="inline" onsubmit="return confirm('Удалить расходник?')">
                                                <input type="hidden" name="action" value="delete">
                                                <input type="hidden" name="consumable_id" value="{{ cart.id }}">
                                                <button type="submit" class="btn btn-danger text-xs px-2 py-1">✕</button>
                                            </form>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    {% endif %}
                    
                    {% if stock.lamps %}
                    <div class="mb-4">
                        <h5 class="font-semibold text-gray-700 mb-2">Лампы проектора:</h5>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Модель</th>
                                        <th style="width:100px;" class="text-center">Количество</th>
                                        <th>Примечание</th>
                                        <th style="width:150px;">Действия</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for lamp in stock.lamps %}
                                    <tr>
                                        <td class="font-medium">{{ lamp.model }}</td>
                                        <td class="text-center font-semibold">{{ lamp.quantity }}</td>
                                        <td class="text-sm text-gray-600">{{ lamp.notes or '—' }}</td>
                                        <td>
                                            <form method="post" class="inline">
                                                <input type="hidden" name="action" value="update_quantity">
                                                <input type="hidden" name="consumable_id" value="{{ lamp.id }}">
                                                <div class="flex gap-2">
                                                    <input type="number" name="quantity" value="{{ lamp.quantity }}" 
                                                           class="form-input w-20 text-center" min="0">
                                                    <button type="submit" class="btn btn-primary text-xs px-2 py-1">✓</button>
                                                </div>
                                            </form>
                                            <form method="post" class="inline" onsubmit="return confirm('Удалить расходник?')">
                                                <input type="hidden" name="action" value="delete">
                                                <input type="hidden" name="consumable_id" value="{{ lamp.id }}">
                                                <button type="submit" class="btn btn-danger text-xs px-2 py-1">✕</button>
                                            </form>
                                                </div>
                                            </form>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    {% endif %}
                    
                    {% if stock.lamps %}
                    <div class="mb-4">
                        <h5 class="font-semibold text-gray-700 mb-2">Лампы проектора:</h5>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Модель</th>
                                        <th style="width:100px;" class="text-center">Количество</th>
                                        <th>Примечание</th>
                                        <th style="width:150px;">Действия</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for lamp in stock.lamps %}
                                    <tr>
                                        <td class="font-medium">{{ lamp.model }}</td>
                                        <td class="text-center font-semibold">{{ lamp.quantity }}</td>
                                        <td class="text-sm text-gray-600">{{ lamp.notes or '—' }}</td>
                                        <td>
                                            <form method="post" class="inline">
                                                <input type="hidden" name="action" value="update_quantity">
                                                <input type="hidden" name="consumable_id" value="{{ lamp.id }}">
                                                <div class="flex gap-2">
                                                    <input type="number" name="quantity" value="{{ lamp.quantity }}" 
                                                           class="form-input w-20 text-center" min="0">
                                                    <button type="submit" class="btn btn-primary text-xs px-2 py-1">✓</button>
                                                    <a href="?delete_id={{ lamp.id }}" class="btn btn-danger text-xs px-2 py-1" 
                                                       onclick="return confirm('Удалить?')">✕</a>
                                                </div>
                                            </form>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    {% endif %}
                    
                    {% if stock.other %}
                    <div>
                        <h5 class="font-semibold text-gray-700 mb-2">Прочее:</h5>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Модель</th>
                                        <th style="width:100px;" class="text-center">Количество</th>
                                        <th>Примечание</th>
                                        <th style="width:150px;">Действия</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for other in stock.other %}
                                    <tr>
                                        <td class="font-medium">{{ other.model }}</td>
                                        <td class="text-center font-semibold">{{ other.quantity }}</td>
                                        <td class="text-sm text-gray-600">{{ other.notes or '—' }}</td>
                                        <td>
                                            <form method="post" class="inline">
                                                <input type="hidden" name="action" value="update_quantity">
                                                <input type="hidden" name="consumable_id" value="{{ other.id }}">
                                                <div class="flex gap-2">
                                                    <input type="number" name="quantity" value="{{ other.quantity }}" 
                                                           class="form-input w-20 text-center" min="0">
                                                    <button type="submit" class="btn btn-primary text-xs px-2 py-1">✓</button>
                                                </div>
                                            </form>
                                            <form method="post" class="inline" onsubmit="return confirm('Удалить расходник?')">
                                                <input type="hidden" name="action" value="delete">
                                                <input type="hidden" name="consumable_id" value="{{ other.id }}">
                                                <button type="submit" class="btn btn-danger text-xs px-2 py-1">✕</button>
                                            </form>
                                                </div>
                                            </form>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
            <div class="empty-state">
                <p class="text-gray-500">Нет расходников. Добавьте их через форму выше.</p>
            </div>
            {% endif %}
        </div>
        
        <!-- Общий список всех расходников -->
        <div class="card p-6">
            <h3 class="text-xl font-bold text-gray-900 mb-4">Все расходники</h3>
            {% if consumables %}
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Тип</th>
                            <th>Название</th>
                            <th style="width:120px;">Устройство</th>
                            <th style="width:100px;" class="text-center">Количество</th>
                            <th>Примечание</th>
                            <th style="width:150px;">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for c in consumables %}
                        <tr>
                            <td><span class="badge badge-blue">{{ c.consumable_type or '—' }}</span></td>
                            <td class="font-medium">{{ c.model }}</td>
                            <td class="text-sm">
                                {% if c.matched_asset_name %}
                                    <span class="text-green-600">{{ c.matched_asset_name }}</span>
                                {% elif c.asset_name %}
                                    <span class="text-orange-600">{{ c.asset_name }}</span>
                                    <span class="text-xs text-gray-500">(не найдено)</span>
                                {% else %}
                                    <span class="text-gray-400">—</span>
                                {% endif %}
                            </td>
                            <td class="text-center font-semibold">{{ c.quantity }}</td>
                            <td class="text-sm text-gray-600">{{ c.notes or '—' }}</td>
                            <td>
                                <form method="post" class="inline">
                                    <input type="hidden" name="action" value="update_quantity">
                                    <input type="hidden" name="consumable_id" value="{{ c.id }}">
                                    <div class="flex gap-2">
                                        <input type="number" name="quantity" value="{{ c.quantity }}" 
                                               class="form-input w-20 text-center" min="0">
                                        <button type="submit" class="btn btn-primary text-xs px-2 py-1">✓</button>
                                    </div>
                                </form>
                                <form method="post" class="inline" onsubmit="return confirm('Удалить расходник?')">
                                    <input type="hidden" name="action" value="delete">
                                    <input type="hidden" name="consumable_id" value="{{ c.id }}">
                                    <button type="submit" class="btn btn-danger text-xs px-2 py-1">✕</button>
                                </form>
                                    </div>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">
                <p class="text-gray-500">Нет расходников</p>
            </div>
            {% endif %}
        </div>
    {% endblock %}
    """
    
    return render(content, page='consumables', consumables=consumables, assets_stock_list=assets_stock_list)

if __name__ == '__main__':
    print("=" * 60)
    print("Система учёта основных средств")
    print("=" * 60)
    print(f"\nСервер: http://127.0.0.1:5000")
    print(f"БД: {DATABASE}")
    print(f"Бэкапы: {app.config['BACKUP_FOLDER']}/")
    print("\nCtrl+C для остановки\n")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
