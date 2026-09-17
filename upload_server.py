#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Icons Home 上传服务
============================
纯 Python 标准库实现，零第三方依赖（Python 3.8+，3.13 亦可用）。

解决「静态页面无法写入文件」的限制：
  - 网页上传的图片 → 直接保存到项目 icons/ 目录（同名自动覆盖）
  - 上传记录     → 写入 data/uploads.json（程序自动维护，建议加入 .gitignore）
  - 所有访问者刷新页面后都能看到新图标

用法（Windows / Linux / macOS 通用）：
    python upload_server.py                   # 监听 0.0.0.0:8000，托管脚本所在目录
    python upload_server.py --port 9000       # 换端口
    python upload_server.py --host 127.0.0.1  # 仅本机访问
    python upload_server.py --dir D:\\Icons-Home  # 指定项目目录

Docker 部署：见 docker-compose.yml（docker compose up -d）
nginx 反代：见 README.md「用 nginx 反代上传服务」

接口：
    GET  /api/uploads           返回已上传图标记录（页面渲染时合并到图标列表）
    GET  /api/categories        返回网页端自定义分类（data/categories.json）
    POST /api/upload            接收 multipart 上传（字段：file=图片文件、category=分类名）
    POST /api/categories        新增自定义分类（JSON：{"name": "分类名"}）
    POST /api/categories/delete 删除自定义分类，并把该分类下的上传图标移到 other（JSON：{"name": "分类名"}）
    POST /api/delete            删除网页上传的图标：删 icons/ 文件 + uploads 记录（JSON：{"name": "文件名"}）
