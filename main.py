import random
import subprocess
import threading
import time
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src import downloader_service
from src.comm import *

app = FastAPI(title="流媒体下载器", description="管理视频下载任务")

# 挂载静态文件和模板
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 数据模型
class DownloadTask(BaseModel):
    avid: str

class DownloadStatus(BaseModel):
    avid:  str
    status: str # pending, downloading, completed, failed
    message: str = ""

# 全局状态
current_task = None
download_status: Dict[str, DownloadStatus] = {}
completed_tasks: List[str] = []
failed_tasks: List[str] = []
console_logs: List[str] = []
stop_requested = False
current_processes = []

# 确保队列目录存在
os.makedirs(os.path.dirname(queue_path), exist_ok=True)

def load_queue_from_file() -> List[str]:
    """从文件加载下载队列"""
    try:
        if os.path.exists(queue_path):
            with open(queue_path, "r", encoding="utf-8") as f:
                tasks = [line.strip() for line in f if line.strip()]
            return tasks
        return []
    except Exception as e:
        logger.error(f"加载队列文件失败: {e}")
        return []

def save_queue_to_file(tasks: List[str]):
    """保存队列到文件"""
    try:
        with open(queue_path, "w", encoding="utf-8") as f:
            for task in tasks:
                f.write(task + "\n")
    except Exception as e:
        logger.error(f"保存队列文件失败: {e}")

def remove_task_from_queue(avid: str):
    """从队列文件中移除任务"""
    tasks = load_queue_from_file()
    tasks = [task for task in tasks if task != avid]
    save_queue_to_file(tasks)

def add_console_log(message: str):
    timestamp = time.strftime("%H:%M:%S")
    console_logs.append(f"{timestamp} {message}")
    # 只保留最近200条日志
    if len(console_logs) > 200:
        console_logs.pop(0)

# 自定义日志处理器，将日志重定向到我们的函数
class WebLogHandler:
    def write(self, message):
        if message.strip() and not message.startswith('{'):
            add_console_log(message.strip())

    def flush(self):
        pass

# 重定向标准输出和标准错误
# sys.stdout = WebLogHandler()
# sys.stderr = WebLogHandler()
logger.add(WebLogHandler(), format="{time:HH:mm:ss} | {level} | {message}", level="DEBUG")

def stop_current_task():
    global stop_requested, current_processes
    logger.info("正在停止当前任务……")
    stop_requested = True

    # 停止所有相关进程
    for process in current_processes:
        try:
            if process and process.poll() is None:
                logger.info(f"停止进程：{process.pid}")
                if os.name == 'nt':
                    process.terminate()
                else:
                    process.terminate()

                # 等待进程结束
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("进程为正常终止，强制杀死")
                    process.kill()
        except Exception as e:
            logger.error(f"停止进程时出错：{e}")

    # 清空进程列表
    current_processes.clear()
    # 更新当前任务状态
    if current_task:
        download_status[current_task] = DownloadStatus(
            avid=current_task,
            status="failed",
            message="任务已停止"
        )
        failed_tasks.append(current_task)

    logger.info("当前任务已停止")

def download_worker():
    """后台下载工作线程"""
    global current_task, stop_requested, current_processes

    while True:
        try:
            stop_requested = False
            current_processes.clear()

            tasks = load_queue_from_file()

            if not tasks:
                current_task = None
                time.sleep(10)
                continue

            current_task = tasks[0]
            logger.info(f"开始下载任务: {current_task}")

            download_status[current_task] = DownloadStatus(
                avid = current_task,
                status = "downloading",
                message = "开始下载"
            )

            try:
                downloader_service.download_video(current_task, current_processes)

                if stop_requested:
                    logger.info(f"任务{current_task}被停止")
                    continue

                download_status[current_task] = DownloadStatus(
                    avid = current_task,
                    status = "completed",
                    message = "下载完成"
                )
                completed_tasks.append(current_task)
                logger.info(f"任务完成: {current_task}")
            except Exception as e:
                if stop_requested:
                    logger.info(f"任务 {current_task} 被停止")
                    continue

                error_msg = str(e)
                download_status[current_task] = DownloadStatus(
                    avid = current_task,
                    status = "failed",
                    message = f"下载失败: {error_msg}"
                )
                failed_tasks.append(current_task)
                logger.error(f"任务失败{current_task}: {error_msg}")

            # remove_task_from_queue(current_task)
            # current_task = None
            #
            # wait_time = random.randint(300, 900)
            # logger.info(f"等待{wait_time}秒后继续下一个任务")
            # time.sleep(wait_time)

            if not stop_requested:
                remove_task_from_queue(current_task)
            current_task = None

            if not stop_requested:
                wait_time = random.randint(300, 900)
                logger.info(f"等待{wait_time}秒后继续下一个任务")
                time.sleep(wait_time)

        except Exception as e:
            logger.error(f"下载工作线程错误: {e}")
            time.sleep(60)

download_thread = threading.Thread(target=download_worker, daemon=True)
download_thread.start()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """主页面"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/tasks/")
async def add_task(task: DownloadTask):
    try:
        tasks = load_queue_from_file()

        if task.avid.upper() in tasks:
            raise HTTPException(status_code=400, detail="任务已存在")

        tasks.append(task.avid.upper())
        save_queue_to_file(tasks)

        download_status[task.avid.upper()] = DownloadStatus(
            avid=task.avid.upper(),
            status="pending",
            message="等待下载"
        )
        logger.info(f"已添加任务: {task.avid}")

        return {"message": "任务添加成功", "avid": task.avid}
    except Exception as e:
        logger.error(f"添加任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks/")
async def get_tasks():
    queue_tasks = load_queue_from_file()

    queue_with_status = []
    for avid in queue_tasks:
        status = download_status.get(avid, DownloadStatus(avid=avid, status="pending"))
        queue_with_status.append(status.model_dump())

    completed_with_status = []
    for avid in completed_tasks[-20:]:
        status = download_status.get(avid, DownloadStatus(avid=avid, status="completed"))
        completed_with_status.append(status.model_dump())

    failed_with_status = []
    for avid in failed_tasks[-20:]:
        status = download_status.get(avid, DownloadStatus(avid=avid, status="failed"))
        failed_with_status.append(status.model_dump())

    return {
        "current_task": current_task,
        "queue": queue_with_status,
        "completed": completed_with_status,
        "failed": failed_with_status,
        "logs": console_logs[-100:] # 只返回最近100条日志
    }

@app.post("/clear-failed-tasks/")
async def clear_failed_tasks():
    """清空所有失败任务"""
    try:
        global failed_tasks, download_status

        # 获取当前失败任务的avid列表
        failed_avids = failed_tasks.copy()
        failed_tasks.clear()

        for avid in failed_avids:
            if avid in download_status and download_status[avid].status == "failed":
                del download_status[avid]

        logger.info(f"已清空 {len(failed_avids)} 个失败任务")
        return {
            "message": f"已清空 {len(failed_avids)} 个失败任务",
            "cleared_count": len(failed_avids)
        }
    except Exception as e:
        logger.error(f"清空失败任务时出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/tasks/{avid}")
async def remove_task(avid: str):
    try:
        remove_task_from_queue(avid.upper())
        logger.info(f"已移除任务: {avid}")
        return {"message": "任务移除成功"}
    except Exception as e:
        logger.error(f"移除任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/")
async def get_status():
    return await get_tasks()

@app.post("/stop/")
async def stop_current_download():
    stop_current_task()
    return {"message": "停止请求已发送"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
