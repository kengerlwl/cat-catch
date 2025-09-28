/**
 * M3U8 下载管理器前端脚本
 */

class M3U8Manager {
    constructor() {
        this.tasks = [];
        this.currentEditTaskId = null;
        this.refreshInterval = null;
        this.fastRefreshInterval = null;
        this.hasActiveTasks = false;
        // 新增：保存选中状态，从本地存储恢复
        this.selectedTaskIds = this.loadSelectionFromStorage();

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadTasks();
        this.startAutoRefresh();
    }

    bindEvents() {
        // 添加任务
        $('#addTaskBtn').click(() => this.addTask());

        // 刷新任务列表
        $('#refreshBtn').click(() => this.manualRefresh());

        // 批量操作相关
        $('#selectAllTasks').change(() => this.toggleSelectAll());
        $('#batchPauseBtn').click(() => this.batchPause());
        $('#batchResumeBtn').click(() => this.batchResume());
        $('#batchConvertBtn').click(() => this.batchConvert());
        $('#batchDeleteBtn').click(() => this.batchDelete());

        // 任务复选框变化事件（使用事件委托）
        $(document).on('change', '.task-checkbox', (e) => {
            const taskId = $(e.target).data('task-id');
            if ($(e.target).prop('checked')) {
                this.selectedTaskIds.add(taskId);
            } else {
                this.selectedTaskIds.delete(taskId);
            }
            this.saveSelectionToStorage();
            this.updateBatchControls();
        });

        // 设置相关
        $('#settingsBtn').click(() => this.showSettings());
        $('#closeSettingsBtn').click(() => this.hideSettings());
        $('#saveSettingsBtn').click(() => this.saveSettings());
        $('#resetSettingsBtn').click(() => this.resetSettings());
        $('#queueStatusBtn').click(() => this.updateQueueStatus());

        // 模态框关闭
        $('.close').click(function() {
            $(this).closest('.modal').hide();
        });

        // 点击模态框外部关闭
        $('.modal').click(function(e) {
            if (e.target === this) {
                $(this).hide();
            }
        });

        // 编辑任务相关
        $('#saveEditBtn').click(() => this.saveEdit());
        $('#cancelEditBtn').click(() => this.cancelEdit());

        // 批量转换模态框相关
        $('#stopBatchConvertBtn').click(() => this.stopBatchConvert());
        $('#closeBatchConvertBtn').click(() => this.closeBatchConvertModal());

        // 回车键添加任务
        $('#m3u8Url').keypress((e) => {
            if (e.which === 13) {
                this.addTask();
            }
        });

        // 设置变化时同步任务线程数
        $('#threadCount').change(() => {
            $('#taskThreadCount').val($('#threadCount').val());
        });
    }

    async addTask() {
        const url = $('#m3u8Url').val().trim();
        const title = $('#taskTitle').val().trim();
        const customDir = $('#customDir').val().trim();
        const threadCount = parseInt($('#taskThreadCount').val()) || 6;

        if (!url) {
            this.showNotification('请输入M3U8链接', 'error');
            return;
        }

        if (!this.isValidUrl(url)) {
            this.showNotification('请输入有效的URL', 'error');
            return;
        }

        try {
            $('#addTaskBtn').prop('disabled', true).html('🔄 添加中...');

            const response = await fetch('/api/tasks', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: url,
                    title: title,
                    custom_dir: customDir,
                    thread_count: threadCount
                })
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('任务添加成功', 'success');
                this.clearForm();
                this.loadTasks();
                this.updateQueueStatus();
            } else {
                this.showNotification(data.error || '添加任务失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        } finally {
            $('#addTaskBtn').prop('disabled', false).html('🚀 添加任务');
        }
    }

