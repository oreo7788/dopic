#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动下载漫画工具
从源网页提取post.php链接 -> 访问并提取readOnline2.php链接 -> 下载图片
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import re
import time
import sys
import os
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
import subprocess
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

BASE_URL = 'https://ahri8-2025-10-01-yhhmc.monster/'


class ComicDownloader:
    """漫画下载器"""
    
    def __init__(self, delay=1.0, download_delay=0.5, download_dir='./downloaded_images', 
                 download_timeout=1800, max_retries=2, create_zip=False):
        """
        初始化下载器
        
        Args:
            delay: 访问URL之间的延迟（秒）
            download_delay: 下载图片之间的延迟（秒）
            download_dir: 下载目录基础路径
            download_timeout: 下载超时时间（秒，默认: 1800即30分钟）
            max_retries: 下载失败时的最大重试次数（默认: 2）
            create_zip: 下载完成后是否压缩文件夹（默认: False）
        """
        self.delay = delay
        self.download_delay = download_delay
        self.download_dir = download_dir
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.create_zip = create_zip
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        
        self.stats = {
            'pages_processed': 0,
            'post_links_found': 0,
            'post_links_visited': 0,
            'readonline_links_found': 0,
            'readonline_links_visited': 0,
            'download_success': 0,
            'download_failed': 0,
            'download_skipped': 0,  # 跳过下载的数量（文件夹已存在）
            'download_retries': 0,  # 重试次数
        }
    
    def extract_post_links(self, html_content: str, base_url: str) -> List[Dict]:
        """
        从HTML内容中提取post.php链接
        
        Args:
            html_content: HTML内容
            base_url: 基础URL
            
        Returns:
            post.php链接列表
        """
        post_links = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 从<a>标签提取
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if href and 'post.php' in href.lower():
                absolute_url = urljoin(base_url, href)
                parsed = urlparse(absolute_url)
                query = parse_qs(parsed.query)
                link_id = query.get('ID', [''])[0]
                
                if link_id:
                    post_links.append({
                        'url': absolute_url,
                        'id': link_id,
                        'href': href,
                    })
        
        # 去重：每个ID只保留一个链接
        unique_links = []
        seen_ids = set()
        for link in post_links:
            if link['id'] not in seen_ids:
                unique_links.append(link)
                seen_ids.add(link['id'])
        
        # 按ID排序
        unique_links.sort(key=lambda x: int(x['id']) if x['id'].isdigit() else 0)
        
        return unique_links
    
    def extract_readonline_links(self, html_content: str) -> Set[str]:
        """
        从HTML内容中提取readOnline2.php链接
        
        Args:
            html_content: HTML内容
            
        Returns:
            readOnline2.php链接集合（相对路径）
        """
        links = set()
        
        # 匹配 readOnline2.php 链接的各种格式（只匹配相对路径）
        patterns = [
            r"['\"]readOnline2\.php\?ID=(\d+)&host_id=(\d+)[^'\"]*['\"]",
            r"['\"]readOnline2\.php\?ID=(\d+)[^'\"]*['\"]",
            r"href=['\"]readOnline2\.php\?ID=(\d+)&host_id=(\d+)[^'\"]*['\"]",
            r"href=['\"]readOnline2\.php\?ID=(\d+)[^'\"]*['\"]",
        ]
        
        # 额外匹配：匹配不在引号内的readOnline2.php链接（但排除完整URL）
        # 先提取所有readOnline2.php链接，然后过滤掉完整URL
        additional_patterns = [
            r"readOnline2\.php\?ID=(\d+)&host_id=(\d+)",
            r"readOnline2\.php\?ID=(\d+)",
        ]
        
        for pattern in additional_patterns:
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for match in matches:
                # 检查前面是否有http://或https://
                start_pos = match.start()
                if start_pos > 0:
                    before_text = html_content[max(0, start_pos-20):start_pos]
                    if 'http://' in before_text.lower() or 'https://' in before_text.lower():
                        continue
                
                groups = match.groups()
                if len(groups) == 2 and groups[1].isdigit():
                    link = f"readOnline2.php?ID={groups[0]}&host_id={groups[1]}"
                elif len(groups) >= 1:
                    link = f"readOnline2.php?ID={groups[0]}"
                else:
                    continue
                
                if link.startswith('readOnline2.php') and 'http' not in link.lower():
                    links.add(link)
        
        for pattern in patterns:
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) == 2 and groups[1].isdigit():
                    # 有host_id的情况
                    link = f"readOnline2.php?ID={groups[0]}&host_id={groups[1]}"
                elif len(groups) >= 1:
                    # 只有ID的情况
                    link = f"readOnline2.php?ID={groups[0]}"
                else:
                    continue
                
                # 确保是相对路径（以readOnline2.php开头，不包含http）
                if link.startswith('readOnline2.php') and 'http' not in link.lower():
                    links.add(link)
        
        return links
    
    def build_full_readonline_urls(self, links: Set[str]) -> List[str]:
        """
        将相对链接转换为完整URL，并去重（优先保留带host_id的）
        
        Args:
            links: 相对链接集合
            
        Returns:
            完整URL列表（已去重）
        """
        url_dict = {}  # key: ID, value: (link, has_host_id)
        
        for link in links:
            # 如果已经是完整URL，直接使用
            if link.startswith('http://') or link.startswith('https://'):
                match = re.search(r'ID=(\d+)', link)
                if match:
                    comic_id = match.group(1)
                    has_host_id = 'host_id' in link
                    if comic_id not in url_dict or (has_host_id and not url_dict[comic_id][1]):
                        url_dict[comic_id] = (link, has_host_id)
                continue
            
            # 处理相对路径
            if not link.startswith('readOnline2.php'):
                continue
            
            match = re.search(r'ID=(\d+)', link)
            if not match:
                continue
            
            comic_id = match.group(1)
            has_host_id = 'host_id' in link
            
            if comic_id not in url_dict or (has_host_id and not url_dict[comic_id][1]):
                url_dict[comic_id] = (link, has_host_id)
        
        full_urls = []
        for link, _ in url_dict.values():
            # 如果已经是完整URL，直接使用；否则拼接BASE_URL
            if link.startswith('http://') or link.startswith('https://'):
                full_url = link
            else:
                full_url = urljoin(BASE_URL, link)
            full_urls.append(full_url)
        
        full_urls.sort(key=lambda x: int(re.search(r'ID=(\d+)', x).group(1)) if re.search(r'ID=(\d+)', x) else 0)
        
        return full_urls
    
    def download_images_for_url(self, url: str, download_script: str = 'download_images.py') -> bool:
        """
        调用 download_images.py 下载指定URL的图片
        
        Args:
            url: 要下载的URL
            download_script: 下载脚本路径
            
        Returns:
            是否成功（会验证文件夹是否真的被创建）
        """
        # 先提取ID，用于验证下载是否成功
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        comic_id = query.get('ID', [''])[0]
        
        # 查找脚本文件的完整路径
        script_path = download_script
        possible_paths = []
        
        if not os.path.isabs(download_script):
            # 相对路径，尝试多个位置
            possible_paths = [
                download_script,  # 当前目录
                os.path.join(os.path.dirname(__file__), download_script),  # 脚本所在目录
                os.path.join(os.getcwd(), download_script),  # 工作目录
            ]
            
            for path in possible_paths:
                if os.path.exists(path) and os.path.isfile(path):
                    script_path = os.path.abspath(path)
                    logger.debug(f"找到下载脚本: {script_path}")
                    break
            else:
                # 如果都找不到，使用原始路径
                script_path = download_script
        else:
            # 绝对路径
            possible_paths = [download_script]
        
        if not os.path.exists(script_path):
            logger.error(f"下载脚本不存在: {script_path}")
            logger.error(f"尝试的路径: {possible_paths}")
            logger.error(f"当前工作目录: {os.getcwd()}")
            logger.error(f"脚本所在目录: {os.path.dirname(__file__)}")
            return False
        
        try:
            cmd = [sys.executable, script_path, url]
            # 如果启用压缩，添加 -z 参数
            if self.create_zip:
                cmd.append('-z')
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.download_timeout  # 可配置的超时时间
            )
            
            # 检查返回码
            if result.returncode != 0:
                logger.error(f"下载脚本返回错误: {result.stderr[:200]}")
                return False
            
            # 验证文件夹是否真的被创建了
            if comic_id:
                download_dir = Path(self.download_dir) / comic_id
                if download_dir.exists() and download_dir.is_dir():
                    # 检查文件夹中是否有文件
                    files = list(download_dir.glob('*'))
                    if files:
                        logger.debug(f"验证成功: 文件夹 {comic_id} 已创建，包含 {len(files)} 个文件")
                        return True
                    else:
                        logger.warning(f"文件夹 {comic_id} 已创建但为空")
                        return False
                else:
                    logger.warning(f"下载脚本返回成功，但文件夹 {comic_id} 未创建")
                    # 输出更多调试信息
                    if result.stdout:
                        logger.debug(f"脚本输出: {result.stdout[-500:]}")
                    if result.stderr:
                        logger.debug(f"脚本错误: {result.stderr[-500:]}")
                    return False
            
            # 如果没有ID，只检查返回码
            return True
                
        except subprocess.TimeoutExpired:
            logger.error(f"下载超时 ({self.download_timeout}秒): {url}")
            return False
        except Exception as e:
            logger.error(f"执行失败 {url}: {e}")
            return False
    
    def extract_next_page_url(self, html_content: str, current_url: str) -> Optional[str]:
        """
        从HTML内容中提取下一页URL
        
        Args:
            html_content: HTML内容
            current_url: 当前页面URL
            
        Returns:
            下一页URL，如果没有则返回None
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 方法1: 查找包含"下一页"、"next"等文本的链接
        next_keywords = ['下一页', 'next', '>', '»', '下页']
        for keyword in next_keywords:
            for a_tag in soup.find_all('a', href=True):
                text = a_tag.get_text(strip=True).lower()
                href = a_tag.get('href', '')
                
                if keyword.lower() in text and 'dnew.php' in href.lower():
                    next_url = urljoin(current_url, href)
                    return next_url
        
        # 方法2: 查找页码链接，找到当前页+1的链接
        parsed = urlparse(current_url)
        query = parse_qs(parsed.query)
        try:
            current_page = int(query.get('page', ['1'])[0])
        except (ValueError, IndexError):
            current_page = 1
        next_page = current_page + 1
        
        # 查找包含page参数的dnew.php链接
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if 'dnew.php' in href.lower():
                full_url = urljoin(current_url, href)
                href_parsed = urlparse(full_url)
                href_query = parse_qs(href_parsed.query)
                try:
                    href_page = int(href_query.get('page', ['1'])[0])
                except (ValueError, IndexError):
                    href_page = 1
                
                if href_page == next_page:
                    return full_url
        
        # 方法3: 直接构建下一页URL（如果当前URL有page参数）
        if 'page' in query:
            query['page'] = [str(next_page)]
            new_query = '&'.join([f"{k}={v[0]}" for k, v in query.items()])
            next_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
            return next_url
        else:
            # 如果当前URL没有page参数，添加page=2
            separator = '&' if '?' in current_url else '?'
            next_url = f"{current_url}{separator}page=2"
            return next_url
    
    def process_source_page(self, source_url: str) -> tuple:
        """
        处理源网页，提取post.php链接和下一页URL
        
        Args:
            source_url: 源网页URL（dnew.php）
            
        Returns:
            (post.php链接列表, 下一页URL) 元组
        """
        max_retries = 2
        retry_delay = 900  # 15分钟 = 900秒
        
        for attempt in range(max_retries + 1):  # 总共尝试3次（初始1次 + 重试2次）
            if attempt > 0:
                logger.info(f"等待 {retry_delay} 秒后重试获取源网页... (第 {attempt}/{max_retries} 次重试)")
                time.sleep(retry_delay)
            
            logger.info(f"正在获取源网页: {source_url}" + (f" (尝试 {attempt + 1}/{max_retries + 1})" if attempt > 0 else ""))
            
            try:
                response = self.session.get(source_url, timeout=30)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or 'utf-8'
                
                logger.info(f"[OK] 成功获取网页 (状态码: {response.status_code})")
                
                post_links = self.extract_post_links(response.text, source_url)
                self.stats['post_links_found'] += len(post_links)
                
                logger.info(f"找到 {len(post_links)} 个post.php链接")
                
                # 提取下一页URL
                next_page_url = self.extract_next_page_url(response.text, source_url)
                
                return post_links, next_page_url
                
            except Exception as e:
                if attempt < max_retries:
                    logger.error(f"获取源网页失败: {e}，将在 {retry_delay} 秒后重试...")
                else:
                    logger.error(f"获取源网页失败: {e}，已重试 {max_retries} 次，放弃")
                    return [], None
        
        return [], None
    
    def process_post_page(self, post_url: str) -> List[str]:
        """
        处理post.php页面，提取readOnline2.php链接
        
        Args:
            post_url: post.php URL
            
        Returns:
            readOnline2.php完整URL列表
        """
        parsed = urlparse(post_url)
        post_id = parse_qs(parsed.query).get('ID', [''])[0]
        
        logger.info(f"正在访问 post.php?ID={post_id}")
        
        try:
            response = self.session.get(post_url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            
            self.stats['post_links_visited'] += 1
            
            # 提取readOnline2.php链接
            links = self.extract_readonline_links(response.text)
            full_urls = self.build_full_readonline_urls(links)
            
            if full_urls:
                self.stats['readonline_links_found'] += len(full_urls)
                logger.info(f"  [OK] 找到 {len(full_urls)} 个readOnline2.php链接")
            else:
                logger.warning(f"  [-] 未找到readOnline2.php链接")
            
            return full_urls
            
        except Exception as e:
            logger.error(f"访问post.php失败 {post_url}: {e}")
            return []
    
    def check_download_dir_exists(self, url: str) -> bool:
        """
        检查下载目录是否已存在
        
        Args:
            url: readOnline2.php URL
            
        Returns:
            目录是否存在
        """
        # 从URL中提取ID
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        comic_id = query.get('ID', [''])[0]
        
        if not comic_id:
            return False
        
        # 构建目录路径（与download_images.py保持一致）
        download_dir = Path(self.download_dir) / comic_id
        
        return download_dir.exists() and download_dir.is_dir()
    
    def check_files_renamed(self, url: str) -> bool:
        """
        检查文件是否已经重命名过（是否有001.jpg等格式的文件）
        
        Args:
            url: readOnline2.php URL
            
        Returns:
            文件是否已重命名
        """
        # 从URL中提取ID
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        comic_id = query.get('ID', [''])[0]
        
        if not comic_id:
            return False
        
        # 构建目录路径
        download_dir = Path(self.download_dir) / comic_id
        
        if not download_dir.exists() or not download_dir.is_dir():
            return False
        
        # 检查是否有001.jpg等格式的文件（3位数字开头的文件）
        pattern = re.compile(r'^\d{3}\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
        for file in download_dir.iterdir():
            if file.is_file() and pattern.match(file.name):
                return True
        
        return False
    
    def check_dir_has_files(self, url: str) -> bool:
        """
        检查文件夹中是否有图片文件（不管是否重命名）
        
        Args:
            url: readOnline2.php URL
            
        Returns:
            文件夹中是否有图片文件
        """
        # 从URL中提取ID
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        comic_id = query.get('ID', [''])[0]
        
        if not comic_id:
            return False
        
        # 构建目录路径
        download_dir = Path(self.download_dir) / comic_id
        
        if not download_dir.exists() or not download_dir.is_dir():
            return False
        
        # 检查是否有图片文件
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
        for file in download_dir.iterdir():
            if file.is_file() and file.suffix.lower() in image_extensions:
                return True
        
        return False
    
    def check_download_complete(self, url: str) -> Tuple[bool, int, int]:
        """
        检查图片是否全部下载完成
        
        Args:
            url: readOnline2.php URL
            
        Returns:
            (是否完成, 已下载数量, 总数量) 元组
        """
        # 从URL中提取ID
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        comic_id = query.get('ID', [''])[0]
        
        if not comic_id:
            return False, 0, 0
        
        # 构建目录路径
        download_dir = Path(self.download_dir) / comic_id
        
        if not download_dir.exists() or not download_dir.is_dir():
            return False, 0, 0
        
        # 获取网页内容，提取图片总数
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            
            # 使用 ImageDownloader 提取图片URL
            from download_images import ImageDownloader
            downloader = ImageDownloader(base_url=url, save_dir=self.download_dir)
            image_urls = downloader.extract_image_urls(response.text, url)
            total_count = len(image_urls)
            
            if total_count == 0:
                return False, 0, 0
            
            # 检查已下载的文件数量（检查001.jpg, 002.jpg等格式的文件）
            pattern = re.compile(r'^(\d{3})\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
            downloaded_numbers = set()
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
            
            for file in download_dir.iterdir():
                if file.is_file() and file.suffix.lower() in image_extensions:
                    match = pattern.match(file.name)
                    if match:
                        # 已重命名的文件（001.jpg格式）
                        downloaded_numbers.add(int(match.group(1)))
                    else:
                        # 未重命名的文件，也计入（假设至少下载了1张）
                        downloaded_numbers.add(1)
            
            downloaded_count = len(downloaded_numbers)
            is_complete = downloaded_count >= total_count
            
            return is_complete, downloaded_count, total_count
            
        except Exception as e:
            logger.warning(f"检查下载完成状态失败: {e}")
            # 如果无法获取总数，检查文件编号是否连续
            pattern = re.compile(r'^(\d{3})\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)
            downloaded_numbers = set()
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
            
            for file in download_dir.iterdir():
                if file.is_file() and file.suffix.lower() in image_extensions:
                    match = pattern.match(file.name)
                    if match:
                        downloaded_numbers.add(int(match.group(1)))
            
            if not downloaded_numbers:
                return False, 0, 0
            
            # 检查编号是否连续（从001开始）
            max_num = max(downloaded_numbers)
            expected_numbers = set(range(1, max_num + 1))
            missing_numbers = expected_numbers - downloaded_numbers
            
            # 如果有缺失的编号，说明未完成
            is_complete = len(missing_numbers) == 0
            downloaded_count = len(downloaded_numbers)
            
            # 估算总数（使用最大编号）
            total_count = max_num if is_complete else max_num + len(missing_numbers)
            
            return is_complete, downloaded_count, total_count
    
    def process_readonline_page(self, readonline_url: str, download_script: str = 'download_images.py') -> bool:
        """
        处理readOnline2.php页面，下载图片
        
        Args:
            readonline_url: readOnline2.php URL
            download_script: 下载脚本路径
            
        Returns:
            是否成功（包括跳过的情况）
        """
        parsed = urlparse(readonline_url)
        comic_id = parse_qs(parsed.query).get('ID', [''])[0]
        
        logger.info(f"正在下载图片: readOnline2.php?ID={comic_id}")
        
        self.stats['readonline_links_visited'] += 1
        
        # 检查目录是否已存在且文件已重命名
        if self.check_download_dir_exists(readonline_url):
            if self.check_files_renamed(readonline_url):
                self.stats['download_skipped'] += 1
                logger.info(f"  [跳过] 目录已存在且文件已重命名，跳过下载")
                return True
            else:
                logger.info(f"  [提示] 目录已存在但文件未重命名，将执行重命名")
                # 直接重命名已存在的文件
                parsed = urlparse(readonline_url)
                query = parse_qs(parsed.query)
                comic_id = query.get('ID', [''])[0]
                if comic_id:
                    download_dir = Path(self.download_dir) / comic_id
                    try:
                        # 导入 ImageDownloader 并重命名
                        from download_images import ImageDownloader
                        downloader = ImageDownloader(base_url=readonline_url, save_dir=self.download_dir)
                        downloader.rename_existing_files(download_dir)
                        self.stats['download_success'] += 1
                        logger.info(f"  [OK] 重命名完成")
                        return True
                    except Exception as e:
                        logger.error(f"  [X] 重命名失败: {e}")
                        # 如果重命名失败，尝试重新下载
                        logger.info(f"  [提示] 重命名失败，将重新下载以执行重命名")
                else:
                    logger.warning(f"  [X] 无法提取ID，将重新下载")
        
        # 调用下载脚本（带重试机制）
        retry_count = 0
        while retry_count <= self.max_retries:
            if retry_count > 0:
                # 重试前检查文件夹是否已存在且有文件
                if self.check_dir_has_files(readonline_url):
                    # 检查是否全部下载完成
                    is_complete, downloaded_count, total_count = self.check_download_complete(readonline_url)
                    
                    if is_complete:
                        logger.info(f"  [跳过重试] 图片已全部下载完成 ({downloaded_count}/{total_count})")
                        # 如果文件未重命名，尝试重命名
                        if not self.check_files_renamed(readonline_url):
                            logger.info(f"  [提示] 文件未重命名，将执行重命名")
                            parsed = urlparse(readonline_url)
                            query = parse_qs(parsed.query)
                            comic_id = query.get('ID', [''])[0]
                            if comic_id:
                                download_dir = Path(self.download_dir) / comic_id
                                try:
                                    from download_images import ImageDownloader
                                    downloader = ImageDownloader(base_url=readonline_url, save_dir=self.download_dir)
                                    downloader.rename_existing_files(download_dir)
                                    logger.info(f"  [OK] 重命名完成")
                                except Exception as e:
                                    logger.warning(f"  [警告] 重命名失败: {e}")
                        self.stats['download_success'] += 1
                        logger.info(f"  [OK] 跳过重试（下载已完成）")
                        return True
                    else:
                        # 未全部完成，继续下载
                        logger.info(f"  [继续下载] 图片未全部下载完成 ({downloaded_count}/{total_count})，继续下载缺失的图片...")
                        # 继续执行下载（download_images.py 会自动跳过已存在的文件）
                
                self.stats['download_retries'] += 1
                wait_time = retry_count * 5  # 每次重试前等待时间递增
                logger.info(f"  [重试 {retry_count}/{self.max_retries}] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            
            if self.download_images_for_url(readonline_url, download_script):
                self.stats['download_success'] += 1
                logger.info(f"  [OK] 下载完成")
                return True
            else:
                retry_count += 1
                if retry_count <= self.max_retries:
                    logger.warning(f"  [重试 {retry_count}/{self.max_retries}] 下载失败，将重试...")
                else:
                    self.stats['download_failed'] += 1
                    logger.error(f"  [X] 下载失败（已重试 {self.max_retries} 次）")
                    return False
        
        return False
    
    def run(self, source_url: str, download_script: str = 'download_images.py', 
            max_posts: Optional[int] = None, start_page: int = 1, 
            end_page: Optional[int] = None, max_pages: Optional[int] = None):
        """
        运行完整的下载流程（支持翻页）
        
        Args:
            source_url: 源网页URL（dnew.php）
            download_script: 下载脚本路径
            max_posts: 每页最大处理post.php数量（None表示处理所有）
            start_page: 起始页码（默认: 1）
            end_page: 结束页码（None表示处理到最后一页）
            max_pages: 最大处理页数（None表示不限制）
        """
        print("=" * 80)
        print("自动下载漫画工具（支持翻页）")
        print("=" * 80)
        print(f"源网页: {source_url}")
        print(f"下载脚本: {download_script}")
        print(f"访问延迟: {self.delay} 秒")
        print(f"下载延迟: {self.download_delay} 秒")
        print(f"下载超时: {self.download_timeout} 秒 ({self.download_timeout // 60} 分钟)")
        print(f"最大重试次数: {self.max_retries}")
        print(f"压缩选项: {'启用' if self.create_zip else '禁用'}")
        print(f"起始页码: {start_page}")
        if end_page:
            print(f"结束页码: {end_page}")
        if max_pages:
            print(f"最大页数: {max_pages}")
        if max_posts:
            print(f"每页最大处理数量: {max_posts}")
        print("=" * 80)
        print()
        
        # 构建起始URL（如果指定了起始页码）
        current_url = source_url
        if start_page > 1:
            parsed = urlparse(source_url)
            query = parse_qs(parsed.query)
            query['page'] = [str(start_page)]
            new_query = '&'.join([f"{k}={v[0]}" for k, v in query.items()])
            current_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
        
        current_page = start_page
        pages_processed = 0
        
        # 循环处理每一页
        while True:
            # 检查页数限制
            if end_page and current_page > end_page:
                logger.info(f"已达到结束页码 {end_page}，停止处理")
                break
            
            if max_pages and pages_processed >= max_pages:
                logger.info(f"已达到最大页数 {max_pages}，停止处理")
                break
            
            print(f"\n{'=' * 80}")
            print(f"处理第 {current_page} 页")
            print(f"{'=' * 80}")
            
            # 处理当前页
            post_links, next_page_url = self.process_source_page(current_url)
            
            if not post_links:
                logger.warning(f"第 {current_page} 页未找到post.php链接，可能已到最后一页")
                break
            
            # 限制每页处理数量
            if max_posts:
                post_links = post_links[:max_posts]
            
            print(f"\n将处理 {len(post_links)} 个post.php链接\n")
            
            # 访问每个post.php页面，提取readOnline2.php链接并下载
            for i, post_link in enumerate(post_links, 1):
                print(f"\n[{i}/{len(post_links)}] 处理 post.php?ID={post_link['id']}")
                
                # 提取readOnline2.php链接
                readonline_urls = self.process_post_page(post_link['url'])
                
                if readonline_urls:
                    # 立即下载（每个post.php对应一个readOnline2.php）
                    for readonline_url in readonline_urls:
                        self.process_readonline_page(readonline_url, download_script)
                        
                        # 下载延迟
                        if self.download_delay > 0:
                            time.sleep(self.download_delay)
                else:
                    logger.warning(f"  未找到readOnline2.php链接，跳过")
                
                # 访问延迟
                if i < len(post_links) and self.delay > 0:
                    time.sleep(self.delay)
            
            self.stats['pages_processed'] += 1
            pages_processed += 1
            
            # 检查是否有下一页
            if not next_page_url:
                logger.info("未找到下一页链接，已处理完所有页面")
                break
            
            # 检查是否应该继续
            if end_page and current_page >= end_page:
                logger.info(f"已达到结束页码 {end_page}，停止处理")
                break
            
            # 准备处理下一页
            current_url = next_page_url
            current_page += 1
            
            # 页面之间的延迟
            if self.delay > 0:
                logger.info(f"等待 {self.delay} 秒后处理下一页...")
                time.sleep(self.delay)
        
        # 打印统计
        print("\n" + "=" * 80)
        print("下载完成统计")
        print("=" * 80)
        print(f"处理的页数: {self.stats['pages_processed']}")
        print(f"找到的post.php链接: {self.stats['post_links_found']}")
        print(f"访问的post.php页面: {self.stats['post_links_visited']}")
        print(f"找到的readOnline2.php链接: {self.stats['readonline_links_found']}")
        print(f"访问的readOnline2.php页面: {self.stats['readonline_links_visited']}")
        print(f"下载成功: {self.stats['download_success']}")
        print(f"下载跳过: {self.stats['download_skipped']} (文件夹已存在)")
        print(f"下载失败: {self.stats['download_failed']}")
        print(f"下载重试: {self.stats['download_retries']} 次")
        print("=" * 80)


def main():
    """主函数"""
    import argparse
    
    global BASE_URL
    
    parser = argparse.ArgumentParser(
        description='自动下载漫画工具 - 从源网页提取链接并下载图片',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从默认源网页开始下载（处理所有页面）
  python auto_download_comics.py
  
  # 指定源网页
  python auto_download_comics.py -u https://ahri8-2025-10-01-yhhmc.monster/dnew.php?category_id=1&t=1761955200
  
  # 限制处理页数（只处理前3页）
  python auto_download_comics.py --max-pages 3
  
  # 处理指定页数范围（第2页到第5页）
  python auto_download_comics.py --start-page 2 --end-page 5
  
  # 限制每页处理数量（测试用）
  python auto_download_comics.py --max-posts 5
  
  # 自定义延迟
  python auto_download_comics.py --delay 2.0 --download-delay 1.0
  
  # 自定义超时时间和重试次数
  python auto_download_comics.py --download-timeout 1800 --max-retries 3
        """
    )
    
    parser.add_argument(
        '-u', '--url',
        type=str,
        default='https://ahri8-2025-10-01-yhhmc.monster/dnew.php?category_id=1&t=1761955200',
        help='源网页URL（默认: dnew.php）'
    )
    
    parser.add_argument(
        '-s', '--script',
        type=str,
        default='download_images.py',
        help='下载脚本路径（默认: download_images.py）'
    )
    
    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=1.0,
        help='访问URL之间的延迟（秒，默认: 1.0）'
    )
    
    parser.add_argument(
        '--download-delay',
        type=float,
        default=0.5,
        help='下载图片之间的延迟（秒，默认: 0.5）'
    )
    
    parser.add_argument(
        '--max-posts',
        type=int,
        default=None,
        help='每页最大处理post.php数量（用于测试，默认: 处理所有）'
    )
    
    parser.add_argument(
        '--start-page',
        type=int,
        default=1,
        help='起始页码（默认: 1）'
    )
    
    parser.add_argument(
        '--end-page',
        type=int,
        default=None,
        help='结束页码（默认: 处理到最后一页）'
    )
    
    parser.add_argument(
        '--max-pages',
        type=int,
        default=None,
        help='最大处理页数（默认: 不限制）'
    )
    
    parser.add_argument(
        '--base-url',
        type=str,
        default=BASE_URL,
        help=f'基础URL（默认: {BASE_URL}）'
    )
    
    parser.add_argument(
        '--download-dir',
        type=str,
        default='./downloaded_images',
        help='下载目录基础路径（默认: ./downloaded_images）'
    )
    
    parser.add_argument(
        '--download-timeout',
        type=int,
        default=1800,
        help='下载超时时间（秒，默认: 1800即30分钟）'
    )
    
    parser.add_argument(
        '--max-retries',
        type=int,
        default=2,
        help='下载失败时的最大重试次数（默认: 2）'
    )
    
    parser.add_argument(
        '-z', '--zip',
        action='store_true',
        help='下载完成后压缩文件夹为zip文件'
    )
    
    args = parser.parse_args()
    
    BASE_URL = args.base_url
    
    # 创建下载器并运行
    downloader = ComicDownloader(
        delay=args.delay,
        download_delay=args.download_delay,
        download_dir=args.download_dir,
        download_timeout=args.download_timeout,
        max_retries=args.max_retries,
        create_zip=args.zip
    )
    
    downloader.run(
        source_url=args.url,
        download_script=args.script,
        max_posts=args.max_posts,
        start_page=args.start_page,
        end_page=args.end_page,
        max_pages=args.max_pages
    )


if __name__ == '__main__':
    main()

