"""SMTP 邮件发送唯一实现：渠道通知与账户安全邮件共用。"""
import asyncio
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from app.core.config import settings


def _new_smtp_client() -> smtplib.SMTP:
    """按端口选择传输：465 走隐式 TLS（SSL），587 走 STARTTLS，其余（如 25）保持明文。"""
    if settings.SMTP_PORT == 465:
        return smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    client = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    if settings.SMTP_PORT == 587:
        client.starttls()
    return client


def send_mail_sync(to: list[str], subject: str, body_html: str) -> None:
    if not settings.SMTP_HOST or not to:
        raise smtplib.SMTPException("未配置 SMTP 服务或收件人为空")
    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = ",".join(to)
    with _new_smtp_client() as server:
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.sendmail(msg["From"], to, msg.as_string())


async def send_mail(to: list[str], subject: str, body_html: str) -> None:
    await asyncio.to_thread(send_mail_sync, to, subject, body_html)
