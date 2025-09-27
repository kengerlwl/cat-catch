/**
 * MP4 转换器
 * 用于将本地m3u8文件转换为mp4格式
 */

class Mp4Converter {
    constructor() {
        this.tasks = new Map(); // 转换任务列表
        this.activeConversions = new Map(); // 活跃转换任务
        this.maxConcurrent = 2; // 最大并发转换数
        this.taskIdCounter = 0;
        this.settings = {
            onlyAudio: false,
            useFFmpeg: true,
            keepOriginalName: true,
            outputDir: '',
            maxConcurrent: 2
        };

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadSettings();
        this.showInterface();
        this.updateUI();
    }

    bindEvents() {
        // 文件选择
        $('#fileInput').on('change', (e) => {
            this.handleFileSelect(e.target.files);
        });

        // 添加文件按钮
        $('#addFiles').click(() => {
            $('#fileInput').click();
        });

        // 清空列表
        $('#clearAll').click(() => {
            this.clearAllTasks();
        });

        // 拖拽支持
        this.setupDragDrop();

        // 设置变更
        $('#onlyAudio').on('change', (e) => {
            this.settings.onlyAudio = e.target.checked;
            this.saveSettings();
        });

        $('#useFFmpeg').on('change', (e) => {
            this.settings.useFFmpeg = e.target.checked;
            this.saveSettings();
        });

        $('#keepOriginalName').on('change', (e) => {
            this.settings.keepOriginalName = e.target.checked;
            this.saveSettings();
        });

        $('#maxConcurrent').on('change', (e) => {
            this.settings.maxConcurrent = parseInt(e.target.value);
            this.maxConcurrent = this.settings.maxConcurrent;
            this.saveSettings();
        });

        // 输出目录选择
        $('#selectOutputDir').click(() => {
            this.selectOutputDirectory();
        });

        // 转换控制按钮
        $('#startAllConversion').click(() => {
            this.startAllConversions();
        });

        $('#pauseAllConversion').click(() => {
            this.pauseAllConversions();
        });

        $('#stopAllConversion').click(() => {
            this.stopAllConversions();
        });

        $('#removeCompleted').click(() => {
            this.removeCompletedTasks();
        });

        $('#removeFailed').click(() => {
            this.removeFailedTasks();
        });
    }

