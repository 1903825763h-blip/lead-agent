import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

from config import load_config


def send_email(to_email, subject, body, image_paths=None) -> bool:
    config = load_config()
    if not config.get("SMTP_HOST") or not config.get("SMTP_USER") or not config.get("SMTP_PASSWORD"):
        raise ValueError("SMTP configuration is incomplete in .env")

    msg = EmailMessage()
    msg["From"] = config.get("SMTP_FROM") or config.get("SMTP_USER")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body or "")

    for image_path in image_paths or []:
        path = Path(image_path.strip().strip('"'))
        if not path.exists() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        mime_type, _ = mimetypes.guess_type(path)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        with path.open("rb") as file:
            msg.add_attachment(
                file.read(),
                maintype=maintype,
                subtype=subtype,
                filename=path.name,
            )

    with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
        smtp.send_message(msg)
    return True
