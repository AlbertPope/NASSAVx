from .downloaderBase import *
import re
from typing import Optional, Tuple


class MissAVDownloader(Downloader):
    def getDownloaderName(self) -> str:
        return "MissAV"

    def getHTML(self, avid: str) -> Optional[str]:
        '''需要实现的方法：根据avid，构造url并请求，获取html, 返回字符串'''
        urls_to_try = [
            f'https://{self.domain}/{avid}-uncensored-leak'.lower(),
            f'https://{self.domain}/{avid}-chinese-subtitle'.lower(),
            f'https://{self.domain}/{avid}'.lower(),
            f'https://{self.domain}/dm13/{avid}'.lower()
        ]

        for url in urls_to_try:
            content = self._fetch_html(url)
            if content and self._is_valid_content(content, avid):
                logger.info(f"找到有效页面: {url}")
                return content
            else:
                logger.warning(f"无法获取页面内容: {url}")

        return None

    def _is_valid_content(self, content: str, avid: str) -> bool:
        """检查页面内容是否有效（不是404页面）"""
        # 检查明显的404错误页面特征
        error_indicators = [
            "404", "Not Found", "Page Not Found", "找不到页面"
        ]

        for indicator in error_indicators:
            if indicator.lower() in content.lower():
                return False

        # 检查是否有视频相关的关键词
        video_indicators = [
            "m3u8", "video", "play", "watch", "播放",
            "download", "下载", "player"
        ]

        # 如果包含视频相关关键词，认为是有效页面
        for indicator in video_indicators:
            if indicator.lower() in content.lower():
                return True

        # 检查是否包含番号（不区分大小写）
        if avid.lower() in content.lower():
            return True

        # 如果没有明确的视频特征但也没有404特征，保守起见认为有效
        # 让解析函数进一步判断
        return True

    def parseHTML(self, html: str) -> Optional[AVDownloadInfo]:
        '''需要实现的方法：根据html，解析出元数据，返回AVMetadata'''
        missavMetadata = AVDownloadInfo()

        # 1. 提取m3u8
        if uuid := self._extract_uuid(html):
            playlist_url = f"https://surrit.com/{uuid}/playlist.m3u8"
            result = self._get_highest_quality_m3u8(playlist_url)
            if result:
                m3u8_url, resolution = result
                logger.debug(f"最高清晰度: {resolution}\nM3U8链接: {m3u8_url}")
                missavMetadata.m3u8 = m3u8_url
            else:
                logger.error("未找到有效视频流")
                return None
        else:
            logger.error("未找到有效uuid")
            return None

        # 2. 提取基本信息
        if not self._extract_metadata(html, missavMetadata):
            return None

        return missavMetadata

    @staticmethod
    def _extract_uuid(html: str) -> Optional[str]:
        try:
            if match := re.search(r"m3u8\|([a-f0-9\|]+)\|com\|surrit\|https\|video", html):
                return "-".join(match.group(1).split("|")[::-1])
            return None
        except Exception as e:
            logger.error(f"UUID提取异常: {str(e)}")
            return None

    @staticmethod
    def _extract_metadata(html: str, metadata: AVDownloadInfo) -> bool:
        try:
            # 提取OG标签
            og_title = re.search(r'<meta property="og:title" content="(.*?)"', html)

            if og_title:  # 处理标题和番号
                title_content = og_title.group(1)
                if code_match := re.search(r'^([A-Z]+(?:-[A-Z]+)*-\d+)', title_content):
                    metadata.avid = code_match.group(1)
                    metadata.title = title_content.replace(metadata.avid, '').strip()
                else:
                    metadata.title = title_content.strip()

        except Exception as e:
            logger.error(f"元数据解析异常: {str(e)}")
            return False

        return True

    @staticmethod
    def _get_highest_quality_m3u8(playlist_url: str) -> Optional[Tuple[str, str]]:
        try:
            # 使用新的请求处理器获取m3u8播放列表
            from src.util.request_handler import RequestHandler
            handler = RequestHandler()
            response_bytes = handler.get(playlist_url)
            if not response_bytes:
                return None

            playlist_content = response_bytes.decode('utf-8')

            streams = []
            url_720 = None
            pattern = re.compile(
                r'#EXT-X-STREAM-INF:BANDWIDTH=(\d+),.*?RESOLUTION=(\d+x\d+).*?\n(.*)'
            )

            for match in pattern.finditer(playlist_content):
                bandwidth = int(match.group(1))
                resolution = match.group(2)
                url = match.group(3).strip()
                streams.append((bandwidth, resolution, url))

                if '720' in resolution:
                    url_720 = url

            # 按带宽降序排序
            streams.sort(reverse=True, key=lambda x: x[0])
            logger.debug(streams)

            if streams:
                # 返回最高质量的流
                base_url = playlist_url.rsplit('/', 1)[0]  # 获取基础URL

                if url_720 is not None:
                    full_url = f"{base_url}/{url_720}"
                    resolution = '1280x720'
                else:
                    best_stream = streams[0]
                    full_url = f"{base_url}/{best_stream[2]}" if not best_stream[2].startswith('http') else best_stream[2]
                    resolution = best_stream[1]
                return full_url, resolution
            return None

        except Exception as e:
            logger.error(f"获取最高质量流失败: {str(e)}")
            return None