from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import json
from core.database import SessionLocal
from models.gemini_model import GeminiModel
import logging
import uuid

logger = logging.getLogger(__name__)

def mask_data(data: dict) -> (dict, dict):
    """
    Masks string values in a JSON object with placeholders.
    """
    masked_data = {}
    masking_map = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked_value, sub_map = mask_data(value)
            masked_data[key] = masked_value
            masking_map.update(sub_map)
        elif isinstance(value, list):
            masked_data[key] = []
            for item in value:
                if isinstance(item, dict):
                    masked_item, sub_map = mask_data(item)
                    masked_data[key].append(masked_item)
                    masking_map.update(sub_map)
                else:
                    masked_data[key].append(item)
        elif isinstance(value, str):
            placeholder = f"__MASKED_{uuid.uuid4().hex}__"
            masked_data[key] = placeholder
            masking_map[placeholder] = value
        else:
            masked_data[key] = value
    return masked_data, masking_map

def unmask_data(data: dict, masking_map: dict) -> dict:
    """
    Unmasks string values in a JSON object using a masking map.
    """
    unmasked_data = {}
    for key, value in data.items():
        if isinstance(value, dict):
            unmasked_data[key] = unmask_data(value, masking_map)
        elif isinstance(value, list):
            unmasked_data[key] = []
            for item in value:
                if isinstance(item, dict):
                    unmasked_data[key].append(unmask_data(item, masking_map))
                elif isinstance(item, str) and item in masking_map:
                    unmasked_data[key].append(masking_map[item])
                else:
                    unmasked_data[key].append(item)
        elif isinstance(value, str) and value in masking_map:
            unmasked_data[key] = masking_map[value]
        else:
            unmasked_data[key] = value
    return unmasked_data

async def convert_json_with_sample(source_json: dict, sink_json: dict) -> dict:
    """
    Converts a source JSON object to a new JSON object based on a sink JSON sample using an LLM.
    """
    db = SessionLocal()
    try:
        # Mask the source JSON
        masked_source_json, masking_map = mask_data(source_json)

        # Fetch the active model from the database
        active_model = db.query(GeminiModel).filter(GeminiModel.is_active == True).first()
        if not active_model:
            logger.error("No active model found in the database.")
            raise ValueError("No active model found in the database.")

        # Configure the generative AI model
        llm = ChatGoogleGenerativeAI(model=active_model.model_name, convert_system_message_to_human=True)

        # Create a prompt for the LLM
        prompt = f"""You are a data transformation expert. Convert the following source JSON to the sink JSON format.

        **Source JSON:**
        ```json
        {json.dumps(masked_source_json, indent=4)}
        ```

        **Sink JSON Sample:**
        ```json
        {json.dumps(sink_json, indent=4)}
        ```

        **Instructions:**

        1.  **Analyze Structure:** Analyze the structure of the source and sink JSON samples.
        2.  **Map Keys and Values:** Map the keys and values from the source to the sink format based on the structure and content.
        3.  **Handle Missing Keys:** If a key from the sink sample is not in the source, omit it from the output.
        4.  **Preserve Unmapped Keys:** If a key from the source is not in the sink sample, you can choose to either include it as-is or omit it. For this task, please omit it.
        5.  **Output:** Return only the converted JSON object, without any extra text or explanations.

        **Converted Sink JSON:**
        """
        logger.info(f"Sending prompt to LLM: {prompt}")

        # Generate the content
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        logger.info(f"Received response from LLM: {response.content}")

        try:
            # The response text should be a JSON string
            # Strip markdown backticks and 'json' prefix
            cleaned_response = response.content.strip(" `json\n")
            masked_output = json.loads(cleaned_response)
            
            # Unmask the output
            unmasked_output = unmask_data(masked_output, masking_map)
            return unmasked_output
        except json.JSONDecodeError as e:
            logger.error(f"LLM did not return valid JSON: {e}\nResponse content: {response.content}", exc_info=True)
            raise ValueError(f"The LLM did not return a valid JSON object. Error: {e}")
    finally:
        db.close()