import os
import subprocess
import tempfile
import zipfile
import urllib.parse
import traceback
import shutil
import time
from flask import Flask, request, render_template_string, send_file
from werkzeug.utils import secure_filename

# 🚀 終極記憶體防護：強制系統將所有暫存檔寫入實體硬碟
LOCAL_TEMP_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_processing')
os.makedirs(LOCAL_TEMP_BASE, exist_ok=True)
os.environ['TMPDIR'] = LOCAL_TEMP_BASE
tempfile.tempdir = LOCAL_TEMP_BASE

def cleanup_old_temp_dirs():
    """🧹 自動資源回收：清除超過 30 分鐘的舊暫存資料夾，避免硬碟塞爆"""
    try:
        now = time.time()
        for dirname in os.listdir(LOCAL_TEMP_BASE):
            dir_path = os.path.join(LOCAL_TEMP_BASE, dirname)
            if os.path.isdir(dir_path):
                # 如果資料夾存在超過 1800 秒 (30 分鐘)
                if now - os.path.getmtime(dir_path) > 1800:
                    shutil.rmtree(dir_path, ignore_errors=True)
    except Exception as e:
        print(f"清理舊暫存檔失敗: {e}")

# 🌟 嘗試載入 Python 內建的 FFmpeg 引擎
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_EXE = "ffmpeg"

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>我的雲端 M4A 裁減伺服器</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 h-screen flex items-center justify-center font-sans p-4">
    <div class="bg-white p-8 rounded-2xl shadow-xl border border-slate-100 w-full max-w-md">
        <div class="text-center mb-8">
            <div class="inline-flex items-center justify-center p-3 bg-blue-100 rounded-full mb-4">
                <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path></svg>
            </div>
            <h1 class="text-2xl font-bold text-slate-800">雲端 M4A 裁減中心</h1>
            <p class="text-slate-500 mt-2 text-sm">檔案將上傳至伺服器硬碟處理，不消耗您的手機效能。</p>
        </div>

        <form id="uploadForm" class="space-y-6">
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-2">1. 選擇錄音檔 (.m4a)</label>
                <input type="file" name="file" accept=".m4a,audio/mp4" required
                       class="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer transition-colors">
            </div>
            
            <div>
                <label class="block text-sm font-medium text-slate-700 mb-2">2. 每段長度 (分鐘)</label>
                <input type="number" name="minutes" value="30" min="1" required
                       class="block w-full rounded-lg border-slate-300 border p-2.5 text-slate-700 shadow-sm focus:border-blue-500 focus:ring-blue-500">
            </div>

            <button type="submit" id="submitBtn"
                    class="w-full bg-blue-600 text-white font-bold py-3 px-4 rounded-xl hover:bg-blue-700 hover:shadow-lg transition-all active:scale-95">
                ☁️ 上傳並開始處理
            </button>
        </form>

        <div id="progressContainer" class="hidden mt-6">
            <div class="flex justify-between text-sm font-medium text-blue-600 mb-1">
                <span id="statusText">準備中...</span>
                <span id="percentText">0%</span>
            </div>
            <div class="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
                <div id="progressBar" class="bg-blue-600 h-2.5 rounded-full transition-all duration-300" style="width: 0%"></div>
            </div>
            <p id="progressHint" class="text-xs text-slate-400 mt-2 text-center">請勿關閉網頁或鎖定螢幕。</p>
        </div>
    </div>

    <script>
        const form = document.getElementById('uploadForm');
        const btn = document.getElementById('submitBtn');
        const progressContainer = document.getElementById('progressContainer');
        const statusText = document.getElementById('statusText');
        const percentText = document.getElementById('percentText');
        const progressBar = document.getElementById('progressBar');
        const progressHint = document.getElementById('progressHint');

        form.addEventListener('submit', (e) => {
            e.preventDefault(); 
            
            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            progressContainer.classList.remove('hidden');

            const formData = new FormData(form);
            const xhr = new XMLHttpRequest();

            xhr.open('POST', '/api/cut', true);
            xhr.responseType = 'blob'; 

            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    statusText.innerText = '⬆️ 檔案上傳中...';
                    percentText.innerText = `${percent}%`;
                    progressBar.style.width = `${percent}%`;
                    progressBar.className = 'bg-blue-600 h-2.5 rounded-full transition-all duration-300';
                    progressHint.innerText = '正在將錄音檔傳送至雲端伺服器，請保持網路暢通。';
                }
            };

            xhr.upload.onload = () => {
                statusText.innerText = '⚙️ 處理與打包中...';
                percentText.innerText = '請稍候';
                progressBar.style.width = '100%';
                progressBar.className = 'bg-indigo-500 h-2.5 rounded-full animate-pulse transition-all duration-300';
                progressHint.innerText = '伺服器正在實體硬碟中裁減音檔，這可能需要幾分鐘，請勿關閉網頁。';
            };

            xhr.onprogress = (event) => {
                statusText.innerText = '⬇️ 處理完成！精準下載中...';
                progressBar.className = 'bg-emerald-500 h-2.5 rounded-full transition-all duration-300';
                progressHint.innerText = '檔案大小已確認，正在安全地將 ZIP 檔下載至您的設備。';
                
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100);
                    percentText.innerText = `${percent}%`;
                    progressBar.style.width = `${percent}%`;
                } else {
                    percentText.innerText = '下載中';
                    progressBar.style.width = '100%';
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    statusText.innerText = '✅ 任務圓滿完成！';
                    percentText.innerText = '100%';
                    progressBar.style.width = '100%';
                    progressHint.innerText = '您的檔案已經完整下載。';

                    let filename = "cut_audio.zip";
                    const disposition = xhr.getResponseHeader('Content-Disposition');
                    if (disposition) {
                        const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/);
                        if (utf8Match) {
                            filename = decodeURIComponent(utf8Match[1]);
                        } else {
                            const normalMatch = disposition.match(/filename="?([^";]+)"?/);
                            if (normalMatch) {
                                filename = decodeURIComponent(normalMatch[1]);
                            }
                        }
                    }

                    const blob = xhr.response;
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                } else {
                    const reader = new FileReader();
                    reader.onload = () => {
                        alert('❌ 伺服器處理失敗：\\n' + reader.result);
                        statusText.innerText = '❌ 處理失敗';
                        progressHint.innerText = '請重試或檢查檔案是否正確。';
                        progressBar.className = 'bg-red-500 h-2.5 rounded-full';
                    };
                    reader.readAsText(xhr.response);
                }
            };

            xhr.onerror = () => {
                alert('網路錯誤：伺服器沒有回應或下載意外中斷。');
                statusText.innerText = '❌ 連線中斷';
                progressBar.className = 'bg-red-500 h-2.5 rounded-full';
            };

            xhr.onloadend = () => {
                btn.disabled = false;
                btn.classList.remove('opacity-50', 'cursor-not-allowed');
                setTimeout(() => {
                    if (xhr.status === 200) {
                        progressContainer.classList.add('hidden');
                        form.reset();
                    }
                }, 4000);
            };

            xhr.send(formData);
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/cut', methods=['POST'])
def cut_audio():
    # 👉 每次有人使用，就先執行垃圾回收，保持伺服器硬碟健康
    cleanup_old_temp_dirs()
    
    temp_dir = None
    try:
        if 'file' not in request.files:
            return "沒有接收到檔案，請重新選擇", 400

        file = request.files['file']
        if file.filename == '':
            return "沒有選擇檔案", 400

        try:
            minutes = int(request.form.get('minutes', 30))
        except ValueError:
            return "分鐘數格式錯誤，請輸入數字", 400

        filename = secure_filename(file.filename)
        if not filename:
            filename = "audio_upload.m4a"
            
        base_name, _ = os.path.splitext(filename)

        temp_dir = tempfile.mkdtemp()
        
        input_path = os.path.join(temp_dir, filename)
        file.save(input_path)

        segment_time = minutes * 60
        output_pattern = os.path.join(temp_dir, f"{base_name}_part%03d.m4a")

        cmd = [
            FFMPEG_EXE,
            "-hide_banner",
            "-loglevel", "error",
            "-i", input_path,
            "-f", "segment",
            "-segment_time", str(segment_time),
            "-reset_timestamps", "1",
            "-c", "copy",
            output_pattern
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return "【系統錯誤】找不到 FFmpeg 核心！", 500
        except subprocess.CalledProcessError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return "【FFmpeg 執行錯誤】: 裁減過程發生錯誤", 500

        zip_filename = f"{base_name}_已裁減.zip"
        zip_path = os.path.join(temp_dir, zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(temp_dir):
                if f.startswith(f"{base_name}_part") and f.endswith(".m4a"):
                    file_path = os.path.join(temp_dir, f)
                    zf.write(file_path, f)

        # 🚀 拋棄會引發中斷的 Generator，改用最穩定的 send_file！
        # send_file 會自動提供檔案的精確大小 (Content-Length)，確保瀏覽器能 100% 完整下載。
        return send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{base_name}_已裁減.zip"
        )

    except Exception as e:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        error_msg = traceback.format_exc()
        print(error_msg)
        return f"【伺服器發生未預期錯誤】: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
