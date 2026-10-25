-- Версии модели процесса (E15, структурная адаптация): каждая принятая
-- корректировка add_checkpoint, ставящая контрольную точку на шаг без срока,
-- порождает новую версию BPMN-модели. Версия 0 — базовая модель из реестра
-- (orchestrator/process_registry.py), строки для неё нет.
--
-- bpmn_xml хранит модель целиком: версия воспроизводима и не зависит от того,
-- как позже изменится генератор. Новые экземпляры запускаются по последней
-- версии, уже идущие доходят по той, с которой стартовали (SpiffWorkflow
-- сериализует модель в состояние экземпляра).

CREATE TABLE IF NOT EXISTS process_model_versions (
    process_key        TEXT        NOT NULL,
    version            INTEGER     NOT NULL CHECK (version > 0),
    added_checkpoints  TEXT[]      NOT NULL,
    bpmn_xml           TEXT        NOT NULL,
    params_version     INTEGER,    -- версия из applied_corrections, которой принята корректировка
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (process_key, version)
);
