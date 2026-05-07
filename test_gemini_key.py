from google import genai

KEY = "AIzaSyAeauPWKKKsXy3dghttnBfHH8wT0qWup_0"

client = genai.Client(api_key=KEY)
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Respondé solo con la palabra "OK".',
)
print("Respuesta:", response.text)
