#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从页面中提取图片信息
"""

import re
import json

with open('page_content.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取 HTTP_IMAGE
http_image_match = re.search(r'var HTTP_IMAGE = "([^"]+)";', content)
if http_image_match:
    http_image = http_image_match.group(1)
    print(f"HTTP_IMAGE: {http_image}")
else:
    print("HTTP_IMAGE not found")

# 提取 Original_Image_List
# 尝试多种模式
patterns = [
    r'Original_Image_List\s*=\s*(\[.*?\]);',
    r'Original_Image_List\s*=\s*(\{[^}]*\});',
    r'Original_Image_List\s*=\s*(\[.*?\]);',
]

for pattern in patterns:
    match = re.search(pattern, content, re.DOTALL)
    if match:
        try:
            image_list_str = match.group(1)
            print(f"\n找到 Original_Image_List (长度: {len(image_list_str)})")
            print(f"前200字符: {image_list_str[:200]}")
            
            # 尝试解析为 JSON
            try:
                image_list = json.loads(image_list_str)
                print(f"\n成功解析为 JSON，包含 {len(image_list)} 个图片")
                for i, img in enumerate(image_list[:5], 1):
                    print(f"  图片 {i}: {img}")
            except:
                print("无法解析为 JSON，尝试手动提取...")
                # 手动提取每个图片对象
                img_objects = re.findall(r'\{"sort":"(\d+)","comic_id":"(\d+)","ext_path_folder":"([^"]*)","new_filename":"([^"]+)","extension":"([^"]+)","version":"([^"]+)"\}', image_list_str)
                print(f"找到 {len(img_objects)} 个图片对象")
                for i, img_obj in enumerate(img_objects[:5], 1):
                    sort, comic_id, ext_path, filename, ext, version = img_obj
                    print(f"  图片 {i}: sort={sort}, filename={filename}, extension={ext}")
                    print(f"    URL: {http_image}{filename}_w900.{ext}")
        except Exception as e:
            print(f"解析错误: {e}")
        break

# 如果上面的方法不行，尝试直接搜索图片对象
if not match:
    print("\n尝试直接搜索图片对象...")
    img_objects = re.findall(r'\{"sort":"(\d+)","comic_id":"(\d+)","ext_path_folder":"([^"]*)","new_filename":"([^"]+)","extension":"([^"]+)","version":"([^"]+)"\}', content)
    print(f"找到 {len(img_objects)} 个图片对象")
    if img_objects:
        print("\n前5个图片:")
        for i, img_obj in enumerate(img_objects[:5], 1):
            sort, comic_id, ext_path, filename, ext, version = img_obj
            print(f"  图片 {i}: sort={sort}, filename={filename}, extension={ext}")
            if http_image_match:
                print(f"    URL: {http_image_match.group(1)}{filename}_w900.{ext}")

