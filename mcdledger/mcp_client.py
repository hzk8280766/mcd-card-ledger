"""麦当劳 MCP (Streamable HTTP) 极简客户端。

只用 Python 标准库实现 JSON-RPC over Streamable HTTP：
- initialize 握手，保持 mcp-session-id
- tools/list / tools/call
- 客户端限流（默认间隔 0.12s，约 500 req/min，官方上限 600 req/min）
- 429 / 5xx 指数退避重试
- 同时兼容 application/json 与 text/event-stream 两种响应体
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

JSONRPC = "2.0"
DEFAULT_BASE_URL = "https://mcp.mcd.cn"


class MCPError(RuntimeError):
    """MCP 通信或业务错误。"""


class MCDClient:
    def __init__(self, token, base_url=DEFAULT_BASE_URL, min_interval=0.12, timeout=30):
        if not token:
            raise MCPError("缺少 MCP Token：请先在 https://open.mcd.cn/mcp 申请")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.timeout = timeout
        self.session_id = None
        self._id = 0
        self._last_ts = 0.0
        self._tools_cache = None

    # ---------- 底层传输 ----------

    def _next_id(self):
        self._id += 1
        return self._id

    def _throttle(self):
        wait = self.min_interval - (time.monotonic() - self._last_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_ts = time.monotonic()

    def _post(self, payload, retries=3):
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
            "User-Agent": "mcd-card-ledger/1.0",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        last_err = None
        for attempt in range(retries):
            self._throttle()
            req = urllib.request.Request(
                self.base_url, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    sid = resp.headers.get("mcp-session-id")
                    if sid:
                        self.session_id = sid
                    raw = resp.read().decode("utf-8", "replace")
                    return self._parse_response(raw)
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                last_err = "HTTP %s: %s" % (e.code, detail)
                if e.code == 429 or 500 <= e.code < 600:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise MCPError(last_err)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = str(e)
                time.sleep(1.0 * (attempt + 1))
        raise MCPError("请求失败（重试 %d 次后放弃）：%s" % (retries, last_err))

    @staticmethod
    def _parse_response(raw):
        """兼容裸 JSON 与 SSE(event-stream) 两种响应体；空体视为空结果。"""
        text = (raw or "").strip()
        if not text:
            return {}
        if text.startswith("{"):
            return json.loads(text)
        # SSE：逐行找 data: 前缀
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data:
                    return json.loads(data)
        raise MCPError("无法解析 MCP 响应：%r" % text[:200])

    def _rpc(self, method, params=None):
        payload = {"jsonrpc": JSONRPC, "id": self._next_id(), "method": method}
        if params is not None:
            payload["params"] = params
        resp = self._post(payload)
        if "error" in resp:
            raise MCPError("RPC %s 错误：%s" % (method, resp["error"]))
        return resp.get("result", {})

    # ---------- MCP 协议 ----------

    def initialize(self):
        """握手。返回服务端协议信息。"""
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "mcd-card-ledger", "version": "1.0.0"},
            },
        )
        # 完成握手通知（notification 无 id，不等响应）
        self._post({"jsonrpc": JSONRPC, "method": "notifications/initialized"})
        return result

    def list_tools(self, refresh=False):
        if self._tools_cache is None or refresh:
            self._tools_cache = self._rpc("tools/list").get("tools", [])
        return self._tools_cache

    def call_tool(self, name, arguments=None):
        """调用工具并把 MCP content 结果转成 Python 对象（尽量 JSON 化）。"""
        result = self._rpc(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        content = result.get("content", []) or []
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        if result.get("isError"):
            raise MCPError(
                "工具 %s 返回错误：%s" % (name, "; ".join(texts)[:300])
            )
        if len(texts) == 1:
            return self._maybe_json(texts[0])
        joined = "\n".join(texts)
        return self._maybe_json(joined)

    @staticmethod
    def _maybe_json(text):
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text

    # ---------- 便捷方法 ----------

    def ping(self):
        """连通性自检：握手 + 拉一次当前时间。"""
        info = self.initialize()
        now = self.call_tool("now-time-info")
        return info, now
