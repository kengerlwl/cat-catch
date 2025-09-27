/**
 * M3U8 队列下载管理器
 * 支持队列管理、并发控制、断点续传、任务管理等功能
 */
class M3U8QueueManager {
    constructor(maxConcurrentDownloads = 2) {
        this.maxConcurrentDownloads = maxConcurrentDownloads;
        this.queue = []; // 等待队列
        this.activeDownloads = new Map(); // 活跃下载任务
        this.completedTasks = new Map(); // 已完成任务
        this.failedTasks = new Map(); // 失败任务
        this.pausedTasks = new Map(); // 暂停任务
        this.taskIdCounter = 0;
        this.events = {};
        this.isEnabled = false;

        // 绑定UI事件
        this.bindUIEvents();

        // 初始化UI
        this.initUI();

        // 从本地存储恢复任务
        this.loadTasksFromStorage();
    }

    /**
     * 启用或禁用队列管理
     */
    setEnabled(enabled) {
        this.isEnabled = enabled;
        this.updateUI();

        if (enabled) {
            $('#queueManager').show();
        } else {
            $('#queueManager').hide();
        }
    }

    /**
     * 设置最大并发数
     */
    setMaxConcurrentDownloads(max) {
        this.maxConcurrentDownloads = Math.max(1, Math.min(10, max));
        this.processQueue();
        this.updateUI();
    }

    /**
     * 添加下载任务到队列
     */
    addTask(taskConfig) {
        const task = {
            id: ++this.taskIdCounter,
            title: taskConfig.title || `M3U8 任务 ${this.taskIdCounter}`,
            url: taskConfig.url,
            fragments: taskConfig.fragments || [],
            status: 'queued', // queued, downloading, paused, completed, failed
            progress: 0,
            downloadedFragments: new Set(),
            failedFragments: new Set(),
            createdAt: new Date(),
            updatedAt: new Date(),
            customSettings: {
                thread: taskConfig.thread || 6,
                customKey: taskConfig.customKey,
                customIV: taskConfig.customIV,
                customFilename: taskConfig.customFilename,
                mp4: taskConfig.mp4 || false,
                onlyAudio: taskConfig.onlyAudio || false,
                skipDecrypt: taskConfig.skipDecrypt || false,
                streamSaver: taskConfig.streamSaver || false,
                rangeStart: taskConfig.rangeStart || 0,
                rangeEnd: taskConfig.rangeEnd || taskConfig.fragments.length
            },
            downloader: null,
            resumeData: null
        };

        // 检查是否重复任务
        if (this.isDuplicateTask(task)) {
            this.emit('taskDuplicate', task);
            return null;
        }

        this.queue.push(task);
        this.saveTasksToStorage();
        this.updateUI();
        this.processQueue();

        this.emit('taskAdded', task);
        return task;
    }

    /**
     * 检查是否重复任务
     */
    isDuplicateTask(newTask) {
        const allTasks = [
            ...this.queue,
            ...this.activeDownloads.values(),
            ...this.completedTasks.values()
        ];

        return allTasks.some(task =>
            task.url === newTask.url &&
            task.status !== 'failed' &&
            task.fragments.length === newTask.fragments.length
        );
    }

    /**
     * 处理队列，启动下载
     */
    processQueue() {
        while (this.activeDownloads.size < this.maxConcurrentDownloads && this.queue.length > 0) {
            const task = this.queue.shift();
            this.startDownload(task);
        }
    }

    /**
     * 开始下载任务
     */
    async startDownload(task) {
        try {
            task.status = 'downloading';
            task.updatedAt = new Date();
            this.activeDownloads.set(task.id, task);
            this.updateUI();

            // 加载断点续传数据
            await this.loadResumeData(task);

            // 创建下载器
            const downloader = this.createDownloader(task);

            // 设置事件监听
            this.setupDownloaderEvents(downloader, task);

            // 过滤已下载的片段
            const filteredFragments = task.fragments.filter((fragment, index) =>
                !task.downloadedFragments.has(index) &&
                index >= task.customSettings.rangeStart &&
                index < task.customSettings.rangeEnd
            );

            if (filteredFragments.length === 0) {
                this.completeTask(task);
                return;
            }

            // 重新设置片段索引
            filteredFragments.forEach((fragment, newIndex) => {
                fragment.originalIndex = fragment.index;
                fragment.index = newIndex;
            });

            downloader.fragments = filteredFragments;
            downloader.start();

            this.emit('taskStarted', task);

        } catch (error) {
            this.handleTaskError(task, error);
        }
    }

