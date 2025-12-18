import google.generativeai as genai

genai.configure(api_key="AIzaSyBoWIU1iCpdWf5MAP61H0mkFSVXb3GV4Hw")

models = genai.list_models()

for m in models:
    print("MODEL:", m.name)
    print("SUPPORTED:", m.supported_generation_methods)
    print("-" * 50)
