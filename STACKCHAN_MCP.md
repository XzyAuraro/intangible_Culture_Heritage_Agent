# StackChan MCP Safe Guide

This project exposes a text-only Palace Museum guide tool to StackChan/Xiaozhi through the MCP endpoint.

## Safety Boundaries

- Only one MCP tool is registered: `palace_museum_guide`.
- The tool only returns guide text.
- It does not call servo, expression, light, volume, reboot, network, or other hardware-control tools.
- The WebSocket endpoint/token must stay in `.env.local` or an environment variable. Do not commit it.
- If a token was shared in chat or screenshots, regenerate it in the StackChan/Xiaozhi app before use.

## Local Setup

Add this to `.env.local`:

```env
XIAOZHI_MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=replace_with_your_new_token
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start the bridge:

```powershell
python xiaozhi_mcp_bridge.py
```

When connected, the StackChan/Xiaozhi MCP page should show Online.

## Trigger Examples

Say one of these to StackChan:

- 请做故宫讲解员，讲解钟表馆。
- 讲解活动机械钟。
- 请介绍这件文物为什么重要。
- 带我看乾清宫原状陈列。

The device AI should call `palace_museum_guide`, receive a short guide text, and speak it using its own voice pipeline.

## Notes

For video recording, keep this bridge running locally. If anything feels wrong, stop it with `Ctrl+C`; no hardware motion command is registered by this project.