    /**
     * 创建下载器
     */
    createDownloader(task) {
        const downloader = new Downloader(task.fragments, task.customSettings.thread);

        // 设置解密函数
        if (task.customSettings.customKey) {
            downloader.setDecrypt((buffer, fragment) => {
                return new Promise((resolve, reject) => {
                    try {
                        let key = task.customSettings.customKey;
                        if (typeof key === 'string') {
                            if (isHexKey(key)) {
                                key = HexStringToArrayBuffer(key);
                            } else if (key.length == 24 && key.slice(-2) == "==") {
                                key = Base64ToArrayBuffer(key);
                            }
                        }

                        let iv = task.customSettings.customIV;
                        if (iv && typeof iv === 'string') {
                            iv = HexStringToArrayBuffer(iv);
                        } else {
                            iv = new Uint8Array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, fragment.sn]);
                        }

                        if (typeof decryptor !== 'undefined') {
                            decryptor.expandKey(key);
                            buffer = decryptor.decrypt(buffer, 0, iv.buffer, true);
                        }

                        resolve(buffer);
                    } catch (e) {
                        reject(e);
                    }
                });
            });
        }

        // 如果启用了边下边存，设置流式下载
        if (task.customSettings.streamSaver && typeof fileStream !== 'undefined') {
            downloader.on('sequentialPush', function (buffer) {
                fileStream && fileStream.write(new Uint8Array(buffer));
            });
        }

        return downloader;
    }

    /**
     * 设置下载器事件
     */
    setupDownloaderEvents(downloader, task) {
        // 单个片段完成
        downloader.on('completed', (buffer, fragment) => {
            task.downloadedFragments.add(fragment.originalIndex || fragment.index);
            task.failedFragments.delete(fragment.originalIndex || fragment.index);
            this.updateTaskProgress(task);
            this.saveResumeData(task);
        });

        // 片段下载失败
        downloader.on('downloadError', (fragment, error) => {
            task.failedFragments.add(fragment.originalIndex || fragment.index);
            this.saveResumeData(task);
        });

        // 全部完成
        downloader.on('allCompleted', (buffer) => {
            this.completeTask(task);
        });

        // 下载进度
        downloader.on('itemProgress', (fragment, state, receivedLength, contentLength) => {
            this.updateTaskProgress(task);
        });

        task.downloader = downloader;
    }

    /**
     * 更新任务进度
     */
    updateTaskProgress(task) {
        const totalFragments = task.customSettings.rangeEnd - task.customSettings.rangeStart;
        const completedFragments = task.downloadedFragments.size;
        task.progress = Math.round((completedFragments / totalFragments) * 100);
        task.updatedAt = new Date();
        this.updateUI();
    }

    /**
     * 完成任务
     */
    completeTask(task) {
        task.status = 'completed';
        task.progress = 100;
        task.updatedAt = new Date();

        this.activeDownloads.delete(task.id);
        this.completedTasks.set(task.id, task);

        // 清理断点续传数据
        this.clearResumeData(task);

        this.saveTasksToStorage();
        this.updateUI();
        this.processQueue();

        this.emit('taskCompleted', task);
    }

    /**
     * 任务失败处理
     */
    handleTaskError(task, error) {
        task.status = 'failed';
        task.error = error.message || error;
        task.updatedAt = new Date();

        this.activeDownloads.delete(task.id);
        this.failedTasks.set(task.id, task);

        this.saveTasksToStorage();
        this.updateUI();
        this.processQueue();

        this.emit('taskFailed', task, error);
    }

    /**
     * 暂停任务
     */
    pauseTask(taskId) {
        const task = this.activeDownloads.get(taskId) || this.queue.find(t => t.id === taskId);
        if (!task) return;

        if (task.status === 'downloading' && task.downloader) {
            task.downloader.stop();
        }

        task.status = 'paused';
        task.updatedAt = new Date();

        this.activeDownloads.delete(taskId);
        this.pausedTasks.set(taskId, task);

        // 从队列中移除
        const queueIndex = this.queue.findIndex(t => t.id === taskId);
        if (queueIndex !== -1) {
            this.queue.splice(queueIndex, 1);
        }

        this.saveTasksToStorage();
        this.updateUI();
        this.processQueue();

        this.emit('taskPaused', task);
    }

    /**
     * 恢复任务
     */
    resumeTask(taskId) {
        const task = this.pausedTasks.get(taskId) || this.failedTasks.get(taskId);
        if (!task) return;

        task.status = 'queued';
        task.updatedAt = new Date();

        this.pausedTasks.delete(taskId);
        this.failedTasks.delete(taskId);
        this.queue.push(task);

        this.saveTasksToStorage();
        this.updateUI();
        this.processQueue();

        this.emit('taskResumed', task);
    }

    /**
     * 删除任务
     */
    deleteTask(taskId) {
        // 先暂停任务
        this.pauseTask(taskId);

        // 从所有集合中删除
        this.queue = this.queue.filter(t => t.id !== taskId);
        this.activeDownloads.delete(taskId);
        this.completedTasks.delete(taskId);
        this.failedTasks.delete(taskId);
        this.pausedTasks.delete(taskId);

        // 清理断点续传数据
        this.clearResumeData({ id: taskId });

        this.saveTasksToStorage();
        this.updateUI();
        this.processQueue();

        this.emit('taskDeleted', taskId);
    }

    /**
     * 暂停所有任务
     */
    pauseAll() {
        [...this.activeDownloads.keys(), ...this.queue.map(t => t.id)].forEach(taskId => {
            this.pauseTask(taskId);
        });
    }

    /**
     * 恢复所有任务
     */
    resumeAll() {
        [...this.pausedTasks.keys(), ...this.failedTasks.keys()].forEach(taskId => {
            this.resumeTask(taskId);
        });
    }

    /**
     * 清理已完成任务
     */
    clearCompleted() {
        this.completedTasks.clear();
        this.saveTasksToStorage();
        this.updateUI();
    }

    /**
     * 保存断点续传数据
     */
    saveResumeData(task) {
        const resumeData = {
            downloadedFragments: Array.from(task.downloadedFragments),
            failedFragments: Array.from(task.failedFragments),
            progress: task.progress
        };
        localStorage.setItem(`m3u8_resume_${task.id}`, JSON.stringify(resumeData));
    }

    /**
     * 加载断点续传数据
     */
    async loadResumeData(task) {
        try {
            const resumeData = localStorage.getItem(`m3u8_resume_${task.id}`);
            if (resumeData) {
                const data = JSON.parse(resumeData);
                task.downloadedFragments = new Set(data.downloadedFragments || []);
                task.failedFragments = new Set(data.failedFragments || []);
                task.progress = data.progress || 0;
            }
        } catch (error) {
            console.warn('Failed to load resume data:', error);
        }
    }

    /**
     * 清理断点续传数据
     */
    clearResumeData(task) {
        localStorage.removeItem(`m3u8_resume_${task.id}`);
    }

    /**
     * 保存任务到本地存储
     */
    saveTasksToStorage() {
        const allTasks = {
            queue: this.queue,
            completed: Array.from(this.completedTasks.values()),
            failed: Array.from(this.failedTasks.values()),
            paused: Array.from(this.pausedTasks.values()),
            taskIdCounter: this.taskIdCounter
        };
        localStorage.setItem('m3u8_queue_tasks', JSON.stringify(allTasks));
    }

    /**
     * 从本地存储加载任务
     */
    loadTasksFromStorage() {
        try {
            const data = localStorage.getItem('m3u8_queue_tasks');
            if (data) {
                const allTasks = JSON.parse(data);
                this.queue = allTasks.queue || [];
                this.completedTasks = new Map(allTasks.completed?.map(t => [t.id, t]) || []);
                this.failedTasks = new Map(allTasks.failed?.map(t => [t.id, t]) || []);
                this.pausedTasks = new Map(allTasks.paused?.map(t => [t.id, t]) || []);
                this.taskIdCounter = allTasks.taskIdCounter || 0;

                // 恢复队列中的任务（不自动开始下载）
                this.updateUI();
            }
        } catch (error) {
            console.warn('Failed to load tasks from storage:', error);
        }
    }

    /**
     * 初始化UI
     */
    initUI() {
        // 如果UI不存在，创建UI
        if ($('#queueManager').length === 0) {
            this.createUI();
        }
    }

    /**
     * 创建队列管理UI
     */
    createUI() {
        const queueHTML = `
            <div id="queueManager" class="queue-manager" style="display: none;">
                <div class="queue-header">
                    <h2>M3U8 下载队列管理</h2>
                    <div class="queue-controls">
                        <button id="pauseAllBtn" class="btn btn-warning">暂停全部</button>
                        <button id="resumeAllBtn" class="btn btn-info">恢复全部</button>
                        <button id="clearCompletedBtn" class="btn btn-secondary">清理已完成</button>
                    </div>
                    <div class="queue-stats">
                        <span>队列: <span id="queueCount">0</span></span> |
                        <span>下载中: <span id="activeCount">0</span></span> |
                        <span>已完成: <span id="completedCount">0</span></span> |
                        <span>失败: <span id="failedCount">0</span></span>
                    </div>
                </div>
                <div class="queue-list" id="queueList">
                    <!-- 任务列表将在这里动态生成 -->
                </div>
            </div>
        `;

        // 插入到页面顶部
        $('.m3u8_wrapper').prepend(queueHTML);
    }

    /**
     * 绑定UI事件
     */
    bindUIEvents() {
        $(document).on('click', '#pauseAllBtn', () => this.pauseAll());
        $(document).on('click', '#resumeAllBtn', () => this.resumeAll());
        $(document).on('click', '#clearCompletedBtn', () => this.clearCompleted());

        // 任务操作事件
        $(document).on('click', '.task-pause', (e) => {
            const taskId = parseInt($(e.target).data('task-id'));
            this.pauseTask(taskId);
        });

        $(document).on('click', '.task-resume', (e) => {
            const taskId = parseInt($(e.target).data('task-id'));
            this.resumeTask(taskId);
        });

        $(document).on('click', '.task-delete', (e) => {
            const taskId = parseInt($(e.target).data('task-id'));
            if (confirm('确定要删除这个任务吗？')) {
                this.deleteTask(taskId);
            }
        });
    }

    /**
     * 更新UI显示
     */
    updateUI() {
        if (!this.isEnabled) return;

        // 更新统计信息
        $('#queueCount').text(this.queue.length);
        $('#activeCount').text(this.activeDownloads.size);
        $('#completedCount').text(this.completedTasks.size);
        $('#failedCount').text(this.failedTasks.size);

        // 更新任务列表
        this.updateTaskList();
    }

    /**
     * 更新任务列表
     */
    updateTaskList() {
        const $queueList = $('#queueList');
        $queueList.empty();

        // 收集所有任务
        const allTasks = [
            ...this.queue,
            ...this.activeDownloads.values(),
            ...this.pausedTasks.values(),
            ...this.failedTasks.values(),
            ...this.completedTasks.values()
        ].sort((a, b) => b.updatedAt - a.updatedAt);

        allTasks.forEach(task => {
            const taskHTML = this.createTaskHTML(task);
            $queueList.append(taskHTML);
        });
    }

    /**
     * 创建任务HTML
     */
    createTaskHTML(task) {
        const statusClass = {
            'queued': 'status-queued',
            'downloading': 'status-downloading',
            'paused': 'status-paused',
            'completed': 'status-completed',
            'failed': 'status-failed'
        }[task.status] || '';

        const statusText = {
            'queued': '排队等待',
            'downloading': '下载中',
            'paused': '已暂停',
            'completed': '已完成',
            'failed': '失败'
        }[task.status] || task.status;

        const totalFragments = task.customSettings.rangeEnd - task.customSettings.rangeStart;
        const completedFragments = task.downloadedFragments.size;
        const failedFragments = task.failedFragments.size;

        const actionButtons = this.getActionButtons(task);

        return `
            <div class="task-item ${statusClass}" data-task-id="${task.id}">
                <div class="task-info">
                    <div class="task-title">${task.title}</div>
                    <div class="task-details">
                        <span class="task-status">${statusText}</span>
                        <span class="task-progress">片段: ${completedFragments}/${totalFragments}</span>
                        ${failedFragments > 0 ? `<span class="task-failed">失败: ${failedFragments}</span>` : ''}
                        <span class="task-time">${task.createdAt.toLocaleString()}</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${task.progress}%"></div>
                        <span class="progress-text">${task.progress}%</span>
                    </div>
                </div>
                <div class="task-actions">
                    ${actionButtons}
                </div>
            </div>
        `;
    }

    /**
     * 获取任务操作按钮
     */
    getActionButtons(task) {
        switch (task.status) {
            case 'queued':
                return `
                    <button class="btn btn-sm btn-warning task-pause" data-task-id="${task.id}">暂停</button>
                    <button class="btn btn-sm btn-danger task-delete" data-task-id="${task.id}">删除</button>
                `;
            case 'downloading':
                return `
                    <button class="btn btn-sm btn-warning task-pause" data-task-id="${task.id}">暂停</button>
                    <button class="btn btn-sm btn-danger task-delete" data-task-id="${task.id}">停止</button>
                `;
            case 'paused':
            case 'failed':
                return `
                    <button class="btn btn-sm btn-success task-resume" data-task-id="${task.id}">恢复</button>
                    <button class="btn btn-sm btn-danger task-delete" data-task-id="${task.id}">删除</button>
                `;
            case 'completed':
                return `
                    <button class="btn btn-sm btn-danger task-delete" data-task-id="${task.id}">删除</button>
                `;
            default:
                return '';
        }
    }

    /**
     * 事件监听
     */
    on(eventName, callback) {
        if (!this.events[eventName]) {
            this.events[eventName] = [];
        }
        this.events[eventName].push(callback);
    }

    /**
     * 触发事件
     */
    emit(eventName, ...args) {
        if (this.events[eventName]) {
            this.events[eventName].forEach(callback => {
                try {
                    callback(...args);
                } catch (error) {
                    console.error('Event callback error:', error);
                }
            });
        }
    }

    /**
     * 获取队列状态信息
     */
    getStatus() {
        return {
            isEnabled: this.isEnabled,
            maxConcurrentDownloads: this.maxConcurrentDownloads,
            queueLength: this.queue.length,
            activeDownloads: this.activeDownloads.size,
            completedTasks: this.completedTasks.size,
            failedTasks: this.failedTasks.size,
            pausedTasks: this.pausedTasks.size
        };
    }
}

