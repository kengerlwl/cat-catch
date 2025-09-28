/**
 * M3U8 下载器 - 仅下载模式
 * 基于原有m3u8.js，但移除了MP4转换功能
 */

// 获取URL参数
const params = new URLSearchParams(location.search);
const _m3u8Url = params.get("url");
const referer = params.get("referer");
let requestHeaders = {};
let _initiator = params.get("initiator") || "";
let _title = params.get("title") || "";
let _fileName = params.get("filename") || "";
const _tabId = parseInt(params.get("tabid")) || null;
const _sourcePageUrl = params.get("source_page_url") || ""; // 新增：直接从参数获取完整的源页面URL

// 全局变量
let _m3u8Content;   // 储存m3u8文件内容
const hls = new Hls({
    enableWorker: false,
    debug: false
});

const _fragments = []; // 储存切片对象
const decryptor = new AESDecryptor(); // 解密工具
let skipDecrypt = false;
let downId = 0;
let downDuration = 0;
let fileStream = undefined;
const downSet = {};
let recorder = false;

// DOM 元素
const $fileSize = $("#fileSize");
const $progress = $("#progress");
const $fileDuration = $("#fileDuration");
const $media_file = $("#media_file");

// 初始化
$(document).ready(function() {
    initPage();
    bindEvents();
    loadSettings();

    if (_m3u8Url) {
        parseM3u8();
    } else {
        showCustomInput();
    }
});

// 初始化页面
function initPage() {
    $("#loading").hide();
    $("#thread").val(G.M3u8Thread || 6);
    $("#StreamSaver").prop("checked", G.M3u8StreamSaver);
    $("#skipDecrypt").prop("checked", G.M3u8SkipDecrypt);
    $("#saveAs").prop("checked", G.saveAs);
    $("#autoClose").prop("checked", G.M3u8AutoClose);
}

// 绑定事件
function bindEvents() {
    $("#parse").click(function() {
        const m3u8Text = $("#m3u8Text").val().trim();
        const baseUrl = $("#baseUrl").val().trim();
        const refererValue = $("#referer").val().trim();

        if (!m3u8Text) {
            alert("请输入m3u8链接或内容");
            return;
        }

        parseCustomM3u8(m3u8Text, baseUrl, refererValue);
    });

    $("#mergeTs").click(function() {
        if ($(this).html() === "开始下载") {
            startDownload();
        }
    });

    $("#stopDownload").click(function() {
        stopDownload();
    });

    $("#convertToMp4").click(function() {
        openMp4Converter();
    });

    // 后台下载功能已移至popup页面，此处不再提供

    bindOtherEvents();
}

// 绑定其他事件
function bindOtherEvents() {
    $("#play").click(function() {
        if ($(this).data("switch") == "on") {
            $("#video").show();
            hls.attachMedia($("#video")[0]);
            $media_file.hide();
            $("#downList").hide();
            $(this).html("关闭").data("switch", "off");
        } else {
            $("#video").hide();
            hls.detachMedia($("#video")[0]);
            $media_file.show();
            $(this).html("播放").data("switch", "on");
        }
    });

    $("#downText").click(function() {
        const filename = GetFileName(_m3u8Url) + '.txt';
        let text = "data:text/plain,";
        _fragments.forEach(function(item) {
            text += item.url + "\n";
        });

        if (G.isFirefox) {
            downloadDataURL(text, filename);
            return;
        }

        chrome.downloads.download({
            url: text,
            filename: filename
        });
    });

    $("#originalM3U8").click(function() {
        writeText(_m3u8Content);
    });

    $("[save='change']").on("change", function() {
        const id = $(this).attr("id");
        const value = $(this).prop("checked");
        localStorage.setItem(`M3u8Download_${id}`, value);
    });
}

// 加载设置
function loadSettings() {
    $("[save='change']").each(function() {
        const id = $(this).attr("id");
        const saved = localStorage.getItem(`M3u8Download_${id}`);
        if (saved !== null) {
            $(this).prop("checked", saved === "true");
        }
    });
}

// 显示自定义输入
function showCustomInput() {
    $("#m3u8Custom").show();
}

// 解析M3U8
function parseM3u8() {
    if (!_m3u8Url) return;

    if (referer) {
        try {
            requestHeaders = JSON.parse(referer);
        } catch {
            requestHeaders = { referer: referer };
        }
    }

    hls.loadSource(_m3u8Url);
}

