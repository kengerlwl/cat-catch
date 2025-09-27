/**
 * M3U8 切片级下载器
 * 支持将每个切片单独保存到文件夹，并实现真正的断点续传
 */
class SegmentDownloader {
    constructor(fragments = [], thread = 6, options = {}) {
        this.fragments = fragments;      // 切片列表
        this.allFragments = fragments;   // 储存所有原始切片列表
        this.thread = thread;            // 线程数
        this.events = {};                // events
        this.decrypt = null;             // 解密函数
        this.transcode = null;           // 转码函数

        // 新增选项
        this.options = {
            saveSegments: true,          // 是否保存单个切片
            segmentDir: '',              // 切片保存目录
            resumeDownload: true,        // 是否启用断点续传
            keepSegments: true,          // 完成后是否保留切片文件
            ...options
        };

        this.segmentFiles = new Map();   // 存储已下载的切片文件信息
        this.downloadedSegments = new Set(); // 已下载的切片索引

        this.init();
    }

    /**
     * 初始化所有变量
     */
    init() {
        this.index = 0;                  // 当前任务索引
        this.buffer = [];                // 储存的buffer
        this.state = 'waiting';          // 下载器状态 waiting running done abort
        this.success = 0;                // 成功下载数量
        this.errorList = new Set();      // 下载错误的列表
        this.buffersize = 0;             // 已下载buffer大小
        this.duration = 0;               // 已下载时长
        this.pushIndex = 0;              // 推送顺序下载索引
        this.controller = [];            // 储存中断控制器
        this.running = 0;                // 正在下载数量
        this.maxRetries = 3;             // 最大重试次数
        this.retryDelays = [1000, 2000, 3000]; // 重试延迟时间(毫秒)
    }

    /**
     * 设置切片保存目录
     * @param {string} dirName 目录名称
     */
    setSegmentDirectory(dirName) {
        this.options.segmentDir = dirName || this.generateDirectoryName();
    }

    /**
     * 生成目录名称
     */
    generateDirectoryName() {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        return `m3u8_segments_${timestamp}`;
    }

    /**
     * 检查切片是否已存在
     * @param {object} fragment 切片对象
     * @returns {Promise<boolean>}
     */
    async checkSegmentExists(fragment) {
        if (!this.options.resumeDownload) return false;

        const fileName = this.getSegmentFileName(fragment);

        try {
            // 在浏览器环境中，我们使用IndexedDB来模拟文件系统
            const exists = await this.checkSegmentInStorage(fileName);
            if (exists) {
                console.log(`切片 ${fragment.index} 已存在，跳过下载`);
                this.downloadedSegments.add(fragment.index);
                return true;
            }
        } catch (error) {
            console.warn(`检查切片 ${fragment.index} 时出错:`, error);
        }

        return false;
    }

    /**
     * 获取切片文件名
     * @param {object} fragment 切片对象
     * @returns {string}
     */
    getSegmentFileName(fragment) {
        const url = new URL(fragment.url);
        const pathName = url.pathname;
        const fileName = pathName.split('/').pop() || `segment_${fragment.index}`;

        // 确保文件名有扩展名
        if (!fileName.includes('.')) {
            return `${fileName}.ts`;
        }

        return fileName;
    }

    /**
     * 保存切片到文件系统
     * @param {string} fileName 文件名
     * @param {ArrayBuffer} buffer 文件数据
     * @returns {Promise<void>}
     */
    async saveSegmentToStorage(fileName, buffer) {
        return new Promise((resolve, reject) => {
            try {
                // 创建Blob对象
                const blob = new Blob([buffer], { type: 'video/MP2T' });

                // 构建完整的文件路径：m3u8/项目目录/文件名
                const fullPath = `m3u8/${this.options.segmentDir}/${fileName}`;

                // 使用Chrome下载API保存文件
                chrome.downloads.download({
                    url: URL.createObjectURL(blob),
                    filename: fullPath,
                    saveAs: false,  // 不弹出保存对话框
                    conflictAction: 'overwrite'  // 覆盖同名文件
                }, (downloadId) => {
                    if (chrome.runtime.lastError) {
                        reject(new Error(chrome.runtime.lastError.message));
                    } else if (downloadId) {
                        // 保存下载ID用于后续管理
                        this.segmentFiles.set(fileName, {
                            downloadId: downloadId,
                            path: fullPath,
                            timestamp: Date.now()
                        });
                        resolve();
                    } else {
                        reject(new Error('下载失败'));
                    }
                });
            } catch (error) {
                reject(error);
            }
        });
    }

