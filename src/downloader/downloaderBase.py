# doc: 定义下载类的基础操作
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from curl_cffi import requests

from src.comm import *


# 下载信息，只保留最基础的信息。只需要填写avid，其他字段用于调试，选填
@dataclass
class AVDownloadInfo:
    m3u8: str = ""
    title: str = ""
    avid: str = ""

    def __str__(self):
        return (
            f"=== 元数据详情 ===\n"
            f"番号: {self.avid or '未知'}\n"
            f"标题: {self.title or '未知'}\n"
            f"M3U8: {self.m3u8 or '无'}"
        )

    def to_json(self, file_path: str, indent: int = 2) -> bool:
        try:
            path = Path(file_path) if isinstance(file_path, str) else file_path
            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open("w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=indent)
            return True
        except (IOError, TypeError) as e:
            logger.error(f"JSON序列化失败: {str(e)}")
            return False

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

class Downloader(ABC):
    """
    使用方式：
    1. downloadInfo生成元数据，并序列化到download_info.json
    2. downloadM3u8下载视频并转成mp4格式
    """
    def __init__(self, path: str, proxy = None, timeout = 15):
        """
        :path: 配置的路径，如/vol1/1000/Video
        :avid: 车牌号
        """
        self.path = path
        self.proxy = proxy
        self.proxies = {
            'http': proxy,
            'https': proxy
        } if proxy else None
        self.timeout = timeout

    def setDomain(self, domain: str) -> bool:
        if domain:
            self.domain = domain
            return True
        return False

    @abstractmethod
    def getDownloaderName(self) -> str:
        pass

    @abstractmethod
    def getHTML(self, avid: str) -> Optional[str]:
        """需要实现的方法：根据avid，构造url并请求，获取html"""
        pass

    @abstractmethod
    def parseHTML(self, html: str) -> Optional[AVDownloadInfo]:
        """
        需要实现的方法：根据html，解析出元数据，返回AVDownloadInfo
        注意：实现新的downloader，只需要获取到m3u8就行了（也可以多匹配点方便调试），元数据同一使用MissAV
        """
        pass

    def downloadDirect(self, avid: str, current_processes=None) -> bool:
        '''直接下载视频，不保存元数据'''
        # 获取html
        avid = avid.upper()
        os.makedirs(os.path.join(self.path, avid), exist_ok=True)

        logger.info("正在获取视频信息...")

        html = self.getHTML(avid)
        if not html:
            logger.error("获取html失败")
            return False

        # 从html中解析m3u8链接
        logger.info("视频信息获取成功，正在解析m3u8链接...")

        info = self.parseHTML(html)
        if info is None or not info.m3u8:
            logger.error("解析m3u8链接失败")
            return False

        # 直接下载m3u8
        logger.info(f"找到m3u8链接，开始下载: {info.m3u8}")

        return self.downloadM3u8(info.m3u8, avid, current_processes)

    def downloadInfo(self, avid:str) -> Optional[AVDownloadInfo]:
        """将元数据download_info.json序列化到到对应位置，同时返回AVDownloadInfo"""
        #获取html
        avid = avid.upper()
        print(os.path.join(self.path, avid))
        os.makedirs(os.path.join(self.path, avid), exist_ok=True)
        html = self.getHTML(avid)
        if not html:
            logger.error("获取html失败")
            return None
        with open(os.path.join(self.path, avid, avid+".html"), "w+", encoding="utf-8") as f:
            f.write(html)

        # 从html中解析元数据，返回 MissAVInfo 结构体
        info = self.parseHTML(html)
        if info is None:
            logger.error("解析元数据失败")
            return None

        info.avid = info.avid.upper() # 强制大写
        info.to_json(os.path.join(self.path, avid, "download_info.json"))
        logger.info("已保存到download_info.json")

        return info

    def downloadM3u8(self, url: str, avid: str, current_processes=None) -> bool:
        """m3u8视频下载"""
        os.makedirs(os.path.dirname(os.path.join(self.path, avid)), exist_ok=True)
        try:
            logger.info("开始下载视频流……")
            if isNeedVideoProxy and self.proxy:
                logger.info("使用代理")
                command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -p {self.proxy} -H Referer:http://{self.domain}"
            else:
                logger.info("不使用代理")
                command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -H Referer:http://{self.domain}"
            logger.debug(f"执行命令: {command}")

            # 使用subprocess运行命令并捕获输出
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            # 保存进程引用以便可以停止它
            if current_processes is not None:
                current_processes.append(process)
            # 实时读取输出
            for line in iter(process.stdout.readline, ''):
                if line.strip():
                    logger.info(f"[下载工具] {line.strip()}")

            process.stdout.close()
            return_code = process.wait()

            if current_processes is not None and process in current_processes:
                current_processes.remove(process)

            if return_code != 0:
                # 难顶。。。使用代理下载失败，尝试不用代理；不用代理下载失败，尝试使用代理
                # 下载失败，尝试备用方案
                logger.info("第一次下载失败，尝试备用方案...")

                if not isNeedVideoProxy and self.proxy:
                    logger.info("尝试使用代理")
                    command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid + '.ts')} -p {self.proxy} -H Referer:http://{self.domain}"
                else:
                    logger.info("尝试不使用代理")
                    command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -H Referer:http://{self.domain}"
                logger.debug(f"重试命令 {command}")

                # 再次尝试
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                # 保存进程引用以便可以停止它
                if current_processes is not None:
                    current_processes.append(process)
                # 实时读取输出
                for line in iter(process.stdout.readline, ''):
                    if line.strip():
                        logger.info(f"[下载工具] {line.strip()}")

                process.stdout.close()
                return_code = process.wait()

                # 从进程列表中移除
                if current_processes is not None and process in current_processes:
                    current_processes.remove(process)

                if return_code != 0:
                    logger.error("下载失败")
                    return False

            logger.info("视频流下载完成，开始转码为MP4")

            # 转mp4
            convert = f"{ffmpeg_tool} -i {os.path.join(self.path, avid, avid+'.ts')} -c copy -f mp4 {os.path.join(self.path, avid, avid+'.mp4')}"
            logger.debug(f"转码命令: {convert}")

            # 使用subprocess运行ffmpeg并捕获输出
            process = subprocess.Popen(
                convert,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            # 保存进程引用以便可以停止它
            if current_processes is not None:
                current_processes.append(process)
            # 实时读取ffmpeg输出
            for line in iter(process.stdout.readline, ''):
                if line.strip():
                    logger.info(f"[FFmpeg] {line.strip()}")

            process.stdout.close()
            return_code = process.wait()

            # 从进程列表中移除
            if current_processes is not None and process in current_processes:
                current_processes.remove(process)

            if return_code != 0:
                logger.error("转码失败")
                return False

            logger.info("转码完成，清理临时文件...")
            ts_path = os.path.join(self.path, avid, avid+'.ts')
            try:
                if os.path.exists(ts_path):
                    os.remove(ts_path)
                    logger.info("临时文件清理完成")
            except Exception as e:
                logger.warning(f"清理临时文件失败：{e}")

            # 检查最终mp4文件是否存在
            mp4_path = os.path.join(self.path, avid, avid+'.mp4')
            if os.path.exists(mp4_path):
                logger.info("下载完成")
                return True
            else:
                logger.error("MP4文件未生成")
                return False
        except Exception as e:
            logger.error(f"下载过程异常：{e}")
            return False

    def _fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        logger.debug(f"fetch url: {url}")
        try:
            newHeader = headers
            if referer:
                newHeader["Referer"] = referer
            response = requests.get(
                url,
                proxies=self.proxies,
                headers=newHeader,
                timeout=self.timeout,
                impersonate="chrome110" # 可选：chrome, chrome110, edge99, safari15_5
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {str(e)}")
            return None