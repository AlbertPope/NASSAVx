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
            const error = await response.json();
            alert('添加任务失败: ' + (error.detail || '未知错误'));
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

// 增加清空失败任务函数
async function clearFailedTasks(){
    if (!confirm('确定要清空所有失败任务吗？此操作不可恢复。')){
        return;
    }

    try {
        const response = await fetch('/clear-failed-tasks/', {
            method: 'POST'
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message);
            updateStatus();
        } else {
            const error = await response.json();
            alert('清空失败任务失败: ' + (error.detail || '未知错误'));
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
            currentTaskEl.textContent = `当前任务: ${data.current_task}`;
            currentTaskEl.className = 'current-task';
            stopButton.disabled = false;
        } else {
            currentTaskEl.textContent = '无任务';
            currentTaskEl.className = '';
            stopButton.disabled = true;
        }

        // 更新清空按钮状态
        const clearFailedBtn = document.getElementById('clearFailedBtn');
        if (data.failed && data.failed.length > 0) {
            clearFailedBtn.disabled = false;
        } else {
            clearFailedBtn.disabled = true;
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

    if (items.length === 0) {
        const li = document.createElement('li');
        li.className = 'task-item';
        li.textContent = '无任务';
        listEl.appendChild(li);
        return;
    }

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

// 为输入框添加回车键支持
document.getElementById('avidInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        addTask();
    }
});

// 每2秒更新一次状态
setInterval(updateStatus, 2000);
updateStatus(); // 初始加载