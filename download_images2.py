#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用网站图片下载工具
自动下载指定网页中的所有图片，支持任意网站，自动识别图片URL并过滤掉.ico文件和图标文件。
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import re
import time
import os
import sys
from pathlib import Path
from typing import List, Set, Optional, Dict
import logging
import zipfile

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 支持的图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}

# 需要跳过的文件名模式
SKIP_PATTERNS = [
    r'\.ico$',
    r'blank\.gif',
    r'touch-icon',
    r'favicon',
    r'icon\.png',
    r'logo\.',
]

# 需要跳过的文件名（完整匹配）
SKIP_FILENAMES = [
    'ipad-landscape.png',
    'ipad-portrait.png',
    'iphone.png',
    'sunny.png',
    'sunny_1.png',
]


class ImageDownloader:
    """图片下载器"""
    
    def __init__(self, base_url: str, save_dir: str = './downloaded_images2', delay: float = 0.5, verbose: bool = False, create_zip: bool = False):
        """
        初始化下载器
        
        Args:
            base_url: 目标网页URL
            save_dir: 保存目录基础路径
            delay: 下载延迟（秒）
            verbose: 是否显示详细日志
            create_zip: 下载完成后是否压缩文件夹（默认: False）
        """
        self.base_url = base_url
        self.save_dir = save_dir
        self.delay = delay
        self.verbose = verbose
        self.create_zip = create_zip
        
        # 设置日志级别
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # 创建 requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        
        # 统计信息
        self.stats = {
            'success': 0,
            'failed': 0,
            'skipped': 0,
        }
        
        # 图片信息列表（用于重命名）
        self.image_info_list: List[Dict] = []
    
    def is_ico_file(self, url: str) -> bool:
        """
        检查是否为.ico文件
        
        Args:
            url: 图片URL
            
        Returns:
            是否为.ico文件
        """
        url_lower = url.lower()
        return url_lower.endswith('.ico') or '.ico?' in url_lower
    
    def should_skip_file(self, url: str) -> bool:
        """
        检查是否应该跳过（图标文件等）
        
        Args:
            url: 图片URL
            
        Returns:
            是否应该跳过
        """
        url_lower = url.lower()
        
        # 检查.ico文件
        if self.is_ico_file(url):
            return True
        
        # 检查跳过模式
        for pattern in SKIP_PATTERNS:
            if re.search(pattern, url_lower, re.IGNORECASE):
                return True
        
        # 检查需要跳过的文件名
        for filename in SKIP_FILENAMES:
            filename_lower = filename.lower()
            # 提取URL中的文件名部分
            parsed = urlparse(url)
            path_filename = os.path.basename(parsed.path)
            # 检查路径中的文件名是否匹配
            if path_filename.lower() == filename_lower:
                return True
            # 也检查URL中是否包含该文件名（作为路径的一部分）
            if f'/{filename_lower}' in url_lower or f'\\{filename_lower}' in url_lower:
                return True
        
        return False
    
    def extract_image_list_from_js(self, html_content: str) -> List[Dict]:
        """
        从JavaScript中提取图片列表（特定网站）
        
        Args:
            html_content: HTML内容
            
        Returns:
            图片信息列表，每个元素包含 url 和可选的 sort
        """
        images = []
        
        # 方法1: 尝试匹配常见的JavaScript图片数组格式
        patterns = [
            r'imageList\s*[:=]\s*\[(.*?)\]',
            r'images\s*[:=]\s*\[(.*?)\]',
            r'imgList\s*[:=]\s*\[(.*?)\]',
            r'var\s+imgs\s*=\s*\[(.*?)\]',
            r'imageArray\s*[:=]\s*\[(.*?)\]',
            r'picList\s*[:=]\s*\[(.*?)\]',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, html_content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                content = match.group(1)
                # 提取URL
                url_matches = re.findall(r'["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|svg))["\']', content, re.IGNORECASE)
                for url in url_matches:
                    if not self.should_skip_file(url):
                        images.append({'url': url, 'sort': None})
        
        # 方法2: 直接从HTML中搜索所有图片URL模式（包括JavaScript中的）
        # 匹配各种格式的图片URL
        url_patterns = [
            r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"\']*)?',
            r'/[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^\s<>"\']*)?',
            r'["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^"\']*)?)["\']',
        ]
        
        for pattern in url_patterns:
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for match in matches:
                url = match.group(1) if match.groups() else match.group(0)
                # 清理URL（移除引号等）
                url = url.strip('"\'')
                if url and not self.should_skip_file(url):
                    # 检查是否已经添加过
                    if not any(img['url'] == url for img in images):
                        images.append({'url': url, 'sort': None})
        
        # 方法3: 匹配 img.cimg-lux.top 格式的图片URL
        # 格式: https://img.cimg-lux.top/comic/thumbnail/158000/d-{ID}/{hash}_w900.jpg
        # 先尝试精确匹配
        cimg_patterns = [
            r'https?://img\.cimg-lux\.top/comic/thumbnail/\d+/d-\d+/[a-zA-Z0-9_]+_w\d+\.(?:jpg|jpeg|png|gif|webp|bmp)',
            r'img\.cimg-lux\.top/comic/thumbnail/\d+/d-\d+/[a-zA-Z0-9_]+_w\d+\.(?:jpg|jpeg|png|gif|webp|bmp)',
            r'["\'](https?://img\.cimg-lux\.top/comic/thumbnail/\d+/d-\d+/[^"\']+\.(?:jpg|jpeg|png|gif|webp|bmp))["\']',
            r'["\'](img\.cimg-lux\.top/comic/thumbnail/\d+/d-\d+/[^"\']+\.(?:jpg|jpeg|png|gif|webp|bmp))["\']',
        ]
        
        for pattern in cimg_patterns:
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for match in matches:
                url = match.group(1) if match.groups() else match.group(0)
                url = url.strip('"\'')
                if url and not url.startswith('http'):
                    url = 'https://' + url
                # 确保URL以图片扩展名结尾
                if url and any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                    if not self.should_skip_file(url):
                        if not any(img['url'] == url for img in images):
                            images.append({'url': url, 'sort': None})
        
        # 如果精确匹配没找到，尝试更宽泛的匹配（匹配所有包含 img.cimg-lux.top 的URL）
        if not images:
            broad_pattern = r'https?://img\.cimg-lux\.top/[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|svg)'
            broad_matches = re.findall(broad_pattern, html_content, re.IGNORECASE)
            for url in broad_matches:
                if not self.should_skip_file(url):
                    if not any(img['url'] == url for img in images):
                        images.append({'url': url, 'sort': None})
        
        return images
    
    def extract_image_base_url(self, html_content: str) -> Optional[str]:
        """
        提取图片基础URL（特定网站）
        
        Args:
            html_content: HTML内容
            
        Returns:
            基础URL，如果没有则返回None
        """
        # 尝试从JavaScript中提取base URL
        patterns = [
            r'baseUrl\s*[:=]\s*["\']([^"\']+)["\']',
            r'base_url\s*[:=]\s*["\']([^"\']+)["\']',
            r'imageBase\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def detect_next_page(self, html_content: str, base_url: str) -> Optional[int]:
        """
        检测是否有下一页图片需要加载
        
        Args:
            html_content: HTML内容
            base_url: 基础URL
            
        Returns:
            下一页的页码，如果没有则返回None
        """
        # 尝试从JavaScript中提取总页数和当前页数
        # 常见模式：totalPages, currentPage, pageCount等
        patterns = [
            r'var\s+totalPages\s*=\s*(\d+);',
            r'var\s+currentPage\s*=\s*(\d+);',
            r'var\s+pageCount\s*=\s*(\d+);',
            r'totalPages\s*[:=]\s*(\d+)',
            r'currentPage\s*[:=]\s*(\d+)',
            r'pageCount\s*[:=]\s*(\d+)',
        ]
        
        current_page = 1
        total_pages = None
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                if 'total' in pattern.lower() or 'count' in pattern.lower():
                    total_pages = value
                elif 'current' in pattern.lower():
                    current_page = value
        
        # 如果有总页数且当前页小于总页数，返回下一页
        if total_pages and current_page < total_pages:
            return current_page + 1
        
        # 尝试从Original_Image_List的长度和已显示的图片数量来判断
        # 如果页面有"加载更多"按钮，可能还有更多图片
        soup = BeautifulSoup(html_content, 'html.parser')
        load_more_patterns = [
            soup.find(string=re.compile(r'加载更多|下一页|更多图片|load more', re.IGNORECASE)),
            soup.find('button', string=re.compile(r'加载更多|下一页|更多图片|load more', re.IGNORECASE)),
            soup.find('a', string=re.compile(r'加载更多|下一页|更多图片|load more', re.IGNORECASE)),
        ]
        
        if any(load_more_patterns):
            # 如果找到"加载更多"按钮，假设还有下一页
            # 尝试从当前页数推断下一页
            parsed = urlparse(base_url)
            query = parse_qs(parsed.query)
            page_param = query.get('page', ['1'])[0]
            try:
                current_page = int(page_param)
                return current_page + 1
            except (ValueError, TypeError):
                return 2  # 默认返回第2页
        
        return None
    
    def load_next_page_images(self, base_url: str, next_page: int) -> Optional[str]:
        """
        加载下一页的HTML内容
        
        Args:
            base_url: 基础URL
            next_page: 下一页页码
            
        Returns:
            下一页的HTML内容，如果失败则返回None
        """
        try:
            # 构建下一页URL（添加或修改page参数）
            parsed = urlparse(base_url)
            query = parse_qs(parsed.query)
            query['page'] = [str(next_page)]
            new_query = '&'.join([f"{k}={v[0]}" for k, v in query.items()])
            next_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
            
            logger.info(f"正在加载第 {next_page} 页: {next_url}")
            response = self.session.get(next_url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            logger.debug(f"最终URL: {response.url}")
            
            return response.text
        except Exception as e:
            logger.warning(f"加载第 {next_page} 页失败: {e}")
            return None
    
    def extract_image_urls(self, html_content: str, base_url: str) -> List[Dict]:
        """
        从HTML中提取图片URL（通用方法）
        
        Args:
            html_content: HTML内容
            base_url: 基础URL
            
        Returns:
            图片信息列表，每个元素包含 url 和可选的 sort
        """
        images = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 新增方法: 针对 show_image_area 和 read_online_image_* 格式的支持
        # 查找 show_image_area 元素，然后提取其中的 read_online_image_1 到 read_online_image_10
        show_image_area = soup.find(id='show_image_area') or soup.find(class_=re.compile(r'show_image_area', re.IGNORECASE))
        if show_image_area:
            logger.info("找到 show_image_area 元素，开始提取 read_online_image_* 图片")
            # 在 show_image_area 中查找所有 read_online_image_* 元素
            # 支持多种可能的格式：id、class、data属性等
            image_elements = []
            
            # 方法1: 通过id属性查找 (read_online_image_1, read_online_image_2, ...)
            for i in range(1, 100):  # 最多查找100个
                elem = show_image_area.find(id=f'read_online_image_{i}') or show_image_area.find(id=f'read_online_image_{i:02d}')
                if elem:
                    image_elements.append((i, elem))
                else:
                    # 如果连续找不到，可能已经到末尾了
                    if i > 10 and not image_elements:
                        break
            
            # 方法2: 如果方法1没找到，尝试通过正则查找所有包含 read_online_image_ 的元素
            if not image_elements:
                all_elements = show_image_area.find_all(id=re.compile(r'read_online_image_\d+', re.IGNORECASE))
                for elem in all_elements:
                    id_attr = elem.get('id', '')
                    num_match = re.search(r'read_online_image_(\d+)', id_attr, re.IGNORECASE)
                    if num_match:
                        num = int(num_match.group(1))
                        image_elements.append((num, elem))
            
            # 方法3: 通过img标签的src属性查找（如果read_online_image_*是img标签）
            if not image_elements:
                img_tags = show_image_area.find_all('img', id=re.compile(r'read_online_image_\d+', re.IGNORECASE))
                for img in img_tags:
                    id_attr = img.get('id', '')
                    num_match = re.search(r'read_online_image_(\d+)', id_attr, re.IGNORECASE)
                    if num_match:
                        num = int(num_match.group(1))
                        image_elements.append((num, img))
            
            # 方法4: 通过data属性或其他属性查找
            if not image_elements:
                all_elements = show_image_area.find_all(attrs={'data-image-id': re.compile(r'read_online_image_\d+', re.IGNORECASE)})
                for elem in all_elements:
                    data_id = elem.get('data-image-id', '')
                    num_match = re.search(r'read_online_image_(\d+)', data_id, re.IGNORECASE)
                    if num_match:
                        num = int(num_match.group(1))
                        image_elements.append((num, elem))
            
            # 如果找到了元素，提取图片URL
            if image_elements:
                # 按编号排序
                image_elements.sort(key=lambda x: x[0])
                logger.info(f"找到 {len(image_elements)} 个 read_online_image_* 元素")
                
                temp_images = []
                for num, elem in image_elements:
                    # 尝试从多个可能的属性中提取图片URL
                    img_url = None
                    
                    # 优先从src属性提取（如果是img标签）
                    if elem.name == 'img':
                        img_url = elem.get('src') or elem.get('data-src') or elem.get('data-url')
                    else:
                        # 如果不是img标签，尝试从子元素中查找img标签
                        img_tag = elem.find('img')
                        if img_tag:
                            img_url = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-url')
                        else:
                            # 尝试从style属性中提取background-image
                            style = elem.get('style', '')
                            bg_match = re.search(r'background-image\s*:\s*url\(["\']?([^"\'()]+)["\']?\)', style, re.IGNORECASE)
                            if bg_match:
                                img_url = bg_match.group(1)
                            else:
                                # 尝试从data属性中提取
                                img_url = elem.get('data-src') or elem.get('data-url') or elem.get('data-image')
                    
                    if img_url:
                        # 转换为绝对URL
                        absolute_url = urljoin(base_url, img_url)
                        if not self.should_skip_file(absolute_url):
                            temp_images.append({
                                'url': absolute_url,
                                'sort': num,  # 使用编号作为排序值
                                'display_index': num - 1  # 从0开始的索引
                            })
                            logger.debug(f"  提取图片 {num}: {absolute_url[:80]}...")
                
                if temp_images:
                    logger.info(f"从 show_image_area 提取到 {len(temp_images)} 张图片，按 read_online_image_* 顺序")
                    return temp_images
            else:
                logger.warning("在 show_image_area 中未找到 read_online_image_* 元素")
        
        # 优先方法: 针对 cimg-lux.top 的特殊处理
        # 从 readOnline2.php 页面提取 HTTP_IMAGE 和 Original_Image_List
        # 这个方法优先级最高，因为它能提供准确的sort信息
        parsed_base = urlparse(base_url)
        query = parse_qs(parsed_base.query)
        comic_id = query.get('ID', [''])[0]
        
        if comic_id and 'readonline2.php' in base_url.lower():
            # 提取 HTTP_IMAGE
            http_image_match = re.search(r'var HTTP_IMAGE = "([^"]+)";', html_content)
            if http_image_match:
                http_image = http_image_match.group(1)
                logger.debug(f"找到 HTTP_IMAGE: {http_image}")
                
                # 提取 Original_Image_List (JSON数组)
                image_list_patterns = [
                    r'Original_Image_List\s*=\s*(\[.*?\]);',
                    r'Original_Image_List\s*=\s*(\{[^}]*\});',
                ]
                
                image_list_str = None
                for pattern in image_list_patterns:
                    match = re.search(pattern, html_content, re.DOTALL)
                    if match:
                        image_list_str = match.group(1)
                        break
                
                if image_list_str:
                    try:
                        import json
                        image_list = json.loads(image_list_str)
                        logger.info(f"成功解析 Original_Image_List，包含 {len(image_list)} 个图片")
                        
                        # 构建图片URL列表（按数组索引顺序，即页面显示顺序）
                        temp_images = []
                        for idx, img_info in enumerate(image_list):
                            if isinstance(img_info, dict):
                                new_filename = img_info.get('new_filename', '')
                                extension = img_info.get('extension', 'jpg')
                                
                                if new_filename:
                                    # 构建完整URL: HTTP_IMAGE + new_filename + "_w900." + extension
                                    image_url = f"{http_image}{new_filename}_w900.{extension}"
                                    
                                    if not self.should_skip_file(image_url):
                                        # 直接使用数组索引+1作为排序值（从1开始），保持页面显示顺序
                                        # 数组的顺序就是页面显示的顺序
                                        display_order = idx + 1
                                        temp_images.append({
                                            'url': image_url, 
                                            'sort': display_order,
                                            'display_index': idx  # 保存原始索引用于调试
                                        })
                        
                        # 如果成功提取到图片，按数组索引顺序返回（不再从其他地方提取）
                        # 数组已经是按页面显示顺序排列的，不需要再排序
                        if temp_images:
                            logger.info(f"从 Original_Image_List 提取到 {len(temp_images)} 张图片，按页面显示顺序（数组索引）")
                            # 输出前几个图片的信息用于调试
                            logger.info(f"前10张图片的显示顺序和URL:")
                            for i, img in enumerate(temp_images[:10]):
                                # 提取文件名用于匹配
                                filename_match = re.search(r'/([^/]+_w\d+\.(?:jpg|jpeg|png|gif|webp|bmp))', img['url'])
                                filename = filename_match.group(1) if filename_match else img['url'][-30:]
                                logger.info(f"  图片 {i+1}: 显示顺序={img.get('sort')}, 数组索引={img.get('display_index')}, filename={filename}")
                            return temp_images
                            
                    except json.JSONDecodeError:
                        logger.warning("无法解析 Original_Image_List 为 JSON")
                        # 如果JSON解析失败，尝试正则提取
                        img_objects = re.findall(
                            r'\{"sort":"(\d+)","comic_id":"(\d+)","ext_path_folder":"([^"]*)","new_filename":"([^"]+)","extension":"([^"]+)","version":"([^"]+)"\}',
                            image_list_str
                        )
                        if img_objects and http_image_match:
                            temp_images = []
                            # 按数组索引顺序（页面显示顺序）提取
                            for idx, (sort, comic_id_val, ext_path, filename, ext, version) in enumerate(img_objects):
                                image_url = f"{http_image}{filename}_w900.{ext}"
                                if not self.should_skip_file(image_url):
                                    # 直接使用数组索引+1作为排序值（从1开始），保持页面显示顺序
                                    display_order = idx + 1
                                    temp_images.append({
                                        'url': image_url, 
                                        'sort': display_order,
                                        'display_index': idx
                                    })
                            
                            # 如果成功提取到图片，按数组索引顺序返回（已经是正确顺序，不需要排序）
                            if temp_images:
                                logger.info(f"从 Original_Image_List 提取到 {len(temp_images)} 张图片（正则方式），按页面显示顺序（数组索引）")
                                return temp_images
            
            # 也尝试匹配已有的 img.cimg-lux.top URL（作为备用）
            cimg_url_pattern = r'https?://img\.cimg-lux\.top/comic/thumbnail/\d+/d-\d+/[a-zA-Z0-9_]+_w\d+\.(?:jpg|jpeg|png|gif|webp|bmp)'
            cimg_matches = re.findall(cimg_url_pattern, html_content, re.IGNORECASE)
            for url in cimg_matches:
                if not self.should_skip_file(url):
                    if not any(img['url'] == url for img in images):
                        images.append({'url': url, 'sort': None})
        
        # 方法1: 从img标签提取
        for img in soup.find_all('img', src=True):
            src = img.get('src', '')
            if src:
                absolute_url = urljoin(base_url, src)
                if not self.should_skip_file(absolute_url):
                    # 尝试提取sort信息
                    sort = None
                    if img.get('data-sort'):
                        try:
                            sort = int(img.get('data-sort'))
                        except (ValueError, TypeError):
                            pass
                    images.append({'url': absolute_url, 'sort': sort})
        
        # 方法2: 从CSS背景图片提取
        for element in soup.find_all(style=True):
            style = element.get('style', '')
            # 匹配 background-image: url(...)
            matches = re.findall(r'background-image\s*:\s*url\(["\']?([^"\'()]+)["\']?\)', style, re.IGNORECASE)
            for match in matches:
                absolute_url = urljoin(base_url, match)
                if not self.should_skip_file(absolute_url):
                    images.append({'url': absolute_url, 'sort': None})
        
        # 方法3: 从JavaScript代码中提取
        js_images = self.extract_image_list_from_js(html_content)
        for img_info in js_images:
            absolute_url = urljoin(base_url, img_info['url'])
            if not self.should_skip_file(absolute_url):
                images.append({'url': absolute_url, 'sort': img_info.get('sort')})
        
        # 方法4: 从JavaScript中提取base URL，然后尝试构建图片URL
        image_base_url = self.extract_image_base_url(html_content)
        if image_base_url:
            # 尝试从JavaScript中提取图片编号
            number_matches = re.findall(r'imageList\[(\d+)\]', html_content, re.IGNORECASE)
            for num in number_matches:
                # 尝试构建图片URL（常见模式）
                num_int = int(num)
                possible_urls = [
                    f"{image_base_url}/{num}.jpg",
                    f"{image_base_url}/{num}.png",
                    f"{image_base_url}/{num_int:04d}.jpg",
                    f"{image_base_url}/{num_int:04d}.png",
                    f"{image_base_url}/{num_int:03d}.jpg",
                    f"{image_base_url}/{num_int:03d}.png",
                ]
                for url in possible_urls:
                    absolute_url = urljoin(base_url, url)
                    if not self.should_skip_file(absolute_url):
                        try:
                            sort = int(num)
                            images.append({'url': absolute_url, 'sort': sort})
                        except (ValueError, TypeError):
                            images.append({'url': absolute_url, 'sort': None})
        
        # 方法5: 从data属性中提取图片URL
        for element in soup.find_all(attrs={'data-src': True}):
            src = element.get('data-src', '')
            if src:
                absolute_url = urljoin(base_url, src)
                if not self.should_skip_file(absolute_url):
                    sort = None
                    if element.get('data-sort'):
                        try:
                            sort = int(element.get('data-sort'))
                        except (ValueError, TypeError):
                            pass
                    images.append({'url': absolute_url, 'sort': sort})
        
        # 方法6: 从data-url、data-image等属性提取
        data_attrs = ['data-url', 'data-image', 'data-img', 'data-pic', 'data-srcset']
        for attr in data_attrs:
            for element in soup.find_all(attrs={attr: True}):
                src = element.get(attr, '')
                if src:
                    # 处理srcset格式（可能包含多个URL）
                    if ',' in src:
                        src = src.split(',')[0].strip().split()[0]
                    absolute_url = urljoin(base_url, src)
                    if not self.should_skip_file(absolute_url):
                        images.append({'url': absolute_url, 'sort': None})
        
        # 去重：优先保留有sort信息的版本
        url_dict = {}  # key: url, value: img_info
        for img_info in images:
            url = img_info['url']
            if url not in url_dict:
                # 第一次遇到这个URL，直接添加
                url_dict[url] = img_info
            else:
                # URL已存在，检查是否有sort信息
                existing_sort = url_dict[url].get('sort')
                new_sort = img_info.get('sort')
                # 如果新版本有sort而旧版本没有，或者两者都有sort但新版本的sort更小（更靠前），则替换
                if new_sort is not None and (existing_sort is None or new_sort < existing_sort):
                    url_dict[url] = img_info
        
        unique_images = list(url_dict.values())
        
        # 如果有sort信息，按sort排序；否则保持原始顺序
        has_any_sort = any(img.get('sort') is not None for img in unique_images)
        if has_any_sort:
            # 按sort排序，确保所有图片都按正确的顺序排列
            # 有sort的按sort值排序，没有sort的放在最后（按原始顺序）
            unique_images.sort(key=lambda x: (
                x.get('sort') is None,  # 有sort的排在前面（False < True）
                x.get('sort') if x.get('sort') is not None else float('inf')  # 按sort值排序
            ))
            logger.debug(f"按sort排序完成，共 {len(unique_images)} 张图片")
            # 输出前几个图片的sort值用于调试
            if logger.level <= logging.DEBUG:
                for i, img in enumerate(unique_images[:5]):
                    logger.debug(f"  图片 {i+1}: sort={img.get('sort')}, url={img['url'][:60]}...")
        
        return unique_images
    
    def download_image(self, url: str, filename: str) -> bool:
        """
        下载单张图片
        
        Args:
            url: 图片URL
            filename: 保存的文件名
            
        Returns:
            是否成功
        """
        try:
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            # 检查Content-Type
            content_type = response.headers.get('Content-Type', '').lower()
            if not any(ext in content_type for ext in ['image', 'jpeg', 'jpg', 'png', 'gif', 'webp', 'bmp', 'svg']):
                logger.warning(f"  跳过非图片文件: {url} (Content-Type: {content_type})")
                return False
            
            # 保存文件
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(filename)
            logger.debug(f"  下载成功: {filename} ({file_size:,} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"  下载失败 {url}: {e}")
            # 如果文件已创建但下载失败，删除它
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except:
                    pass
            return False
    
    def get_save_directory(self) -> Path:
        """
        获取保存目录
        
        Returns:
            保存目录Path对象
        """
        # 从URL中提取ID
        parsed = urlparse(self.base_url)
        query = parse_qs(parsed.query)
        comic_id = query.get('ID', [''])[0]
        
        if comic_id:
            # 使用ID作为目录名
            save_dir = Path(self.save_dir) / comic_id
        else:
            # 如果没有ID，使用URL的路径部分
            path_part = parsed.path.strip('/').replace('/', '_')
            if not path_part:
                path_part = 'images'
            save_dir = Path(self.save_dir) / path_part
        
        return save_dir
    
    def download_all_images(self, image_urls: List[Dict], start_index: int = 1) -> None:
        """
        批量下载图片（下载时直接使用重命名后的文件名）
        
        Args:
            image_urls: 图片URL列表，每个元素包含 url 和可选的 sort
            start_index: 起始编号（从1开始），用于连续编号多页图片
        """
        if not image_urls:
            logger.warning("没有找到图片URL")
            return
        
        save_dir = self.get_save_directory()
        save_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"保存目录: {save_dir}")
        logger.info(f"开始下载 {len(image_urls)} 张图片...")
        logger.info("-" * 80)
        
        # 先清理可能存在的旧编号文件（001.jpg, 002.jpg 等格式）
        pattern = re.compile(r'^\d{3}\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
        cleaned_count = 0
        for existing_file in save_dir.iterdir():
            if existing_file.is_file() and pattern.match(existing_file.name):
                try:
                    existing_file.unlink()
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"清理旧文件失败 {existing_file.name}: {e}")
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个旧编号文件")
        
        # 检查是否有sort信息，如果有则按sort排序
        has_sort = any(img.get('sort') is not None for img in image_urls)
        if has_sort:
            # 按sort排序，确保顺序正确
            # 有sort的按sort值排序，没有sort的放在最后（按原始顺序）
            files_with_index = [(i, img) for i, img in enumerate(image_urls)]
            sorted_files_with_index = sorted(
                files_with_index,
                key=lambda x: (
                    x[1].get('sort') is None,  # 有sort的排在前面（False < True）
                    x[1].get('sort') if x[1].get('sort') is not None else float('inf'),  # 按sort值排序
                    x[0]  # 如果sort相同或都没有sort，按原始索引排序
                )
            )
            sorted_image_urls = [img for _, img in sorted_files_with_index]
            logger.info(f"按sort排序完成，共 {len(sorted_image_urls)} 张图片")
            # 输出前几个图片的sort值用于调试
            if logger.level <= logging.DEBUG:
                for i, img in enumerate(sorted_image_urls[:5]):
                    logger.debug(f"  排序后 {i+1}: sort={img.get('sort')}, url={img['url'][:60]}...")
        else:
            # 没有sort信息，保持原始顺序
            logger.info(f"未找到sort信息，保持原始顺序，共 {len(image_urls)} 张图片")
            sorted_image_urls = image_urls
        
        # 下载图片，直接使用重命名后的文件名
        downloaded_files = []
        
        for idx, img_info in enumerate(sorted_image_urls):
            i = start_index + idx  # 实际编号
            url = img_info['url']
            logger.info(f"[{i:03d}/{len(sorted_image_urls)}] 正在下载: {url[:80]}...")
            
            # 获取文件扩展名（优先从URL推断）
            ext = '.jpg'  # 默认扩展名
            url_ext_match = re.search(r'\.(jpg|jpeg|png|gif|webp|bmp|svg)', url, re.IGNORECASE)
            if url_ext_match:
                ext = '.' + url_ext_match.group(1).lower()
            
            # 直接使用重命名后的文件名：001.jpg, 002.jpg 等
            new_filename = f"{i:03d}{ext}"
            filepath = save_dir / new_filename
            
            # 如果文件已存在，跳过下载
            if filepath.exists():
                file_size = os.path.getsize(filepath)
                self.stats['skipped'] += 1
                downloaded_files.append({
                    'filepath': filepath,
                    'sort': img_info.get('sort'),
                    'original_url': url
                })
                logger.info(f"⊘ [{i}] 跳过已存在文件: {new_filename} ({file_size:,} bytes)")
                continue
            
            # 下载图片
            if self.download_image(url, str(filepath)):
                self.stats['success'] += 1
                downloaded_files.append({
                    'filepath': filepath,
                    'sort': img_info.get('sort'),
                    'original_url': url
                })
                logger.info(f"✓ [{i}] 下载成功: {new_filename}")
            else:
                self.stats['failed'] += 1
                logger.error(f"✗ [{i}] 下载失败")
            
            # 下载延迟
            if i < len(sorted_image_urls) and self.delay > 0:
                time.sleep(self.delay)
        
        logger.info(f"下载完成: 成功 {self.stats['success']} 张，失败 {self.stats['failed']} 张")
        self.image_info_list = downloaded_files
    
    def rename_images_by_sort(self, downloaded_files: List[Dict], save_dir: Path) -> None:
        """
        按顺序重命名图片（每个文件夹从001开始）
        
        Args:
            downloaded_files: 已下载的文件列表
            save_dir: 保存目录
        """
        if not downloaded_files:
            return
        
        logger.info("正在按顺序重命名图片...")
        logger.info(f"需要重命名的文件数量: {len(downloaded_files)}")
        
        # 先清理可能存在的旧编号文件（001.jpg, 002.jpg 等格式）
        # 只清理3位数字开头的文件，避免误删其他文件
        pattern = re.compile(r'^\d{3}\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
        cleaned_count = 0
        for existing_file in save_dir.iterdir():
            if existing_file.is_file() and pattern.match(existing_file.name):
                try:
                    existing_file.unlink()
                    cleaned_count += 1
                    logger.debug(f"清理旧文件: {existing_file.name}")
                except Exception as e:
                    logger.warning(f"清理旧文件失败 {existing_file.name}: {e}")
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个旧编号文件")
        
        # 检查是否有sort信息
        has_sort = any(f.get('sort') is not None for f in downloaded_files)
        
        if has_sort:
            # 按sort排序，没有sort的放在最后（按原始顺序）
            # 为每个文件添加原始索引，以便在没有sort时保持顺序
            files_with_index = [(i, f) for i, f in enumerate(downloaded_files)]
            sorted_files_with_index = sorted(
                files_with_index,
                key=lambda x: (
                    x[1].get('sort') is None,  # 有sort的排在前面
                    x[1].get('sort') if x[1].get('sort') is not None else float('inf'),  # 按sort值排序
                    x[0]  # 如果sort相同或都没有sort，按原始索引排序
                )
            )
            sorted_files = [f for _, f in sorted_files_with_index]
        else:
            # 没有sort信息，保持下载顺序（即列表顺序）
            sorted_files = downloaded_files
        
        # 临时目录，用于重命名
        temp_dir = save_dir / 'temp_rename'
        temp_dir.mkdir(exist_ok=True)
        
        # 先移动到临时目录
        temp_paths = []
        for f in sorted_files:
            try:
                original_path = f['filepath']
                # 确保是 Path 对象
                if isinstance(original_path, str):
                    original_path = Path(original_path)
                
                # 检查文件是否存在
                if not original_path.exists():
                    logger.warning(f"文件不存在，跳过: {original_path}")
                    temp_paths.append(None)
                    continue
                
                temp_path = temp_dir / f"temp_{original_path.name}"
                original_path.rename(temp_path)
                # 更新文件路径为临时路径
                f['filepath'] = temp_path
                temp_paths.append(temp_path)
                logger.debug(f"移动文件到临时目录: {original_path.name} -> {temp_path.name}")
            except Exception as e:
                logger.warning(f"移动文件失败 {f.get('filepath', 'unknown')}: {e}")
                temp_paths.append(None)
        
        # 重命名为新名称（从001开始：001.jpg, 002.jpg 等格式）
        renamed_count = 0
        skipped_count = 0
        for i, (f, temp_path) in enumerate(zip(sorted_files, temp_paths), 1):
            if temp_path is None or not temp_path.exists():
                logger.warning(f"跳过重命名，文件不存在: {f.get('filepath', 'unknown')}")
                skipped_count += 1
                continue
                
            try:
                # 获取原始扩展名（优先从原始URL推断）
                original_url = f.get('original_url', '')
                if original_url:
                    url_ext_match = re.search(r'\.(jpg|jpeg|png|gif|webp|bmp|svg)', original_url, re.IGNORECASE)
                    if url_ext_match:
                        ext = '.' + url_ext_match.group(1).lower()
                    else:
                        ext = temp_path.suffix or '.jpg'
                else:
                    ext = temp_path.suffix or '.jpg'
                
                # 使用3位数字格式：001, 002, 003...（从1开始）
                new_name = f"{i:03d}{ext}"
                new_path = save_dir / new_name
                
                # 如果新路径已存在（理论上不应该，因为已经清理过了），删除它
                if new_path.exists():
                    logger.warning(f"目标文件已存在，删除: {new_name}")
                    new_path.unlink()
                
                temp_path.rename(new_path)
                renamed_count += 1
                logger.info(f"重命名: {temp_path.name} -> {new_name}")
            except Exception as e:
                logger.error(f"重命名失败 {temp_path}: {e}")
                skipped_count += 1
        
        logger.info(f"重命名完成: 成功 {renamed_count} 个，跳过 {skipped_count} 个")
        
        # 删除临时目录
        try:
            temp_dir.rmdir()
        except:
            # 如果临时目录不为空，尝试删除其中的文件
            try:
                for file in temp_dir.iterdir():
                    file.unlink()
                temp_dir.rmdir()
            except:
                pass
    
    def rename_existing_files(self, save_dir: Path) -> None:
        """
        重命名已存在的文件（按文件名排序）
        
        Args:
            save_dir: 保存目录
        """
        if not save_dir.exists() or not save_dir.is_dir():
            logger.warning(f"目录不存在: {save_dir}")
            return
        
        # 获取所有图片文件（排除已重命名的文件）
        pattern_renamed = re.compile(r'^\d{3}\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
        image_files = []
        for file in save_dir.iterdir():
            if file.is_file() and not pattern_renamed.match(file.name):
                # 检查是否是图片文件
                if any(file.name.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    image_files.append(file)
        
        if not image_files:
            logger.info("没有需要重命名的文件")
            return
        
        logger.info(f"找到 {len(image_files)} 个需要重命名的文件")
        
        # 按文件名排序
        image_files.sort(key=lambda x: x.name)
        
        # 先清理可能存在的旧编号文件
        pattern = re.compile(r'^\d{3}\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
        cleaned_count = 0
        for existing_file in save_dir.iterdir():
            if existing_file.is_file() and pattern.match(existing_file.name):
                try:
                    existing_file.unlink()
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"清理旧文件失败 {existing_file.name}: {e}")
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个旧编号文件")
    
    def create_zip_file(self, folder_path: Path) -> None:
        """
        将文件夹压缩成zip文件
        
        Args:
            folder_path: 要压缩的文件夹路径
        """
        logger.info(f"准备压缩文件夹: {folder_path}")
        logger.info(f"文件夹绝对路径: {folder_path.absolute()}")
        
        if not folder_path.exists() or not folder_path.is_dir():
            logger.warning(f"文件夹不存在，无法压缩: {folder_path}")
            return
        
        # 检查文件夹中是否有文件
        files = [f for f in folder_path.iterdir() if f.is_file()]
        logger.info(f"文件夹中包含 {len(files)} 个文件")
        
        if not files:
            logger.warning(f"文件夹为空，跳过压缩: {folder_path}")
            return
        
        # 创建zip文件路径（格式：(ID).zip）
        # 从文件夹名提取ID（文件夹名就是ID）
        folder_id = folder_path.name
        zip_path = folder_path.parent / f"({folder_id}).zip"
        
        try:
            logger.info(f"开始压缩文件夹: {folder_path.name}")
            logger.info(f"压缩文件保存位置: {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 遍历文件夹中的所有文件
                for file_path in files:
                    # 使用相对路径作为zip内的文件名
                    arcname = file_path.name
                    zipf.write(file_path, arcname=arcname)
                    logger.debug(f"  已添加文件到压缩包: {arcname}")
            
            # 获取压缩文件大小
            zip_size = zip_path.stat().st_size
            logger.info(f"压缩完成: {zip_path.name} ({zip_size:,} bytes, {zip_size / 1024 / 1024:.2f} MB)")
            
        except Exception as e:
            logger.error(f"压缩失败: {e}")
        
        # 创建临时目录
        temp_dir = save_dir / 'temp_rename'
        temp_dir.mkdir(exist_ok=True)
        
        # 移动到临时目录
        temp_paths = []
        for file in image_files:
            try:
                temp_path = temp_dir / f"temp_{file.name}"
                file.rename(temp_path)
                temp_paths.append(temp_path)
            except Exception as e:
                logger.warning(f"移动文件失败 {file.name}: {e}")
                temp_paths.append(None)
        
        # 重命名
        renamed_count = 0
        skipped_count = 0
        for i, temp_path in enumerate(temp_paths, 1):
            if temp_path is None or not temp_path.exists():
                skipped_count += 1
                continue
            
            try:
                ext = temp_path.suffix or '.jpg'
                new_name = f"{i:03d}{ext}"
                new_path = save_dir / new_name
                
                if new_path.exists():
                    new_path.unlink()
                
                temp_path.rename(new_path)
                renamed_count += 1
                logger.info(f"重命名: {temp_path.name} -> {new_name}")
            except Exception as e:
                logger.error(f"重命名失败 {temp_path}: {e}")
                skipped_count += 1
        
        logger.info(f"重命名完成: 成功 {renamed_count} 个，跳过 {skipped_count} 个")
        
        # 删除临时目录
        try:
            temp_dir.rmdir()
        except:
            try:
                for file in temp_dir.iterdir():
                    file.unlink()
                temp_dir.rmdir()
            except:
                pass
    
    def fetch_and_download(self) -> None:
        """
        获取网页并下载所有图片
        """
        print("=" * 80)
        print("通用网站图片下载工具")
        print("=" * 80)
        print(f"目标URL: {self.base_url}")
        print(f"保存目录: {self.get_save_directory()}")
        print("=" * 80)
        
        # 检查URL是否本身就是图片
        parsed = urlparse(self.base_url)
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']):
            logger.info(f"URL本身就是图片，直接下载: {self.base_url}")
            save_dir = self.get_save_directory()
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取文件名
            filename = os.path.basename(parsed.path) or 'image.jpg'
            filepath = save_dir / filename
            
            # 如果文件已存在，添加序号
            counter = 1
            original_filepath = filepath
            while filepath.exists():
                stem = original_filepath.stem
                suffix = original_filepath.suffix
                filepath = save_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            
            if self.download_image(self.base_url, str(filepath)):
                self.stats['success'] += 1
                logger.info(f"✓ 下载成功: {filepath.name}")
            else:
                self.stats['failed'] += 1
                logger.error(f"✗ 下载失败")
            
            # 如果启用压缩，下载完成后压缩文件夹
            if self.create_zip:
                logger.info("下载完成，开始压缩文件夹...")
                self.create_zip_file(save_dir)
            
            # 打印统计信息
            print()
            print("=" * 80)
            print("下载完成！")
            print(f"  保存位置: {save_dir.absolute()}")
            print(f"  成功: {self.stats['success']} 张")
            print(f"  失败: {self.stats['failed']} 张")
            print(f"  跳过: {self.stats['skipped']} 张（包括.ico文件）")
            print("=" * 80)
            return
        
        logger.info(f"正在获取网页: {self.base_url}")
        
        try:
            # 分页加载：先下载第一页，再加载下一页
            all_image_urls = []  # 存储所有页面的图片
            current_page = 1
            html_content = None
            
            while True:
                # 获取当前页的HTML内容
                if html_content is None:
                    # 第一页：获取初始页面（允许重定向）
                    response = self.session.get(self.base_url, timeout=30, allow_redirects=True)
                    response.raise_for_status()
                    response.encoding = response.apparent_encoding or 'utf-8'
                    html_content = response.text
                    logger.info(f"正在解析第 {current_page} 页内容...")
                    logger.debug(f"最终URL: {response.url}")
                else:
                    # 后续页：已经在上次循环中加载了
                    logger.info(f"正在解析第 {current_page} 页内容...")
                
                # 提取当前页的图片URL
                page_image_urls = self.extract_image_urls(html_content, self.base_url)
                
                if not page_image_urls:
                    logger.warning(f"第 {current_page} 页未找到图片URL")
                    # 如果没有图片，停止加载更多页面
                    break
                
                logger.info(f"第 {current_page} 页找到 {len(page_image_urls)} 个图片URL")
                
                # 先下载当前页的所有图片（连续编号，从上一页的末尾继续）
                logger.info(f"开始下载第 {current_page} 页的 {len(page_image_urls)} 张图片...")
                print()
                
                # 计算起始编号（从上一页的末尾继续）
                if all_image_urls:
                    # 获取已下载的文件数量作为起始编号
                    save_dir = self.get_save_directory()
                    if save_dir.exists():
                        # 统计已存在的编号文件
                        pattern = re.compile(r'^(\d{3})\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
                        existing_numbers = []
                        for file in save_dir.iterdir():
                            if file.is_file():
                                match = pattern.match(file.name)
                                if match:
                                    existing_numbers.append(int(match.group(1)))
                        start_index = max(existing_numbers) + 1 if existing_numbers else 1
                    else:
                        start_index = 1
                else:
                    start_index = 1
                
                # 保存当前统计信息，以便计算本页的下载情况
                page_start_success = self.stats['success']
                page_start_failed = self.stats['failed']
                page_start_skipped = self.stats['skipped']
                
                # 下载当前页图片（连续编号）
                self.download_all_images(page_image_urls, start_index=start_index)
                
                # 计算本页下载情况
                page_success = self.stats['success'] - page_start_success
                page_failed = self.stats['failed'] - page_start_failed
                page_skipped = self.stats['skipped'] - page_start_skipped
                logger.info(f"第 {current_page} 页下载完成: 成功 {page_success} 张，失败 {page_failed} 张，跳过 {page_skipped} 张")
                
                # 将当前页的图片添加到总列表（用于统计）
                all_image_urls.extend(page_image_urls)
                
                # 检测是否有下一页
                next_page = self.detect_next_page(html_content, self.base_url)
                if next_page is None:
                    logger.info("没有更多页面，下载完成")
                    break
                
                # 加载下一页
                logger.info(f"检测到第 {next_page} 页，正在加载...")
                next_html = self.load_next_page_images(self.base_url, next_page)
                if next_html is None:
                    logger.warning(f"无法加载第 {next_page} 页，停止加载")
                    break
                
                # 更新为下一页的内容
                html_content = next_html
                current_page = next_page
                
                # 页面之间的延迟
                if self.delay > 0:
                    logger.info(f"等待 {self.delay} 秒后加载下一页...")
                    time.sleep(self.delay)
            
            # 如果启用压缩，在所有页面下载完成后压缩文件夹
            if self.create_zip:
                save_dir = self.get_save_directory()
                logger.info("所有页面下载完成，开始压缩文件夹...")
                self.create_zip_file(save_dir)
            
            # 打印统计信息
            print()
            print("=" * 80)
            print("下载完成！")
            print(f"  保存位置: {self.get_save_directory().absolute()}")
            print(f"  总共处理 {current_page} 页")
            print(f"  成功: {self.stats['success']} 张")
            print(f"  失败: {self.stats['failed']} 张")
            print(f"  跳过: {self.stats['skipped']} 张（包括.ico文件）")
            print("=" * 80)
            
        except Exception as e:
            logger.error(f"获取网页失败: {e}")
            sys.exit(1)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='通用网站图片下载工具 - 自动下载指定网页中的所有图片',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 下载指定网页的所有图片
  python download_images.py https://example.com/page
  
  # 指定保存目录
  python download_images.py https://example.com/page -o ./my_images
  
  # 设置下载延迟
  python download_images.py https://example.com/page -d 1.0
  
  # 显示详细日志
  python download_images.py https://example.com/page -v
  
  # 完整示例
  python download_images.py https://example.com/gallery -o ./gallery_images -d 1.0 -v
        """
    )
    
    parser.add_argument(
        'url',
        nargs='?',
        type=str,
        default=None,
        help='目标网页URL（如果不提供，使用默认URL，向后兼容）'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='./downloaded_images2',
        help='保存目录基础路径（默认: ./downloaded_images2）'
    )
    
    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=0.5,
        help='下载延迟（秒，默认: 0.5）'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    
    parser.add_argument(
        '-z', '--zip',
        action='store_true',
        help='下载完成后压缩文件夹为zip文件'
    )
    
    args = parser.parse_args()
    
    # 如果没有提供URL，使用默认URL（向后兼容）
    if not args.url:
        # 默认URL可以从环境变量或配置中读取
        default_url = 'https://ahri8-2025-10-01-yhhmc.monster/readOnline2.php?ID=156900'
        logger.warning(f"未提供URL参数，使用默认URL: {default_url}")
        args.url = default_url
    
    # 创建下载器并运行
    downloader = ImageDownloader(
        base_url=args.url,
        save_dir=args.output,
        delay=args.delay,
        verbose=args.verbose,
        create_zip=args.zip
    )
    
    downloader.fetch_and_download()


if __name__ == '__main__':
    main()

