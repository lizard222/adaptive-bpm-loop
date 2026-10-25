-- Ключевые даты конкретной защиты (E14): дата предзащиты и дата защиты.
-- Назначает секретарь при запуске экземпляра или позже; при переносе строка
-- перезаписывается, а история переносов остаётся в event_log (событие
-- milestones_set с прежним и новым значением).
-- Таймеры процесса берут сроки не отсюда, а из данных экземпляра
-- (api/milestones.py кладёт туда вычисленные моменты): эта таблица — для
-- показа дат и запросов по ним без разбора состояния движка.

CREATE TABLE IF NOT EXISTS case_milestones (
    case_id   TEXT        NOT NULL REFERENCES process_instances (case_id) ON DELETE CASCADE,
    milestone TEXT        NOT NULL CHECK (milestone IN ('predefense_at', 'defense_at')),
    at        TIMESTAMPTZ NOT NULL,
    set_by    TEXT        NOT NULL,
    set_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, milestone)
);
