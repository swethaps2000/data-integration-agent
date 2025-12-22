import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from services.json_conversion_service import convert_json_with_sample
load_dotenv()


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

llm = ChatGoogleGenerativeAI(
    model="models/gemini-flash-latest",
    temperature=0,
    google_api_key=GOOGLE_API_KEY
)

app = FastAPI(title="POC")

session = {
    "intent": None,
    "source_json": None,
    "sink_json": None,
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
def analyze_schemas(source_schema: str, sink_schema: str) -> str:
    """
    Analyze source and sink JSON schemas and suggest mappings.
    """
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
"""
    response = llm.invoke(prompt)
    return response.content



@tool
async def transform_json(source_json: str, sink_json: str) -> dict:
    """
    Execute the final JSON transformation.
    Must be called ONLY after user approval.
    """
    source = json.loads(source_json)
    sink = json.loads(sink_json)
    return await convert_json_with_sample(source, sink)

def build_agent_context():
    return f"""
CURRENT STATUS: {session['status']}

SOURCE JSON:
{json.dumps(session['source_json'], indent=2) if session['source_json'] else 'NOT PROVIDED'}

SINK JSON:
{json.dumps(session['sink_json'], indent=2) if session['sink_json'] else 'NOT PROVIDED'}

SOURCE SCHEMA:
{json.dumps(session['source_schema'], indent=2) if session['source_schema'] else 'NOT PROVIDED'}

SINK SCHEMA:
{json.dumps(session['sink_schema'], indent=2) if session['sink_schema'] else 'NOT PROVIDED'}

CURRENT DRAFT:
{session['draft'] if session['draft'] else 'NO DRAFT'}
"""


SYSTEM_PROMPT = """
You are an autonomous data transformation agent.

You must follow these rules strictly:

1. If SOURCE JSON or SINK JSON is missing, ask the user to upload them.
2. If both are available and no draft exists:
   - Create a detailed DRAFT.
   - Start the response with "DRAFT:".
3. If a draft exists:
   - Wait for user approval.
   - Do NOT execute yet.
4. When the user approves the draft:
   - CALL the `transform_json` tool.
   - Pass SOURCE JSON and SINK JSON exactly as provided.
   - Return ONLY the final transformed JSON.
5. Never ask for schemas or data again after execution.
6. Do not explain after calling the tool.

        """


prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{input}"),
     ("placeholder", "{agent_scratchpad}")
])

agent = create_tool_calling_agent(
    llm=llm,
    tools=[analyze_schemas, transform_json],
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=[analyze_schemas, transform_json],
    verbose=False 
)




@app.post("/chat")
async def chat(message: str = Form(...)):
    context = build_agent_context()

    result = await agent_executor.ainvoke({
        "input": context + "\n\nUSER MESSAGE:\n" + message
    })

    output = result["output"]

    if isinstance(output, dict):
        session["status"] = "SUBMITTED"
        return {
            "reply": output,
            "status": session["status"]
        }
    if isinstance(output, str) and output.startswith("DRAFT:"):
        session["draft"] = output
        session["status"] = "DRAFT"

    return {
        "reply": output,
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
    session["source_json"] = source_data
    session["sink_json"] = sink_data



    agent_input = f"""
Create a draft transformation for the following schemas.

SOURCE SCHEMA:
{json.dumps(source_schema)}

SINK SCHEMA:
{json.dumps(sink_schema)}
"""

    result = agent_executor.invoke({
    "input": agent_input,
    "source_schema": session["source_schema"],
    "sink_schema": session["sink_schema"]
})


    session["draft"] = result["output"]
    session["status"] = "DRAFT"

    return {
        "message": "Files uploaded successfully. Draft created by agent.",
        "draft": session["draft"],
        "status": session["status"]
    }
