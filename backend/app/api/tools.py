"""Tool catalog endpoint — lets the agent config form offer a real tool list."""

from __future__ import annotations

from fastapi import APIRouter

from app.tools.registry import list_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_available_tools() -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "requires_approval": t.requires_approval,
        }
        for t in list_tools()
    ]