    setupDragDrop() {
        const dragDropArea = $('#dragDropArea')[0];

        dragDropArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            dragDropArea.classList.add('drag-over');
        });

        dragDropArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragDropArea.classList.remove('drag-over');
        });

        dragDropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            dragDropArea.classList.remove('drag-over');

            const files = Array.from(e.dataTransfer.files);
            this.handleFileSelect(files);
        });
    }

    handleFileSelect(files) {
        const validFiles = Array.from(files).filter(file => {
            const ext = file.name.toLowerCase().split('.').pop();
            return ext === 'm3u8' || ext === 'ts';
        });

        if (validFiles.length === 0) {
            alert('请选择有效的m3u8或ts文件');
            return;
        }

        validFiles.forEach(file => {
            this.addTask(file);
        });

        this.updateUI();
    }

    addTask(file) {
        const taskId = ++this.taskIdCounter;

        const task = {
            id: taskId,
            file: file,
            fileName: file.name,
            status: 'pending', // pending, converting, completed, failed, paused
            progress: 0,
            error: null,
            startTime: null,
            endTime: null,
            outputFile: null,
            converter: null
        };

        this.tasks.set(taskId, task);
        return task;
    }

    removeTask(taskId) {
        const task = this.tasks.get(taskId);
        if (task && task.converter) {
            task.converter.stop();
        }

        this.tasks.delete(taskId);
        this.activeConversions.delete(taskId);
        this.updateUI();
    }

    clearAllTasks() {
        // 停止所有活跃转换
        this.activeConversions.forEach((task, taskId) => {
            if (task.converter) {
                task.converter.stop();
            }
        });

        this.tasks.clear();
        this.activeConversions.clear();
        this.updateUI();
    }

    startAllConversions() {
        const pendingTasks = Array.from(this.tasks.values()).filter(task =>
            task.status === 'pending' || task.status === 'failed'
        );

        pendingTasks.forEach(task => {
            this.startConversion(task.id);
        });
    }

    pauseAllConversions() {
        this.activeConversions.forEach((task, taskId) => {
            this.pauseConversion(taskId);
        });
    }

    stopAllConversions() {
        this.activeConversions.forEach((task, taskId) => {
            this.stopConversion(taskId);
        });
    }

    startConversion(taskId) {
        const task = this.tasks.get(taskId);
        if (!task || this.activeConversions.size >= this.maxConcurrent) {
            return;
        }

        task.status = 'converting';
        task.startTime = new Date();
        task.progress = 0;
        task.error = null;

        this.activeConversions.set(taskId, task);

        // 创建转换器
        task.converter = new FileConverter(task, this.settings);

        // 设置事件监听
        task.converter.on('progress', (progress) => {
            task.progress = progress;
            this.updateTaskUI(taskId);
            this.updateGlobalProgress();
        });

        task.converter.on('completed', (outputFile) => {
            task.status = 'completed';
            task.endTime = new Date();
            task.outputFile = outputFile;
            task.progress = 100;

            this.activeConversions.delete(taskId);
            this.updateTaskUI(taskId);
            this.updateGlobalProgress();

            // 启动下一个任务
            this.processQueue();
        });

        task.converter.on('error', (error) => {
            task.status = 'failed';
            task.error = error;
            task.endTime = new Date();

            this.activeConversions.delete(taskId);
            this.updateTaskUI(taskId);
            this.updateGlobalProgress();

            // 启动下一个任务
            this.processQueue();
        });

        // 开始转换
        task.converter.start();
        this.updateTaskUI(taskId);
        this.updateGlobalProgress();
    }

    pauseConversion(taskId) {
        const task = this.tasks.get(taskId);
        if (task && task.converter) {
            task.converter.pause();
            task.status = 'paused';
            this.activeConversions.delete(taskId);
            this.updateTaskUI(taskId);
        }
    }

    stopConversion(taskId) {
        const task = this.tasks.get(taskId);
        if (task && task.converter) {
            task.converter.stop();
            task.status = 'pending';
            task.progress = 0;
            this.activeConversions.delete(taskId);
            this.updateTaskUI(taskId);
        }
    }

    processQueue() {
        // 检查是否有待处理的任务
        const pendingTasks = Array.from(this.tasks.values()).filter(task =>
            task.status === 'pending'
        );

        // 启动新任务直到达到最大并发数
        while (this.activeConversions.size < this.maxConcurrent && pendingTasks.length > 0) {
            const nextTask = pendingTasks.shift();
            this.startConversion(nextTask.id);
        }
    }

    removeCompletedTasks() {
        const completedTasks = Array.from(this.tasks.entries()).filter(([id, task]) =>
            task.status === 'completed'
        );

        completedTasks.forEach(([id, task]) => {
            this.tasks.delete(id);
        });

        this.updateUI();
    }

    removeFailedTasks() {
        const failedTasks = Array.from(this.tasks.entries()).filter(([id, task]) =>
            task.status === 'failed'
        );

        failedTasks.forEach(([id, task]) => {
            this.tasks.delete(id);
        });

        this.updateUI();
    }

    selectOutputDirectory() {
        // 在浏览器环境中，我们不能直接选择目录
        // 这里提供一个输入框让用户手动输入
        const dir = prompt('请输入输出目录路径:', this.settings.outputDir);
        if (dir !== null) {
            this.settings.outputDir = dir;
            $('#outputDir').val(dir);
            this.saveSettings();
        }
    }

    showInterface() {
        $('#loading').hide();
        $('#converter').show();
    }

    updateUI() {
        this.updateTaskList();
        this.updateGlobalProgress();
        this.updateEmptyState();
    }

    updateTaskList() {
        const taskList = $('#taskList');

        if (this.tasks.size === 0) {
            taskList.html('<div class="empty-state"><p>暂无转换任务，请先添加文件</p></div>');
            return;
        }

        let html = '';
        this.tasks.forEach((task, taskId) => {
            html += this.generateTaskHTML(task);
        });

        taskList.html(html);

        // 绑定任务控制事件
        this.bindTaskEvents();
    }

    generateTaskHTML(task) {
        const statusText = this.getStatusText(task.status);
        const statusClass = `status-${task.status}`;
        const progressWidth = task.progress || 0;

        return `
            <div class="task-item" data-task-id="${task.id}">
                <div class="task-header">
                    <div class="task-info">
                        <span class="task-name">${task.fileName}</span>
                        <span class="task-status ${statusClass}">${statusText}</span>
                    </div>
                    <div class="task-controls">
                        ${this.generateTaskControlButtons(task)}
                        <button class="btn-remove" data-task-id="${task.id}">删除</button>
                    </div>
                </div>
                <div class="task-progress">
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: ${progressWidth}%;"></div>
                    </div>
                    <span class="progress-text">${progressWidth.toFixed(1)}%</span>
                </div>
                ${task.error ? `<div class="task-error">错误: ${task.error}</div>` : ''}
                ${task.outputFile ? `<div class="task-output">输出: ${task.outputFile}</div>` : ''}
            </div>
        `;
    }

    generateTaskControlButtons(task) {
        switch (task.status) {
            case 'pending':
            case 'failed':
                return `<button class="btn-start" data-task-id="${task.id}">开始</button>`;
            case 'converting':
                return `
                    <button class="btn-pause" data-task-id="${task.id}">暂停</button>
                    <button class="btn-stop" data-task-id="${task.id}">停止</button>
                `;
            case 'paused':
                return `<button class="btn-resume" data-task-id="${task.id}">继续</button>`;
            case 'completed':
                return `<button class="btn-restart" data-task-id="${task.id}">重新转换</button>`;
            default:
                return '';
        }
    }

    bindTaskEvents() {
        // 任务控制按钮事件
        $('.btn-start, .btn-resume, .btn-restart').off('click').on('click', (e) => {
            const taskId = parseInt(e.target.dataset.taskId);
            this.startConversion(taskId);
        });

        $('.btn-pause').off('click').on('click', (e) => {
            const taskId = parseInt(e.target.dataset.taskId);
            this.pauseConversion(taskId);
        });

        $('.btn-stop').off('click').on('click', (e) => {
            const taskId = parseInt(e.target.dataset.taskId);
            this.stopConversion(taskId);
        });

        $('.btn-remove').off('click').on('click', (e) => {
            const taskId = parseInt(e.target.dataset.taskId);
            this.removeTask(taskId);
        });
    }

    updateTaskUI(taskId) {
        const task = this.tasks.get(taskId);
        if (!task) return;

        const taskElement = $(`.task-item[data-task-id="${taskId}"]`);
        if (taskElement.length > 0) {
            taskElement.replaceWith(this.generateTaskHTML(task));
            this.bindTaskEvents();
        }
    }

    updateGlobalProgress() {
        const totalTasks = this.tasks.size;
        const completedTasks = Array.from(this.tasks.values()).filter(task =>
            task.status === 'completed'
        ).length;

        let totalProgress = 0;
        this.tasks.forEach(task => {
            totalProgress += task.progress || 0;
        });

        const avgProgress = totalTasks > 0 ? totalProgress / totalTasks : 0;

        $('#globalProgress').text(`总体进度: ${avgProgress.toFixed(1)}%`);
        $('#globalStats').text(`${completedTasks}/${totalTasks} 完成`);
        $('#globalProgressBar').css('width', `${avgProgress}%`);
    }

    updateEmptyState() {
        if (this.tasks.size === 0) {
            $('#taskList').html('<div class="empty-state"><p>暂无转换任务，请先添加文件</p></div>');
        }
    }

    getStatusText(status) {
        const statusMap = {
            'pending': '等待中',
            'converting': '转换中',
            'completed': '已完成',
            'failed': '失败',
            'paused': '已暂停'
        };
        return statusMap[status] || status;
    }

    loadSettings() {
        const saved = localStorage.getItem('Mp4Converter_settings');
        if (saved) {
            this.settings = { ...this.settings, ...JSON.parse(saved) };
        }

        // 应用设置到UI
        $('#onlyAudio').prop('checked', this.settings.onlyAudio);
        $('#useFFmpeg').prop('checked', this.settings.useFFmpeg);
        $('#keepOriginalName').prop('checked', this.settings.keepOriginalName);
        $('#outputDir').val(this.settings.outputDir);
        $('#maxConcurrent').val(this.settings.maxConcurrent);

        this.maxConcurrent = this.settings.maxConcurrent;
    }

    saveSettings() {
        localStorage.setItem('Mp4Converter_settings', JSON.stringify(this.settings));
    }
}

