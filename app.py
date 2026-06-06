import os
import asyncio
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
import edge_tts  # 引入微软高保真语音合成

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建并挂载存放音频的静态文件夹
OS_AUDIO_DIR = "static_audio"
os.makedirs(OS_AUDIO_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=OS_AUDIO_DIR), name="static")

# ==================== 核心配置区域 ====================
ALIYUN_API_KEY = "sk-6391565e9d9e42a3b3d4acc9e64c3434"

client = OpenAI(
    api_key=ALIYUN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
# ====================================================

KNOWLEDGE_BASE = {
    "水": "沧浪亭之胜，独处孤绝，环之以水。苏舜钦《沧浪亭记》云：‘前竹后水，水之阳有竹千个’。造园重水，因水能借景，澄澈心境。",
    "沧浪亭": "沧浪亭创自北宋文人苏舜钦。庆历四年，苏氏削籍隐居吴中，斥钱四万于三元代旁建亭，取‘沧浪之水清兮，可以濯我缨’之意。",
    "修竹": "苏舜钦《沧浪亭记']云：‘前竹后水’。文人爱竹，取其虚心有节，与水相映，最称清高之致。"
}

SYSTEM_PROMPT = """你生于北宋，是一位同游园林的宋代文人墨客。
【身份约束】你绝不知道现代科技、打卡、微信等词汇。如果游客问及现代时事，请委婉拒绝并引导回园林主题。
【生成策略】请参考【历史史料】提供的信息。将其转化为富有诗意、字句节制、带有文人机锋的宋式口语化讲解词。
【硬性限制】你必须基于提供的材料回答，严禁时空穿越引用明清（如《园冶》《长物志》）的内容！"""

@app.post("/api/chat")
async def chat_endpoint(file: UploadFile = File(...), text_fallback: str = None):
    try:
        user_text = text_fallback if text_fallback else "为什么沧浪亭里处处有修竹与清流？"
        print(f"[收到提问]: {user_text}")
        
        # 1. RAG 知识库检索
        context = ""
        source = "根据心中所学即兴化用"
        for key, value in KNOWLEDGE_BASE.items():
            if key in user_text:
                context = value
                source = "北宋·苏舜钦《沧浪亭记》"
                break
        
        # 2. 大模型生成
        user_message = f"【历史史料】: {context}\n【游客提问】: {user_text}" if context else f"【游客提问】: {user_text}"
        chat_completion = client.chat.completions.create(
            model="qwen-plus", 
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1
        )
        speech_text = chat_completion.choices[0].message.content
        print(f"[文人生成的讲解词]: {speech_text}")
        
        # 3. === 【终极绝杀：调用微软 Edge 高保真说书人男声】 ===
        output_audio_name = "output_response.mp3"
        output_audio_path = f"{OS_AUDIO_DIR}/{output_audio_name}"
        
        # 使用 zh-CN-YunxiNeural (云希经典温润男声)
        communicate = edge_tts.Communicate(speech_text, "zh-CN-YunxiNeural")
        await communicate.save(output_audio_path)
        print(f"[语音合成成功]: {output_audio_path}")
        
        return JSONResponse({
            "status": "success",
            "user_text": user_text,
            "speech_text": speech_text,
            "source": source,
            "audio_url": f"http://127.0.0.1:8000/static/{output_audio_name}"
        })
        
    except Exception as e:
        print(f"[核心全链路报错]: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)