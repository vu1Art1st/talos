"""SMTP 传输选择：465 隐式 TLS / 587 STARTTLS / 25 明文，均通过桩验证调用形态。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.mail_service as mail_service


def _settings(monkeypatch, **overrides) -> None:
    values = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": 25,
        "SMTP_USER": "sender@example.com",
        "SMTP_PASS": "secret",
        "SMTP_FROM": "sender@example.com",
    }
    values.update(overrides)
    monkeypatch.setattr(mail_service, "settings", SimpleNamespace(**values))


def _fake_server() -> MagicMock:
    server = MagicMock()
    server.__enter__.return_value = server
    return server


def test_port_465_uses_implicit_ssl(monkeypatch):
    _settings(monkeypatch, SMTP_PORT=465)
    server = _fake_server()
    ssl_ctor = MagicMock(return_value=server)
    monkeypatch.setattr(mail_service.smtplib, "SMTP_SSL", ssl_ctor)

    mail_service.send_mail_sync(["to@example.com"], "主题", "<p>正文</p>")

    ssl_ctor.assert_called_once_with("smtp.example.com", 465, timeout=15)
    server.starttls.assert_not_called()
    server.login.assert_called_once_with("sender@example.com", "secret")
    server.sendmail.assert_called_once()


def test_port_587_uses_starttls(monkeypatch):
    _settings(monkeypatch, SMTP_PORT=587)
    server = _fake_server()
    smtp_ctor = MagicMock(return_value=server)
    monkeypatch.setattr(mail_service.smtplib, "SMTP", smtp_ctor)

    mail_service.send_mail_sync(["to@example.com"], "主题", "<p>正文</p>")

    smtp_ctor.assert_called_once_with("smtp.example.com", 587, timeout=15)
    server.starttls.assert_called_once_with()
    server.login.assert_called_once_with("sender@example.com", "secret")


def test_port_25_stays_plaintext(monkeypatch):
    _settings(monkeypatch, SMTP_PORT=25)
    server = _fake_server()
    smtp_ctor = MagicMock(return_value=server)
    monkeypatch.setattr(mail_service.smtplib, "SMTP", smtp_ctor)

    mail_service.send_mail_sync(["to@example.com"], "主题", "<p>正文</p>")

    smtp_ctor.assert_called_once_with("smtp.example.com", 25, timeout=15)
    server.starttls.assert_not_called()
