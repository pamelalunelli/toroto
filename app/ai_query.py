"""
AI Query Layer — Part 3.

Strategy: LLM → Structured Intent → Predefined Function
The LLM never generates raw SQL. It extracts a structured intent object
that is routed to an existing, tested function in repository.py.
Uses Groq (free tier) with llama-3.3-70b-versatile.
"""

import os
import json
import httpx
from sqlalchemy.orm import Session
from app import repository as repo

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are a geospatial query interpreter for an environmental intervention monitoring system.
Convert natural language questions into a structured JSON intent object.

Available query types and their parameters:

1. nearest_neighbor
   - lat: float (required)
   - lon: float (required)
   - status: string (optional) — one of: validated, in_progress, pending, rejected
   - subtype: string (optional) — one of: gavion, reforestacion, presa, terraza, zanja_trinchera

2. within_radius
   - lat: float (required)
   - lon: float (required)
   - radius_km: float (required)
   - status: string (optional)
   - subtype: string (optional)
   - start_date: string (optional, format YYYY-MM-DD)
   - end_date: string (optional, format YYYY-MM-DD)

3. within_area
   - area_id: string (required) — one of: zone_a, zone_b, zone_c
   - status: string (optional)
   - subtype: string (optional)

4. status_summary
   - (no parameters)

5. subtype_by_region
   - (no parameters)

Respond ONLY with a valid JSON object. No prose, no markdown, no explanation.

Examples:
Q: "What is the closest intervention to 20.701, -103.321?"
A: {"query_type": "nearest_neighbor", "params": {"lat": 20.701, "lon": -103.321}}

Q: "Which validated interventions are within 5km of 20.700, -103.320 in March 2026?"
A: {"query_type": "within_radius", "params": {"lat": 20.700, "lon": -103.320, "radius_km": 5, "status": "validated", "start_date": "2026-03-01", "end_date": "2026-03-31"}}

Q: "How many interventions are inside zone_c?"
A: {"query_type": "within_area", "params": {"area_id": "zone_c"}}

Q: "Count interventions by status"
A: {"query_type": "status_summary", "params": {}}
"""

VALID_QUERY_TYPES = {
    "nearest_neighbor",
    "within_radius",
    "within_area",
    "status_summary",
    "subtype_by_region",
}


async def interpret_and_execute(question: str, db: Session) -> dict:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set. Add it to your environment variables.")

    intent = await _extract_intent(question)

    query_type = intent.get("query_type")
    if query_type not in VALID_QUERY_TYPES:
        raise ValueError(f"Unrecognized query type: '{query_type}'")

    params = intent.get("params", {})

    if query_type == "nearest_neighbor":
        result = repo.get_nearest_intervention(db, **params)
        return {"query_type": query_type, "intent": intent, "result": result}

    elif query_type == "within_radius":
        results = repo.get_interventions_within_radius(db, **params)
        return {"query_type": query_type, "intent": intent, "total": len(results), "results": results}

    elif query_type == "within_area":
        results, area_name = repo.get_interventions_within_area(db, **params)
        return {"query_type": query_type, "intent": intent, "area_name": area_name, "total": len(results), "results": results}

    elif query_type == "status_summary":
        result = repo.get_status_summary(db)
        return {"query_type": query_type, "intent": intent, "result": result}

    elif query_type == "subtype_by_region":
        result = repo.get_subtype_by_region(db)
        return {"query_type": query_type, "intent": intent, "result": result}


async def _extract_intent(question: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "temperature": 0,
                "max_tokens": 256,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
            },
        )
        response.raise_for_status()

    data = response.json()
    raw_text = data["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if model adds them
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]

    return json.loads(raw_text.strip())