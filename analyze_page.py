#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析 readOnline2.php 页面的 JavaScript 代码
"""

import requests
from bs4 import BeautifulSoup
import re
import json

url = "https://ahri8-2025-10-01-yhhmc.monster/readOnline2.php?ID=157100&host_id=0"

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
})

print("正在获取页面...")
response = session.get(url, timeout=30)
response.raise_for_status()
html_content = response.text

print(f"页面大小: {len(html_content)} 字符")
print("\n" + "="*80)
print("查找所有 <script> 标签")
print("="*80)

soup = BeautifulSoup(html_content, 'html.parser')
scripts = soup.find_all('script')

for i, script in enumerate(scripts, 1):
    script_content = script.string or ""
    if script_content:
        print(f"\n--- Script {i} ({len(script_content)} 字符) ---")
        # 查找包含图片相关的关键词
        keywords = ['img', 'image', 'cimg-lux', 'thumbnail', '157100', 'w900', 'jpg', 'png']
        if any(keyword.lower() in script_content.lower() for keyword in keywords):
            print("包含图片相关关键词！")
            # 显示前500个字符
            print(script_content[:500])
            if len(script_content) > 500:
                print("...")
                print(script_content[-500:])

print("\n" + "="*80)
print("查找所有包含 img.cimg-lux.top 的内容")
print("="*80)

# 查找所有包含 img.cimg-lux.top 的行
for line_num, line in enumerate(html_content.split('\n'), 1):
    if 'img.cimg-lux.top' in line.lower() or 'cimg-lux' in line.lower():
        print(f"行 {line_num}: {line[:200]}")

print("\n" + "="*80)
print("查找 Base64 或加密字符串")
print("="*80)

# 查找可能的 Base64 字符串
base64_pattern = r'[A-Za-z0-9+/=]{30,}'
matches = re.findall(base64_pattern, html_content)
for i, match in enumerate(matches[:10], 1):  # 只显示前10个
    print(f"{i}. {match[:50]}... (长度: {len(match)})")

print("\n" + "="*80)
print("查找 JavaScript 变量定义")
print("="*80)

# 查找可能的图片列表变量
js_patterns = [
    r'var\s+(\w+)\s*=\s*\[(.*?)\]',
    r'let\s+(\w+)\s*=\s*\[(.*?)\]',
    r'const\s+(\w+)\s*=\s*\[(.*?)\]',
    r'(\w+)\s*[:=]\s*\[(.*?)\]',
]

for pattern in js_patterns:
    matches = re.finditer(pattern, html_content, re.DOTALL | re.IGNORECASE)
    for match in matches:
        var_name = match.group(1)
        var_content = match.group(2)
        if 'img' in var_name.lower() or 'image' in var_name.lower() or 'pic' in var_name.lower():
            print(f"变量: {var_name}")
            print(f"内容: {var_content[:200]}...")
            print()

print("\n" + "="*80)
print("保存完整 HTML 到文件")
print("="*80)

with open('page_content.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
print("已保存到 page_content.html")