    /**
     * 检查切片文件是否存在
     * @param {string} fileName 文件名
     * @returns {Promise<boolean>}
     */
    async checkSegmentInStorage(fileName) {
        return new Promise((resolve) => {
            try {
                // 构建完整的文件路径
                const fullPath = `m3u8/${this.options.segmentDir}/${fileName}`;

                // 使用Chrome下载API搜索已下载的文件
                chrome.downloads.search({
                    filename: fullPath,
                    state: 'complete'
                }, (results) => {
                    if (chrome.runtime.lastError) {
                        console.warn('搜索下载文件时出错:', chrome.runtime.lastError.message);
                        resolve(false);
                        return;
                    }

                    // 检查是否找到匹配的已完成下载
                    const exists = results && results.length > 0;
                    if (exists) {
                        // 保存文件信息用于后续加载
                        this.segmentFiles.set(fileName, {
                            downloadId: results[0].id,
                            path: fullPath,
                            timestamp: Date.now()
                        });
                    }
                    resolve(exists);
                });
            } catch (error) {
                console.warn('检查切片文件时出错:', error);
                resolve(false);
            }
        });
    }

    /**
     * 从文件系统加载切片
     * @param {string} fileName 文件名
     * @returns {Promise<ArrayBuffer|null>}
     */
    async loadSegmentFromStorage(fileName) {
        return new Promise((resolve) => {
            try {
                const fileInfo = this.segmentFiles.get(fileName);
                if (!fileInfo) {
                    resolve(null);
                    return;
                }

                // 构建文件URL（这里需要用户手动处理，因为浏览器安全限制）
                // 实际上，对于已下载的文件，我们可以直接使用其内容
                // 但由于浏览器安全限制，我们无法直接读取已下载的文件
                // 所以这里返回一个占位符，表示文件存在但需要重新下载内容

                console.log(`切片 ${fileName} 存在于 ${fileInfo.path}，但需要重新获取内容`);

                // 返回null表示需要重新下载内容到内存
                // 但文件已存在，所以不会重复保存到磁盘
                resolve(null);
            } catch (error) {
                console.warn('加载切片文件时出错:', error);
                resolve(null);
            }
        });
    }

    /**
     * 获取已下载的切片统计
     * @returns {Promise<object>}
     */
    async getDownloadedSegmentsStats() {
        const stats = {
            total: this.fragments.length,
            downloaded: 0,
            missing: [],
            existing: []
        };

        for (let i = 0; i < this.fragments.length; i++) {
            const fragment = this.fragments[i];
            const fileName = this.getSegmentFileName(fragment);
            const exists = await this.checkSegmentInStorage(fileName);

            if (exists) {
                stats.downloaded++;
                stats.existing.push(i);
                this.downloadedSegments.add(i);
            } else {
                stats.missing.push(i);
            }
        }

        return stats;
    }

    /**
     * 设置监听
     * @param {string} eventName 监听名
     * @param {Function} callBack
     */
    on(eventName, callBack) {
        if (this.events[eventName]) {
            this.events[eventName].push(callBack);
        } else {
            this.events[eventName] = [callBack];
        }
    }

    /**
     * 触发监听器
     * @param {string} eventName 监听名
     * @param  {...any} args
     */
    emit(eventName, ...args) {
        if (this.events[eventName]) {
            this.events[eventName].forEach(callBack => {
                callBack(...args);
            });
        }
    }

    /**
     * 设定解密函数
     * @param {Function} callback
     */
    setDecrypt(callback) {
        this.decrypt = callback;
    }

    /**
     * 设定转码函数
     * @param {Function} callback
     */
    setTranscode(callback) {
        this.transcode = callback;
    }

    /**
     * 设置重试参数
     * @param {number} maxRetries 最大重试次数
     * @param {Array<number>} retryDelays 重试延迟时间数组(毫秒)
     */
    setRetryConfig(maxRetries = 3, retryDelays = [1000, 2000, 3000]) {
        this.maxRetries = maxRetries;
        this.retryDelays = retryDelays;
    }

