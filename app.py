import json, os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
llm = ChatGoogleGenerativeAI(
    model="models/gemini-flash-latest",
    temperature=0,
    google_api_key=GEMINI_API_KEY
)

app = FastAPI(title="POC")

session = {
    "intent": None,
    "source_schema": None,
    "sink_schema": None,
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

@tool
def analyze_schemas(source_schema: List[dict], sink_schema: List[dict]) -> str:
    """
    Analyze source and sink JSON schemas and suggest:
    - Field mappings
    - Missing or extra fields
    - Required transformations
    - Assumptions and explanations
    """
    prompt = f"""
You are a senior data integration expert.

SOURCE SCHEMA:
{json.dumps(source_schema, indent=2)}

SINK SCHEMA:
{json.dumps(sink_schema, indent=2)}

Tasks:
- Suggest field mappings
- Identify missing or extra fields
- Suggest transformations
- Clearly explain assumptions

Output should be clear and structured.
"""
    response = llm.invoke(prompt)
    return response.content
SYSTEM_PROMPT = """
You are a data transformation agent.

Rules:
- Understand user intent
- Ask for source and sink files before analysis
- Generate transformation as a draft
- Keep everything in DRAFT until user says OK
- Do not auto-submit without confirmation
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{input}"),
     ("placeholder", "{agent_scratchpad}")
])

agent = create_tool_calling_agent(
    llm=llm,
    tools=[analyze_schemas],
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=[analyze_schemas],
    verbose=True
)

@app.post("/chat")
async def chat(message: str = Form(...)):
    msg = message.lower().strip()

    if any(word in msg for word in ["convert", "transform", "map"]):
        session["intent"] = "SOURCE_TO_SINK"
        return {
            "reply": "Got it 👍 Please upload the source and sink JSON files.",
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
        refine_prompt = f"""
You are refining an existing transformation draft.

CURRENT DRAFT:
{session["draft"]}

USER FEEDBACK:
{message}

Rules:
- Update the draft based on feedback
- Keep it concise
- Maintain correct mappings
"""
        response = llm.invoke(refine_prompt)
        session["draft"] = response.content

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

    source_data = json.loads(await source_file.read())
    sink_data = json.loads(await sink_file.read())

    source_schema = extract_json_schema(source_data)
    sink_schema = extract_json_schema(sink_data)

    session["source_schema"] = source_schema
    session["sink_schema"] = sink_schema


    agent_input = f"""
Create a draft transformation for the following schemas.

SOURCE SCHEMA:
{json.dumps(source_schema)}

SINK SCHEMA:
{json.dumps(sink_schema)}
"""

    result = agent_executor.invoke({"input": agent_input})

    session["draft"] = result["output"]
    session["status"] = "DRAFT"

    return {
        "message": "Files uploaded successfully. Draft created by agent.",
        "draft": session["draft"],
        "status": session["status"]
    }
