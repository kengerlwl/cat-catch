#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 处理器 - 参考 cat-catch 的实现方式
处理加密、解密、切片验证等功能
"""

import os
import re
import requests
import m3u8
import struct
from urllib.parse import urljoin, urlparse
import binascii
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 尝试导入加密库，如果失败则禁用加密功能
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from Cryptodome.Cipher import AES
        from Cryptodome.Util.Padding import unpad
        CRYPTO_AVAILABLE = True
    except ImportError:
        print("警告: 未找到加密库 (pycryptodome)，加密视频解密功能将不可用")
        print("安装命令: pip install pycryptodome")
        CRYPTO_AVAILABLE = False
        AES = None
        unpad = None

class M3U8Processor:
    def __init__(self, m3u8_url, headers=None, source_url=None):
        self.m3u8_url = m3u8_url
        # 默认header配置，模拟浏览器行为
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'DNT': '1'
        }
        
        # 从source_url解析host并设置默认的Referer和Origin
        if source_url:
            try:
                from urllib.parse import urlparse
                parsed_url = urlparse(source_url)
                if parsed_url.scheme and parsed_url.netloc:
                    # 构建基础URL（协议+域名+端口）
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    # 只有在没有提供或headers中不包含这些属性时才设置默认值
                    if not headers or 'Referer' not in headers:
                        default_headers['Referer'] = base_url
                    if not headers or 'Origin' not in headers:
                        default_headers['Origin'] = base_url
                    print(f"从来源页面URL自动设置Referer和Origin为: {base_url}")
            except Exception as e:
                print(f"解析来源页面URL失败，无法设置默认Referer和Origin: {e}")
        
        # 如果提供了自定义headers，则合并到默认headers中
        if headers:
            default_headers.update(headers)
        print(f"最终headers: {default_headers}")
        self.headers = default_headers
        self.m3u8_obj = None
        self.segments = []
        self.keys = {}  # 存储解密密钥
        self._lock = threading.Lock()  # 用于线程安全的进度更新

    def parse_m3u8(self):
        """解析 M3U8 文件"""
        try:
            print(f"正在解析 M3U8: {self.m3u8_url}")
            self.m3u8_obj = m3u8.load(self.m3u8_url, headers=self.headers)

            if not self.m3u8_obj.segments:
                raise ValueError("M3U8 文件中没有找到视频片段")

            # 处理每个切片
            base_url = self.m3u8_url.rsplit('/', 1)[0] + '/'

            for i, segment in enumerate(self.m3u8_obj.segments):
                segment_info = {
                    'index': i,
                    'url': self._resolve_url(segment.uri, base_url),
                    'duration': segment.duration,
                    'encrypted': False,
                    'key_uri': None,
                    'iv': None,
                    'method': None
                }

                # 检查加密信息
                if segment.key and segment.key.method and segment.key.method != 'NONE':
                    segment_info['encrypted'] = True
                    segment_info['method'] = segment.key.method
                    segment_info['key_uri'] = self._resolve_url(segment.key.uri, base_url) if segment.key.uri else None
                    segment_info['iv'] = segment.key.iv

                self.segments.append(segment_info)

            print(f"解析完成，共 {len(self.segments)} 个切片")
            return True

        except Exception as e:
            print(f"解析 M3U8 失败: {e}")
            return False

    def _resolve_url(self, url, base_url):
        """解析相对URL为绝对URL"""
        if url.startswith('http'):
            return url
        return urljoin(base_url, url)

    def download_key(self, key_uri):
        """下载解密密钥"""
        if key_uri in self.keys:
            return self.keys[key_uri]

        try:
            print(f"下载密钥: {key_uri}")
            response = requests.get(key_uri, headers=self.headers, timeout=30)
            response.raise_for_status()

            key_data = response.content
            if len(key_data) == 16:  # AES-128 密钥长度
                self.keys[key_uri] = key_data
                print(f"密钥下载成功，长度: {len(key_data)} 字节")
                return key_data
            else:
                print(f"密钥长度异常: {len(key_data)} 字节")
                return None

        except Exception as e:
            print(f"下载密钥失败: {e}")
            return None

    def decrypt_segment(self, encrypted_data, segment_info):
        """解密切片数据"""
        if not segment_info['encrypted']:
            return encrypted_data

        if not CRYPTO_AVAILABLE:
            print(f"警告: 切片 {segment_info['index']} 是加密的，但未安装加密库，无法解密")
            return encrypted_data

        try:
            # 获取密钥
            key_data = self.download_key(segment_info['key_uri'])
            if not key_data:
                print(f"无法获取密钥，跳过解密")
                return encrypted_data

            # 处理 IV
            if segment_info['iv']:
                # 如果 IV 以 0x 开头，去掉前缀并转换为字节
                iv_str = segment_info['iv']
                if iv_str.startswith('0x') or iv_str.startswith('0X'):
                    iv_str = iv_str[2:]
                iv = binascii.unhexlify(iv_str.zfill(32))  # 确保是32个字符（16字节）
            else:
                # 默认 IV：前12字节为0，后4字节为切片序号
                iv = b'\x00' * 12 + struct.pack('>I', segment_info['index'])

            # AES 解密
            cipher = AES.new(key_data, AES.MODE_CBC, iv)
            decrypted_data = cipher.decrypt(encrypted_data)

            # 去除 PKCS7 填充
            try:
                decrypted_data = unpad(decrypted_data, AES.block_size)
            except ValueError:
                # 如果去填充失败，可能不需要去填充
                pass

            print(f"切片 {segment_info['index']} 解密成功")
            return decrypted_data

        except Exception as e:
            print(f"解密切片 {segment_info['index']} 失败: {e}")
            return encrypted_data

    def download_segment(self, segment_info, output_path):
        """下载并处理单个切片"""
        try:
            print(f"下载切片 {segment_info['index']}: {segment_info['url']}")

            response = requests.get(segment_info['url'], headers=self.headers, timeout=30)
            response.raise_for_status()

            data = response.content

            # 检查是否是有效的 TS 文件
            if not self._is_valid_ts_data(data):
                print(f"警告: 切片 {segment_info['index']} 可能不是有效的 TS 格式")

            # 如果加密，进行解密
            if segment_info['encrypted']:
                data = self.decrypt_segment(data, segment_info)

            # 保存文件
            with open(output_path, 'wb') as f:
                f.write(data)

            print(f"切片 {segment_info['index']} 下载完成，大小: {len(data)} 字节")
            return True

        except Exception as e:
            print(f"下载切片 {segment_info['index']} 失败: {e}")
            return False

    def _is_valid_ts_data(self, data):
        """检查数据是否是有效的 TS 格式"""
        if len(data) < 4:
            return False

        # TS 文件应该以 0x47 开头（同步字节）
        # 但有些文件可能有其他格式，所以这里只是警告
        return data[0] == 0x47

    def download_all_segments(self, output_dir, max_retries=3, progress_callback=None, max_workers=6, resume_mode=False):
        """下载所有切片 - 支持多线程并发下载和断点续传"""
        if not self.segments:
            print("没有可下载的切片")
            return False

        os.makedirs(output_dir, exist_ok=True)
        success_count = 0
        total_segments = len(self.segments)

        # 准备下载任务列表
        download_tasks = []
        failed_segments = []
        
        for segment_info in self.segments:
            filename = f"segment_{segment_info['index']:06d}.ts"
            output_path = os.path.join(output_dir, filename)

            # 检查文件是否存在
            if os.path.exists(output_path):
                # 检查文件是否有效（大小大于0）
                file_size = os.path.getsize(output_path)
                if file_size > 0:
                    print(f"切片 {segment_info['index']} 已存在且有效，跳过")
                    with self._lock:
                        success_count += 1
                        if progress_callback:
                            progress_callback(success_count, total_segments)
                    continue
                else:
                    print(f"切片 {segment_info['index']} 文件大小为0，需要重新下载")
                    os.remove(output_path)  # 删除无效文件

            # 在恢复模式下，记录失败的切片
            if resume_mode:
                failed_segments.append(segment_info['index'])
            
            download_tasks.append((segment_info, output_path, max_retries))

        if not download_tasks:
            print("所有切片已存在，无需下载")
            return True

        if resume_mode and failed_segments:
            print(f"恢复模式：需要重新下载 {len(failed_segments)} 个失败的切片: {failed_segments}")
        else:
            print(f"开始下载 {len(download_tasks)} 个切片，使用 {max_workers} 个线程")

        # 使用线程池并发下载
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_segment = {
                executor.submit(self._download_segment_with_retry, task[0], task[1], task[2]): task[0]
                for task in download_tasks
            }

            # 处理完成的任务
            for future in as_completed(future_to_segment):
                segment_info = future_to_segment[future]
                try:
                    download_success = future.result()
                    if download_success:
                        with self._lock:
                            success_count += 1
                            if progress_callback:
                                progress_callback(success_count, total_segments)
                    else:
                        print(f"切片 {segment_info['index']} 最终下载失败")
                except Exception as e:
                    print(f"切片 {segment_info['index']} 下载异常: {e}")

        final_success_count = success_count
        print(f"下载完成: {final_success_count}/{total_segments} 个切片成功")
        return final_success_count == total_segments

    def _download_segment_with_retry(self, segment_info, output_path, max_retries):
        """带重试的切片下载 - 单个切片单线程下载"""
        retry_count = 0
        while retry_count < max_retries:
            if self.download_segment(segment_info, output_path):
                return True
            else:
                retry_count += 1
                if retry_count < max_retries:
                    print(f"重试下载切片 {segment_info['index']} ({retry_count}/{max_retries})")

        print(f"切片 {segment_info['index']} 下载失败，已达到最大重试次数")
        return False

    def create_local_m3u8(self, output_dir, m3u8_filename="playlist.m3u8"):
        """创建本地 M3U8 文件"""
        m3u8_path = os.path.join(output_dir, m3u8_filename)

        with open(m3u8_path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write("#EXT-X-VERSION:3\n")
            f.write("#EXT-X-TARGETDURATION:10\n")

            for segment_info in self.segments:
                f.write(f"#EXTINF:{segment_info['duration']:.6f},\n")
                f.write(f"segment_{segment_info['index']:06d}.ts\n")

            f.write("#EXT-X-ENDLIST\n")

        print(f"本地 M3U8 文件已创建: {m3u8_path}")
        return m3u8_path

def test_processor():
    """测试函数"""
    # 这里可以添加测试代码
    pass

if __name__ == "__main__":
    test_processor()
