import asyncio
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import edge_tts
from fastapi import FastAPI, File, Request, UploadFile
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
STACKCHAN_STATE_PATH = DATA_DIR / "stackchan_state.json"

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


_stackchan_mcp_task: asyncio.Task | None = None


def stackchan_mcp_enabled() -> bool:
    flag = os.getenv("ENABLE_STACKCHAN_MCP_BRIDGE", "").strip().lower()
    endpoint = os.getenv("XIAOZHI_MCP_ENDPOINT") or os.getenv("MCP_ENDPOINT")
    return flag in {"1", "true", "yes", "on"} and bool(endpoint)


@app.on_event("startup")
async def start_stackchan_mcp_bridge() -> None:
    global _stackchan_mcp_task
    if not stackchan_mcp_enabled():
        return
    from xiaozhi_mcp_bridge import run_forever

    _stackchan_mcp_task = asyncio.create_task(run_forever())


@app.on_event("shutdown")
async def stop_stackchan_mcp_bridge() -> None:
    global _stackchan_mcp_task
    if _stackchan_mcp_task is None:
        return
    _stackchan_mcp_task.cancel()
    try:
        await _stackchan_mcp_task
    except asyncio.CancelledError:
        pass
    _stackchan_mcp_task = None


API_KEY = (
    os.getenv("CULTURE_AGENT_DASHSCOPE_API_KEY")
    or os.getenv("DASHSCOPE_API_KEY")
    or os.getenv("ALIYUN_API_KEY")
)
client = OpenAI(
    api_key=API_KEY or "missing-key",
    base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
)

DEVICE_RELATIONSHIPS: dict[str, int] = {}


