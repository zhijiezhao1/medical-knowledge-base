"""
医学知识库 - 后端 REST API 服务器
基于 Python 标准库 http.server（Flask 替代方案，零外部依赖）
"""
import os
import sys
import json
import re
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# 导入项目模块
sys.path.insert(0, os.path.dirname(__file__))
from database import (
    init_db, insert_document, get_documents,
    get_document_by_id, delete_document, search_documents
)
from doc_parser import parse_file

# ========== 配置 ==========
HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 8080))

# 数据目录：从环境变量读取（Railway 持久化存储挂载点）
# 本地开发默认使用项目根目录，Railway 部署使用 /data
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__))))

# 数据库路径和上传目录路径
DB_DIR = DATA_DIR  # 与 database.py 共享同一个数据目录
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(DATA_DIR, 'uploads'))

# 前端目录（始终在项目内，不参与持久化）
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ========== CORS 头 ==========
def set_cors_headers(handler):
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.send_header('Access-Control-Allow-Headers', 'X-Requested-With')


def json_response(handler, data, status=200):
    """发送 JSON 响应"""
    handler.send_response(status)
    set_cors_headers(handler)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


def text_response(handler, text, status=200, content_type='text/plain; charset=utf-8'):
    """发送纯文本响应"""
    handler.send_response(status)
    set_cors_headers(handler)
    handler.send_header('Content-Type', content_type)
    handler.end_headers()
    if isinstance(text, str):
        text = text.encode('utf-8')
    handler.wfile.write(text)


def send_file(handler, file_path, content_type):
    """发送文件"""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        handler.send_response(200)
        set_cors_headers(handler)
        handler.send_header('Content-Type', content_type)
        handler.send_header('Content-Length', len(content))
        handler.end_headers()
        handler.wfile.write(content)
    except FileNotFoundError:
        handler.send_response(404)
        handler.end_headers()
        handler.wfile.write(b'File not found')


def parse_multipart(body_bytes, content_type):
    """
    手动解析 multipart/form-data，替代有问题的 cgi.FieldStorage。
    返回 {'file': (filename, content_bytes)} 或 {}
    """
    # 提取 boundary
    parts = content_type.split(';')
    boundary = None
    for part in parts:
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part[9:].strip('"\'')
            break
    if not boundary:
        return {}

    delimiter = b"--" + boundary.encode()
    end_delimiter = delimiter + b"--"

    # 分割各 part（不保留分隔符）
    raw_parts = body_bytes.split(delimiter)
    result = {}

    for raw in raw_parts:
        raw = raw.strip(b"\r\n")
        if not raw or raw == b"--" or raw == b"":
            continue
        if raw.endswith(b"--"):
            continue

        # 每个 part 以 CRLF 开始
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        elif raw.startswith(b"\n"):
            raw = raw[1:]

        # 找到 header 和 body 的分隔符（两个 CRLF）
        header_end = raw.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        header_block = raw[:header_end].decode("utf-8", errors="replace")
        body = raw[header_end + 4:]

        # 跳过末尾的 CRLF（如果存在）
        if body.endswith(b"\r\n"):
            body = body[:-2]

        # 解析 Content-Disposition
        name = None
        filename = None
        for line in header_block.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                for segment in line.split(";"):
                    segment = segment.strip()
                    if segment.startswith("name="):
                        name = segment[5:].strip('"\'')
                    elif segment.startswith("filename="):
                        filename = segment[9:].strip('"\'')
                        # 取 basename，防止路径穿越
                        filename = os.path.basename(filename)

        if name == "file" and filename:
            result["file"] = (filename, body)

    return result


