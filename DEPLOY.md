# Deployment

This project needs a running Python backend for RAG, LLM calls, and text-to-speech.
GitHub Pages can host only the static page, so the recommended public demo path is:

1. Push this repository to GitHub.
2. Create a Render Web Service from this GitHub repository.
3. Render will read `render.yaml`, install dependencies, and run:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

4. Add this environment variable in Render:

```bash
CULTURE_AGENT_DASHSCOPE_API_KEY=your_key_here
```

Optional environment variables:

```bash
DASHSCOPE_API_KEY=your_general_dashscope_key_if_you_do_not_use_the_project_specific_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
EDGE_TTS_VOICE=zh-CN-YunxiNeural
```

After deployment, open the Render service URL. The same public URL serves the frontend and the API.

Local development still works at:

```bash
http://127.0.0.1:8001/index.html
```

When the frontend is served by the backend in production, it automatically uses the same origin as `API_BASE`.
