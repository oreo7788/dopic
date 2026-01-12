# 通用网站图片下载工具

自动下载指定网页中的所有图片，支持任意网站，自动识别图片URL并过滤掉.ico文件和图标文件。

## 功能特点

- ✅ 支持任意网站，自动识别图片URL
- ✅ 自动解析网页HTML，提取所有图片URL
- ✅ 支持多种图片格式（jpg, png, gif, webp, bmp, svg）
- ✅ 自动过滤.ico文件和图标文件
- ✅ 支持命令行参数，灵活配置
- ✅ 自动创建保存目录
- ✅ 显示下载进度和统计信息
- ✅ 错误处理和日志记录
- ✅ 支持从img标签、CSS背景、JavaScript代码中提取图片URL
- ✅ 支持按顺序重命名（如果网站提供排序信息）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本使用

下载指定网页的所有图片：

```bash
python download_images.py https://example.com/page
```

### 指定保存目录

使用 `-o` 或 `--output` 参数指定保存目录：

```bash
python download_images.py https://example.com/page -o ./my_images
```

### 设置下载延迟

使用 `-d` 或 `--delay` 参数设置下载间隔（秒），避免请求过快：

```bash
python download_images.py https://example.com/page -d 1.0
```

### 显示详细日志

使用 `-v` 或 `--verbose` 参数显示详细日志：

```bash
python download_images.py https://example.com/page -v
```

### 查看帮助

```bash
python download_images.py --help
```

### 完整示例

```bash
# 下载网页图片，保存到指定目录，延迟1秒
python download_images.py https://example.com/gallery -o ./gallery_images -d 1.0 -v
```

### 向后兼容

如果不提供URL参数，脚本会使用默认URL（向后兼容）：

```bash
python download_images.py
```

## 代码说明

### ImageDownloader 类

主要的图片下载器类，包含以下方法：

- `__init__(base_url, save_dir)`: 初始化下载器
- `fetch_and_download()`: 获取网页并下载所有图片
- `extract_image_urls(html_content)`: 从HTML中提取图片URL（通用方法）
- `extract_image_list_from_js(html_content)`: 从JavaScript中提取图片列表（特定网站）
- `extract_image_base_url(html_content)`: 提取图片基础URL（特定网站）
- `download_image(url, filename)`: 下载单张图片
- `download_all_images(image_urls)`: 批量下载图片
- `is_ico_file(url)`: 检查是否为.ico文件
- `should_skip_file(url)`: 检查是否应该跳过（图标文件等）
- `rename_images_by_sort()`: 按顺序重命名图片

### 支持的图片格式

- .jpg / .jpeg
- .png
- .gif
- .webp
- .bmp
- .svg

**注意**：.ico文件和图标文件（blank.gif, touch-icon等）会被自动过滤，不会下载。

### 图片提取策略

脚本使用多层次的图片提取策略：

1. **特定网站优化**：如果检测到特定网站结构（如漫画网站），会使用优化的提取方法
2. **通用提取**：从HTML的img标签、CSS背景、JavaScript代码中提取图片URL
3. **智能猜测**：如果常规方法找不到图片，会尝试根据URL模式猜测

### 自动重命名

如果网站提供了图片排序信息（如sort字段），脚本会自动按顺序重命名图片为：
- `000.jpg`, `001.jpg`, `002.jpg` ... 

否则，图片会保持原始文件名。

## 输出示例

```
================================================================================
漫画网站图片下载工具
================================================================================
目标URL: https://ahri8-2025-10-01-yhhmc.monster/readOnline2.php?ID=156900&...
保存目录: ./downloaded_images/comic_156900
================================================================================
正在获取网页: https://ahri8-2025-10-01-yhhmc.monster/readOnline2.php?ID=156900&...
正在解析网页内容...
找到 25 个图片URL

开始下载 25 张图片...
------------------------------------------------------------
[1/25] 正在下载: https://...
✓ [1] 下载成功: image_0001.jpg (123,456 bytes)
...
================================================================================
下载完成！
  保存位置: D:\www\trade\dopic\downloaded_images\comic_156900
  成功: 25 张
  失败: 0 张
  跳过: 0 张（包括.ico文件）
================================================================================
```

## 注意事项

1. 脚本会自动设置User-Agent，模拟真实浏览器访问
2. 下载过程中会有0.5秒的延迟，避免请求过快
3. 如果文件已存在，会自动添加序号避免覆盖
4. 所有操作都会记录日志，方便排查问题

## 错误处理

- 网络错误：自动重试并记录错误
- 无效URL：跳过并继续下载其他图片
- 非图片文件：自动检测并跳过
- .ico文件：自动过滤

## 许可证

本项目仅供学习交流使用。