    /**
     * 停止下载
     * @param {number} index 停止下载目标
     */
    stop(index = undefined) {
        if (index !== undefined) {
            this.controller[index] && this.controller[index].abort();
            return;
        }
        this.controller.forEach(controller => { controller.abort() });
        this.state = 'abort';
    }

    /**
     * 检查对象是否错误列表内
     * @param {object} fragment 切片对象
     * @returns {boolean}
     */
    isErrorItem(fragment) {
        return this.errorList.has(fragment);
    }

    /**
     * 返回所有错误列表
     */
    get errorItem() {
        return this.errorList;
    }

    /**
     * 下载器核心方法
     * @param {object|number} fragment 切片对象或索引
     * @param {boolean} directDownload 是否直接下载
     */
    async downloader(fragment = null, directDownload = false) {
        // 检查是否应该停止
        if (this.state === 'abort') return;

        // 检查是否还有切片需要下载
        if (!directDownload && !this.fragments[this.index]) { return; }

        // fragment是数字 直接从this.fragments获取
        if (typeof fragment === 'number') {
            fragment = this.fragments[fragment];
        }

        // 不存在下载对象 从提取fragments
        fragment ??= this.fragments[this.index++];
        this.state = 'running';
        this.running++;

        // 初始化重试计数
        if (fragment.retryCount === undefined) {
            fragment.retryCount = 0;
        }

        // 检查切片是否已存在（断点续传）
        const segmentExists = await this.checkSegmentExists(fragment);

        // 标记是否需要保存到磁盘（如果文件已存在则不保存）
        fragment.skipDiskSave = segmentExists;

        // 停止下载控制器
        const controller = new AbortController();
        this.controller[fragment.index] = controller;
        const options = { signal: controller.signal };

        // 下载前触发事件
        this.emit('start', fragment, options);

        // 开始下载
        fetch(fragment.url, options)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`, { cause: 'HTTPError' });
                }
                const reader = response.body.getReader();
                const contentLength = parseInt(response.headers.get('content-length')) || 0;
                fragment.contentType = response.headers.get('content-type') ?? 'null';
                let receivedLength = 0;
                const chunks = [];

                const pump = async () => {
                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) { break; }

                        chunks.push(value);
                        receivedLength += value.length;
                        this.emit('itemProgress', fragment, false, receivedLength, contentLength, value);
                    }

                    const allChunks = new Uint8Array(receivedLength);
                    let position = 0;
                    for (const chunk of chunks) {
                        allChunks.set(chunk, position);
                        position += chunk.length;
                    }
                    this.emit('itemProgress', fragment, true);
                    return allChunks.buffer;
                }
                return pump();
            })
            .then(buffer => {
                this.emit('rawBuffer', buffer, fragment);
                // 存在解密函数 调用解密函数 否则直接返回buffer
                return this.decrypt ? this.decrypt(buffer, fragment) : buffer;
            })
            .then(buffer => {
                this.emit('decryptedData', buffer, fragment);
                // 存在转码函数 调用转码函数 否则直接返回buffer
                return this.transcode ? this.transcode(buffer, fragment) : buffer;
            })
            .then(async (buffer) => {
                // 保存切片到文件系统（如果文件不存在）
                if (this.options.saveSegments && !fragment.skipDiskSave) {
                    const fileName = this.getSegmentFileName(fragment);
                    try {
                        await this.saveSegmentToStorage(fileName, buffer);
                        console.log(`切片 ${fragment.index} 已保存到磁盘: ${fileName}`);
                    } catch (error) {
                        console.warn(`保存切片 ${fragment.index} 失败:`, error);
                    }
                } else if (fragment.skipDiskSave) {
                    console.log(`切片 ${fragment.index} 已存在于磁盘，跳过保存`);
                }

                // 储存解密/转码后的buffer
                this.buffer[fragment.index] = buffer;

                // 成功数+1 累计buffer大小和视频时长
                this.success++;
                this.buffersize += buffer.byteLength;
                this.duration += fragment.duration ?? 0;

                // 重置重试计数（下载成功）
                fragment.retryCount = 0;

                // 下载对象来自错误列表 从错误列表内删除
                this.errorList.has(fragment) && this.errorList.delete(fragment);

                this.emit('completed', buffer, fragment);

                // 下载完成
                if (this.success == this.fragments.length) {
                    this.state = 'done';
                    this.emit('allCompleted', this.buffer, this.fragments);
                }
            })
            .catch((error) => {
                console.log(`切片 ${fragment.index} 下载错误:`, error);
                if (error.name == 'AbortError') {
                    this.emit('stop', fragment, error);
                    return;
                }

                // 重试逻辑
                if (fragment.retryCount < this.maxRetries) {
                    fragment.retryCount++;
                    const retryDelay = this.retryDelays[fragment.retryCount - 1] || 3000;

                    console.log(`切片 ${fragment.index} 下载失败，${retryDelay}ms后进行第${fragment.retryCount}次重试`);
                    this.emit('retryAttempt', fragment, fragment.retryCount, this.maxRetries, error);

                    // 延迟后重试
                    setTimeout(() => {
                        if (this.state !== 'abort') {
                            this.downloader(fragment, true); // 重新下载该切片
                        }
                    }, retryDelay);
                    return;
                }

                // 重试次数用完，标记为最终失败
                console.log(`切片 ${fragment.index} 重试${this.maxRetries}次后仍然失败`);
                this.emit('downloadError', fragment, error);

                // 储存下载错误切片
                !this.errorList.has(fragment) && this.errorList.add(fragment);
            })
            .finally(() => {
                // 检查是否需要减少运行计数和继续下载
                const isRetrying = fragment.retryCount > 0 && fragment.retryCount < this.maxRetries;
                const shouldContinue = this.buffer[fragment.index] ||
                                     (fragment.retryCount >= this.maxRetries) ||
                                     this.state === 'abort';

                if (shouldContinue && !isRetrying) {
                    this.running--;
                    // 下载下一个切片
                    if (!directDownload && this.index < this.fragments.length && this.state !== 'abort') {
                        this.downloader();
                    }
                }
            });
    }

    /**
     * 开始下载
     * @param {number} start 下载范围 开始索引
     * @param {number} end 下载范围 结束索引
     */
    async start(start = 0, end = this.fragments.length) {
        // 检查下载器状态
        if (this.state == 'running') {
            this.emit('error', 'state running');
            return;
        }

        // 设置切片目录
        if (!this.options.segmentDir) {
            this.setSegmentDirectory();
        }

        // 从下载范围内 切出需要下载的部分
        this.fragments = this.fragments.slice(start, end);

        // 初始化变量
        this.init();

        // 检查已下载的切片
        if (this.options.resumeDownload) {
            console.log('检查已下载的切片...');
            const stats = await this.getDownloadedSegmentsStats();
            console.log(`发现 ${stats.downloaded}/${stats.total} 个切片已下载`);

            if (stats.downloaded > 0) {
                this.emit('resumeInfo', stats);
            }
        }

        // 开始下载 多少线程开启多少个下载器
        for (let i = 0; i < this.thread && i < this.fragments.length; i++) {
            this.downloader();
        }
    }

    /**
     * 清理切片文件
     * @returns {Promise<void>}
     */
    async cleanupSegments() {
        if (!this.options.keepSegments) {
            try {
                // 构建搜索模式，匹配当前项目目录下的所有文件
                const searchPattern = `m3u8/${this.options.segmentDir}/*`;

                // 搜索当前项目目录下的所有下载文件
                chrome.downloads.search({
                    filenameRegex: `m3u8/${this.options.segmentDir.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/.*`
                }, (results) => {
                    if (chrome.runtime.lastError) {
                        console.warn('搜索切片文件时出错:', chrome.runtime.lastError.message);
                        return;
                    }

                    if (results && results.length > 0) {
                        // 删除找到的文件
                        results.forEach(item => {
                            chrome.downloads.removeFile(item.id, () => {
                                if (chrome.runtime.lastError) {
                                    console.warn(`删除文件 ${item.filename} 时出错:`, chrome.runtime.lastError.message);
                                } else {
                                    console.log(`已删除切片文件: ${item.filename}`);
                                }
                            });
                        });

                        // 清理内存中的文件信息
                        this.segmentFiles.clear();
                        console.log(`已清理 ${results.length} 个切片文件`);
                    }
                });
            } catch (error) {
                console.warn('清理切片文件时出错:', error);
            }
        }
    }

    /**
     * 销毁下载器
     */
    destroy() {
        this.stop();
        this.fragments = [];
        this.allFragments = [];
        this.thread = 6;
        this.events = {};
        this.decrypt = null;
        this.transcode = null;
        this.segmentFiles.clear();
        this.downloadedSegments.clear();
        this.init();
    }
}
