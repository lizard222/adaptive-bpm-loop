"""Dev-заплатка для SPADE-агентов, подключающихся к локальному Prosody без TLS.

slixmpp (транспорт SPADE) по умолчанию отказывается слать PLAIN-логин по
незашифрованному каналу — это политика САМОГО КЛИЕНТА (`security_settings`),
а не настройка сервера, и SPADE не даёт публичного способа её переопределить
(spade.agent.Agent пересоздаёт XMPPClient внутри start(), до этого момента
клиент недоступен для настройки). Для локального прототипа (docker-compose,
доверенная сеть) заменяем класс на подкласс, разрешающий unencrypted_plain.

Использование: импортировать и вызвать enable_unencrypted_plain_auth() один
раз при старте процесса, до создания любых Agent(...).
"""
import spade.agent
from spade.xmpp_client import XMPPClient as _BaseXMPPClient


class _DevXMPPClient(_BaseXMPPClient):
    def __init__(self, jid, password, verify_security, auto_register):
        super().__init__(jid, password, verify_security, auto_register)
        # 'feature_mechanisms' — плагин slixmpp, отвечающий за выбор SASL-механизма;
        # регистрируется автоматически внутри ClientXMPP.__init__ (см. clientxmpp.py).
        # Его настройка unencrypted_plain по умолчанию False — это и есть тот самый
        # клиентский запрет, который выдавал "No appropriate login method".
        self["feature_mechanisms"].unencrypted_plain = True


def enable_unencrypted_plain_auth() -> None:
    spade.agent.XMPPClient = _DevXMPPClient
