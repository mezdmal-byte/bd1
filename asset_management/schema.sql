-- ============================================================
-- Схема БД: Система учёта основных средств
-- ============================================================

-- Основные средства (данные из бухгалтерии / 1С)
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

-- Фактическая инвентаризация (независимо от бухгалтерии, накопительная)
CREATE TABLE IF NOT EXISTS fact_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_number VARCHAR(50),
    name TEXT,
    serial_number VARCHAR(100),
    condition_status VARCHAR(50),
    physical_label_status VARCHAR(50),
    location TEXT,
    ip_address VARCHAR(45),
    notes TEXT,
    source VARCHAR(20),
    observed_date DATE,
    matched_asset_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matched_asset_id) REFERENCES assets(id) ON DELETE SET NULL
);

-- Фактическое состояние (привязка к бух. объекту, 1:1)
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
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

-- Расходники к оборудованию (картриджи, лампы и т.д.)
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

-- История изменений (расширенная)
CREATE TABLE IF NOT EXISTS change_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT DEFAULT 'user',
    reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Местоположения (справочник)
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building VARCHAR(50),
    floor VARCHAR(10),
    room_number VARCHAR(20) NOT NULL,
    room_name VARCHAR(100),
    responsible_person VARCHAR(100),
    is_active BOOLEAN DEFAULT 1
);

-- ============================================================
-- Индексы
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_assets_inventory ON assets(inventory_number);
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_actual_assets_asset_id ON actual_assets(asset_id);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_inv ON fact_inventory(inventory_number);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_serial ON fact_inventory(serial_number);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_matched ON fact_inventory(matched_asset_id);
CREATE INDEX IF NOT EXISTS idx_change_history_entity ON change_history(entity_type, entity_id);

-- ============================================================
-- Триггеры автообновления updated_at
-- ============================================================
CREATE TRIGGER IF NOT EXISTS update_assets_timestamp
AFTER UPDATE ON assets BEGIN
    UPDATE assets SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_actual_assets_timestamp
AFTER UPDATE ON actual_assets BEGIN
    UPDATE actual_assets SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_fact_inventory_timestamp
AFTER UPDATE ON fact_inventory BEGIN
    UPDATE fact_inventory SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Начальные данные
INSERT OR IGNORE INTO locations (building, floor, room_number, room_name) VALUES
('Главный корпус', '1', '101', 'Бухгалтерия'),
('Главный корпус', '1', '102', 'Отдел кадров'),
('Главный корпус', '2', '201', 'Компьютерный класс'),
('Главный корпус', '2', '202', 'Лаборатория'),
('Главный корпус', '3', '301', 'Аудитория');
