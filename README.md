轻量级获客 Agent，结合搜索 API、网页爬取、LLM 判断、SQLite 存储和 Excel 导出。LLM 主要用于过滤无关网页并筛选合适的商务邮箱，提高纯爬虫方案的数据质量。
使用方法:在.env中放入api key,运行main.py
# Lead Generation Email Automation Tool

A lightweight LLM-powered lead generation agent that helps discover potential company websites, analyze candidate pages, extract business emails, and export structured leads to Excel.

## Overview

This project is a Python-based automation tool designed for B2B lead generation.

The system uses SerpAPI to search for potential company websites, crawls public web pages such as home, contact, and about pages, and then uses an LLM to judge whether the result is a real target company website and select the most suitable business email.

Unlike a simple crawler, this tool uses an LLM as a decision-making layer to reduce noisy results such as government pages, reports, registration guides, blogs, and unrelated websites.

## Features

- Search potential company websites by keyword and country
- Crawl public company web pages
- Extract candidate emails from page text and mailto links
- Use LLM to judge whether a result is a target company
- Use LLM to select the best business email
- Store structured lead data in SQLite
- Export leads to Excel
- Support email template rendering
- SMTP email sending support
- Designed for local Windows execution and future exe packaging

## Tech Stack

- Python
- SQLite
- SerpAPI
- Requests
- BeautifulSoup
- OpenAI-compatible LLM API
- OpenPyXL
- SMTP

## Project Structure

```text
project/
├── main.py
├── config.py
├── database.py
├── search.py
├── crawler.py
├── llm_analyzer.py
├── template.py
├── mailer.py
├── exporter.py
├── requirements.txt
├── .gitignore
└── data/
