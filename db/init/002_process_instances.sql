-- Оркестратор (T-31): минимальное хранилище состояния экземпляров процессов.
-- Полная онтология предметной области и версионируемые process_params — задача T-25;
-- эта таблица её не заменяет, только даёт оркестратору персистентность (ФТ-С-3.3).

CREATE TABLE IF NOT EXISTS process_instances (
    case_id     TEXT PRIMARY KEY,
    process_key TEXT        NOT NULL,           -- какой процесс (vkr_defense / workload_planning / ...)
    status      TEXT        NOT NULL DEFAULT 'active',  -- active | completed
    state       JSONB       NOT NULL,           -- BpmnWorkflowSerializer.serialize_json()
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_process_instances_status ON process_instances (status);
CREATE INDEX IF NOT EXISTS ix_process_instances_process_key ON process_instances (process_key);
