import random
import subprocess
import threading
import time
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src import downloader_service
from src.comm import *

app = FastAPI(title="流媒体下载器", description="管理视频下载任务")

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
async def read_root():
    """主页面"""
    return """
    <!doctype html>
    <html>
    <head>
        <title>流媒体下载器</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
            .task-form { display: flex; gap: 10px; margin-bottom: 20px; }
            input[type="text"] { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
            button { padding: 8px 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .task-list { list-style: none; padding: 0; }
            .task-item { padding: 8px; margin: 5px 0; background: #f8f9fa; border-radius: 4px; }
            .status-pending { border-left: 4px solid #ffc107; }
            .status-downloading { border-left: 4px solid #007bff; }
            .status-completed { border-left: 4px solid #28a745; }
            .status-failed { border-left: 4px solid #dc3545; }
            .current-task { background: #e3f2fd; font-weight: bold; }
            .log-container { max-height: 400px; overflow-y: auto; background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 4px; font-family: 'Courier New', monospace; font-size: 14px; line-height: 1.4; }
            .log-entry { margin: 2px 0; white-space: pre-wrap; }
            .log-info { color: #569cd6; }
            .log-error { color: #f44747; }
            .log-debug { color: #ce9178; }
            .log-warning { color: #ffcc00; }
            .two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            .control-buttons { display: flex; gap: 10px; margin-top: 10px; }
            @media (max-width: 768px) {
                .two-column { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>视频下载管理器</h1>
            
            <div class="section">
                <h2>添加下载任务</h2>
                <div class="task-form">
                    <input type="text" id="avidInput" placeholder="输入视频番号 (如: AAA-111)" />
                    <button class="btn-primary" onclick="addTask()">添加任务</button>
                </div>
            </div>

            <div class="section">
                <h2>当前下载状态</h2>
                <div id="currentTask">无任务</div>
                <div class="control-buttons">
                    <button class="btn-danger" id="stopButton" onclick="stopTask()" disabled>停止当前任务</button>
                </div>
            </div>

            <div class="two-column">
                <div class="section">
                    <h2>任务状态</h2>
                    
                    <h3>下载队列</h3>
                    <ul class="task-list" id="queueList"></ul>
                    
                    <h3>已完成任务</h3>
                    <ul class="task-list" id="completedList"></ul>
                    
                    <h3>失败任务</h3>
                    <ul class="task-list" id="failedList"></ul>
                </div>

                <div class="section">
                    <h2>实时控制台输出</h2>
                    <div class="log-container" id="logContainer">
                        <div class="log-entry">系统启动中...</div>
                    </div>
                </div>
            </div>
        </div>
    
    <script>
        async function addTask() {
            const avid = document.getElementById('avidInput').value.trim();
            if (!avid) {
                alert('请输入番号');
                return;
            }
            
            try {
                const response = await fetch('/tasks/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ avid: avid })
                });
                if (response.ok) {
                    document.getElementById('avidInput').value = '';
                    updateStatus();
                } else {
                    alert('添加任务失败');
                }
            } catch (error) {
                alert('网络错误: ' + error);
            }
        }
        
        async function stopTask() {
            if (!confirm('确定要停止当前任务吗？')) {
                return;
            }
            try {
                    const response = await fetch('/stop/', {
                        method: 'POST'
                    });
                    
                    if (response.ok) {
                        alert('已发送停止请求');
                        updateStatus();
                    } else {
                        alert('停止请求失败');
                    }
                } catch (error) {
                    alert('网络错误: ' + error);
                }
            }
        
        async function updateStatus() {
                try {
                    const response = await fetch('/status/');
                    const data = await response.json();
                    
                    // 更新当前任务
                    const currentTaskEl = document.getElementById('currentTask');
                    const stopButton = document.getElementById('stopButton');
                    
                    if (data.current_task) {
                        currentTaskEl.textContent = '当前任务: ${data.current_task}';
                        currentTaskEl.className = 'current-task';
                        stopButton.disabled = false;
                    } else {
                        currentTaskEl.textContent = '无任务';
                        currentTaskEl.className = '';
                        stopButton.disabled = true;
                    }
                    
                    // 更新队列
                    updateList('queueList', data.queue);
                    
                    // 更新已完成
                    updateList('completedList', data.completed);
                    
                    // 更新失败
                    updateList('failedList', data.failed);
                    
                    // 更新日志
                    updateLogs(data.logs);
                    
                } catch (error) {
                    console.error('更新状态失败:', error);
                }
            }
        
            function updateList(elementId, items) {
                const listEl = document.getElementById(elementId);
                listEl.innerHTML = '';
                
                items.forEach(item => {
                    const li = document.createElement('li');
                    li.className = `task-item status-${item.status || 'pending'}`;
                    li.textContent = `${item.avid}${item.message ? ' - ' + item.message : ''}`;
                    listEl.appendChild(li);
                });
            }
            
            function updateLogs(logs) {
                const logContainer = document.getElementById('logContainer');
                logContainer.innerHTML = '';
                
                if (logs && logs.length > 0) {
                    logs.forEach(log => {
                        const logEntry = document.createElement('div');
                        logEntry.className = 'log-entry';
                        
                        // 根据日志级别添加样式
                        if (log.includes('ERROR') || log.includes('错误')) {
                            logEntry.className += ' log-error';
                        } else if (log.includes('WARNING') || log.includes('警告')) {
                            logEntry.className += ' log-warning';
                        } else if (log.includes('DEBUG') || log.includes('调试')) {
                            logEntry.className += ' log-debug';
                        } else {
                            logEntry.className += ' log-info';
                        }
                        
                        logEntry.textContent = log;
                        logContainer.appendChild(logEntry);
                    });
                    // 滚动到底部
                    logContainer.scrollTop = logContainer.scrollHeight;
                } else {
                    logContainer.innerHTML = '<div class="log-entry log-info">暂无日志</div>';
                }
            }

            // 每2秒更新一次状态
            setInterval(updateStatus, 2000);
            updateStatus(); // 初始加载
        </script>
    </body>
    </html>
    """

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
