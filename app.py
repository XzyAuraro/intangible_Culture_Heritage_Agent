import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any

import edge_tts
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel


ROOT = Path(__file__).parent
AUDIO_DIR = ROOT / "static_audio"
DATA_DIR = ROOT / "data"
KNOWLEDGE_PATH = DATA_DIR / "canglang_pavilion_knowledge.json"
PALACE_PATH = DATA_DIR / "palace_museum_demo.json"

AUDIO_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


def load_local_env() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()


app = FastAPI(title="Song Literati Garden Museum Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=AUDIO_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")


API_KEY = (
    os.getenv("CULTURE_AGENT_DASHSCOPE_API_KEY")
    or os.getenv("DASHSCOPE_API_KEY")
    or os.getenv("ALIYUN_API_KEY")
)
client = OpenAI(
    api_key=API_KEY or "missing-key",
    base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
)


DEFAULT_KNOWLEDGE: dict[str, Any] = {
    "museum": {
        "title": "沧浪亭虚拟展馆",
        "subtitle": "与宋代文人同游园林",
        "opening": "此馆以沧浪亭为第一处样例园林，将水、竹、亭、窗与文人居游拆成可游、可听、可问的展区。",
    },
    "spots": [
        {
            "id": "water",
            "title": "水景与沧浪之意",
            "era": "北宋",
            "keywords": ["水", "沧浪", "濯缨", "清流", "临水", "园林"],
            "summary": "沧浪亭以水为园外之景，借清流营造疏朗、清远的文人居游气质。",
            "source": "北宋·苏舜钦《沧浪亭记》",
            "evidence": "沧浪之名取意于“沧浪之水清兮，可以濯吾缨”。园中之水不只是景物，也是文人自持与退隐心境的象征。",
            "plain": "水景让园林空间显得更开阔，也把“清”“远”“退隐”的文人气质放进了游览体验。",
        },
        {
            "id": "bamboo",
            "title": "修竹与文人品格",
            "era": "北宋",
            "keywords": ["竹", "修竹", "有节", "清高", "君子", "文人"],
            "summary": "竹在文人园林中常被看作清劲、有节、虚心的象征。",
            "source": "苏舜钦《沧浪亭记》及宋代文人咏竹传统",
            "evidence": "沧浪亭叙事常与“前竹后水”的空间印象相连。竹之中空外直、有节不屈，适合承载宋代士人的人格想象。",
            "plain": "竹子不只是装饰，它让游客把自然景物和文人的人格理想联系起来。",
        },
        {
            "id": "pavilion",
            "title": "亭名、题咏与身份",
            "era": "北宋",
            "keywords": ["亭", "沧浪亭", "题名", "苏舜钦", "退居", "隐逸"],
            "summary": "亭是园林中最适合停步、远望、题咏和叙事的建筑节点。",
            "source": "北宋·苏舜钦《沧浪亭记》",
            "evidence": "苏舜钦退居吴中后营构沧浪亭，亭名与楚辞典故相连，既指景，也指人的处境与心志。",
            "plain": "亭名不是普通命名，而是在表达主人如何看待自己的遭遇、志向和生活方式。",
        },
        {
            "id": "window",
            "title": "漏窗、框景与借景",
            "era": "园林营造理论补充",
            "keywords": ["窗", "漏窗", "框景", "借景", "空间", "游线"],
            "summary": "窗让园林不是一次看尽，而是在行走中不断出现新的画面。",
            "source": "园林营造理论与江南园林实践",
            "evidence": "园林通过门窗、墙洞、曲折游线控制观看节奏，使一处景物被分割、遮掩、再显现，形成近似画卷展开的体验。",
            "plain": "窗景的作用类似取景框，让游客边走边发现不同层次的景。",
        },
        {
            "id": "literati",
            "title": "文人居游与非遗讲解",
            "era": "宋代文化语境",
            "keywords": ["文人", "居游", "诗", "画", "审美", "非遗", "讲解"],
            "summary": "园林讲解可以从“看建筑”转向“理解一种文人生活方式”。",
            "source": "宋代文人诗文、园记与后世园林研究",
            "evidence": "文人园林并非只陈列景点，而是把读书、会友、题咏、观水、听竹等活动组织成日常生活的审美秩序。",
            "plain": "游客理解园林时，不只是在看景，更是在理解古人怎样生活、怎样表达志趣。",
        },
    ],
}


