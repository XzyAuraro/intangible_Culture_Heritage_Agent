# StackChan MCP 安全讲解接入

这个项目通过小智/StackChan 的 MCP Endpoint 暴露一个“故宫讲解员”工具。当前版本只做文字讲解，不做任何硬件动作控制。

## 安全边界

- 只注册一个 MCP 工具：`palace_museum_guide`。
- 工具只返回讲解文本。
- 不注册、不调用舵机、动作、表情、灯光、音量、重启、网络设置等硬件控制能力。
- MCP WebSocket 地址和 token 只能放在 `.env.local` 或云端环境变量里，不要提交到 GitHub。
- 如果 token 已经出现在聊天或截图中，建议重新生成后再使用。

## 本地启动

在 `.env.local` 中加入：

```env
XIAOZHI_MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=replace_with_your_new_token
ENABLE_STACKCHAN_MCP_BRIDGE=true
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动桥接：

```powershell
python xiaozhi_mcp_bridge.py
```

连接成功后，小智/StackChan MCP 页面应显示 Online。

## Render 云端启动

如果希望电脑不运行本地脚本，也能直接对 StackChan 说话触发讲解，需要让已部署的 Render Web Service 自动启动 MCP 桥接。

在 Render 当前 Web Service 的 Environment Variables 中加入：

```env
XIAOZHI_MCP_ENDPOINT=你的 StackChan MCP wss 地址
ENABLE_STACKCHAN_MCP_BRIDGE=true
```

重新部署后，网页服务启动时会在后台连接小智 MCP。由于 Render 免费 Web Service 可能在空闲时休眠，录制演示前建议先打开网页唤醒服务，再确认 StackChan MCP 页面为 Online。

## 触发示例

可以对 StackChan 说：

- 请做故宫讲解员，讲解钟表馆。
- 讲解活动机械钟。
- 请介绍这件文物为什么重要。
- 带我看乾清宫原状陈列。

设备侧 AI 应调用 `palace_museum_guide`，拿到一段短讲解文本，再用 StackChan 自己的语音链路说出来。
