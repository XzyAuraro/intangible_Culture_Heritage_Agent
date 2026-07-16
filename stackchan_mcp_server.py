import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from app import build_palace_fallback, call_palace_llm, get_artifact_persona, retrieve_palace


if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")


logger = logging.getLogger("stackchan_palace_mcp")
mcp = FastMCP("PalaceMuseumGuide")


def compact_text(text: str, max_chars: int = 300) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip("，、；：,. ") + "。"


@mcp.tool()
def palace_museum_guide(
    question: str,
    gallery_id: str = "",
    artifact_id: str = "",
    max_chars: int = 300,
) -> dict[str, Any]:
    """当用户要求 StackChan 做故宫讲解员、讲解展馆或文物时调用。只返回讲解文本，不控制硬件动作、表情、灯光或舵机。"""
    safe_max = max(80, min(int(max_chars or 300), 500))
    query = (question or "请讲解当前文物。").strip()
    bundle = retrieve_palace(query, gallery_id or None, artifact_id or None)
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    persona = get_artifact_persona(gallery, artifact)
    try:
        reply = call_palace_llm(query, bundle, mode="chat", relationship_score=1)
    except Exception as exc:
        logger.warning("LLM unavailable, using local RAG fallback: %s", type(exc).__name__)
        reply = build_palace_fallback(bundle)
    line = compact_text(reply, safe_max)
    return {
        "success": True,
        "text": line,
        "gallery_id": gallery["id"],
        "gallery_name": gallery["name"],
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "persona": persona.get("name", "讲解者"),
        "safety": "text_only_no_hardware_action",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
