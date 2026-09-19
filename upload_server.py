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

管理员模式：
  - 初始账户 admin / password（首次启动自动写入 data/auth.json，密码为加盐哈希存储）
  - POST /api/login 校验通过后返回 token，之后所有写接口需带 X-Auth-Token 请求头
  - 服务重启后 token 失效，需重新登录

用法（Windows / Linux / macOS 通用）：
    python upload_server.py                   # 监听 0.0.0.0:8000，托管脚本所在目录
    python upload_server.py --port 9000       # 换端口
    python upload_server.py --host 127.0.0.1  # 仅本机访问
    python upload_server.py --dir D:\\Icons-Home  # 指定项目目录

Docker 部署：见 docker-compose.yml（docker compose up -d）
nginx 反代：见 README.md「用 nginx 反代上传服务」

接口：
    GET  /api/uploads             返回已上传图标记录（页面渲染时合并到图标列表）
    GET  /api/categories          返回网页端自定义分类（data/categories.json）
    GET  /api/settings            返回站点设置（标题、隐藏的分类/图标、移动记录、favicon）
    GET  /api/auth/check          校验登录状态（需 X-Auth-Token）
    POST /api/login               管理员登录（JSON：{username, password} → {token, username}）
    POST /api/change-password     修改密码（需登录，JSON：{old_password, new_password}）
    POST /api/change-username     修改用户名（需登录，JSON：{new_username, password}）
    POST /api/upload              接收 multipart 上传（需登录；字段：file、category、link 可选）
    POST /api/categories          新增自定义分类（需登录，JSON：{"name": "分类名"}）
    POST /api/categories/delete   删除自定义分类并把其下上传图标移到 other（需登录）
    POST /api/delete              删除网页上传的图标：删 icons/ 文件 + uploads 记录（需登录）
    POST /api/move                批量移动上传图标的分类（需登录，JSON：{names: [...], category}）
    POST /api/rename              重命名上传图标：改 icons/ 文件 + uploads 记录 + 引用同步（需登录，JSON：{old, new}）
    POST /api/settings            更新站点设置（需登录；title? / deleted_categories? / deleted_icons? / icon_moves? / favicon?）
    GET  /api/backup              备份：打包 icons/ + data/ 为「项目名_时间戳.zip」下载（需登录）
    POST /api/restore             恢复：接收备份 zip 并覆盖 icons/ 与 data/（需登录，multipart file）
