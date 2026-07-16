-- E3 (часть T-25): текущие параметры процесса, реально читаемые живыми
-- агентами (Планировщик/Контролер), в отличие от applied_corrections (T-42),
-- который только журналирует ИСТОРИЮ применённых корректировок, но не даёт
-- дешёвого способа узнать "а какие параметры действуют ПРЯМО СЕЙЧАС".
-- Одна строка на процесс — состояние, не журнал (журнал — applied_corrections).

CREATE TABLE IF NOT EXISTS process_params_current (
    process_key    TEXT PRIMARY KEY,
    reminder_days  INT         NOT NULL,
    escalation_days INT        NOT NULL,
    version        INT         NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
