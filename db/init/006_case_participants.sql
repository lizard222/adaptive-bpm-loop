-- Участники экземпляра процесса (E13, часть T-25): кто конкретно участвует в
-- данной защите. Нужна, чтобы шаги дорожки «Студент» видел и выполнял только
-- студент, чья это защита, а не любой пользователь с ролью student; и чтобы
-- экран «Моя защита» знал, какой экземпляр показывать.
-- role — роль в процессе (сейчас используется только 'student'; таблица
-- общая, чтобы позже так же привязать руководителя ВКР к своим студентам).
-- username — логин из api/auth.py (DEMO_USERS); персональных данных здесь нет.

CREATE TABLE IF NOT EXISTS case_participants (
    case_id    TEXT        NOT NULL REFERENCES process_instances (case_id) ON DELETE CASCADE,
    role       TEXT        NOT NULL,
    username   TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, role)
);

CREATE INDEX IF NOT EXISTS ix_case_participants_user ON case_participants (role, username);