"""
import email
import hashlib
import io
import json
import os
import re
import secrets
import sys
import time
import zipfile
from email import policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".ico", ".bmp", ".icns"}
MAX_BODY = 20 * 1024 * 1024  # 单次请求体上限 20MB

ARGS = {"host": "0.0.0.0", "port": 8000, "dir": os.path.dirname(os.path.abspath(__file__))}

# 写接口（需登录）：token -> username（内存，重启失效）
TOKENS = {}


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


def hash_password(password, salt):
    return hashlib.sha256((salt + "::" + password).encode("utf-8")).hexdigest()


class AuthStore:
    """data/auth.json：管理员账户（加盐哈希存储，绝不存明文密码）"""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "auth.json")
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            self.set_password("admin", "password")

    def _write(self, obj):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def verify(self, username, password):
        u = self.load().get(username or "")
        if not u:
            return False
        return u.get("hash") == hash_password(password or "", u.get("salt", ""))

    def set_password(self, username, password):
        salt = secrets.token_hex(8)
        obj = self.load()
        obj[username] = {"salt": salt, "hash": hash_password(password, salt)}
        self._write(obj)

    def rename(self, old_username, new_username, password):
        """修改用户名：校验原密码后把账户迁移到新用户名（保留加盐哈希，旧键删除）"""
        obj = self.load()
        u = obj.get(old_username or "")
        if not u:
            return False, "用户不存在"
        if u.get("hash") != hash_password(password or "", u.get("salt", "")):
            return False, "密码不正确"
        new_username = (new_username or "").strip()
        if not new_username:
            return False, "用户名不能为空"
        if new_username != old_username and new_username in obj:
            return False, "该用户名已存在"
        obj[new_username] = u
        if new_username != old_username:
            obj.pop(old_username, None)
        self._write(obj)
        return True, ""


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

    def save(self, records):
        self._write(records)

    def upsert(self, name, category, link=""):
        """新增或覆盖同名记录（含自定义链接与添加时间），返回最新列表
        category 为单个分类；兼容历史数组数据（取第一个）"""
        cat = self._norm_cat(category)
        records = [r for r in self.load() if r.get("name") != name]
        records.append({"name": name, "category": cat, "link": link, "added_at": time.time()})
        self._write(records)
        return records

    @staticmethod
    def _norm_cat(category):
        """规范化分类为单个字符串：列表/数组取第一个，字符串直接取；空则 'other'"""
        if isinstance(category, list):
            out = next((str(x).strip() for x in category if str(x).strip()), "")
        elif isinstance(category, str):
            out = category.strip()
        else:
            out = ""
        return out or "other"

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
            if self._norm_cat(r.get("category")) == old_name:
                r["category"] = new_name
                changed = True
        if changed:
            self._write(records)
        return records

    def move_many(self, names, category):
        """批量把指定文件名的记录移到目标分类，返回最新列表"""
        cat = self._norm_cat(category)
        records = [dict(r) for r in self.load()]
        changed = False
        for r in records:
            if r.get("name") in names and self._norm_cat(r.get("category")) != cat:
                r["category"] = cat
                changed = True
        if changed:
            self._write(records)
        return records

    def rename(self, old, new):
        """重命名记录的文件名（old→new），返回最新列表；old 不存在或 new 已占用返回 None"""
        records = [dict(r) for r in self.load()]
        if not any(r.get("name") == old for r in records):
            return None
        if any(r.get("name") == new for r in records):
            return None
        for r in records:
            if r.get("name") == old:
                r["name"] = new
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


class SettingsStore:
    """data/settings.json：站点级设置（标题、隐藏的分类/图标、移动记录、favicon）"""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "settings.json")
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            self._write({})

    def _write(self, obj):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def update(self, patch):
        obj = self.load()
        obj.update(patch)
        self._write(obj)
        return obj


class Handler(SimpleHTTPRequestHandler):
    """静态托管 + 上传 / 分类管理 / 图标删除 / 批量移动 / 站点设置 / 管理员认证 API"""

    def __init__(self, *args, **kwargs):
        kwargs["directory"] = ARGS["dir"]
        data_dir = os.path.join(ARGS["dir"], "data")
        self.store = UploadsStore(data_dir)
        self.categories = CategoriesStore(data_dir)
        self.settings = SettingsStore(data_dir)
        self.auth = AuthStore(data_dir)
        super().__init__(*args, **kwargs)

    # ---------- 响应工具 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, code=400, errcode=""):
        self._json({"ok": False, "error": msg, "code": errcode}, code)

    def _check_auth(self):
        """写接口鉴权：请求头 X-Auth-Token 必须是已签发的有效 token"""
        token = self.headers.get("X-Auth-Token", "")
        return bool(token and TOKENS.get(token))

    def _auth_user(self):
        return TOKENS.get(self.headers.get("X-Auth-Token", ""), "")

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/uploads":
            self._json({"ok": True, "uploads": self.store.load()})
            return
        if path == "/api/categories":
            self._json({"ok": True, "categories": self.categories.load()})
            return
        if path == "/api/settings":
            self._json({"ok": True, "settings": self.settings.load()})
            return
        if path == "/api/auth/check":
            user = self._auth_user()
            if user:
                self._json({"ok": True, "username": user})
            else:
                self._err("未登录或登录已过期", 401, "auth")
            return
        if path == "/api/backup":
            if not self._check_auth():
                self._err("未登录或登录已过期，请重新登录", 401, "auth")
                return
            self._handle_backup()
            return
        super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/login":
            data = self._read_json()
            if data is not None:
                self._handle_login(data)
            return
        if path == "/api/change-password":
            if not self._check_auth():
                self._err("未登录或登录已过期，请重新登录", 401, "auth")
                return
            data = self._read_json()
            if data is not None:
                self._handle_change_password(data)
            return
        if path == "/api/change-username":
            if not self._check_auth():
                self._err("未登录或登录已过期，请重新登录", 401, "auth")
                return
            data = self._read_json()
            if data is not None:
                self._handle_change_username(data)
            return
        if path == "/api/upload":
            if not self._check_auth():
                self._err("未登录或登录已过期，请重新登录", 401, "auth")
                return
            self._handle_upload()
            return
        if path == "/api/restore":
            if not self._check_auth():
                self._err("未登录或登录已过期，请重新登录", 401, "auth")
                return
            self._handle_restore()
            return
        if path in ("/api/categories", "/api/categories/delete", "/api/delete", "/api/move", "/api/rename", "/api/settings"):
            if not self._check_auth():
                self._err("未登录或登录已过期，请重新登录", 401, "auth")
                return
            data = self._read_json()
            if data is None:
                return
            if path == "/api/categories":
                self._handle_add_category(data)
            elif path == "/api/categories/delete":
                self._handle_delete_category(data)
            elif path == "/api/delete":
                self._handle_delete_icon(data)
            elif path == "/api/move":
                self._handle_move(data)
            elif path == "/api/rename":
                self._handle_rename(data)
            else:
                self._handle_update_settings(data)
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

    # ---------- 认证 ----------
    def _handle_login(self, data):
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if self.auth.verify(username, password):
            token = secrets.token_hex(16)
            TOKENS[token] = username
            self._json({"ok": True, "token": token, "username": username})
        else:
            self._err("用户名或密码错误", 401)

    def _handle_change_password(self, data):
        username = self._auth_user()
        old = data.get("old_password") or ""
        new = data.get("new_password") or ""
        if not self.auth.verify(username, old):
            self._err("当前密码不正确", 401)
            return
        if len(new) < 4:
            self._err("新密码至少 4 位")
            return
        self.auth.set_password(username, new)
        self._json({"ok": True})

    def _handle_change_username(self, data):
        old_username = self._auth_user()
        new_username = (data.get("new_username") or "").strip()
        password = data.get("password") or ""
        if not new_username:
            self._err("用户名不能为空")
            return
        ok, err = self.auth.rename(old_username, new_username, password)
        if not ok:
            self._err(err, 401 if "密码" in err else 400)
            return
        # 更新本 token 的用户名映射，前端保持登录态
        token = self.headers.get("X-Auth-Token", "")
        if token in TOKENS:
            TOKENS[token] = new_username
        self._json({"ok": True, "username": new_username})

    # ---------- 上传 ----------
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
            self._err("没有可保存的文件（仅支持 png / jpg / jpeg / webp / svg / gif / ico / bmp / icns）")
            return

        category = (fields.get("category") or "other").strip() or "other"
        link = (fields.get("link") or "").strip()[:500]
        for name in saved:
            self.store.upsert(name, category, link)
        self._json({"ok": True, "count": len(saved), "files": saved})

    # ---------- 分类 / 图标 / 移动 ----------
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

    def _handle_move(self, data):
        names = []
        for x in (data.get("names") or []):
            n = clean_filename(str(x))
            if n:
                names.append(n)
        if not names:
            self._err("没有可移动的图标")
            return
        category = (str(data.get("category") or "")).strip()[:50] or "other"
        records = self.store.move_many(names, category)
        self._json({"ok": True, "uploads": records})

    def _handle_rename(self, data):
        """重命名上传图标：改 icons/ 文件 + uploads 记录 + settings 里移动记录/隐藏记录的文件名引用"""
        old_raw = (data.get("old") or "").strip()
        new_raw = (data.get("new") or "").strip()
        old_name = clean_filename(old_raw)
        new_name = clean_filename(new_raw)
        if not old_name or not new_name:
            self._err("文件名无效")
            return
        # 拒绝含非法字符/路径的名字（clean_filename 会静默替换，这里要求一致）
        if old_raw != old_name or new_raw != new_name:
            self._err("文件名包含非法字符（\\ / : * ? \" < > |）")
            return
        if old_name == new_name:
            self._err("新文件名与当前相同")
            return
        # 扩展名锁定：不允许通过改名改变扩展名，防止图标格式错乱
        if os.path.splitext(old_name)[1].lower() != os.path.splitext(new_name)[1].lower():
            self._err("扩展名不能修改（仅允许修改文件名主体）")
            return
        records = self.store.load()
        if not any(r.get("name") == old_name for r in records):
            self._err("该图标不是网页上传的图标（data.js 基础图标请编辑 data.js 后手动重命名 icons/ 下文件）")
            return
        old_path = os.path.join(ARGS["dir"], "icons", old_name)
        new_path = os.path.join(ARGS["dir"], "icons", new_name)
        if not os.path.isfile(old_path):
            self._err("服务器上找不到原图标文件：" + old_name)
            return
        if os.path.exists(new_path):
            self._err("已存在同名文件：" + new_name)
            return
        # 1) 重命名文件
        os.rename(old_path, new_path)
        # 2) 更新 uploads 记录（含冲突检测，失败则回滚文件）
        updated = self.store.rename(old_name, new_name)
        if updated is None:
            try:
                os.rename(new_path, old_path)
            except Exception:
                pass
            self._err("重命名冲突：目标文件名已存在")
            return
        # 3) 同步 settings.json 中按文件名记录的引用（icon_moves / deleted_icons）
        try:
            st = self.settings.load()
            changed = False
            if isinstance(st.get("icon_moves"), dict) and old_name in st["icon_moves"]:
                st["icon_moves"][new_name] = st["icon_moves"].pop(old_name)
                changed = True
            if isinstance(st.get("deleted_icons"), list):
                st["deleted_icons"] = [new_name if x == old_name else x for x in st["deleted_icons"]]
                changed = True
            if changed:
                self.settings.update(st)
        except Exception:
            pass
        self._json({"ok": True, "uploads": updated})

    # ---------- 站点设置 ----------
    def _handle_update_settings(self, data):
        """更新站点设置：标题 / 隐藏的基础分类 / 隐藏的基础图标 / 图标移动记录 / favicon"""
        patch = {}
        if "title" in data:
            t = (data.get("title") or "").strip()
            if len(t) > 60:
                self._err("标题过长（最多 60 字符）")
                return
            patch["title"] = t
        if "deleted_categories" in data:
            cats = [str(x).strip() for x in (data.get("deleted_categories") or [])]
            cats = [c for c in cats if c]
            if "other" in cats:
                self._err("「其他」是兜底分类，不能删除")
                return
            patch["deleted_categories"] = cats
        if "deleted_icons" in data:
            icons = [clean_filename(str(x)) for x in (data.get("deleted_icons") or [])]
            icons = [i for i in icons if i]
            # 去重保序
            patch["deleted_icons"] = list(dict.fromkeys(icons))
        if "icon_moves" in data:
            moves = data.get("icon_moves")
            if not isinstance(moves, dict):
                self._err("icon_moves 必须是对象")
                return
            clean_moves = {}
            for k, v in moves.items():
                nk = clean_filename(str(k))
                if nk:
                    clean_moves[nk] = (str(v) or "").strip()[:50]
            patch["icon_moves"] = clean_moves
        if "favicon" in data:
            f = (data.get("favicon") or "").strip()[:500]
            patch["favicon"] = f
        if "category_order" in data:
            order = data.get("category_order")
            if not isinstance(order, list):
                self._err("category_order 必须是数组")
                return
            order = [str(x).strip()[:50] for x in order]
            order = [x for x in order if x]
            # 去重保序
            patch["category_order"] = list(dict.fromkeys(order))
        if "lang" in data:
            lang = (data.get("lang") or "").strip()[:10].lower()
            if lang in ("zh", "en"):
                patch["lang"] = lang
        if not patch:
            self._err("没有可更新的字段")
            return
        self.settings.update(patch)
        self._json({"ok": True, "settings": self.settings.load()})

    # ---------- 备份 / 恢复 ----------
    def _handle_backup(self):
        """打包 icons/ 与 data/（json）为 zip 下载，文件名 = 项目名_时间戳.zip"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            icons_dir = os.path.join(ARGS["dir"], "icons")
            if os.path.isdir(icons_dir):
                for name in sorted(os.listdir(icons_dir)):
                    fp = os.path.join(icons_dir, name)
                    if os.path.isfile(fp):
                        zf.write(fp, os.path.join("icons", name))
            data_dir = os.path.join(ARGS["dir"], "data")
            if os.path.isdir(data_dir):
                for name in sorted(os.listdir(data_dir)):
                    fp = os.path.join(data_dir, name)
                    if os.path.isfile(fp) and name.endswith(".json"):
                        zf.write(fp, os.path.join("data", name))
        body = buf.getvalue()
        proj = os.path.basename(os.path.normpath(ARGS["dir"])) or "Icons-Home"
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = "%s_%s.zip" % (proj, ts)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_restore(self):
        """接收备份 zip，解压覆盖 icons/ 与 data/（仅允许这两类文件，防路径穿越）"""
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
            self._err("未收到备份文件")
            return
        fname, content = files[0]
        if not content or content[:2] != b"PK":
            self._err("不是有效的 ZIP 备份文件")
            return

        icons_dir = os.path.join(ARGS["dir"], "icons")
        data_dir = os.path.join(ARGS["dir"], "data")
        os.makedirs(icons_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                # 兼容静态模式备份：根级 data.json + icons/*（图片以 DataURL 存在 uploads 里）
                static_data = None
                if "data.json" in names:
                    try:
                        with zf.open("data.json") as src:
                            static_data = json.loads(src.read().decode("utf-8"))
                    except Exception:
                        static_data = None
                if static_data is not None:
                    # 覆盖式还原站点数据
                    def _dump_json(path, obj):
                        tmp = path + ".tmp"
                        with open(tmp, "w", encoding="utf-8") as f:
                            json.dump(obj, f, ensure_ascii=False, indent=2)
                        os.replace(tmp, path)
                    up = static_data.get("uploads") or []
                    # 服务模式记录不需要 dataUrl（图片会从 icons/* 落盘）
                    clean_up = []
                    for u in up:
                        item = {"name": u.get("name", ""), "category": UploadsStore._norm_cat(u.get("category"))}
                        if u.get("link"):
                            item["link"] = u.get("link")
                        if u.get("added_at"):
                            item["added_at"] = u.get("added_at")
                        clean_up.append(item)
                    _dump_json(os.path.join(data_dir, "uploads.json"), {"uploads": clean_up})
                    _dump_json(os.path.join(data_dir, "categories.json"), {"categories": static_data.get("categories") or []})
                    st = static_data.get("settings") or {}
                    settings_obj = {}
                    if st.get("title"):
                        settings_obj["title"] = st["title"][:60]
                    if st.get("favicon"):
                        settings_obj["favicon"] = st["favicon"][:500]
                    if st.get("deleted_categories"):
                        settings_obj["deleted_categories"] = st["deleted_categories"]
                    if st.get("deleted_icons"):
                        settings_obj["deleted_icons"] = st["deleted_icons"]
                    if st.get("icon_moves") and isinstance(st["icon_moves"], dict):
                        settings_obj["icon_moves"] = st["icon_moves"]
                    if st.get("category_order") and isinstance(st["category_order"], list):
                        settings_obj["category_order"] = st["category_order"]
                    _dump_json(os.path.join(data_dir, "settings.json"), settings_obj)
                    # 图片文件：DataURL 转二进制落盘 icons/
                    written = 0
                    for u in up:
                        data_url = u.get("dataUrl") or ""
                        m = re.match(r"^data:([^;]+);base64,(.*)$", data_url, re.S)
                        if not m:
                            continue
                        name = clean_filename(u.get("name") or "")
                        if not name:
                            continue
                        import base64
                        try:
                            raw = base64.b64decode(m.group(2))
                        except Exception:
                            continue
                        with open(os.path.join(icons_dir, name), "wb") as f:
                            f.write(raw)
                        written += 1
                    self._json({"ok": True, "count": len(clean_up) + written, "static": True})
                    return
                # 服务模式备份格式：data/*.json + icons/*
                valid = []
                for n in names:
                    parts = n.replace("\\", "/").split("/")
                    if len(parts) == 2 and parts[0] == "icons":
                        clean = clean_filename(parts[1])
                        if clean:
                            valid.append((n, os.path.join(icons_dir, clean)))
                    elif len(parts) == 2 and parts[0] == "data" and parts[1].endswith(".json"):
                        b = os.path.basename(parts[1])
                        if b == parts[1] and b in ("uploads.json", "categories.json", "settings.json", "auth.json"):
                            valid.append((n, os.path.join(data_dir, b)))
                if not valid:
                    self._err("备份文件内没有可恢复的图标或数据")
                    return
                for n, dst in valid:
                    with zf.open(n) as src, open(dst, "wb") as out:
                        out.write(src.read())
        except zipfile.BadZipFile:
            self._err("备份文件损坏或不是 ZIP")
            return
        self._json({"ok": True, "count": len(valid)})

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
    # 确保 data/uploads.json、data/auth.json 与 icons/ 存在
    store = UploadsStore(os.path.join(ARGS["dir"], "data"))
    AuthStore(os.path.join(ARGS["dir"], "data"))
    os.makedirs(os.path.join(ARGS["dir"], "icons"), exist_ok=True)

    server = ThreadingHTTPServer((ARGS["host"], ARGS["port"]), Handler)
    url = "http://%s:%d/index.html" % (ARGS["host"], ARGS["port"])
    print("Icons Home 已启动：" + url)
    print("项目目录：" + ARGS["dir"])
    print("上传记录：" + store.path)
    print("管理员：admin / password（登录后可修改密码）")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
