from config import get_data_dir


DEFAULT_TEMPLATE = """Subject: 合作咨询

您好，{company_name}：

我在网上看到了贵司官网：{website}

我们希望向 {industry} 行业的企业介绍我们的服务。

祝好，
您的姓名
"""


def get_template_path():
    return get_data_dir() / "email_template.txt"


def load_template() -> str:
    path = get_template_path()
    if not path.exists():
        path.write_text(DEFAULT_TEMPLATE, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def render_template(template_text, company, contact) -> dict:
    def value(row, key):
        if row is None:
            return ""
        if hasattr(row, "get"):
            return row.get(key, "") or ""
        try:
            return row[key] or ""
        except Exception:
            return ""

    values = {
        "company_name": value(company, "company_name"),
        "website": value(company, "website"),
        "country": value(company, "country"),
        "industry": value(company, "industry"),
        "email": value(contact, "email"),
        "email_type": value(contact, "email_type"),
    }

    rendered = template_text.format_map(DefaultDict(values))
    lines = rendered.splitlines()
    subject = "合作咨询"
    body_lines = lines
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or subject
        body_lines = lines[1:]
    body = "\n".join(body_lines).lstrip()
    return {"subject": subject, "body": body}


class DefaultDict(dict):
    def __missing__(self, key):
        return ""
