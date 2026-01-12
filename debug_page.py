#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import re

url = 'https://ahri8-2025-10-01-yhhmc.monster/readOnline2.php?ID=154788'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

session = requests.Session()
session.headers.update(headers)

# 允许重定向
response = session.get(url, timeout=30, allow_redirects=True)
print(f'Status: {response.status_code}')
print(f'Final URL: {response.url}')
print(f'HTML length: {len(response.text)}')

html = response.text

# 保存HTML
with open('debug_page.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML saved to debug_page.html')

# 查找 show_image_area
soup = BeautifulSoup(html, 'html.parser')
show_area = soup.find(id='show_image_area') or soup.find(class_=re.compile(r'show_image_area', re.IGNORECASE))
print(f'\nshow_image_area found: {show_area is not None}')

if show_area:
    print(f'show_image_area content length: {len(str(show_area))}')
    # 查找 read_online_image_*
    read_images = show_area.find_all(id=re.compile(r'read_online_image_\d+', re.IGNORECASE))
    print(f'Found {len(read_images)} read_online_image_* elements')
    for i, elem in enumerate(read_images[:5]):
        print(f'  {i+1}. id={elem.get("id")}, tag={elem.name}')

# 查找所有包含 read_online_image 的内容
all_read_images = re.findall(r'read_online_image[^\s"\'<>]*', html, re.IGNORECASE)
print(f'\nAll read_online_image matches in HTML: {len(all_read_images)}')
if all_read_images:
    print('First 10:', all_read_images[:10])

# 查找所有包含 show_image 的内容
all_show_images = re.findall(r'show_image[^\s"\'<>]*', html, re.IGNORECASE)
print(f'\nAll show_image matches in HTML: {len(all_show_images)}')
if all_show_images:
    print('First 10:', all_show_images[:10])

# 检查是否有 HTTP_IMAGE 和 Original_Image_List
http_image = re.search(r'var HTTP_IMAGE = "([^"]+)";', html)
if http_image:
    print(f'\nFound HTTP_IMAGE: {http_image.group(1)}')

image_list = re.search(r'Original_Image_List\s*=\s*(\[.*?\]);', html, re.DOTALL)
if image_list:
    print(f'Found Original_Image_List (length: {len(image_list.group(1))})')