// 解析自定义M3U8
function parseCustomM3u8(m3u8Text, baseUrl, refererValue) {
    if (m3u8Text.split("\n").length == 1 && GetExt(m3u8Text) == "m3u8") {
        let url = "m3u8-download.html?url=" + encodeURIComponent(m3u8Text);
        if (refererValue) {
            if (refererValue.startsWith("http")) {
                url += "&referer=" + encodeURIComponent(JSON.stringify({ referer: refererValue }));
            } else {
                url += "&referer=" + encodeURIComponent(refererValue);
            }
        }
        window.location.href = url;
        return;
    }

    if (!m3u8Text.includes("#EXTM3U")) {
        const tsList = m3u8Text.split("\n");
        m3u8Text = "#EXTM3U\n#EXT-X-TARGETDURATION:233\n";
        for (let ts of tsList) {
            if (ts) {
                m3u8Text += "#EXTINF:1\n" + ts + "\n";
            }
        }
        m3u8Text += "#EXT-X-ENDLIST";
    }

    if (baseUrl) {
        m3u8Text = addBashUrl(baseUrl, m3u8Text);
    }

    if (refererValue) {
        requestHeaders = { referer: refererValue };
    }

    const blob = new Blob([new TextEncoder("utf-8").encode(m3u8Text)]);
    const url = URL.createObjectURL(blob);
    hls.loadSource(url);
    $("#m3u8Custom").hide();
}

// HLS事件监听
hls.on(Hls.Events.MANIFEST_LOADED, function(event, data) {
    $("#m3u8_url").attr("href", data.url).html(data.url);
});

hls.on(Hls.Events.MANIFEST_PARSED, function(event, data) {
    _m3u8Content = data.m3u8Content || "";
    showMainInterface(data);
});

// 显示主界面
function showMainInterface(data) {
    $("#m3u8Custom").hide();
    $("#m3u8").show();

    processFragments(data);
    showVideoInfo();
}

// 处理切片
function processFragments(data) {
    _fragments.length = 0;

    if (data.fragments) {
        _fragments.push(...data.fragments);
    }

    updateFragmentsList();
}

// 更新切片列表
function updateFragmentsList() {
    let text = "";
    _fragments.forEach((fragment, index) => {
        text += `${index + 1}. ${fragment.url}\n`;
    });
    $media_file.val(text);

    $("#count").html(`共 ${_fragments.length} 个切片`);
}

// 显示视频信息
function showVideoInfo() {
    let duration = 0;
    let size = 0;

    _fragments.forEach(fragment => {
        duration += fragment.duration || 0;
        size += (fragment.duration || 0) * 1024 * 1024;
    });

    $("#info").html(`时长: ${secToTime(duration)}`);
    $("#estimateFileSize").html(`估算大小: ${byteToSize(size)}`);
}

// 开始下载
function startDownload() {
    if (_fragments.length === 0) {
        alert("没有可下载的切片");
        return;
    }

    initDownload();

    const start = parseInt($("#rangeStart").val()) - 1 || 0;
    const end = parseInt($("#rangeEnd").val()) || _fragments.length;

    downloadNew(start, end);
}

// 初始化下载变量
function initDownload() {
    $fileSize.html("");
    downDuration = 0;
    $fileDuration.html("");
    fileStream = undefined;

    downSet.streamSaver = $("#StreamSaver").prop("checked");
    downSet.skipDecrypt = $("#skipDecrypt").prop("checked");
    downSet.saveAs = $("#saveAs").prop("checked");
}

// 下载方法
function downloadNew(start = 0, end = _fragments.length) {
    $("#video").hide();
    hls.detachMedia($("#video")[0]);

    buttonState("#mergeTs", false);

    // 使用新的切片级下载器
    const options = {
        saveSegments: true,
        resumeDownload: true,
        keepSegments: true,
        segmentDir: generateSegmentDirName()
    };

    const down = new SegmentDownloader(_fragments.slice(start, end), parseInt($("#thread").val()), options);

    // 显示当前项目目录
    $("#currentSegmentDir").text(options.segmentDir);

    // 断点续传信息显示
    down.on('resumeInfo', function(stats) {
        $progress.html(`发现 ${stats.downloaded}/${stats.total} 个切片已下载，继续下载剩余切片...`);
    });

    down.setDecrypt(function(buffer, fragment) {
        return new Promise(function(resolve, reject) {
            if (downSet.skipDecrypt || !fragment.encrypted || !fragment.decryptdata) {
                resolve(buffer);
                return;
            }

            try {
                decryptor.expandKey(fragment.decryptdata.keyContent);
                const iv = fragment.decryptdata.iv ?? new Uint8Array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, fragment.sn]);
                buffer = decryptor.decrypt(buffer, 0, iv.buffer, true);
                resolve(buffer);
            } catch (e) {
                $progress.html("解密错误: " + e);
                down.stop();
                buttonState("#mergeTs", true);
                reject(e);
            }
        });
    });

    down.on('completed', function(buffer, fragment) {
        $progress.html(`${down.success}/${down.total}`);
        $fileSize.html(`已下载: ${byteToSize(down.buffersize)}`);
        $fileDuration.html(`已下载时长: ${secToTime(down.duration)}`);
    });

    down.on('allCompleted', function(buffer) {
        $("#stopDownload").hide();

        if (fileStream) {
            fileStream.close();
            fileStream = undefined;
            $progress.html("下载完成");
        } else {
            saveTsFile(down);
        }

        buttonState("#mergeTs", true);
        $("#convertToMp4").show();
    });

    down.on('downloadError', function(fragment, error) {
        console.error("下载错误:", error);
        $("#errorDownload").show();
    });

    down.start();
    $("#stopDownload").show();
}

