-- Каркас (T-30): минимальная схема — только журнал событий, нужный с первого дня.
-- Полная онтология предметной области и версионируемые process_params — задача T-25.

CREATE TABLE IF NOT EXISTS event_log (
    event_id    BIGSERIAL PRIMARY KEY,
    case_id     TEXT        NOT NULL,           -- экземпляр процесса
    process_key TEXT        NOT NULL,           -- какой процесс (vkr_defense / workload_planning)
    activity    TEXT        NOT NULL,           -- действие
    lifecycle   TEXT        NOT NULL DEFAULT 'complete',  -- start / complete / escalate / ...
    resource    TEXT,                           -- исполнитель или агент
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    attributes  JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_event_log_case ON event_log (case_id);
CREATE INDEX IF NOT EXISTS ix_event_log_ts   ON event_log (ts);

-- Журнал неизменяем (ФТ-С-5.2): запрещаем UPDATE/DELETE на уровне БД.
-- ВАЖНО: TRUNCATE этот триггер не перехватывает (в PostgreSQL TRUNCATE — не
-- построчная операция, BEFORE DELETE на неё не срабатывает). Это осознанно
-- оставлено как единственный путь очистки для dev/тестового окружения; если
-- потребуется гарантия неизменяемости и от TRUNCATE, нужно дополнительно
-- REVOKE TRUNCATE ON event_log FROM <роль приложения>.
CREATE OR REPLACE FUNCTION forbid_event_log_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'event_log is append-only (FT-S-5.2)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_event_log_immutable ON event_log;
CREATE TRIGGER trg_event_log_immutable
    BEFORE UPDATE OR DELETE ON event_log
    FOR EACH ROW EXECUTE FUNCTION forbid_event_log_mutation();
