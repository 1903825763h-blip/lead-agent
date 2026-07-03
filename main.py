from database import (
    get_companies_by_status,
    get_contacts_by_company,
    init_database,
    insert_company,
    insert_contact,
    insert_rejected_result,
    mark_company_failed,
    mark_company_sent,
)
from exporter import export_to_excel
from llm_analyzer import analyze_candidate_with_llm
from mailer import send_email
from search import search_candidates
from template import load_template, render_template


def ask_int(prompt, default):
    value = input(prompt).strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"输入不是有效数字，将使用默认值：{default}")
        return default


def collect_leads():
    keyword = input("请输入产品/行业关键词（例如：medical device）：").strip()
    country = input("请输入国家/地区（仅用于记录和导出，可留空）：").strip()
    limit = ask_int("请输入目标有效联系人数量（例如：5）：", 5)
    if not keyword:
        print("关键词不能为空。")
        return

    init_database()
    counters = {"skipped": 0, "rejected": 0, "contact_found": 0, "no_contact": 0}

    print(f"\n[1/4] 正在搜索候选网站：{keyword}")
    try:
        candidates = search_candidates(keyword, limit * 3)
    except Exception as exc:
        print(f"搜索失败：{exc}")
        return
    print(f"找到 {len(candidates)} 个候选网址。\n")

    for index, candidate in enumerate(candidates, start=1):
        if counters["contact_found"] >= limit:
            break

        print(f"[{index}/{len(candidates)}] 正在抓取：{candidate['url']}")
        try:
            from crawler import crawl_candidate

            crawl_result = crawl_candidate(candidate["url"])
        except Exception as exc:
            counters["skipped"] += 1
            print(f"  已跳过：抓取失败：{exc}")
            continue

        print("  正在交给 LLM 判断官网真实性和邮箱质量...")
        try:
            analysis = analyze_candidate_with_llm(keyword, candidate, crawl_result)
        except Exception as exc:
            counters["skipped"] += 1
            print(f"  已跳过：LLM 分析失败：{exc}")
            continue

        if not analysis.get("is_target_company"):
            counters["rejected"] += 1
            reason = analysis.get("reason", "LLM 判断不是目标公司官网")
            insert_rejected_result(candidate.get("title", ""), candidate.get("url", ""), candidate.get("domain", ""), reason)
            print(f"  已拒绝：{reason}")
            continue

        best_email = analysis.get("best_email", "")
        status = "contact_found" if best_email else "no_contact"
        company_id = insert_company(
            analysis.get("company_name") or candidate.get("domain", "Unknown"),
            analysis.get("website") or crawl_result.get("final_url") or candidate.get("url"),
            country,
            analysis.get("industry") or keyword,
            status,
            analysis.get("confidence", 0.0),
            analysis.get("reason", ""),
        )

        if best_email:
            insert_contact(
                company_id,
                best_email,
                analysis.get("email_type", "unknown"),
                crawl_result.get("final_url") or candidate.get("url"),
            )
            counters["contact_found"] += 1
            print(f"  已保存有效联系人：{analysis.get('company_name')} | {best_email}")
        else:
            counters["no_contact"] += 1
            print(f"  已保存公司，但没有合适邮箱：{analysis.get('company_name')}")

    output_path = export_to_excel()
    print("\n处理完成。")
    print(
        "统计："
        f"找到邮箱={counters['contact_found']}，"
        f"无合适邮箱={counters['no_contact']}，"
        f"已拒绝={counters['rejected']}，"
        f"已跳过={counters['skipped']}"
    )
    print(f"Excel 已导出：{output_path}")


def export_excel_menu():
    init_database()
    output_path = export_to_excel()
    print(f"Excel 已导出：{output_path}")


def send_emails_from_template():
    init_database()
    image_input = input("附件图片路径，多个路径用英文逗号分隔，可留空：").strip()
    image_paths = [item.strip() for item in image_input.split(",") if item.strip()]
    template_text = load_template()
    companies = get_companies_by_status("contact_found")
    print(f"待发送公司数量：{len(companies)}")

    sent = 0
    failed = 0
    for company in companies:
        contacts = get_contacts_by_company(company["id"])
        if not contacts:
            continue
        contact = contacts[0]
        rendered = render_template(template_text, company, contact)
        try:
            send_email(contact["email"], rendered["subject"], rendered["body"], image_paths=image_paths)
            mark_company_sent(company["id"])
            sent += 1
            print(f"发送成功：{company['company_name']} <{contact['email']}>")
        except Exception as exc:
            mark_company_failed(company["id"], str(exc))
            failed += 1
            print(f"发送失败：{company['company_name']} <{contact['email']}> | {exc}")

    print(f"发送完成：成功={sent}，失败={failed}")


def main():
    while True:
        print("\n潜在客户邮箱自动化工具")
        print("1. 搜索并收集潜在客户")
        print("2. 导出 Excel")
        print("3. 使用模板发送邮件")
        print("4. 退出")
        choice = input("请选择：").strip()

        if choice == "1":
            collect_leads()
        elif choice == "2":
            export_excel_menu()
        elif choice == "3":
            send_emails_from_template()
        elif choice == "4":
            print("已退出。")
            break
        else:
            print("无效选择，请重新输入。")


if __name__ == "__main__":
    main()