// 全局队列管理器实例
let queueManager = null;

/**
 * 初始化队列管理器
 */
function initQueueManager() {
    if (!queueManager) {
        queueManager = new M3U8QueueManager(2);

        // 监听队列事件
        queueManager.on('taskAdded', (task) => {
            console.log('任务已添加到队列:', task.title);
        });

        queueManager.on('taskCompleted', (task) => {
            console.log('任务下载完成:', task.title);
            // 调用原有的合并逻辑
            if (task.downloader && task.downloader.buffer && task.downloader.buffer.length > 0) {
                // 临时设置全局变量以兼容原有逻辑
                const originalProgress = $progress.html();
                const originalFileSize = $fileSize.html();
                const originalFileDuration = $fileDuration.html();

                try {
                    mergeTsNew(task.downloader);
                } catch (error) {
                    console.error('合并文件失败:', error);
                    // 恢复原始显示
                    $progress.html(originalProgress);
                    $fileSize.html(originalFileSize);
                    $fileDuration.html(originalFileDuration);
                }
            }
        });

        queueManager.on('taskFailed', (task, error) => {
            console.error('任务下载失败:', task.title, error);
        });

        queueManager.on('taskDuplicate', (task) => {
            alert('任务已存在，请勿重复添加！');
        });
    }

    return queueManager;
}

/**
 * 获取队列管理器实例
 */
function getQueueManager() {
    return queueManager || initQueueManager();
}
