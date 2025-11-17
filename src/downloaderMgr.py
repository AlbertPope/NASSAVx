from typing import Optional

from src.comm import *
from src.downloader.KanAVDownloader import KanAVDownloader
from src.downloader.downloaderBase import Downloader
from src.downloader.hohoJDownloader import HohoJDownloader
from src.downloader.jableDownloader import JableDownloader
from src.downloader.memoDownloader import MemoDownloader
from src.downloader.missAVDownloader import MissAVDownloader


class DownloaderMgr:
    downloaders: dict = {}

    def __init__(self):
        """注册handler"""
        downloader = MissAVDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = JableDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = HohoJDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = MemoDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = KanAVDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

    def GetDownloader(self, downloaderName: str) -> Optional[Downloader]:
        return self.downloaders[downloaderName]