// 文件转换器类
class FileConverter {
    constructor(task, settings) {
        this.task = task;
        this.settings = settings;
        this.events = {};
        this.isRunning = false;
        this.isPaused = false;
    }

    on(eventName, callback) {
        if (!this.events[eventName]) {
            this.events[eventName] = [];
        }
        this.events[eventName].push(callback);
    }

    emit(eventName, ...args) {
        if (this.events[eventName]) {
            this.events[eventName].forEach(callback => {
                callback(...args);
            });
        }
    }

    async start() {
        if (this.isRunning) return;

        this.isRunning = true;
        this.isPaused = false;

        try {
            await this.convertFile();
        } catch (error) {
            this.emit('error', error.message);
        }
    }

    pause() {
        this.isPaused = true;
    }

    stop() {
        this.isRunning = false;
        this.isPaused = false;
    }

    async convertFile() {
        // 模拟转换过程
        const file = this.task.file;

        // 读取文件内容
        const content = await this.readFile(file);

        // 解析m3u8或处理ts文件
        if (file.name.toLowerCase().endsWith('.m3u8')) {
            await this.convertM3u8(content);
        } else if (file.name.toLowerCase().endsWith('.ts')) {
            await this.convertTs(content);
        }
    }

    async readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = (e) => reject(new Error('文件读取失败'));
            reader.readAsText(file);
        });
    }

    async convertM3u8(content) {
        // 模拟M3U8转换过程
        const lines = content.split('\n');
        const tsFiles = lines.filter(line => line.trim() && !line.startsWith('#'));

        for (let i = 0; i < tsFiles.length; i++) {
            if (!this.isRunning || this.isPaused) {
                return;
            }

            // 模拟处理每个TS文件
            await this.delay(100); // 模拟处理时间

            const progress = ((i + 1) / tsFiles.length) * 100;
            this.emit('progress', progress);
        }

        // 模拟最终合并
        await this.delay(500);

        const outputFileName = this.generateOutputFileName();
        this.emit('completed', outputFileName);
    }

    async convertTs(content) {
        // 模拟TS文件转换
        for (let i = 0; i <= 100; i += 10) {
            if (!this.isRunning || this.isPaused) {
                return;
            }

            await this.delay(200);
            this.emit('progress', i);
        }

        const outputFileName = this.generateOutputFileName();
        this.emit('completed', outputFileName);
    }

    generateOutputFileName() {
        const originalName = this.task.fileName;
        const nameWithoutExt = originalName.replace(/\.[^/.]+$/, "");
        const ext = this.settings.onlyAudio ? 'mp3' : 'mp4';

        if (this.settings.keepOriginalName) {
            return `${nameWithoutExt}.${ext}`;
        } else {
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            return `converted_${timestamp}.${ext}`;
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// 初始化转换器
$(document).ready(function() {
    window.mp4Converter = new Mp4Converter();
});