// 保存TS文件
function saveTsFile(down) {
    $progress.html("正在合并文件...");

    const fileBlob = new Blob(down.buffer, { type: "video/MP2T" });

    let fileName = "";
    const customFilename = $('#customFilename').val().trim();
    if (customFilename) {
        fileName = customFilename;
    } else if (_fileName) {
        fileName = _fileName;
    } else {
        fileName = _title ? stringModify(_title) : GetFileName(_m3u8Url);
    }

    if (!fileName.endsWith('.ts')) {
        fileName += '.ts';
    }

    apiDownload(fileBlob, fileName.replace('.ts', ''), 'ts');
}

// API下载
function apiDownload(fileBlob, fileName, ext) {
    chrome.downloads.download({
        url: URL.createObjectURL(fileBlob),
        filename: fileName + "." + ext,
        saveAs: $("#saveAs").prop("checked")
    }, function(downloadId) {
        if (downloadId) {
            downId = downloadId;
            $(".openDir").show();
            buttonState("#mergeTs", true);
        }
    });
}

// 停止下载
function stopDownload() {
    buttonState("#mergeTs", true);
    $("#stopDownload").hide();
}

// 打开MP4转换器
function openMp4Converter() {
    window.open('mp4-converter.html', '_blank');
}

// 按钮状态控制
function buttonState(selector, enabled) {
    $(selector).prop("disabled", !enabled);
}

// 工具函数
function secToTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
}

function byteToSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function GetExt(url) {
    return url.split('.').pop().split('?')[0].toLowerCase();
}

function GetFileName(url) {
    return url.split('/').pop().split('?')[0].split('.')[0];
}

function stringModify(str) {
    return str.replace(/[<>:"/\\|?*]/g, '_');
}

function addBashUrl(baseUrl, m3u8Content) {
    return m3u8Content;
}

function writeText(text) {
    navigator.clipboard.writeText(typeof text === 'string' ? text : JSON.stringify(text, null, 2));
}

function downloadDataURL(dataUrl, filename) {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    a.click();
}

// 后台下载功能已移至popup页面

// 获取当前任务配置
function getCurrentTaskConfig() {
    // 计算下载范围
    let start = $("#rangeStart").val();
    if (start && start.includes(":")) {
        start = timeToIndex(start);
    } else {
        start = parseInt(start);
        start = start ? start - 1 : 0;
    }

    let end = $("#rangeEnd").val();
    if (end && end.includes(":")) {
        end = timeToIndex(end);
    } else {
        end = parseInt(end);
        end = end ? end : _fragments.length;
    }

    // 验证范围
    if (start < 0) start = 0;
    if (end > _fragments.length) end = _fragments.length;
    if (start >= end) end = start + 1;

    // 获取文件名
    let title = "";
    const customFilename = $('#customFilename').val().trim();
    if (customFilename) {
        title = customFilename;
    } else if (_fileName) {
        title = _fileName;
    } else {
        title = _title ? stringModify(_title) : GetFileName(_m3u8Url);
    }

    return {
        title: title,
        url: _m3u8Url,
        fragments: _fragments.slice(start, end),
        thread: parseInt($("#thread").val()) || 6,
        customKey: $("#customKey").val().trim(),
        customIV: $("#customIV").val().trim(),
        customFilename: customFilename,
        skipDecrypt: $("#skipDecrypt").prop("checked"),
        rangeStart: start,
        rangeEnd: end
    };
}

// 时间转索引
function timeToIndex(timeStr) {
    const parts = timeStr.split(':');
    if (parts.length === 2) {
        const minutes = parseInt(parts[0]);
        const seconds = parseInt(parts[1]);
        return Math.floor((minutes * 60 + seconds) / 10); // 假设每个切片10秒
    }
    return 0;
}

// 生成切片目录名称
function generateSegmentDirName() {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const urlName = _m3u8Url ? GetFileName(_m3u8Url) : 'unknown';
    return `${urlName}_${timestamp}`;
}
