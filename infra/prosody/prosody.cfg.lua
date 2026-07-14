-- Минимальный dev-конфиг Prosody для локальной разработки агентов SPADE (T-33, T-34).
-- НЕ для продакшена: регистрация открыта, шифрование не обязательно — сеть
-- считается доверенной (docker-compose network / localhost).

pidfile = "/var/run/prosody/prosody.pid"

authentication = "internal_plain"
storage = "internal"

-- Открытая in-band регистрация (XEP-0077): агенты SPADE регистрируются сами
-- при первом подключении (Agent(..., auto_register=True), значение по умолчанию).
allow_registration = true

c2s_require_encryption = false
s2s_require_encryption = false
s2s_secure_auth = false
-- Без TLS Prosody по умолчанию не предлагает SASL PLAIN — разрешаем явно.
-- Только для доверенной dev-сети внутри docker-compose/localhost.
allow_unencrypted_plain_auth = true

-- Модуль "tls" намеренно НЕ включён: сертификат в образе prosody/prosody
-- принадлежит root с правами rw-------, процесс prosody читать его не может
-- (баг образа). Пытаться его чинить смысла нет — для локального прототипа
-- используем чистый plaintext c2s, без попытки STARTTLS вообще.
modules_enabled = {
    "roster"; "saslauth"; "dialback"; "disco";
    "private"; "vcard4"; "vcard_legacy";
    "version"; "uptime"; "time"; "ping";
    "register";
}

log = {
    info = "*console";
    error = "*console";
}

VirtualHost "localhost"