def read_stackchan_state() -> dict[str, Any]:
    if not STACKCHAN_STATE_PATH.exists():
        return {"active": False}
    try:
        return json.loads(STACKCHAN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active": False}


def publish_stackchan_state(payload: dict[str, Any]) -> dict[str, Any]:
    state = {
        "active": True,
        "event_id": uuid.uuid4().hex,
        "created_at": int(time.time() * 1000),
        **payload,
    }
    temp_path = STACKCHAN_STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(STACKCHAN_STATE_PATH)
    return state


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


def get_artifact_persona(gallery: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    trigger = artifact.get("personaTrigger") or {}
    persona = trigger.get("persona") or gallery["persona"]
    return {
        **persona,
        "trigger_reason": trigger.get("reason", ""),
        "trigger_tone": trigger.get("tone", ""),
        "trigger_topics": trigger.get("topics", []),
        "trigger_keywords": trigger.get("keywords", []),
    }


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
            artifact_persona = get_artifact_persona(gallery, artifact)
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
                            f"文物绑定讲解人物为{artifact_persona['name']}，身份是{artifact_persona['role']}，表达特点是{artifact_persona['voice']}。",
                            f"角色触发原因：{artifact_persona.get('trigger_reason', '')}。适合话题：{'、'.join(artifact_persona.get('trigger_topics', []))}。",
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
    clean_text = sanitize_tts_text(text)
    audio_name = f"response_{uuid.uuid4().hex}.mp3"
    audio_path = AUDIO_DIR / audio_name
    voice = os.getenv("EDGE_TTS_VOICE", "zh-CN-YunxiNeural")
    communicate = edge_tts.Communicate(clean_text, voice)
    await communicate.save(str(audio_path))
    return f"/static/{audio_name}"


async def synthesize_with_timeout(text: str) -> str:
    timeout = float(os.getenv("TTS_TIMEOUT_SECONDS", "25"))
    return await asyncio.wait_for(synthesize(text), timeout=timeout)


def sanitize_tts_text(text: str) -> str:
    clean_text = text.replace("——", "，").replace("……", "。")
    clean_text = clean_text.replace("《", "").replace("》", "")
    clean_text = re.sub(r"[<>\[\]{}|\\^`]", "", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return clean_text or "讲解内容暂时为空。"


def strip_dialogue_speakers(text: str, personas: list[dict[str, Any]]) -> str:
    speaker_names = [re.escape(persona["name"]) for persona in personas if persona.get("name")]
    if not speaker_names:
        return text
    speaker_pattern = re.compile(rf"^\s*(?:{'|'.join(speaker_names)})\s*[：:]\s*")
    lines = [speaker_pattern.sub("", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def build_stackchan_line(text: str, artifact: dict[str, Any], persona: dict[str, Any]) -> str:
    clean_text = strip_dialogue_speakers(text, [persona])
    clean_text = re.sub(r"【[^】]+】", "", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", clean_text) if item.strip()]
    line = "".join(sentences[:2]) if sentences else clean_text
    if len(line) > 92:
        line = line[:90].rstrip("，、；：,. ") + "。"
    if not line:
        line = f"我是{persona.get('name', '讲解者')}。现在为你讲解{artifact['title']}。"
    return line


def stackchan_payload(line: str, artifact: dict[str, Any], persona: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "stackchan.say",
        "arguments": {
            "text": line,
            "emotion": "happy",
            "face": "talk",
            "artifact_id": artifact["id"],
            "persona": persona.get("name", "讲解者"),
        },
        "execute": False,
        "note": "仅用于预览未来 MCP 调用格式；当前不会连接或控制实体硬件。",
    }


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
    relationship_score: int = 1


class PalaceSceneRequest(BaseModel):
    question: str = "请两位讲解者围绕当前文物进行一段双人讲解。"
    gallery_id: str | None = None
    artifact_id: str | None = None
    relationship_score: int = 1


class DeviceChatRequest(BaseModel):
    device_id: str = "web-simulator"
    text: str = "请讲解当前文物。"
    gallery_id: str | None = None
    artifact_id: str | None = None
    mode: str = "chat"
    with_audio: bool = True


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


@app.get("/api/stackchan/state")
async def stackchan_state():
    return JSONResponse(
        read_stackchan_state(),
        headers={"Cache-Control": "no-store"},
    )


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


def describe_relationship(score: int) -> str:
    if score >= 10:
        return "熟识观众：语气可以更从容亲近，可简短承接“你常来问此物”的感觉，但仍不得虚构私人往事。"
    if score >= 4:
        return "多次交流：语气比初见更熟络，可略微主动补充相关话题，但仍要围绕文物证据。"
    return "初次见面：语气保持礼貌、清楚、克制，先建立基本理解。"


def scene_partner_persona(gallery: dict[str, Any], artifact: dict[str, Any], primary: dict[str, Any]) -> dict[str, str]:
    gallery_id = gallery["id"]
    artifact_id = artifact["id"]
    primary_name = primary["name"]
    partners: dict[str, dict[str, str]] = {
        "qianlong": {
            "name": "乾隆皇帝",
            "role": "清高宗弘历",
            "voice": "从帝王审美、收藏趣味和宫廷使用解释文物。",
        },
        "display_officer": {
            "name": "内廷陈设官",
            "role": "清代宫廷家具与陈设管理者",
            "voice": "从陈设制度、空间秩序和使用痕迹解释器物。",
        },
        "ritual_officer": {
            "name": "内廷礼制官",
            "role": "清代宫廷礼仪与典章记录者",
            "voice": "从礼制、秩序和仪式空间解释宫廷文物。",
        },
        "kiln_officer": {
            "name": "御窑厂督陶官",
            "role": "清代景德镇御窑督陶官",
            "voice": "从窑口、釉色、烧造与宫廷使用解释陶瓷。",
        },
        "song_connoisseur": {
            "name": "宋代瓷器鉴赏家",
            "role": "熟悉宋代单色釉审美的文人鉴赏者",
            "voice": "从釉色、器形和含蓄审美讲述宋瓷气韵。",
        },
        "craftsman": {
            "name": "样式雷匠师",
            "role": "清代宫廷营造世家匠师",
            "voice": "从尺度、结构、图档和施工管理解释宫廷建筑。",
        },
        "clock_interpreter": {
            "name": "内廷西洋钟表通事",
            "role": "清宫接触西洋器物的译介者",
            "voice": "从贡品、贸易和技术交流解释西洋钟表入宫。",
        },
        "clockmaker": {
            "name": "造办处钟表匠",
            "role": "清代内廷造办处做钟处匠师",
            "voice": "从机械联动、报时娱乐和宫廷制造解释钟表。",
        },
        "treasure_curator": {
            "name": "乾隆朝鉴藏宝臣",
            "role": "清代内廷鉴藏与陈设官",
            "voice": "从材质、礼制、祥瑞寓意和皇家审美解释珍宝。",
        },
        "daily_recorder": {
            "name": "内廷起居注官",
            "role": "清代宫廷日常记录者",
            "voice": "从政务、起居、召对和内廷秩序解释宫殿空间。",
        },
    }
    if gallery_id == "ceramics":
        choice = "kiln_officer" if primary_name != "御窑厂督陶官" else "song_connoisseur"
    elif gallery_id == "furniture":
        choice = "display_officer" if primary_name != "内廷陈设官" else "qianlong"
    elif gallery_id == "architecture":
        choice = "craftsman" if primary_name != "样式雷匠师" else "ritual_officer"
    elif gallery_id == "original_display":
        choice = "ritual_officer" if artifact_id == "taihe_hall" else "daily_recorder"
    elif gallery_id == "clocks":
        choice = "clockmaker" if "皇帝" in primary_name or "乾隆" in primary_name else "clock_interpreter"
    elif gallery_id == "treasures":
        choice = "treasure_curator" if primary_name != "乾隆朝鉴藏宝臣" else "ritual_officer"
    else:
        choice = "display_officer"
    partner = partners[choice]
    if partner["name"] == primary_name:
        partner = partners["display_officer"] if artifact_id != "red_lacquer_table" else partners["qianlong"]
    return partner


def build_scene_prompt(
    question: str,
    bundle: dict[str, Any],
    relationship_score: int = 1,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    primary = get_artifact_persona(gallery, artifact)
    partner = scene_partner_persona(gallery, artifact, primary)
    personas = [primary, partner]
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
            f"【展馆】{gallery['name']}，位置：{gallery['zone']}",
            f"【展馆介绍】{gallery['summary']}",
            f"【当前文物】{artifact['title']}，时代：{artifact['period']}",
            f"【文物说明】{artifact['description']}",
            f"【视觉线索】{artifact['image_hint']}",
            f"【来源】{artifact['source']}",
            f"【角色甲】{primary['name']}，身份：{primary['role']}，表达特点：{primary['voice']}",
            f"【角色乙】{partner['name']}，身份：{partner['role']}，表达特点：{partner['voice']}",
            f"【观众关系】第{max(1, relationship_score)}次交流，{describe_relationship(relationship_score)}",
        ]
    )
    system = f"""你是故宫虚拟展馆的“场景导演”。
你要协调两个历史讲解角色进行一段短对话：
角色甲：{primary['name']}（{primary['role']}）
角色乙：{partner['name']}（{partner['role']}）

要求：
1. 必须围绕当前展馆、当前文物和检索资料，不得编造馆藏编号、尺寸、年代断语、出处或资料中没有的具体历史事件。
2. 输出 4 句以内，每句单独一行，格式必须是“{primary['name']}：……”或“{partner['name']}：……”。
3. 两个角色要有互补视角：一位讲文物自身，一位补充制度、工艺、审美或空间背景。
4. 可以有轻微观点张力，但不要争吵、不要写舞台动作、不要使用括号旁白。
5. 语言适合语音讲解，总长度控制在 45-75 秒。
6. 不要说“根据资料库”“作为 AI”。"""
    user = f"观众问题：{question}\n\n当前上下文：\n{context_text}\n\n检索资料：\n{retrieved_text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], personas


def build_role_agent_prompt(
    question: str,
    bundle: dict[str, Any],
    persona: dict[str, Any],
    relationship_score: int = 1,
) -> list[dict[str, str]]:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    evidence = "\n".join(f"- {item['title']}：{item['evidence']}" for item in bundle["contexts"][:4])
    system = f"""你是一个独立历史角色 agent：{persona['name']}。
身份：{persona['role']}
表达特点：{persona['voice']}

任务：只从你的角色视角，为稍后的双人讲解提供观点素材。
要求：
1. 必须基于文物说明和资料线索，不得编造资料中没有的事实。
2. 只输出 2 条要点，每条不超过 45 个汉字。
3. 不要直接写成最终对话，不要提“AI”或“资料库”。
4. 观众关系：第{max(1, relationship_score)}次交流，{describe_relationship(relationship_score)}"""
    user = "\n".join(
        [
            f"观众问题：{question}",
            f"展馆：{gallery['name']}",
            f"文物：{artifact['title']}，时代：{artifact['period']}",
            f"文物说明：{artifact['description']}",
            f"资料线索：\n{evidence}",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_scene_director_prompt(
    question: str,
    bundle: dict[str, Any],
    personas: list[dict[str, Any]],
    role_notes: list[str],
    relationship_score: int = 1,
) -> list[dict[str, str]]:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    primary, partner = personas
    notes_text = "\n\n".join(
        f"【{persona['name']}的独立观点】\n{note}"
        for persona, note in zip(personas, role_notes)
    )
    evidence = "\n".join(f"- {item['title']}：{item['evidence']}" for item in bundle["contexts"][:4])
    system = f"""你是故宫虚拟展馆的场景导演 agent。
你已经收到两个独立角色 agent 的观点，现在要把它们编排成一段双人讲解。

角色：
1. {primary['name']}（{primary['role']}）
2. {partner['name']}（{partner['role']}）

要求：
1. 输出 4 句以内，每句单独一行，格式必须是“{primary['name']}：……”或“{partner['name']}：……”。
2. 两位角色要观点互补，不要互相重复；可以轻微接话，但不要争吵。
3. 必须受当前文物、资料线索和两个角色独立观点约束，不得新增资料中没有的具体事实。
4. 不写舞台动作、括号旁白；适合 45-75 秒语音讲解。
5. 观众关系：第{max(1, relationship_score)}次交流，{describe_relationship(relationship_score)}
6. 不要说“根据资料库”“作为 AI”。"""
    user = "\n".join(
        [
            f"观众问题：{question}",
            f"展馆：{gallery['name']}",
            f"文物：{artifact['title']}，时代：{artifact['period']}",
            f"文物说明：{artifact['description']}",
            f"资料线索：\n{evidence}",
            notes_text,
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_scene_fallback(bundle: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    primary = get_artifact_persona(gallery, artifact)
    partner = scene_partner_persona(gallery, artifact, primary)
    evidence_items = [item["evidence"] for item in bundle["contexts"][:2]]
    evidence = " ".join(evidence_items) if evidence_items else artifact["description"]
    scene_text = "\n".join(
        [
            f"{primary['name']}：请看《{artifact['title']}》。{artifact['description']}",
            f"{partner['name']}：若从{gallery['name']}的脉络看，它还关系到{gallery['summary']}",
            f"{primary['name']}：可参考的资料线索是：{evidence}",
            f"{partner['name']}：所以这件文物不只可看其形，也要连同工艺、制度与空间一并理解。",
        ]
    )
    return scene_text, [primary, partner]


def call_scene_llm(question: str, bundle: dict[str, Any], relationship_score: int = 1) -> tuple[str, list[dict[str, str]]]:
    if not API_KEY:
        return build_scene_fallback(bundle)
    _messages, personas = build_scene_prompt(question, bundle, relationship_score)
    role_notes = []
    for persona in personas:
        role_completion = client.chat.completions.create(
            model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
            messages=build_role_agent_prompt(question, bundle, persona, relationship_score),
            temperature=0.25,
        )
        role_notes.append(role_completion.choices[0].message.content.strip())
    messages = build_scene_director_prompt(question, bundle, personas, role_notes, relationship_score)
    completion = client.chat.completions.create(
        model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        messages=messages,
        temperature=0.35,
    )
    return completion.choices[0].message.content.strip(), personas


def build_palace_prompt(
    question: str,
    bundle: dict[str, Any],
    mode: str,
    relationship_score: int = 1,
) -> list[dict[str, str]]:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    persona = get_artifact_persona(gallery, artifact)
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
            f"【文物触发原因】{persona.get('trigger_reason', '')}",
            f"【建议语气】{persona.get('trigger_tone', '')}",
            f"【专属话题】{'、'.join(persona.get('trigger_topics', []))}",
            f"【观众关系】第{max(1, relationship_score)}次交流，{describe_relationship(relationship_score)}",
        ]
    )
    system = f"""你是故宫虚拟展馆的导览讲解员，当前讲解角度参考“{persona['name']}”（身份：{persona['role']}）。
要求：
1. 回答必须围绕当前展馆与当前文物，不得编造具体馆藏编号、尺寸、年代断语或不存在的出处。
2. 只能扩写“当前上下文”和“检索资料”中已经出现的信息，不得新增未给出的纹样、寓意、用途、图像细节、摆放位置或历史场景。
3. 可以体现讲解人物的身份、关注点和语气，但不得写成亲历回忆；不得使用“我平日”“曾置”“常置”“日日相对”等暗示具体使用事实的表达，除非资料中明确出现。
4. 不要写舞台动作、括号旁白或戏剧台词；可少量使用符合身份的称谓，但不要让角色扮演压过文物事实。
5. 语言要有沉浸感，但保持清楚易懂，适合 30-60 秒语音播放。
6. 若问题超出当前文物，可先简短回应，再引回当前展馆或相关历史语境。
7. 优先使用“检索资料”中的证据；资料不足时说“这里还不能断定”，不要硬编。
8. 结合“观众关系”调整亲疏程度：初见礼貌克制，多次交流可以更自然熟络，十次以上可像熟客一样多给一点引导。
9. 不要说“根据资料库”“作为 AI”。"""
    if mode == "intro":
        user = f"请为观众生成当前文物的入馆讲解。\n\n当前上下文：\n{context_text}\n\n检索资料：\n{retrieved_text}"
    else:
        user = f"观众问题：{question}\n\n当前上下文：\n{context_text}\n\n检索资料：\n{retrieved_text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_palace_llm(question: str, bundle: dict[str, Any], mode: str, relationship_score: int = 1) -> str:
    if not API_KEY:
        return build_palace_fallback(bundle)
    completion = client.chat.completions.create(
        model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        messages=build_palace_prompt(question, bundle, mode, relationship_score),
        temperature=0.25,
    )
    return completion.choices[0].message.content.strip()


def build_palace_fallback(bundle: dict[str, Any]) -> str:
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    persona = get_artifact_persona(gallery, artifact)
    evidence_items = [item["evidence"] for item in bundle["contexts"][:2]]
    evidence = " ".join(evidence_items) if evidence_items else artifact["description"]
    return (
        f"{persona['name']}请诸位看《{artifact['title']}》。{artifact['description']}"
        f"它所在的{gallery['name']}强调的是：{gallery['summary']}"
        f"可参考的资料线索包括：{evidence}"
    )


@app.post("/api/palace/chat")
async def palace_chat(payload: PalaceChatRequest):
    bundle = retrieve_palace(payload.question, payload.gallery_id, payload.artifact_id)
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    warnings = []
    relationship_score = max(1, min(payload.relationship_score, 50))
    try:
        speech_text = call_palace_llm(payload.question, bundle, payload.mode, relationship_score)
    except Exception as exc:
        speech_text = build_palace_fallback(bundle)
        warnings.append(f"模型生成暂时不可用，已改用本地 RAG 资料回答：{type(exc).__name__}")
    try:
        audio_url = await synthesize_with_timeout(speech_text)
    except Exception as exc:
        audio_url = ""
        warnings.append(f"语音合成暂时不可用：{type(exc).__name__}")
    return {
        "status": "success",
        "degraded": bool(warnings),
        "warnings": warnings,
        "user_text": payload.question,
        "gallery_id": gallery["id"],
        "gallery_name": gallery["name"],
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "persona": get_artifact_persona(gallery, artifact),
        "relationship_score": relationship_score,
        "relationship_stage": describe_relationship(relationship_score),
        "speech_text": speech_text,
        "plain_text": artifact["description"],
        "source": artifact["source"],
        "contexts": bundle["contexts"],
        "audio_url": audio_url,
    }


@app.post("/api/device/chat")
async def device_chat(payload: DeviceChatRequest, request: Request):
    device_id = re.sub(r"[^a-zA-Z0-9_.:-]", "_", payload.device_id.strip() or "web-simulator")[:80]
    question = payload.text.strip() or "请讲解当前文物。"
    bundle = retrieve_palace(question, payload.gallery_id, payload.artifact_id)
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    persona = get_artifact_persona(gallery, artifact)
    relationship_key = f"{device_id}::{artifact['id']}::{persona['name']}"
    relationship_score = max(1, min(DEVICE_RELATIONSHIPS.get(relationship_key, 1), 50))
    warnings = []
    try:
        speech_text = call_palace_llm(question, bundle, payload.mode, relationship_score)
    except Exception as exc:
        speech_text = build_palace_fallback(bundle)
        warnings.append(f"模型生成暂时不可用，已改用本地 RAG 资料回答：{type(exc).__name__}")
    if payload.with_audio:
        try:
            audio_url = await synthesize_with_timeout(speech_text)
        except Exception as exc:
            audio_url = ""
            warnings.append(f"语音合成暂时不可用：{type(exc).__name__}")
    else:
        audio_url = ""
    next_score = min(relationship_score + 1, 50)
    DEVICE_RELATIONSHIPS[relationship_key] = next_score
    base_url = str(request.base_url).rstrip("/")
    audio_absolute_url = f"{base_url}{audio_url}" if audio_url else ""
    stackchan_line = build_stackchan_line(speech_text, artifact, persona)
    return {
        "status": "success",
        "degraded": bool(warnings),
        "warnings": warnings,
        "device_id": device_id,
        "input_text": question,
        "gallery_id": gallery["id"],
        "gallery_name": gallery["name"],
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "persona": persona,
        "relationship_score": next_score,
        "relationship_stage": describe_relationship(next_score),
        "reply_text": speech_text,
        "speech_text": speech_text,
        "stackchan_line": stackchan_line,
        "mcp_preview": stackchan_payload(stackchan_line, artifact, persona),
        "contexts": bundle["contexts"],
        "audio_url": audio_url,
        "audio_absolute_url": audio_absolute_url,
        "with_audio": payload.with_audio,
        "device_contract": {
            "request": {
                "device_id": device_id,
                "gallery_id": gallery["id"],
                "artifact_id": artifact["id"],
                "text": "请讲解这件文物。",
                "with_audio": payload.with_audio,
            },
            "playback": "硬件端可直接播放 audio_absolute_url；网页端可使用 audio_url。",
            "stackchan_line": "如果只让 Stack-chan 说出台词，可读取 stackchan_line；需要 MCP 时再把 mcp_preview 转成真实工具调用。",
        },
    }


@app.post("/api/palace/scene-chat")
async def palace_scene_chat(payload: PalaceSceneRequest):
    bundle = retrieve_palace(payload.question, payload.gallery_id, payload.artifact_id)
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    warnings = []
    relationship_score = max(1, min(payload.relationship_score, 50))
    try:
        scene_text, personas = call_scene_llm(payload.question, bundle, relationship_score)
    except Exception as exc:
        scene_text, personas = build_scene_fallback(bundle)
        warnings.append(f"双人讲解暂时改用本地 RAG 资料生成：{type(exc).__name__}")
    try:
        audio_url = await synthesize_with_timeout(strip_dialogue_speakers(scene_text, personas))
    except Exception as exc:
        audio_url = ""
        warnings.append(f"语音合成暂时不可用：{type(exc).__name__}")
    return {
        "status": "success",
        "degraded": bool(warnings),
        "warnings": warnings,
        "user_text": payload.question,
        "gallery_id": gallery["id"],
        "gallery_name": gallery["name"],
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "personas": personas,
        "relationship_score": relationship_score,
        "relationship_stage": describe_relationship(relationship_score),
        "scene_text": scene_text,
        "speech_text": scene_text,
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
    audio_url = await synthesize_with_timeout(speech_text)
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
    audio_url = await synthesize_with_timeout(speech_text)
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