class RequestHandler(BaseHTTPRequestHandler):
    """自定义 HTTP 请求处理器"""

    def log_message(self, format, *args):
        """格式化日志输出"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        set_cors_headers(self)
        self.end_headers()

    def do_GET(self):
        """GET 请求处理"""
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        # 静态文件服务（前端页面）
        if path == '/' or path == '/index.html':
            send_file(self, os.path.join(FRONTEND_DIR, 'index.html'), 'text/html; charset=utf-8')
            return

        if path == '/styles.css':
            send_file(self, os.path.join(FRONTEND_DIR, 'styles.css'), 'text/css; charset=utf-8')
            return

        if path == '/app.js':
            send_file(self, os.path.join(FRONTEND_DIR, 'app.js'), 'application/javascript; charset=utf-8')
            return

        # 测试页面
        if path == '/test.html' or path == '/test_search.html':
            send_file(self, os.path.join(FRONTEND_DIR, path.lstrip('/')), 'text/html; charset=utf-8')
            return

        # API: 文档列表
        if path == '/api/documents':
            format_filter = query.get('format', ['all'])[0]
            sort_order = query.get('sort', ['desc'])[0]
            docs = get_documents(format_filter, sort_order)
            json_response(self, {'documents': docs})
            return

        # API: 单个文档内容
        match = re.match(r'^/api/documents/(\d+)$', path)
        if match:
            doc_id = int(match.group(1))
            doc = get_document_by_id(doc_id)
            if doc:
                json_response(self, doc)
            else:
                json_response(self, {'error': '文档不存在'}, 404)
            return

        # API: 搜索
        if path == '/api/search':
            keyword = query.get('q', [''])[0].strip()
            if not keyword:
                json_response(self, {'query': '', 'results': [], 'total': 0})
                return
            results = search_documents(keyword)
            json_response(self, {
                'query': keyword,
                'results': results,
                'total': len(results)
            })
            return

        # 未知路径
        self.send_response(404)
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not Found'}).encode('utf-8'))

    def do_POST(self):
        """POST 请求处理"""
        path = urllib.parse.urlparse(self.path).path

        # 文件上传
        if path == '/api/documents/upload':
            self._handle_upload()
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not Found'}).encode('utf-8'))

    def do_DELETE(self):
        """DELETE 请求处理"""
        path = urllib.parse.urlparse(self.path).path

        # 删除文档
        match = re.match(r'^/api/documents/(\d+)$', path)
        if match:
            doc_id = int(match.group(1))
            deleted = delete_document(doc_id)
            if deleted:
                json_response(self, {'message': '删除成功', 'id': doc_id})
            else:
                json_response(self, {'error': '文档不存在'}, 404)
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not Found'}).encode('utf-8'))

    def _handle_upload(self):
        """处理文件上传"""
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                json_response(self, {'error': '需要 multipart/form-data 格式'}, 400)
                return

            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            # 手动解析 multipart
            parts = parse_multipart(body, content_type)
            if 'file' not in parts:
                json_response(self, {'error': '未找到文件字段'}, 400)
                return

            file_name, file_data = parts['file']
            if not file_name:
                json_response(self, {'error': '未选择文件'}, 400)
                return

            file_ext = os.path.splitext(file_name)[1].lower()
            if file_ext not in ('.docx', '.rtf', '.txt'):
                json_response(self, {'error': f'不支持的文件格式: {file_ext}，仅支持 .docx .rtf .txt'}, 400)
                return

            file_size = len(file_data)

            # 限制文件大小 50MB
            if file_size > 50 * 1024 * 1024:
                json_response(self, {'error': '文件超过 50MB 限制'}, 400)
                return

            # 保存上传文件到临时目录
            temp_path = os.path.join(UPLOAD_DIR, f'temp_{file_name}')
            with open(temp_path, 'wb') as f:
                f.write(file_data)

            # 解析文档
            try:
                html_content, plain_text, fmt = parse_file(temp_path)
            except ValueError as e:
                os.remove(temp_path)
                json_response(self, {'error': str(e)}, 400)
                return
            except Exception as e:
                os.remove(temp_path)
                json_response(self, {'error': f'文档解析失败: {str(e)}'}, 500)
                return

            # 清理临时文件
            os.remove(temp_path)

            # 提取标题（去掉扩展名）
            title = os.path.splitext(file_name)[0]

            # 写入数据库
            try:
                doc_id = insert_document(
                    title=title,
                    file_name=file_name,
                    format=fmt,
                    html_content=html_content,
                    plain_text=plain_text,
                    file_size=file_size
                )
            except ValueError as e:
                json_response(self, {'error': str(e)}, 400)
                return

            print(f"[Upload] 文档上传成功: {file_name} (ID: {doc_id})")
            json_response(self, {
                'id': doc_id,
                'title': title,
                'format': fmt,
                'upload_time': datetime.now().isoformat()
            }, 201)

        except Exception as e:
            print(f"[Upload Error] {str(e)}")
            import traceback
            traceback.print_exc()
            json_response(self, {'error': f'服务器错误: {str(e)}'}, 500)


def run():
    """启动服务器"""
    init_db()
    server = HTTPServer((HOST, PORT), RequestHandler)
    print(f"""
╔═══════════════════════════════════════════════════╗
║         医学知识库后端服务                          ║
║         Local Server                               ║
╠═══════════════════════════════════════════════════╣
║  访问地址:  http://{HOST}:{PORT}                    ║
║  API 文档:  http://{HOST}:{PORT}/api/documents      ║
║  数据目录:  {DATA_DIR}                    ║
║  上传目录:  {UPLOAD_DIR}                    ║
║  按 Ctrl+C 停止服务                                ║
╚═══════════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[Server] 服务已停止')
        server.shutdown()


if __name__ == '__main__':
    run()
