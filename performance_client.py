"""Read-only performance API proxy; credentials never leave the local backend."""
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://192.168.100.247:8765"
QUERY_KEYS = frozenset("q department status person_id person_name archived due_from due_to page page_size sort_by descending fresh".split())
CONFIG_LOCK = threading.RLock()


class PerformanceError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PerformanceClient:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "performance-api.json"
        self.lock = CONFIG_LOCK

    def _config(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"baseUrl": DEFAULT_URL, "token": ""}

    def settings(self):
        with self.lock:
            config = self._config()
            return {"baseUrl": config["baseUrl"], "configured": bool(config.get("token"))}

    def save(self, body):
        url = str(body.get("baseUrl", DEFAULT_URL)).strip().rstrip("/")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise PerformanceError("请输入不带路径、用户名或参数的 HTTP/HTTPS 接口地址", 400)
        with self.lock:
            config = self._config()
            token = body.get("token")
            if token is not None and (not isinstance(token, str) or len(token) > 4096 or any(c.isspace() for c in token)):
                raise PerformanceError("密钥格式无效", 400)
            if token:
                config["token"] = token
            elif url != config["baseUrl"]:
                config["token"] = ""
            if url != config["baseUrl"]:
                config.pop("writeToken", None)
            if body.get("clearToken"):
                config["token"] = ""
                config.pop("writeToken", None)
            config["baseUrl"] = url
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".performance-")
            try:
                with os.fdopen(fd, "w") as handle:
                    json.dump(config, handle)
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return self.settings()

    def get(self, resource, query=""):
        if resource not in {"meta", "people", "records"} and not re.fullmatch(r"records/rec[A-Za-z0-9_-]+", resource):
            raise PerformanceError("不支持的任务接口", 404)
        with self.lock:
            config = self._config()
        if not config.get("token"):
            raise PerformanceError("请先在连接设置中填写只读密钥", 401)
        params = urllib.parse.parse_qs(query, keep_blank_values=False)
        allowed = QUERY_KEYS if resource == "records" else frozenset()
        filtered = {key: values[-1] for key, values in params.items() if key in allowed}
        url = config["baseUrl"] + "/v1/" + resource
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered)
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + config["token"], "Accept": "application/json"})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
                payload = json.load(response)
            if payload.get("ok") is not True:
                raise PerformanceError("任务服务返回了无效响应")
            return payload
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read(128000)).get("detail", "任务请求失败")
                if not isinstance(detail, str):
                    detail = json.dumps(detail, ensure_ascii=False)
            except (ValueError, AttributeError):
                detail = "任务请求失败"
            detail = detail.replace(config["token"], "[redacted]")
            raise PerformanceError(detail, error.code if error.code in {401,403,404,409,422,502,503} else 502) from None
        except (OSError, ValueError):
            raise PerformanceError("无法连接任务服务，请检查接口地址、网络或树莓派状态", 502) from None
