import os
import subprocess
import tempfile
import zipfile
import io
import urllib.parse
import traceback
from flask import Flask, request, render_template_string, send_file
from werkzeug.utils import secure_filename

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
            <p class="text-slate-500 mt-2 text-sm">檔案將上傳至伺服器處理，不消耗您的手機效能。</p>
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

        <div id="loading" class="hidden mt-6 text-center text-blue-600 font-medium">
            <div class="flex items-center justify-center space-x-2 mb-2">
                <svg class="animate-spin h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>檔案上傳與處理中...</span>
            </div>
            <p class="text-xs text-slate-400">這可能需要幾分鐘，請勿關閉網頁或鎖定螢幕。</p>
        </div>
    </div>

    <script>
        const form = document.getElementById('uploadForm');
        const btn = document.getElementById('submitBtn');
        const loading = document.getElementById('loading');

        form.addEventListener('submit', async (e) => {
            e.preventDefault(); 
            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            loading.classList.remove('hidden');

            const formData = new FormData(form);

            try {
                const response = await fetch('/api/cut', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    let filename = "cut_audio.zip";
                    const disposition = response.headers.get('Content-Disposition');
                    if (disposition && disposition.includes('filename*=UTF-8\\'\\'')) {
                        filename = decodeURIComponent(disposition.split('filename*=UTF-8\\'\\'')[1]);
                    }

                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                } else {
                    const errorText = await response.text();
                    alert('伺服器處理失敗：\\n' + errorText);
                }
            } catch (error) {
                alert('網路錯誤：伺服器可能沒有回應，或處理時間過長。');
            } finally {
                btn.disabled = false;
                btn.classList.remove('opacity-50', 'cursor-not-allowed');
                loading.classList.add('hidden');
                form.reset();
            }
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
    # 使用 try...except 包覆全部邏輯，避免直接拋出 500 HTML 錯誤頁面
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

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, filename)
            file.save(input_path)

            segment_time = minutes * 60
            output_pattern = os.path.join(temp_dir, f"{base_name}_part%03d.m4a")

            cmd = [
                "ffmpeg",
                "-i", input_path,
                "-f", "segment",
                "-segment_time", str(segment_time),
                "-reset_timestamps", "1",
                "-c", "copy",
                output_pattern
            ]

            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError:
                # 若發生此錯誤，代表 Railway 沒有正確安裝 ffmpeg
                return "【系統錯誤】伺服器內找不到 FFmpeg 指令！請確認您的 apt.txt 檔案名稱全小寫，內容為 ffmpeg。", 500
            except subprocess.CalledProcessError as e:
                return f"【FFmpeg 執行錯誤】: {e.stderr.decode('utf-8', errors='ignore')}", 500

            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in os.listdir(temp_dir):
                    if f.startswith(f"{base_name}_part") and f.endswith(".m4a"):
                        file_path = os.path.join(temp_dir, f)
                        zf.write(file_path, f)

            memory_file.seek(0)
        
        encoded_filename = urllib.parse.quote(f"已裁減_雲端處理.zip")

        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"已裁減_雲端處理.zip"
        )
    except Exception as e:
        # 捕捉所有未預期的錯誤並回傳清楚的訊息
        error_msg = traceback.format_exc()
        print(error_msg) # 將錯誤列印到 Railway 後台以便除錯
        return f"【伺服器發生未預期錯誤】: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
