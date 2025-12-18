# import json
# from fastapi import FastAPI, UploadFile, File, Form, HTTPException
# import google.generativeai as genai
# from typing import Dict, Any

# # -----------------------------
# # Gemini Configuration
# # -----------------------------
# GEMINI_API_KEY = "AIzaSyD2-OfDcas_HPsgqfqpCryhxei5Xn3WvPU"
# genai.configure(api_key=GEMINI_API_KEY)

# model = genai.GenerativeModel("models/gemini-flash-latest")

# app = FastAPI(title="Chat-First JSON Transformation POC")

# # -----------------------------
# # In-memory session (POC only)
# # -----------------------------
# session = {
#     "intent": None,
#     "source_schema": None,
#     "sink_schema": None,
#     "source_data": None,
#     "mapping": None,
#     "status": "DRAFT"
# }

# # -----------------------------
# # Utility: Extract JSON schema
# # -----------------------------
# def extract_json_schema(data):
#     if isinstance(data, list):
#         if not data:
#             return []
#         data = data[0]

#     if not isinstance(data, dict):
#         return []

#     return [
#         {"field": k, "type": type(v).__name__}
#         for k, v in data.items()
#     ]

# # -----------------------------
# # Utility: Execute transformation
# # -----------------------------
# def apply_transformation(source_data, mapping_config):
#     if isinstance(source_data, dict):
#         source_data = [source_data]

#     transformed = []

#     for record in source_data:
#         new_record = {}

#         for target_field, rule in mapping_config.items():
#             src = rule.get("source_field")
#             action = rule.get("transformation")

#             if action in ["direct", "rename"] and src:
#                 value = record.get(src)
#                 if isinstance(value, str):
#                     value = value.strip()
#                 new_record[target_field] = value

#             elif action == "default":
#                 new_record[target_field] = rule.get("default_value")

#         transformed.append(new_record)

#     return transformed

# # -----------------------------
# # 1️⃣ Chat Endpoint
# # -----------------------------
# @app.post("/chat")
# async def chat(message: str = Form(...)):
#     msg = message.lower().strip()

#     # Detect intent
#     if any(word in msg for word in ["convert", "transform", "map", "source", "sink"]):
#         session["intent"] = "SOURCE_TO_SINK"
#         return {
#             "reply": "Got it 👍 Please upload the source and sink JSON files.",
#             "status": session["status"]
#         }

#     # Approval → execute transformation
#     if msg in ["ok", "okay", "proceed", "submit", "looks good"]:
#         if not session["mapping"]:
#             return {"reply": "Nothing to submit yet."}

#         session["status"] = "SUBMITTED"
#         result = apply_transformation(
#             session["source_data"],
#             session["mapping"]
#         )

#         return {
#             "reply": "✅ Transformation executed successfully.",
#             "result": result,
#             "status": session["status"]
#         }

#     return {
#         "reply": "Please describe what you want to do (e.g., convert source JSON to sink JSON).",
#         "status": session["status"]
#     }

# # -----------------------------
# # 2️⃣ Upload Endpoint (Design Phase)
# # -----------------------------
# @app.post("/upload")
# async def upload_files(
#     source_file: UploadFile = File(...),
#     sink_file: UploadFile = File(...)
# ):
#     if not source_file.filename.endswith(".json") or not sink_file.filename.endswith(".json"):
#         raise HTTPException(status_code=400, detail="Only JSON files are supported")

#     source_data = json.loads(await source_file.read())
#     sink_data = json.loads(await sink_file.read())

#     source_schema = extract_json_schema(source_data)
#     sink_schema = extract_json_schema(sink_data)

#     session["source_schema"] = source_schema
#     session["sink_schema"] = sink_schema
#     session["source_data"] = source_data

#     # 🔹 Structured mapping prompt
#     prompt = f"""
# You are an expert data integration agent.

# SOURCE SCHEMA:
# {json.dumps(source_schema, indent=2)}

# SINK SCHEMA:
# {json.dumps(sink_schema, indent=2)}

# TASK:
# Generate a JSON mapping describing how to convert source data into sink format.

# RULES:
# 1. Keys must be sink field names.
# 2. Each key must contain:
#    - source_field: source field name or "" if missing
#    - transformation: direct | rename | default
#    - default_value: value if transformation is default
# 3. Return ONLY valid JSON.
# 4. Do not include explanations.

# EXAMPLE:
# {{
#   "user_id": {{
#     "source_field": "id",
#     "transformation": "rename"
#   }},
#   "age": {{
#     "source_field": "",
#     "transformation": "default",
#     "default_value": "Unknown"
#   }}
# }}
# """

#     response = model.generate_content(prompt)

#     try:
#         mapping = json.loads(response.text.strip("```json").strip("```").strip())
#     except Exception:
#         raise HTTPException(status_code=500, detail="LLM did not return valid mapping JSON")

#     session["mapping"] = mapping
#     session["status"] = "DRAFT"

#     return {
#         "message": "Files uploaded successfully. Mapping draft created.",
#         "mapping": mapping,
#         "status": session["status"]
#     }

