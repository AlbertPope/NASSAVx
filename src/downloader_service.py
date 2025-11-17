from . import data
from . import downloaderMgr
from .comm import *


def download_video(avid, force=False, current_processes=None):
    """下载视频的主要函数"""
    logger.info(f"开始下载: {avid}")
    data.initialize_db(downloaded_path, "MissAV")

    # 检查是否已下载
    if not force and data.find_in_db(avid, downloaded_path, "MissAV"):
        logger.info(f"{avid} 已存在于数据库中")
        return True

    mgr = downloaderMgr.DownloaderMgr()
    try:
        if not sorted_downloaders:
            raise ValueError(f"没有配置下载器: {sorted_downloaders}")

        # 检查是否已经存在MP4文件
        mp4_path = os.path.join(save_path, avid, f"{avid}.mp4")
        if os.path.exists(mp4_path):
            logger.info(f"MP4文件已存在：{mp4_path}")
            data.batch_insert_bvids([avid], downloaded_path, "MissAV")
            return True

        for i, it in enumerate(sorted_downloaders):
            downloader = mgr.GetDownloader(it["downloaderName"])
            if not downloader.setDomain(it["domain"]):
                logger.error(f"下载器 {downloader.getDownloaderName()} 没有配置域名")
                continue

            logger.info(f"尝试使用下载器: {downloader.getDownloaderName()}")

            if downloader.downloadDirect(avid, current_processes):
                logger.info(f"下载完成: {avid}")
                data.batch_insert_bvids([avid], downloaded_path, "MissAV")
                # 下载成功，立即跳出循环，不再尝试其他下载器
                return True
            else:
                logger.error(f"下载器 {downloader.getDownloaderName()} 下载失败")
                # 继续尝试下一个下载器

        raise ValueError(f"所有下载器都无法下载 {avid} 的视频")

    except Exception as e:
        logger.error(f"下载 {avid} 时发生错误: {e}")
        raise