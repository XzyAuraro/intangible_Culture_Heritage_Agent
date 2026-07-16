import logging
import os
import sys
import json
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

from app import (
    build_palace_fallback,
    call_palace_llm,
    get_artifact_persona,
    load_palace,
    publish_stackchan_state,
    read_web_state,
    retrieve_palace,
)


if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")


logger = logging.getLogger("stackchan_palace_mcp")
mcp = FastMCP("PalaceMuseumGuide")


def use_llm_for_stackchan() -> bool:
    return os.getenv("STACKCHAN_MCP_USE_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def compact_text(text: str, max_chars: int = 300) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip("，、；：,. ") + "。"


def read_current_web_state() -> tuple[dict[str, Any], str]:
    state_url = os.getenv("STACKCHAN_WEB_STATE_URL", "").strip()
    if not state_url and os.getenv("PORT"):
        state_url = f"http://127.0.0.1:{os.getenv('PORT')}/api/web/state"

    if state_url:
        try:
            request = urllib.request.Request(state_url, headers={"Cache-Control": "no-store"})
            with urllib.request.urlopen(request, timeout=1.5) as response:
                data = json.loads(response.read().decode("utf-8"))
                if isinstance(data, dict):
                    return data, "api"
        except Exception as exc:
            logger.warning("Unable to read web state from API, falling back to file: %s", type(exc).__name__)

    state = read_web_state()
    if state.get("active"):
        return state, "file"
    return state, "none"


def resolve_ids_from_question(question: str, gallery_id: str = "", artifact_id: str = "") -> tuple[str, str, str, str]:
    """Prefer explicit gallery/artifact names spoken by the user over stale device context."""
    palace = load_palace()
    query = question or ""
    explicit_gallery = ""
    explicit_artifact = ""
    target_view = "detail" if artifact_id else "gallery"

    for gallery in palace["galleries"]:
        gallery_aliases = {gallery["id"], gallery["name"], gallery["name"].replace("馆", "")}
        if any(alias and alias in query for alias in gallery_aliases):
            explicit_gallery = gallery["id"]
            explicit_artifact = ""
            target_view = "gallery"
        for artifact in gallery["artifacts"]:
            artifact_aliases = {
                artifact["id"],
                artifact["title"],
                artifact["title"].replace("《", "").replace("》", ""),
            }
            if any(alias and alias in query for alias in artifact_aliases):
                explicit_gallery = gallery["id"]
                explicit_artifact = artifact["id"]
                target_view = "detail"
                break

    if explicit_gallery:
        return explicit_gallery, explicit_artifact, target_view, "spoken"

    web_state, _source = read_current_web_state()
    if web_state.get("active") and web_state.get("gallery_id"):
        return (
            str(web_state.get("gallery_id") or ""),
            str(web_state.get("artifact_id") or ""),
            str(web_state.get("view") or "detail"),
            "web_state",
        )
    return gallery_id, artifact_id, target_view, "tool_args"


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
    web_state_snapshot, web_state_source = read_current_web_state()
    resolved_gallery_id, resolved_artifact_id, target_view, resolution_source = resolve_ids_from_question(
        query,
        gallery_id,
        artifact_id,
    )
    bundle = retrieve_palace(query, resolved_gallery_id or None, resolved_artifact_id or None)
    gallery = bundle["gallery"]
    artifact = bundle["artifact"]
    persona = get_artifact_persona(gallery, artifact)
    reply = build_palace_fallback(bundle)
    if use_llm_for_stackchan():
        try:
            reply = call_palace_llm(query, bundle, mode="chat", relationship_score=1)
        except Exception as exc:
            logger.warning("LLM unavailable, using local RAG fallback: %s", type(exc).__name__)
    line = compact_text(reply, safe_max)
    publish_stackchan_state(
        {
            "source": "stackchan_mcp",
            "question": query,
            "text": line,
            "gallery_id": gallery["id"],
            "gallery_name": gallery["name"],
            "artifact_id": artifact["id"],
            "artifact_title": artifact["title"],
            "persona": persona.get("name", "讲解者"),
            "target_view": target_view,
            "resolution_source": resolution_source,
            "web_state_source": web_state_source,
            "web_state_snapshot": {
                "active": bool(web_state_snapshot.get("active")),
                "gallery_id": web_state_snapshot.get("gallery_id", ""),
                "artifact_id": web_state_snapshot.get("artifact_id", ""),
                "view": web_state_snapshot.get("view", ""),
                "updated_at": web_state_snapshot.get("updated_at", ""),
            },
        }
    )
    return {
        "success": True,
        "text": line,
        "gallery_id": gallery["id"],
        "gallery_name": gallery["name"],
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "persona": persona.get("name", "讲解者"),
        "target_view": target_view,
        "resolution_source": resolution_source,
        "web_state_source": web_state_source,
        "web_state_gallery_id": web_state_snapshot.get("gallery_id", ""),
        "web_state_artifact_id": web_state_snapshot.get("artifact_id", ""),
        "resolved_from_question": resolution_source == "spoken",
        "safety": "text_only_no_hardware_action",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