"""
import email
import json
import os
import re
import sys
from email import policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
MAX_BODY = 20 * 1024 * 1024  # 单次请求体上限 20MB

ARGS = {"host": "0.0.0.0", "port": 8000, "dir": os.path.dirname(os.path.abspath(__file__))}


def parse_args(argv):
    """极简参数解析：--host / --port / --dir"""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--host", "--port", "--dir") and i + 1 < len(argv):
            if a == "--host":
                ARGS["host"] = argv[i + 1]
            elif a == "--port":
                ARGS["port"] = int(argv[i + 1])
            else:
                ARGS["dir"] = argv[i + 1]
            i += 2
        else:
            i += 1
    ARGS["dir"] = os.path.abspath(ARGS["dir"])


def clean_filename(name):
    """清洗文件名：去掉路径与非法字符，校验扩展名白名单，防止路径穿越"""
    if not name:
        return None
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip().strip(".")
    if not name or name in (".", ".."):
        return None
    if os.path.splitext(name)[1].lower() not in ALLOWED_EXTS:
        return None
    return name


class UploadsStore:
    """data/uploads.json 的读写封装（原子写入，同名覆盖）"""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "uploads.json")
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            self._write([])

    def _write(self, records):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"uploads": records}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("uploads"), list):
                return data["uploads"]
        except Exception:
            pass
        return []

    def upsert(self, name, category):
        """新增或覆盖同名记录，返回最新列表"""
        records = [r for r in self.load() if r.get("name") != name]
        records.append({"name": name, "category": category})
        self._write(records)
        return records

    def remove(self, name):
        """删除指定文件名的记录，返回最新列表"""
        records = [r for r in self.load() if r.get("name") != name]
        self._write(records)
        return records

    def move_category(self, old_name, new_name):
        """把某分类下的记录改到另一分类，返回最新列表"""
        records = [dict(r) for r in self.load()]
        changed = False
        for r in records:
            if r.get("category") == old_name:
                r["category"] = new_name
                changed = True
        if changed:
            self._write(records)
        return records


class CategoriesStore:
    """data/categories.json：网页端自定义分类（以 name 为唯一标识）"""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "categories.json")
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            self._write([])

    def _write(self, records):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"categories": records}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("categories"), list):
                return data["categories"]
        except Exception:
            pass
        return []

    def has(self, name):
        return any(c.get("name") == name for c in self.load())

    def add(self, name):
        records = self.load()
        if not any(c.get("name") == name for c in records):
            records.append({"name": name})
            self._write(records)
        return records

    def remove(self, name):
        records = [c for c in self.load() if c.get("name") != name]
        self._write(records)
        return records


class Handler(SimpleHTTPRequestHandler):
    """静态托管 + 上传 / 分类管理 / 图标删除 API"""

    def __init__(self, *args, **kwargs):
        kwargs["directory"] = ARGS["dir"]
        data_dir = os.path.join(ARGS["dir"], "data")
        self.store = UploadsStore(data_dir)
        self.categories = CategoriesStore(data_dir)
        super().__init__(*args, **kwargs)

    # ---------- 响应工具 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, code=400):
        self._json({"ok": False, "error": msg}, code)

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/uploads":
            self._json({"ok": True, "uploads": self.store.load()})
            return
        if path == "/api/categories":
            self._json({"ok": True, "categories": self.categories.load()})
            return
        super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/upload":
            self._handle_upload()
            return
        if path in ("/api/categories", "/api/categories/delete", "/api/delete"):
            data = self._read_json()
            if data is None:
                return
            if path == "/api/categories":
                self._handle_add_category(data)
            elif path == "/api/categories/delete":
                self._handle_delete_category(data)
            else:
                self._handle_delete_icon(data)
            return
        self._err("未知接口", 404)

    def _read_json(self):
        """读取并解析 JSON 请求体，失败返回 None（已回错误响应）"""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._err("请求体无效")
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._err("请求体不是有效 JSON")
            return None

    def _handle_upload(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._err("请求体为空")
            return
        if length > MAX_BODY:
            self._err("文件过大（单次上限 20MB）", 413)
            return
        body = self.rfile.read(length)

        files, fields = self._parse_multipart(body)
        if not files:
            self._err("未收到文件字段")
            return

        saved = []
        for fname, content in files:
            name = clean_filename(fname)
            if not name or len(content) > MAX_BODY:
                continue
            icons_dir = os.path.join(ARGS["dir"], "icons")
            os.makedirs(icons_dir, exist_ok=True)
            with open(os.path.join(icons_dir, name), "wb") as f:
                f.write(content)
            saved.append(name)

        if not saved:
            self._err("没有可保存的文件（仅支持 png / jpg / webp / svg / gif）")
            return

        category = (fields.get("category") or "other").strip() or "other"
        for name in saved:
            self.store.upsert(name, category)
        self._json({"ok": True, "count": len(saved), "files": saved})

    def _handle_add_category(self, data):
        name = (data.get("name") or "").strip()
        if not name:
            self._err("分类名称不能为空")
            return
        if self.categories.has(name):
            self._err("分类已存在：" + name)
            return
        self.categories.add(name)
        self._json({"ok": True, "categories": self.categories.load()})

    def _handle_delete_category(self, data):
        name = (data.get("name") or "").strip()
        if not name:
            self._err("分类名称不能为空")
            return
        if name == "other":
            self._err("「其他」是兜底分类，不能删除")
            return
        # 该分类下的上传图标移到 other
        self.store.move_category(name, "other")
        # 移除自定义分类记录（不在记录里则无操作）
        self.categories.remove(name)
        self._json({"ok": True, "categories": self.categories.load(), "uploads": self.store.load()})

    def _handle_delete_icon(self, data):
        name = clean_filename(data.get("name") or "")
        if not name:
            self._err("文件名无效")
            return
        records = self.store.load()
        if not any(r.get("name") == name for r in records):
            self._err("该图标不是网页上传的图标（基础图标请在 data.js 中管理）")
            return
        fpath = os.path.join(ARGS["dir"], "icons", name)
        if os.path.isfile(fpath):
            os.remove(fpath)
        self.store.remove(name)
        self._json({"ok": True})

    def _parse_multipart(self, body):
        """解析 multipart/form-data，返回 (files, fields)"""
        files = []
        fields = {}
        try:
            # email 解析需要完整 MIME 消息（带头部）；浏览器发送的是纯 body，先补上 Content-Type 头
            ctype = self.headers.get("Content-Type", "multipart/form-data")
            head = ("Content-Type: " + ctype + "\r\nMIME-Version: 1.0\r\n\r\n").encode("utf-8")
            msg = email.message_from_bytes(head + body, policy=policy.default)
            for part in msg.iter_parts():
                disp = part.get_content_disposition() or ""
                if disp != "form-data":
                    continue
                pname = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if filename:
                    files.append((filename, payload))
                elif pname:
                    fields[pname] = payload.decode("utf-8", errors="replace")
        except Exception:
            pass
        return files, fields

    def log_message(self, fmt, *args):
        sys.stderr.write("[icons-home] " + fmt % args + "\n")


def main():
    parse_args(sys.argv[1:])
    if not os.path.isdir(ARGS["dir"]):
        print("项目目录不存在：" + ARGS["dir"], file=sys.stderr)
        sys.exit(1)
    # 确保 data/uploads.json 与 icons/ 存在
    store = UploadsStore(os.path.join(ARGS["dir"], "data"))
    os.makedirs(os.path.join(ARGS["dir"], "icons"), exist_ok=True)

    server = ThreadingHTTPServer((ARGS["host"], ARGS["port"]), Handler)
    url = "http://%s:%d/index.html" % (ARGS["host"], ARGS["port"])
    print("Icons Home 已启动：" + url)
    print("项目目录：" + ARGS["dir"])
    print("上传记录：" + store.path)
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
