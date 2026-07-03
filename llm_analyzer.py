import json
import re

from openai import OpenAI

from config import load_config


EMAIL_TYPES = {"sales", "info", "contact", "support", "unknown", "none"}


def compact_pages(crawl_result: dict) -> str:
    chunks = []
    total = 0
    for page in crawl_result.get("pages", []):
        text = page.get("text", "")[:3000]
        block = f"URL: {page.get('url', '')}\nTitle: {page.get('title', '')}\nText: {text}"
        remaining = 12000 - total
        if remaining <= 0:
            break
        block = block[:remaining]
        chunks.append(block)
        total += len(block)
    return "\n\n--- PAGE ---\n\n".join(chunks)


def extract_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def normalize_result(data: dict, fallback_website: str = "") -> dict:
    return {
        "is_target_company": bool(data.get("is_target_company", False)),
        "company_name": str(data.get("company_name", "") or ""),
        "website": str(data.get("website", "") or fallback_website or ""),
        "industry": str(data.get("industry", "") or ""),
        "country": str(data.get("country", "") or ""),
        "best_email": str(data.get("best_email", "") or "").strip().lower(),
        "all_candidate_emails": list(data.get("all_candidate_emails", []) or []),
        "email_type": str(data.get("email_type", "unknown") or "unknown")
        if str(data.get("email_type", "unknown") or "unknown") in EMAIL_TYPES
        else "unknown",
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0))),
        "reason": str(data.get("reason", "") or ""),
    }


def failed_result(reason: str, fallback_website: str = "") -> dict:
    return {
        "is_target_company": False,
        "company_name": "",
        "website": fallback_website,
        "industry": "",
        "country": "",
        "best_email": "",
        "all_candidate_emails": [],
        "email_type": "none",
        "confidence": 0.0,
        "reason": reason,
    }


def analyze_candidate_with_llm(keyword, search_result, crawl_result) -> dict:
    config = load_config()
    api_key = config.get("LLM_API_KEY")
    fallback_website = crawl_result.get("final_url") or search_result.get("url", "")
    if not api_key:
        return failed_result(".env 中缺少 LLM_API_KEY", fallback_website)

    client = OpenAI(api_key=api_key, base_url=config.get("LLM_BASE_URL") or None)
    candidate_emails = crawl_result.get("candidate_emails", [])
    links = crawl_result.get("links", [])[:30]

    system_prompt = (
        "你是一个严格的 B2B 潜在客户筛选分析师。"
        "你只能输出一个合法 JSON 对象，不要输出 markdown、解释、注释或多余文本。"
    )
    user_prompt = f"""
用户目标：
- 关键词：{keyword}

任务：
请判断这个搜索结果和抓取到的网站，是否属于真实目标公司的官方网站。
你需要结合搜索标题、摘要、URL、网站正文、候选邮箱和站内链接来判断。

如果页面是政府/监管机构、注册审批文章、市场报告、新闻/博客、咨询服务、
目录/黄页/列表页、社交主页、数据库页面、文档文件，或任何无关信息页面，
都不要认为它是目标公司官网。

如果它是与关键词相关的公司官方网站，返回 is_target_company=true。
如果不是，返回 false。

只能从候选邮箱中选择最适合商务开发的邮箱。
优先级：sales@、info@、contact@、inquiry@、export@、business@、marketing@。
只有在没有更好商务邮箱时，才选择 support@。
必须过滤 privacy@、legal@、dpo@、hr@、careers@、jobs@、noreply@、no-reply@、
webmaster@、abuse@、postmaster@。个人邮箱也要过滤，除非它明显是商务联系人。
如果没有合适邮箱，设置 best_email="" 且 email_type="none"。

reason 字段请用中文简要说明判断原因。

必须输出以下 JSON 结构：
{{
  "is_target_company": true,
  "company_name": "",
  "website": "",
  "industry": "",
  "best_email": "",
  "all_candidate_emails": [],
  "email_type": "sales/info/contact/support/unknown/none",
  "confidence": 0.0,
  "reason": ""
}}

搜索结果：
标题：{search_result.get("title", "")}
URL：{search_result.get("url", "")}
摘要：{search_result.get("snippet", "")}
域名：{search_result.get("domain", "")}

网站抓取结果：
最终 URL：{crawl_result.get("final_url", "")}
页面标题：{crawl_result.get("title", "")}
抓取错误：{crawl_result.get("error", "")}
候选邮箱：{json.dumps(candidate_emails, ensure_ascii=False)}
站内链接：{json.dumps(links, ensure_ascii=False)}

网页正文：
{compact_pages(crawl_result)}
"""

    try:
        response = client.chat.completions.create(
            model=config.get("LLM_MODEL", "deepseek-chat"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        parsed = extract_json_object(content)
        return normalize_result(parsed, fallback_website)
    except Exception as exc:
        return failed_result(f"LLM JSON 解析失败：{exc}", fallback_website)
