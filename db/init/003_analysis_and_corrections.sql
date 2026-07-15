-- Агент Аналитик-Адаптер (T-42): хранение отчётов анализа циклов и применённых
-- корректировок. Минимальный эквивалент версионируемой process_params
-- (полная схема — задача T-25): здесь версия закрепляется за ЦИКЛОМ анализа
-- целиком (все принятые в этом цикле корректировки получают один номер),
-- а не за отдельным параметром.

CREATE TABLE IF NOT EXISTS analysis_reports (
    report_id    BIGSERIAL PRIMARY KEY,
    process_key  TEXT        NOT NULL,
    n_cases      INT         NOT NULL,
    fitness      DOUBLE PRECISION,
    precision_   DOUBLE PRECISION,
    report       JSONB       NOT NULL,  -- сериализованный ConveyorReport (ФТ-А-А-5, воспроизводимость)
    corrections  JSONB       NOT NULL,  -- предложенные corrections.propose_corrections (до решения человека)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS applied_corrections (
    id           BIGSERIAL PRIMARY KEY,
    process_key  TEXT        NOT NULL,
    version      INT         NOT NULL,  -- номер версии параметров процесса (общий на весь цикл)
    kind         TEXT        NOT NULL,
    target       TEXT        NOT NULL,
    mode         TEXT        NOT NULL,  -- 'propose' | 'auto' (ФТ-С-7.6)
    evidence     JSONB       NOT NULL,
    justification TEXT       NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_applied_corrections_process ON applied_corrections (process_key);
CREATE INDEX IF NOT EXISTS ix_analysis_reports_process ON analysis_reports (process_key);
