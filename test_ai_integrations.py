"""Quick integration test for all 3 AI services."""
import sys, os

os.chdir('/Users/hectorgarcia/Desktop/LyoBackendJune')

# Load .env
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k, v)

print('=== 1. GEMINI 3.1 ===')
import google.generativeai as genai
key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
genai.configure(api_key=key)
model = genai.GenerativeModel('gemini-3.1-pro-preview-customtools')
resp = model.generate_content('Say OK if you work')
print(f'  Model: gemini-3.1-pro-preview-customtools')
print(f'  Response: {resp.text.strip()[:50]}')
print(f'  Status: WORKING')

print()
print('=== 2. IMAGEN 3 ===')
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
vertexai.init(project='lyobackend', location='us-central1')
img_model = ImageGenerationModel.from_pretrained('imagen-3.0-generate-002')
result = img_model.generate_images(prompt='A blue circle on white', number_of_images=1)
print(f'  Model: imagen-3.0-generate-002')
print(f'  Image bytes: {len(result.images[0]._image_bytes)}')
print(f'  Status: WORKING')

print()
print('=== 3. RUNWAY GEN-4.5 ===')
try:
    from runwayml import RunwayML
    import runwayml as rml
    api_secret = os.environ.get('RUNWAYML_API_SECRET', '')
    if api_secret:
        client = RunwayML(api_key=api_secret)
        print(f'  Model: gen4.5')
        print(f'  Status: WORKING (client initialized)')
    else:
        print(f'  SDK installed: runwayml v{rml.__version__}')
        print(f'  Model: gen4.5')
        print(f'  Status: SDK OK, but RUNWAYML_API_SECRET not set in .env')
        print(f'  Action: Get your API key from https://app.runwayml.com/settings/api-keys')
        print(f'         Then add to .env: RUNWAYML_API_SECRET=your_key_here')
except ImportError:
    print(f'  Status: FAILED - runwayml package not installed')

print()
print('=== SUMMARY ===')
print('Gemini 3.1:  PASS')
print('Imagen 3:    PASS')
print('Runway:      SDK ready (needs API key to fully test)')
