-- Основные средства (данные из бухгалтерии)
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_number VARCHAR(50) UNIQUE,
    name TEXT NOT NULL,
    okof_code VARCHAR(20),
    acquisition_date DATE,
    initial_cost DECIMAL(12,2),
    useful_life_months INTEGER,
    wear_percent DECIMAL(5,2),
    quantity INTEGER DEFAULT 1,
    accounting_status VARCHAR(50),
    category VARCHAR(50),
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Местоположения
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building VARCHAR(50),
    floor VARCHAR(10),
    room_number VARCHAR(20) NOT NULL,
    room_name VARCHAR(100),
    responsible_person VARCHAR(100),
    is_active BOOLEAN DEFAULT 1
);

-- Фактическое состояние
CREATE TABLE IF NOT EXISTS actual_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    location_id INTEGER,
    serial_number VARCHAR(100),
    condition_status VARCHAR(50) DEFAULT 'Исправно',
    physical_label_status VARCHAR(50) DEFAULT 'Есть',
    last_verified_date DATE,
    verified_by VARCHAR(100),
    notes TEXT,
    is_found BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Расхождения
CREATE TABLE IF NOT EXISTS discrepancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    discrepancy_type VARCHAR(50) NOT NULL,
    expected_value TEXT,
    actual_value TEXT,
    severity VARCHAR(20) DEFAULT 'MEDIUM',
    status VARCHAR(20) DEFAULT 'NEW',
    detected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_date TIMESTAMP,
    resolution_notes TEXT,
    assigned_to VARCHAR(100),
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

-- Расходники к оборудованию
CREATE TABLE IF NOT EXISTS equipment_consumables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_asset_id INTEGER NOT NULL,
    consumable_type VARCHAR(50),
    model VARCHAR(100),
    installation_date DATE,
    installed_by VARCHAR(100),
    estimated_yield INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

-- Приход товара
CREATE TABLE IF NOT EXISTS incoming_goods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arrival_date DATE NOT NULL,
    item_name TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    supplier VARCHAR(200),
    document_number VARCHAR(100),
    category VARCHAR(50),
    temporary_storage_location VARCHAR(100),
    status VARCHAR(50) DEFAULT 'PENDING',
    assigned_asset_id INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assigned_asset_id) REFERENCES assets(id)
);

-- Дефекты и неисправности
CREATE TABLE IF NOT EXISTS defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    reported_date DATE NOT NULL,
    reported_by VARCHAR(100),
    defect_description TEXT NOT NULL,
    defect_type VARCHAR(50),
    priority VARCHAR(20) DEFAULT 'MEDIUM',
    status VARCHAR(50) DEFAULT 'OPEN',
    repair_date DATE,
    repair_notes TEXT,
    repair_cost DECIMAL(10,2),
    repaired_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

-- История перемещений
CREATE TABLE IF NOT EXISTS movement_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    from_location_id INTEGER,
    to_location_id INTEGER NOT NULL,
    movement_date DATE NOT NULL,
    reason TEXT,
    moved_by VARCHAR(100),
    approved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY (from_location_id) REFERENCES locations(id),
    FOREIGN KEY (to_location_id) REFERENCES locations(id)
);

-- Лог импорта
CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_name VARCHAR(255),
    records_imported INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    error_log TEXT,
    imported_by VARCHAR(100)
);

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    email VARCHAR(100),
    role VARCHAR(20) DEFAULT 'VIEWER',
    is_active BOOLEAN DEFAULT 1,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для ускорения поиска
CREATE INDEX IF NOT EXISTS idx_assets_inventory ON assets(inventory_number);
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_actual_assets_asset_id ON actual_assets(asset_id);
CREATE INDEX IF NOT EXISTS idx_actual_assets_location_id ON actual_assets(location_id);
CREATE INDEX IF NOT EXISTS idx_discrepancies_asset_id ON discrepancies(asset_id);
CREATE INDEX IF NOT EXISTS idx_discrepancies_status ON discrepancies(status);
CREATE INDEX IF NOT EXISTS idx_defects_asset_id ON defects(asset_id);
CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status);

-- Триггер для автоматического обновления updated_at
CREATE TRIGGER IF NOT EXISTS update_assets_timestamp
AFTER UPDATE ON assets
BEGIN
    UPDATE assets SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_actual_assets_timestamp
AFTER UPDATE ON actual_assets
BEGIN
    UPDATE actual_assets SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Фактическая инвентаризация (независимо от бухгалтерии)
CREATE TABLE IF NOT EXISTS fact_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_number VARCHAR(50),
    name TEXT,
    serial_number VARCHAR(100),
    condition_status VARCHAR(50),
    physical_label_status VARCHAR(50),
    location TEXT,
    notes TEXT,
    source VARCHAR(20), -- manual/import
    observed_date DATE, -- когда зафиксировано
    matched_asset_id INTEGER, -- явное сопоставление с assets
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matched_asset_id) REFERENCES assets(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_inventory_inv ON fact_inventory(inventory_number);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_serial ON fact_inventory(serial_number);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_matched ON fact_inventory(matched_asset_id);

CREATE TRIGGER IF NOT EXISTS update_fact_inventory_timestamp
AFTER UPDATE ON fact_inventory
BEGIN
    UPDATE fact_inventory SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
-- Вставка дефолтного администратора (admin / admin123)
INSERT OR IGNORE INTO users (username, password_hash, full_name, role)
VALUES ('admin', 'pbkdf2:sha256:260000$salt$hash', 'Администратор', 'ADMIN');

-- Пример локаций
INSERT OR IGNORE INTO locations (building, floor, room_number, room_name) VALUES
('Главный корпус', '1', '101', 'Бухгалтерия'),
('Главный корпус', '1', '102', 'Отдел кадров'),
('Главный корпус', '2', '201', 'Компьютерный класс'),
('Главный корпус', '2', '202', 'Лаборатория'),
('Главный корпус', '3', '301', 'Аудитория');