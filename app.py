import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
import google.generativeai as genai

GEMINI_API_KEY = "AIzaSyD2-OfDcas_HPsgqfqpCryhxei5Xn3WvPU"
genai.configure(api_key=GEMINI_API_KEY)


model = genai.GenerativeModel("models/gemini-flash-latest")

app = FastAPI(title="POC")

session = {
    "intent": None,
    "source": None,
    "sink": None,
    "draft": None,
    "status": "DRAFT"
}

def extract_json_schema(data):
    if isinstance(data, list):
        if not data:
            return []
        data = data[0]

    if not isinstance(data, dict):
        return []

    return [
        {"field": k, "type": type(v).__name__}
        for k, v in data.items()
    ]

@app.post("/chat")
async def chat(message: str = Form(...)):
    msg = message.lower().strip()

    if any(word in msg for word in ["convert", "transform", "map", "source", "sink"]):
        session["intent"] = "SOURCE_TO_SINK"
        return {
            "reply": (
                "Got it.You want to convert source JSON to sink JSON.\n"
                "Please upload the source and sink files."
            ),
            "status": session["status"]
        }

    if msg in ["ok", "okay", "proceed", "submit", "looks good"]:
        if not session["draft"]:
            return {"reply": "Nothing to submit yet."}

        session["status"] = "SUBMITTED"
        return {
            "reply": "✅ Transformation submitted successfully.",
            "final_output": session["draft"],
            "status": session["status"]
        }

    if session["draft"]:
        prompt = f"""
You are refining an existing draft transformation.

CURRENT DRAFT:
{session['draft']}

USER FEEDBACK:
{message}

Rules:
- Update the draft based on feedback
- Keep it concise
- Maintain previous correct mappings
"""

        response = model.generate_content(prompt)
        session["draft"] = response.text

        return {
            "reply": "Draft updated based on your feedback.",
            "draft": session["draft"],
            "status": session["status"]
        }

    return {
        "reply": "Please describe what you want to do (e.g., convert source JSON to sink JSON).",
        "status": session["status"]
    }

@app.post("/upload")
async def upload_files(
    source_file: UploadFile = File(...),
    sink_file: UploadFile = File(...)
):
    if not source_file.filename.endswith(".json") or not sink_file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only JSON files are supported")

    source_json = json.loads(await source_file.read())
    sink_json = json.loads(await sink_file.read())

    source_schema = extract_json_schema(source_json)
    sink_schema = extract_json_schema(sink_json)

    session["source"] = source_schema
    session["sink"] = sink_schema

    prompt = f"""
You are a senior data integration expert.

SOURCE SCHEMA:
{source_schema}

SINK SCHEMA:
{sink_schema}

Tasks:
- Suggest field mappings
- Identify missing or extra fields
- Suggest transformations
- Clearly explain assumptions

Output should be clear and structured.
"""

    response = model.generate_content(prompt)

    session["draft"] = response.text
    session["status"] = "DRAFT"

    return {
        "message": "Files uploaded successfully. Draft created.",
        "draft": session["draft"],
        "status": session["status"]
    }