def ensure_knowledge_file() -> None:
    if KNOWLEDGE_PATH.exists():
        return
    KNOWLEDGE_PATH.write_text(
        json.dumps(DEFAULT_KNOWLEDGE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_knowledge() -> dict[str, Any]:
    ensure_knowledge_file()
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


def load_palace() -> dict[str, Any]:
    return json.loads(PALACE_PATH.read_text(encoding="utf-8"))


def tokenize(text: str) -> set[str]:
    chunks = re.findall(r"[\u4e00-\u9fff]{1,4}|[A-Za-z0-9_]+", text.lower())
    grams: set[str] = set()
    for chunk in chunks:
        grams.add(chunk)
        if len(chunk) > 1 and re.match(r"^[\u4e00-\u9fff]+$", chunk):
            grams.update(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return grams


def retrieve(question: str, spot_id: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
    knowledge = load_knowledge()
    query_tokens = tokenize(question)
    ranked = []
    for spot in knowledge["spots"]:
        haystack = " ".join(
            [
                spot["title"],
                spot["summary"],
                spot["evidence"],
                spot["plain"],
                " ".join(spot.get("keywords", [])),
            ]
        )
        score = len(query_tokens & tokenize(haystack))
        if spot_id and spot["id"] == spot_id:
            score += 8
        if score > 0:
            ranked.append((score, spot))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked and spot_id:
        ranked = [(1, spot) for spot in knowledge["spots"] if spot["id"] == spot_id]
    return [spot for _, spot in ranked[:limit]]


def find_gallery(gallery_id: str | None) -> dict[str, Any]:
    palace = load_palace()
    galleries = palace["galleries"]
    if gallery_id:
        for gallery in galleries:
            if gallery["id"] == gallery_id:
                return gallery
    return galleries[0]


def find_artifact(gallery: dict[str, Any], artifact_id: str | None) -> dict[str, Any]:
    artifacts = gallery["artifacts"]
    if artifact_id:
        for artifact in artifacts:
            if artifact["id"] == artifact_id:
                return artifact
    return artifacts[0]


def retrieve_palace(question: str, gallery_id: str | None = None, artifact_id: str | None = None) -> dict[str, Any]:
    palace = load_palace()
    gallery = find_gallery(gallery_id)
    artifact = find_artifact(gallery, artifact_id)
    contexts = retrieve_palace_contexts(question, gallery, artifact)
    if not gallery_id and contexts:
        gallery = find_gallery(contexts[0].get("gallery_id"))
        artifact = find_artifact(gallery, contexts[0].get("artifact_id"))
    return {"museum": palace["museum"], "gallery": gallery, "artifact": artifact, "contexts": contexts}


def build_palace_documents() -> list[dict[str, Any]]:
    palace = load_palace()
    documents: list[dict[str, Any]] = [
        {
            "id": "museum:route",
            "type": "museum",
            "gallery_id": None,
            "artifact_id": None,
            "title": palace["museum"]["title"],
            "source": "故宫博物院导览与本项目策展说明",
            "text": " ".join(
                [
                    palace["museum"]["subtitle"],
                    palace["museum"]["opening"],
                    palace["museum"]["route_note"],
                ]
            ),
        }
    ]
    for gallery in palace["galleries"]:
        persona = gallery["persona"]
        gallery_text = " ".join(
            [
                f"{gallery['name']}位于{gallery['zone']}。",
                gallery["summary"],
                f"讲解人物为{persona['name']}，身份是{persona['role']}，表达特点是{persona['voice']}",
            ]
        )
        documents.append(
            {
                "id": f"gallery:{gallery['id']}",
                "type": "gallery",
                "gallery_id": gallery["id"],
                "artifact_id": None,
                "gallery": gallery["name"],
                "title": gallery["name"],
                "source": gallery["source"],
                "text": gallery_text,
            }
        )
        for artifact in gallery["artifacts"]:
            documents.append(
                {
                    "id": f"artifact:{artifact['id']}",
                    "type": "artifact",
                    "gallery_id": gallery["id"],
                    "artifact_id": artifact["id"],
                    "gallery": gallery["name"],
                    "title": artifact["title"],
                    "source": artifact["source"],
                    "text": " ".join(
                        [
                            f"{artifact['title']}属于{gallery['name']}，时代为{artifact['period']}。",
                            artifact["description"],
                            f"视觉线索：{artifact['image_hint']}。",
                            f"展馆背景：{gallery['summary']}",
                        ]
                    ),
                }
            )
    return documents


def document_frequency(documents: list[dict[str, Any]]) -> dict[str, int]:
    frequency: dict[str, int] = {}
    for doc in documents:
        for token in tokenize(f"{doc['title']} {doc['text']}"):
            frequency[token] = frequency.get(token, 0) + 1
    return frequency


def retrieve_palace_contexts(
    question: str,
    gallery: dict[str, Any],
    artifact: dict[str, Any],
    limit: int = 6,
) -> list[dict[str, Any]]:
    documents = build_palace_documents()
    df = document_frequency(documents)
    expanded_query = " ".join(
        [
            question,
            gallery["name"],
            gallery["zone"],
            artifact["title"],
            artifact["period"],
            artifact["image_hint"],
        ]
    )
    query_tokens = tokenize(expanded_query)
    total_docs = max(1, len(documents))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for doc in documents:
        doc_tokens = tokenize(f"{doc['title']} {doc['text']}")
        overlap = query_tokens & doc_tokens
        score = sum(math.log((total_docs + 1) / (df.get(token, 0) + 1)) + 1 for token in overlap)
        if doc.get("gallery_id") == gallery["id"]:
            score += 5.0
        if doc.get("artifact_id") == artifact["id"]:
            score += 9.0
        if doc["title"] in question:
            score += 4.0
        if doc["type"] == "museum":
            score += 0.5
        if score > 0:
            ranked.append((score, doc))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": doc["id"],
            "type": doc["type"],
            "gallery_id": doc.get("gallery_id"),
            "gallery": doc.get("gallery", gallery["name"]),
            "artifact_id": doc.get("artifact_id"),
            "title": doc["title"],
            "source": doc["source"],
            "evidence": doc["text"],
            "score": round(score, 3),
        }
        for score, doc in ranked[:limit]
    ]


def build_prompt(question: str, contexts: list[dict[str, Any]], mode: str) -> list[dict[str, str]]:
    context_text = "\n\n".join(
        f"【展区】{item['title']}\n【依据】{item['evidence']}\n【现代释义】{item['plain']}\n【来源】{item['source']}"
        for item in contexts
    )
    system = """你是一位陪游客同游江南园林的宋代文人讲解者。
要求：
1. 必须基于给定展区资料回答，不得编造书名、作者、时代和出处。
2. 语气要文雅、节制、口语化，适合语音讲解；不要堆砌难懂文言。
3. 如果问题超出园林、宋代文化、文人审美、非遗导览范围，请温和引导回园林主题。
4. 回答分三段以内，总长度适合 30-60 秒语音播放。
5. 不要提到“我是 AI”“根据资料库”等现代后台措辞。"""
    if mode == "intro":
        user = f"请为这个展区生成一段开场讲解。\n\n{context_text}"
    else:
        user = f"游客问题：{question}\n\n可用展区资料：\n{context_text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_llm(question: str, contexts: list[dict[str, Any]], mode: str) -> str:
    if not API_KEY:
        fallback = contexts[0] if contexts else load_knowledge()["spots"][0]
        return f"客且看此处：{fallback['summary']} {fallback['plain']} 此中妙处，不在繁华，而在清远有致。"
    completion = client.chat.completions.create(
        model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        messages=build_prompt(question, contexts, mode),
        temperature=0.2,
    )
    return completion.choices[0].message.content.strip()


async def synthesize(text: str) -> str:
    audio_name = f"response_{uuid.uuid4().hex}.mp3"
    audio_path = AUDIO_DIR / audio_name
    voice = os.getenv("EDGE_TTS_VOICE", "zh-CN-YunxiNeural")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(audio_path))
    return f"http://127.0.0.1:8000/static/{audio_name}"


class ChatRequest(BaseModel):
    question: str
    spot_id: str | None = None
    gallery_id: str | None = None
    artifact_id: str | None = None
    mode: str = "chat"


class PalaceChatRequest(BaseModel):
    question: str
    gallery_id: str | None = None
    artifact_id: str | None = None
    mode: str = "chat"


@app.get("/api/health")
async def health():
    return {"status": "ok", "has_api_key": bool(API_KEY)}


@app.get("/")
async def home():
    return FileResponse(ROOT / "index.html")


@app.get("/index.html")
async def index_page():
    return FileResponse(ROOT / "index.html")


@app.get("/api/museum")
async def museum():
    knowledge = load_knowledge()
    return {
        "museum": knowledge["museum"],
        "spots": [
            {
                "id": spot["id"],
                "title": spot["title"],
                "era": spot["era"],
                "summary": spot["summary"],
                "keywords": spot["keywords"],
            }
            for spot in knowledge["spots"]
        ],
    }


@app.get("/api/palace")
async def palace():
    data = load_palace()
    return data


@app.get("/api/palace/search")
async def palace_search(q: str, gallery_id: str | None = None, artifact_id: str | None = None):
    gallery = find_gallery(gallery_id)
    artifact = find_artifact(gallery, artifact_id)
    return {
        "query": q,
        "gallery_id": gallery["id"],
        "artifact_id": artifact["id"],
        "contexts": retrieve_palace_contexts(q, gallery, artifact),
    }


def build_palace_prompt(question: str, bundle: dict[str, Any], mode: str) -> list[dict[str, str]]:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    persona = gallery["persona"]
    retrieved_text = "\n\n".join(
        "\n".join(
            [
                f"【资料{i}】{item['title']}",
                f"【类型】{item['type']}",
                f"【来源】{item['source']}",
                f"【内容】{item['evidence']}",
            ]
        )
        for i, item in enumerate(bundle["contexts"], start=1)
    )
    context_text = "\n".join(
        [
            f"【博物馆】{bundle['museum']['title']}",
            f"【展馆】{gallery['name']}，位置：{gallery['zone']}",
            f"【展馆介绍】{gallery['summary']}",
            f"【当前文物】{artifact['title']}，时代：{artifact['period']}",
            f"【文物说明】{artifact['description']}",
            f"【视觉线索】{artifact['image_hint']}",
            f"【来源】{artifact['source']}",
            f"【讲解人物】{persona['name']}，身份：{persona['role']}，表达特点：{persona['voice']}",
        ]
    )
    system = f"""你是故宫虚拟展馆的导览讲解员，当前讲解角度参考“{persona['name']}”（身份：{persona['role']}）。
要求：
1. 回答必须围绕当前展馆与当前文物，不得编造具体馆藏编号、尺寸、年代断语或不存在的出处。
2. 只能扩写“当前上下文”和“检索资料”中已经出现的信息，不得新增未给出的纹样、寓意、用途、图像细节、摆放位置或历史场景。
3. 不要写成亲历回忆；不得使用“我平日”“曾置”“常置”“日日相对”等暗示具体使用事实的表达，除非资料中明确出现。
4. 使用第三人称或导览员口吻，不要自称“我”“朕”，不要写舞台动作、括号旁白或戏剧台词。
5. 语言要有沉浸感，但保持清楚易懂，适合 30-60 秒语音播放。
6. 若问题超出当前文物，可先简短回应，再引回当前展馆或相关历史语境。
7. 优先使用“检索资料”中的证据；资料不足时说“这里还不能断定”，不要硬编。
8. 不要说“根据资料库”“作为 AI”。"""
    if mode == "intro":
        user = f"请为观众生成当前文物的入馆讲解。\n\n当前上下文：\n{context_text}\n\n检索资料：\n{retrieved_text}"
    else:
        user = f"观众问题：{question}\n\n当前上下文：\n{context_text}\n\n检索资料：\n{retrieved_text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_palace_llm(question: str, bundle: dict[str, Any], mode: str) -> str:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    if not API_KEY:
        evidence = bundle["contexts"][0]["evidence"] if bundle["contexts"] else artifact["description"]
        return f"诸位请看《{artifact['title']}》。{evidence} 若从{gallery['persona']['name']}的眼中观之，此物不只是陈设，也是{gallery['name']}所要讲述的历史线索。"
    completion = client.chat.completions.create(
        model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        messages=build_palace_prompt(question, bundle, mode),
        temperature=0,
    )
    return completion.choices[0].message.content.strip()


@app.post("/api/palace/chat")
async def palace_chat(payload: PalaceChatRequest):
    bundle = retrieve_palace(payload.question, payload.gallery_id, payload.artifact_id)
    speech_text = call_palace_llm(payload.question, bundle, payload.mode)
    audio_url = await synthesize(speech_text)
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    return {
        "status": "success",
        "user_text": payload.question,
        "gallery_id": gallery["id"],
        "gallery_name": gallery["name"],
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "persona": gallery["persona"],
        "speech_text": speech_text,
        "plain_text": artifact["description"],
        "source": artifact["source"],
        "contexts": bundle["contexts"],
        "audio_url": audio_url,
    }


@app.post("/api/chat")
async def chat_endpoint(
    file: UploadFile = File(None),
    text_fallback: str | None = None,
    spot_id: str | None = None,
    mode: str = "chat",
):
    question = text_fallback or "请讲讲沧浪亭。"
    contexts = retrieve(question, spot_id=spot_id)
    speech_text = call_llm(question, contexts, mode)
    audio_url = await synthesize(speech_text)
    primary = contexts[0] if contexts else None
    return JSONResponse(
        {
            "status": "success",
            "user_text": question,
            "spot_id": primary["id"] if primary else spot_id,
            "spot_title": primary["title"] if primary else "",
            "speech_text": speech_text,
            "plain_text": primary["plain"] if primary else "",
            "source": primary["source"] if primary else "展馆资料库",
            "contexts": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "source": item["source"],
                    "evidence": item["evidence"],
                    "plain": item["plain"],
                }
                for item in contexts
            ],
            "audio_url": audio_url,
        }
    )


@app.post("/api/chat-json")
async def chat_json(payload: ChatRequest):
    contexts = retrieve(payload.question, spot_id=payload.spot_id)
    speech_text = call_llm(payload.question, contexts, payload.mode)
    audio_url = await synthesize(speech_text)
    primary = contexts[0] if contexts else None
    return {
        "status": "success",
        "user_text": payload.question,
        "spot_id": primary["id"] if primary else payload.spot_id,
        "spot_title": primary["title"] if primary else "",
        "speech_text": speech_text,
        "plain_text": primary["plain"] if primary else "",
        "source": primary["source"] if primary else "展馆资料库",
        "contexts": contexts,
        "audio_url": audio_url,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