    async loadTasks() {
        try {
            const response = await fetch('/api/tasks');
            const data = await response.json();

            if (response.ok) {
                if (data.database_initializing) {
                    // 数据库正在初始化，显示提示并稍后重试
                    this.tasks = [];
                    this.renderInitializingState();

                    // 3秒后重试
                    setTimeout(() => this.loadTasks(), 3000);
                    return;
                }

                this.tasks = data.tasks;
                this.renderTasks();
                this.updateTaskCount();

                // 检查是否有活跃任务（下载中、等待中、排队中）
                const activeTaskStates = ['downloading', 'pending', 'queued'];
                const hasActiveTasksNow = this.tasks.some(task => activeTaskStates.includes(task.status));

                // 如果活跃任务状态发生变化，调整刷新策略
                if (hasActiveTasksNow !== this.hasActiveTasks) {
                    this.hasActiveTasks = hasActiveTasksNow;
                    this.adjustRefreshStrategy();
                }
            } else {
                this.showNotification('加载任务失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        }
    }

    renderInitializingState() {
        const $tasksList = $('#tasksList');
        $tasksList.html(`
            <div class="empty-state">
                <h3>🔄 系统初始化中...</h3>
                <p>正在创建数据库和配置文件，请稍候...</p>
                <div class="spinner-border text-primary" role="status">
                    <span class="sr-only">Loading...</span>
                </div>
            </div>
        `);
        $('#taskCount').text('系统初始化中...');
    }

    renderTasks() {
        const $tasksList = $('#tasksList');

        if (this.tasks.length === 0) {
            $tasksList.html(`
                <div class="empty-state">
                    <h3>📭 暂无下载任务</h3>
                    <p>添加您的第一个M3U8下载任务吧！</p>
                </div>
            `);
            // 清空选中状态和批量控件状态
            this.selectedTaskIds.clear();
            this.saveSelectionToStorage();
            $('#selectedCount').text('已选择 0 个任务');
            $('#selectAllTasks').prop('checked', false).prop('indeterminate', false);
            $('.batch-actions .btn').prop('disabled', true);
            return;
        }

        // 清理不存在的任务ID
        const currentTaskIds = new Set(this.tasks.map(task => task.task_id));
        const originalSize = this.selectedTaskIds.size;
        this.selectedTaskIds = new Set([...this.selectedTaskIds].filter(id => currentTaskIds.has(id)));

        // 如果清理了一些任务ID，保存到本地存储
        if (this.selectedTaskIds.size !== originalSize) {
            this.saveSelectionToStorage();
        }

        const tasksHtml = this.tasks.map(task => this.renderTaskItem(task)).join('');
        $tasksList.html(tasksHtml);

        // 恢复选中状态
        this.restoreSelectionState();

        // 渲染完成后更新批量控件状态
        setTimeout(() => this.updateBatchControls(), 0);
    }

    renderTaskItem(task) {
        const statusText = this.getStatusText(task.status);
        const statusClass = `status-${task.status}`;
        const createdAt = new Date(task.created_at).toLocaleString();

        return `
            <div class="task-item" data-task-id="${task.task_id}">
                <div class="task-checkbox-container">
                    <input type="checkbox" class="task-checkbox" data-task-id="${task.task_id}">
                </div>
                <div class="task-content">
                    <div class="task-header">
                        <h3 class="task-title">${this.escapeHtml(task.title)}</h3>
                        <span class="task-status ${statusClass}">${statusText}</span>
                    </div>

                    <div class="task-info">
                        <div class="info-row">
                            <span class="info-label">进度:</span>
                            <span class="info-value">${task.progress}% (${task.downloaded_segments}/${task.total_segments})</span>
                            ${task.status === 'downloading' ? `
                                <span class="info-label">速度:</span>
                                <span class="info-value">${this.formatSpeed(task.download_speed || 0)}</span>
                            ` : ''}
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill ${task.status === 'downloading' ? 'active' : ''}" style="width: ${task.progress}%"></div>
                        </div>
                        <div class="info-row">
                            <span class="info-label">线程数:</span>
                            <span class="info-value">${task.thread_count || 6}</span>
                            <span class="info-label">创建时间:</span>
                            <span class="info-value">${createdAt}</span>
                            ${task.file_size > 0 ? `
                                <span class="info-label">文件大小:</span>
                                <span class="info-value">${this.formatFileSize(task.file_size)}</span>
                            ` : ''}
                            ${task.is_converted ? `
                                <span class="info-label">转换时间:</span>
                                <span class="info-value">${new Date(task.converted_at).toLocaleString()}</span>
                            ` : ''}
                        </div>
                        ${task.status === 'downloading' && task.total_segments > 0 ? `
                            <div class="info-row">
                                <span class="info-label">预计剩余:</span>
                                <span class="info-value">${this.estimateRemainingTime(task)}</span>
                            </div>
                        ` : ''}
                        ${task.error_message ? `
                            <div class="info-row">
                                <span class="info-label">错误信息:</span>
                                <span class="info-value" style="color: #dc3545;">${this.escapeHtml(task.error_message)}</span>
                            </div>
                        ` : ''}
                    </div>

                    <div class="task-url">${this.escapeHtml(task.url)}</div>

                    <div class="task-actions">
                        ${this.renderTaskActions(task)}
                    </div>
                </div>
            </div>
        `;
    }

    renderTaskActions(task) {
        const actions = [];

        // 根据任务状态显示不同的操作按钮
        switch (task.status) {
            case 'downloading':
                actions.push(`<button class="btn btn-warning" onclick="manager.pauseTask('${task.task_id}')">⏸️ 暂停</button>`);
                break;
            case 'paused':
                actions.push(`<button class="btn btn-success" onclick="manager.resumeTask('${task.task_id}')">▶️ 恢复</button>`);
                break;
            case 'completed':
                if (task.is_converted) {
                    actions.push(`<button class="btn btn-success" disabled>✅ 已转换MP4</button>`);
                } else {
                    actions.push(`<button class="btn btn-info" onclick="manager.convertToMp4('${task.task_id}')">🔄 转换MP4</button>`);
                }
                break;
            case 'failed':
                actions.push(`<button class="btn btn-success" onclick="manager.resumeTask('${task.task_id}')">🔄 重试</button>`);
                break;
        }

        // 通用操作按钮
        actions.push(`<button class="btn btn-secondary" onclick="manager.editTask('${task.task_id}')">✏️ 编辑</button>`);
        actions.push(`<button class="btn btn-info" onclick="manager.playTask('${task.task_id}')">▶️ 播放</button>`);
        actions.push(`<button class="btn btn-danger" onclick="manager.deleteTask('${task.task_id}')">🗑️ 删除</button>`);

        return actions.join('');
    }

    async pauseTask(taskId) {
        try {
            const response = await fetch(`/api/tasks/${taskId}/pause`, {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('任务已暂停', 'success');
                this.loadTasks();
            } else {
                this.showNotification(data.error || '暂停失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        }
    }

    async resumeTask(taskId) {
        try {
            const response = await fetch(`/api/tasks/${taskId}/resume`, {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('任务已恢复', 'success');
                this.loadTasks();
            } else {
                this.showNotification(data.error || '恢复失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        }
    }

    async deleteTask(taskId) {
        if (!confirm('确定要删除这个任务吗？此操作不可恢复。')) {
            return;
        }

        try {
            const response = await fetch(`/api/tasks/${taskId}/delete`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('任务已删除', 'success');
                this.loadTasks();
            } else {
                this.showNotification(data.error || '删除失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        }
    }

    async convertToMp4(taskId) {
        if (!confirm('确定要转换为MP4格式吗？这可能需要一些时间。')) {
            return;
        }

        try {
            // 显示转换中状态
            this.showNotification('开始转换，请稍候...', 'info');

            // 禁用转换按钮并显示转换中状态
            const convertBtn = document.querySelector(`button[onclick="manager.convertToMp4('${taskId}')"]`);
            if (convertBtn) {
                convertBtn.disabled = true;
                convertBtn.innerHTML = '🔄 转换中...';
                convertBtn.classList.add('btn-warning');
                convertBtn.classList.remove('btn-info');
            }

            const response = await fetch(`/api/tasks/${taskId}/convert`, {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('转换成功！', 'success');

                // 立即刷新任务状态
                await this.loadTasks();

                // 如果转换成功，显示额外信息
                if (data.converted) {
                    this.showNotification(`MP4文件已保存到: ${data.output_path}`, 'info');
                }
            } else {
                this.showNotification(data.error || '转换失败', 'error');

                // 恢复按钮状态
                if (convertBtn) {
                    convertBtn.disabled = false;
                    convertBtn.innerHTML = '🔄 转换MP4';
                    convertBtn.classList.add('btn-info');
                    convertBtn.classList.remove('btn-warning');
                }
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');

            // 恢复按钮状态
            const convertBtn = document.querySelector(`button[onclick="manager.convertToMp4('${taskId}')"]`);
            if (convertBtn) {
                convertBtn.disabled = false;
                convertBtn.innerHTML = '🔄 转换MP4';
                convertBtn.classList.add('btn-info');
                convertBtn.classList.remove('btn-warning');
            }
        }
    }

    async playTask(taskId) {
        const task = this.tasks.find(t => t.task_id === taskId);
        if (!task || !task.source_url) {
            this.showNotification('未找到原始播放网页URL', 'error');
            return;
        }
        window.open(task.source_url, '_blank');
    }

    editTask(taskId) {
        const task = this.tasks.find(t => t.task_id === taskId);
        if (!task) {
            this.showNotification('任务不存在', 'error');
            return;
        }

        this.currentEditTaskId = taskId;
        $('#editUrl').val(task.url);
        $('#editTitle').val(task.title);
        $('#editModal').show();
    }

    async saveEdit() {
        if (!this.currentEditTaskId) return;

        const newUrl = $('#editUrl').val().trim();
        const newTitle = $('#editTitle').val().trim();

        if (!newUrl) {
            this.showNotification('请输入URL', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/tasks/${this.currentEditTaskId}/update_url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: newUrl,
                    title: newTitle
                })
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('任务已更新', 'success');
                $('#editModal').hide();
                this.loadTasks();
            } else {
                this.showNotification(data.error || '更新失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        }
    }

    cancelEdit() {
        $('#editModal').hide();
        this.currentEditTaskId = null;
    }

    clearForm() {
        $('#m3u8Url').val('');
        $('#taskTitle').val('');
        $('#customDir').val('');
    }

    // 设置管理方法
    async showSettings() {
        try {
            const response = await fetch('/api/settings');
            const settings = await response.json();

            if (response.ok) {
                // 填充设置表单
                $('#threadCount').val(settings.thread_count);
                $('#maxConcurrentTasks').val(settings.max_concurrent_tasks);
                $('#downloadTimeout').val(settings.download_timeout);
                $('#maxRetryCount').val(settings.max_retry_count);
                $('#ffmpegThreads').val(settings.ffmpeg_threads);
                $('#autoCleanupDays').val(settings.auto_cleanup_days);
                $('#taskThreadCount').val(settings.thread_count);
                $('#enableAiNaming').prop('checked', settings.enable_ai_naming || false);

                // 更新队列状态显示
                $('#activeTasksCount').text(settings.active_tasks_count);
                $('#queuedTasksCount').text(settings.queued_tasks_count);

                $('#settingsPanel').show();
            } else {
                this.showNotification('获取设置失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        }
    }

    hideSettings() {
        $('#settingsPanel').hide();
    }

    async saveSettings() {
        const settings = {
            thread_count: parseInt($('#threadCount').val()),
            max_concurrent_tasks: parseInt($('#maxConcurrentTasks').val()),
            download_timeout: parseInt($('#downloadTimeout').val()),
            max_retry_count: parseInt($('#maxRetryCount').val()),
            ffmpeg_threads: parseInt($('#ffmpegThreads').val()),
            auto_cleanup_days: parseInt($('#autoCleanupDays').val()),
            enable_ai_naming: $('#enableAiNaming').prop('checked')
        };

        try {
            $('#saveSettingsBtn').prop('disabled', true).html('💾 保存中...');

            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('设置保存成功', 'success');
                $('#taskThreadCount').val(settings.thread_count);
                this.updateQueueStatus();
            } else {
                this.showNotification(data.error || '保存设置失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        } finally {
            $('#saveSettingsBtn').prop('disabled', false).html('💾 保存设置');
        }
    }

    async resetSettings() {
        if (!confirm('确定要重置所有设置为默认值吗？')) {
            return;
        }

        try {
            $('#resetSettingsBtn').prop('disabled', true).html('🔄 重置中...');

            const response = await fetch('/api/settings/reset', {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok) {
                this.showNotification('设置已重置', 'success');
                this.showSettings(); // 重新加载设置
            } else {
                this.showNotification('重置设置失败', 'error');
            }
        } catch (error) {
            this.showNotification('网络错误: ' + error.message, 'error');
        } finally {
            $('#resetSettingsBtn').prop('disabled', false).html('🔄 重置默认');
        }
    }

    async updateQueueStatus() {
        try {
            const response = await fetch('/api/queue/status');
            const status = await response.json();

            if (response.ok) {
                if (status.database_initializing) {
                    // 数据库正在初始化，显示提示信息
                    $('#activeTasksCount').text('初始化中...');
                    $('#queuedTasksCount').text('初始化中...');

                    // 3秒后重试
                    setTimeout(() => this.updateQueueStatus(), 3000);
                } else {
                    $('#activeTasksCount').text(status.active_tasks);
                    $('#queuedTasksCount').text(status.queued_tasks);

                    // 更新任务计数
                    this.updateTaskCount();
                }
            }
        } catch (error) {
            console.warn('更新队列状态失败:', error);
        }
    }

    updateTaskCount() {
        $('#taskCount').text(`共 ${this.tasks.length} 个任务`);
    }

    getStatusText(status) {
        const statusMap = {
            'pending': '⏳ 等待中',
            'downloading': '⬇️ 下载中',
            'paused': '⏸️ 已暂停',
            'completed': '✅ 已完成',
            'failed': '❌ 失败'
        };
        return statusMap[status] || status;
    }

    isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 恢复选中状态
    restoreSelectionState() {
        $('.task-checkbox').each((index, checkbox) => {
            const $checkbox = $(checkbox);
            const taskId = $checkbox.data('task-id');
            const isSelected = this.selectedTaskIds.has(taskId);

            $checkbox.prop('checked', isSelected);
            const taskItem = $checkbox.closest('.task-item');
            if (isSelected) {
                taskItem.addClass('selected');
            } else {
                taskItem.removeClass('selected');
            }
        });
    }

    // 批量操作相关方法
    toggleSelectAll() {
        const selectAllCheckbox = $('#selectAllTasks');
        const taskCheckboxes = $('.task-checkbox');
        const isChecked = selectAllCheckbox.prop('checked');

        // 更新内存中的选中状态
        if (isChecked) {
            taskCheckboxes.each((index, checkbox) => {
                const taskId = $(checkbox).data('task-id');
                this.selectedTaskIds.add(taskId);
            });
        } else {
            this.selectedTaskIds.clear();
        }

        taskCheckboxes.prop('checked', isChecked);
        taskCheckboxes.each(function() {
            const taskItem = $(this).closest('.task-item');
            if (isChecked) {
                taskItem.addClass('selected');
            } else {
                taskItem.removeClass('selected');
            }
        });

        this.saveSelectionToStorage();
        this.updateBatchControls();
    }

    updateBatchControls() {
        const selectedTasks = this.getSelectedTasks();
        const selectedCount = selectedTasks.length;

        // 更新选中数量显示
        $('#selectedCount').text(`已选择 ${selectedCount} 个任务`);

        // 更新全选复选框状态
        const totalTasks = $('.task-checkbox').length;
        const selectAllCheckbox = $('#selectAllTasks');
        if (selectedCount === 0) {
            selectAllCheckbox.prop('indeterminate', false);
            selectAllCheckbox.prop('checked', false);
        } else if (selectedCount === totalTasks) {
            selectAllCheckbox.prop('indeterminate', false);
            selectAllCheckbox.prop('checked', true);
        } else {
            selectAllCheckbox.prop('indeterminate', true);
        }

        // 更新批量操作按钮状态
        const hasSelected = selectedCount > 0;
        $('#batchPauseBtn').prop('disabled', !hasSelected);
        $('#batchResumeBtn').prop('disabled', !hasSelected);
        $('#batchConvertBtn').prop('disabled', !hasSelected);
        $('#batchDeleteBtn').prop('disabled', !hasSelected);

        // 根据选中任务的状态智能启用/禁用按钮
        if (hasSelected) {
            const canPause = selectedTasks.some(task => task.status === 'downloading');
            const canResume = selectedTasks.some(task => ['paused', 'failed'].includes(task.status));
            const canConvert = selectedTasks.some(task => task.status === 'completed' && !task.is_converted);

            $('#batchPauseBtn').prop('disabled', !canPause);
            $('#batchResumeBtn').prop('disabled', !canResume);
            $('#batchConvertBtn').prop('disabled', !canConvert);
        }

        // 更新任务项的选中样式
        $('.task-checkbox').each(function() {
            const taskItem = $(this).closest('.task-item');
            if ($(this).prop('checked')) {
                taskItem.addClass('selected');
            } else {
                taskItem.removeClass('selected');
            }
        });
    }

    getSelectedTasks() {
        return this.tasks.filter(task => this.selectedTaskIds.has(task.task_id));
    }

    // 本地存储相关方法
    loadSelectionFromStorage() {
        try {
            const stored = localStorage.getItem('m3u8_selected_tasks');
            if (stored) {
                const taskIds = JSON.parse(stored);
                return new Set(taskIds);
            }
        } catch (error) {
            console.warn('加载选中状态失败:', error);
        }
        return new Set();
    }

    saveSelectionToStorage() {
        try {
            const taskIds = Array.from(this.selectedTaskIds);
            localStorage.setItem('m3u8_selected_tasks', JSON.stringify(taskIds));
        } catch (error) {
            console.warn('保存选中状态失败:', error);
        }
    }

    clearSelectionStorage() {
        try {
            localStorage.removeItem('m3u8_selected_tasks');
        } catch (error) {
            console.warn('清除选中状态失败:', error);
        }
    }

    async batchPause() {
        const selectedTasks = this.getSelectedTasks().filter(task => task.status === 'downloading');

        if (selectedTasks.length === 0) {
            this.showNotification('没有可暂停的任务', 'warning');
            return;
        }

        if (!confirm(`确定要暂停 ${selectedTasks.length} 个任务吗？`)) {
            return;
        }

        this.showNotification('正在批量暂停任务...', 'info');

        let successCount = 0;
        let failCount = 0;

        for (const task of selectedTasks) {
            try {
                const response = await fetch(`/api/tasks/${task.task_id}/pause`, {
                    method: 'POST'
                });

                if (response.ok) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (error) {
                failCount++;
            }
        }

        this.showNotification(`批量暂停完成：成功 ${successCount} 个，失败 ${failCount} 个`,
                            failCount > 0 ? 'warning' : 'success');
        this.loadTasks();
    }

    async batchResume() {
        const selectedTasks = this.getSelectedTasks().filter(task =>
            ['paused', 'failed'].includes(task.status));

        if (selectedTasks.length === 0) {
            this.showNotification('没有可恢复的任务', 'warning');
            return;
        }

        if (!confirm(`确定要恢复 ${selectedTasks.length} 个任务吗？`)) {
            return;
        }

        this.showNotification('正在批量恢复任务...', 'info');

        let successCount = 0;
        let failCount = 0;

        for (const task of selectedTasks) {
            try {
                const response = await fetch(`/api/tasks/${task.task_id}/resume`, {
                    method: 'POST'
                });

                if (response.ok) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (error) {
                failCount++;
            }
        }

        this.showNotification(`批量恢复完成：成功 ${successCount} 个，失败 ${failCount} 个`,
                            failCount > 0 ? 'warning' : 'success');
        this.loadTasks();
    }

    async batchDelete() {
        const selectedTasks = this.getSelectedTasks();

        if (selectedTasks.length === 0) {
            this.showNotification('没有选中的任务', 'warning');
            return;
        }

        if (!confirm(`确定要删除 ${selectedTasks.length} 个任务吗？此操作不可恢复！`)) {
            return;
        }

        this.showNotification('正在批量删除任务...', 'info');

        let successCount = 0;
        let failCount = 0;

        for (const task of selectedTasks) {
            try {
                const response = await fetch(`/api/tasks/${task.task_id}/delete`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (error) {
                failCount++;
            }
        }

        this.showNotification(`批量删除完成：成功 ${successCount} 个，失败 ${failCount} 个`,
                            failCount > 0 ? 'warning' : 'success');
        this.loadTasks();
    }

    async batchConvert() {
        const selectedTasks = this.getSelectedTasks().filter(task =>
            task.status === 'completed' && !task.is_converted);

        if (selectedTasks.length === 0) {
            this.showNotification('没有可转换的任务（只能转换已完成且未转换的任务）', 'warning');
            return;
        }

        if (!confirm(`确定要串行转换 ${selectedTasks.length} 个任务为MP4吗？这可能需要较长时间。`)) {
            return;
        }

        // 显示批量转换进度模态框
        this.showBatchConvertModal(selectedTasks);

        // 开始串行转换
        this.startBatchConvert(selectedTasks);
    }

    showBatchConvertModal(tasks) {
        const modal = $('#batchConvertModal');
        const progressList = $('#convertProgressList');

        // 初始化进度显示
        $('#convertOverallProgress').text(`0/${tasks.length}`);
        $('#convertCurrentTask').text('准备开始...');

        // 生成任务列表
        let html = '';
        tasks.forEach(task => {
            html += `
                <div class="convert-item" data-task-id="${task.task_id}">
                    <div class="convert-info">
                        <div class="convert-title">${this.escapeHtml(task.title)}</div>
                        <div class="convert-status waiting">等待转换...</div>
                    </div>
                </div>
            `;
        });
        progressList.html(html);

        // 重置按钮状态
        $('#stopBatchConvertBtn').prop('disabled', false);
        $('#closeBatchConvertBtn').prop('disabled', true);

        modal.show();
    }

    async startBatchConvert(tasks) {
        this.batchConvertStopped = false;
        let completedCount = 0;

        for (let i = 0; i < tasks.length; i++) {
            if (this.batchConvertStopped) {
                break;
            }

            const task = tasks[i];

            // 更新当前任务显示
            $('#convertCurrentTask').text(`正在转换: ${task.title}`);

            // 更新任务状态为转换中
            const convertItem = $(`.convert-item[data-task-id="${task.task_id}"]`);
            convertItem.removeClass('waiting').addClass('converting');
            convertItem.find('.convert-status').removeClass('waiting').addClass('converting').text('转换中...');

            try {
                const response = await fetch(`/api/tasks/${task.task_id}/convert`, {
                    method: 'POST'
                });

                const data = await response.json();

                if (response.ok) {
                    // 转换成功
                    convertItem.removeClass('converting').addClass('completed');
                    convertItem.find('.convert-status').removeClass('converting').addClass('completed').text('转换成功');
                    completedCount++;
                } else {
                    // 转换失败
                    convertItem.removeClass('converting').addClass('failed');
                    convertItem.find('.convert-status').removeClass('converting').addClass('failed').text(`转换失败: ${data.error || '未知错误'}`);
                }
            } catch (error) {
                // 网络错误
                convertItem.removeClass('converting').addClass('failed');
                convertItem.find('.convert-status').removeClass('converting').addClass('failed').text(`网络错误: ${error.message}`);
            }

            // 更新总进度
            $('#convertOverallProgress').text(`${i + 1}/${tasks.length}`);
        }

        // 转换完成
        $('#convertCurrentTask').text(this.batchConvertStopped ? '转换已停止' : '转换完成');
        $('#stopBatchConvertBtn').prop('disabled', true);
        $('#closeBatchConvertBtn').prop('disabled', false);

        if (!this.batchConvertStopped) {
            this.showNotification(`批量转换完成：成功 ${completedCount} 个，失败 ${tasks.length - completedCount} 个`,
                                completedCount === tasks.length ? 'success' : 'warning');
        }

        // 刷新任务列表
        this.loadTasks();
    }

    stopBatchConvert() {
        this.batchConvertStopped = true;
        $('#convertCurrentTask').text('正在停止转换...');
        $('#stopBatchConvertBtn').prop('disabled', true);
    }

    closeBatchConvertModal() {
        $('#batchConvertModal').hide();
    }

    formatSpeed(speed) {
        if (speed === 0) return '0 KB/s';
        if (speed < 1) return `${(speed * 1024).toFixed(1)} KB/s`;
        return `${speed.toFixed(1)} MB/s`;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
    }

    estimateRemainingTime(task) {
        if (!task.download_speed || task.download_speed === 0) {
            return '计算中...';
        }

        const remainingSegments = task.total_segments - task.downloaded_segments;
        if (remainingSegments <= 0) return '即将完成';

        // 假设每个切片平均大小为1MB（这是一个估算）
        const avgSegmentSize = 1; // MB
        const remainingSize = remainingSegments * avgSegmentSize;
        const remainingSeconds = remainingSize / task.download_speed;

        return this.formatTime(remainingSeconds);
    }

    formatTime(seconds) {
        if (seconds < 60) {
            return `${Math.round(seconds)}秒`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const secs = Math.round(seconds % 60);
            return `${minutes}分${secs}秒`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}小时${minutes}分钟`;
        }
    }

    showNotification(message, type = 'info') {
        const notification = $(`
            <div class="notification ${type}">
                ${this.escapeHtml(message)}
            </div>
        `);

        $('body').append(notification);

        setTimeout(() => {
            notification.addClass('show');
        }, 100);

        setTimeout(() => {
            notification.removeClass('show');
            setTimeout(() => {
                notification.remove();
            }, 300);
        }, 3000);
    }

    startAutoRefresh() {
        // 初始启动时使用快速刷新
        this.adjustRefreshStrategy();
    }

    adjustRefreshStrategy() {
        // 清除现有的定时器
        this.stopAutoRefresh();

        if (this.hasActiveTasks) {
            // 有活跃任务时，每1秒刷新
            this.fastRefreshInterval = setInterval(() => {
                this.refreshTasks();
            }, 1000);
            this.updateRefreshIndicator('快速刷新 (1s)', true);
            console.log('启用快速刷新模式 (1秒)');
        } else {
            // 没有活跃任务时，每5秒刷新
            this.refreshInterval = setInterval(() => {
                this.refreshTasks();
            }, 5000);
            this.updateRefreshIndicator('慢速刷新 (5s)', false);
            console.log('启用慢速刷新模式 (5秒)');
        }
    }

    async refreshTasks() {
        // 显示刷新动画
        this.showRefreshAnimation();

        // 执行刷新
        await this.loadTasks();
        await this.updateQueueStatus();
    }

    updateRefreshIndicator(mode, isFast) {
        $('#refreshMode').text(mode);
        const indicator = $('#refreshIndicator');

        if (isFast) {
            indicator.addClass('fast-refresh');
        } else {
            indicator.removeClass('fast-refresh');
        }
    }

    showRefreshAnimation() {
        const indicator = $('#refreshIndicator');
        indicator.addClass('refreshing');

        setTimeout(() => {
            indicator.removeClass('refreshing');
        }, 300);
    }

    async manualRefresh() {
        const $refreshBtn = $('#refreshBtn');

        // 禁用按钮并显示加载状态
        $refreshBtn.prop('disabled', true).html('🔄 刷新中...');

        try {
            await this.refreshTasks();
            this.showNotification('刷新成功', 'success');
        } catch (error) {
            this.showNotification('刷新失败: ' + error.message, 'error');
        } finally {
            // 恢复按钮状态
            $refreshBtn.prop('disabled', false).html('🔄 刷新');
        }
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
        if (this.fastRefreshInterval) {
            clearInterval(this.fastRefreshInterval);
            this.fastRefreshInterval = null;
        }
    }
}

// 全局变量
let manager;

// 页面加载完成后初始化
$(document).ready(function() {
    manager = new M3U8Manager();
});

// 页面卸载时停止自动刷新
$(window).on('beforeunload', function() {
    if (manager) {
        manager.stopAutoRefresh();
    }
});
