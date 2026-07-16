-- Интерфейсный агент (T-37, ФТ-А-И): очередь предложений Аналитик-Адаптера
-- (FIPA propose, T-42), ожидающих решения человека через REST/UI, вместо
-- заглушки-агента в смоук-тестах. Одна строка = одно предложение = один
-- FIPA thread; после решения человека (REST) Интерфейсный агент отправляет
-- реальный accept-proposal/reject-proposal обратно тому, кто предложил
-- (proposer_jid), и помечает replied_at.

CREATE TABLE IF NOT EXISTS pending_decisions (
    id            BIGSERIAL PRIMARY KEY,
    thread        TEXT        NOT NULL UNIQUE,  -- FIPA thread — по нему сверяется ответ
    proposer_jid  TEXT        NOT NULL,          -- кому слать accept-proposal/reject-proposal
    process_key   TEXT        NOT NULL,
    kind          TEXT        NOT NULL,
    target        TEXT        NOT NULL,
    justification TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected
    decided_by    TEXT,                                     -- логин пользователя, принявшего решение
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at    TIMESTAMPTZ,
    replied_at    TIMESTAMPTZ                               -- когда FIPA-ответ реально отправлен
);

CREATE INDEX IF NOT EXISTS ix_pending_decisions_status ON pending_decisions (status);
