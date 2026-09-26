İMPORTANT!!

You can change the language to English on my platform. (From the top of the screen)


TruthLens AI
Explainable Turkish Social Media Security and Verification Platform
TruthLens AI is a decision-support prototype that analyzes social media content for general toxicity, insults, bullying, hate speech, visual/OCR signals, and verifiable claims. Its moderation and human-in-the-loop decision engine is called DiyalogKalkanı (DialogueShield).
The system does not automatically or irreversibly delete content or penalize users. Instead, it presents reversible recommendations to the moderator—such as allow, tag, send to human review, or limit visibility—by displaying the model output, source chain, rationale, and risk level.
Important: This README has been prepared based on the direct Google Gemini architecture used in this project. NaraRouter, Cohere, or Laguna are not used in the active backend flow. Older experimental scripts are not part of this architecture.

1. How the Project Works
The TruthLens analysis pipeline operates in the following sequence:
Plaintext
User Text / URL / Image
          │
          ├── General BERT+LoRA toxicity model
          ├── Insult model
          ├── Bullying model
          ├── Hate speech model
          └── OCR and visual signals
                    │
                    ▼
          Gemini 3.5 Flash Lite
          Claim extraction
                    │
                    ▼
          Tavily evidence search
                    │
                    ▼
          Gemini 3.5 Flash Lite
          Final reasoning
                    │
                    ▼
          DiyalogKalkanı moderation recommendation
                    │
                    ▼
          Next.js results screen + source chain
Models Used
Task	Model	Output
General Toxicity	Doruk2404/truthlens-toxic-lora	toxic or non-toxic and binary probability
Insult	nanelimon/bert-base-turkish-offensive	Real class probabilities of the insult model
Bullying	nanelimon/bert-base-turkish-bullying	Bullying sub-classes and total score vs. Neutral
Hate Speech	ctoraman/hate-speech-berturk	Neutral/Normal, Offensive, Hate probabilities
Claim Reasoning	Gemini 3.5 Flash Lite	Claim extraction and final evaluation
Evidence Search	Tavily	Source candidates and URLs
The general BERT+LoRA model performs binary tasks only. Its confidence score is not converted into insult or bullying percentages. The scores for these three risk areas come from their respective models.
The verified mapping used in the interface for the Hate model is:
LABEL_0 = Neutral / Normal = Neutral / normal content
LABEL_1 = Offensive = Offensive / derogatory content
LABEL_2 = Hate = Hate speech


2. Requirements
Running the project requires the following:
Requirement	Recommended Version
Python	3.10 or higher
Node.js	20 or higher
npm	Included with Node.js
Internet	Required for initial model downloads, Gemini, and Tavily
Operating System	macOS, Linux, or Windows
GPU	Optional; works with CPU, GPU recommended
Upon first run, four Hugging Face models are downloaded. Total model size and CPU memory requirements vary by system. If Hugging Face access fails due to DNS or network issues, the backend honestly displays a fallback state and does not generate fake model scores.
3

. Project Folder Structure
Your project folder should be structured as follows:
Plaintext
truthlens-ai/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env
│   ├── .env.example
│   ├── truthlens.db                 # Created during runtime
│   └── test_*.py
│
└── frontend/
    ├── app/
    │   ├── page.tsx
    │   ├── layout.tsx
    │   └── globals.css
    ├── package.json
    ├── package-lock.json
    └── tsconfig.json
If the files in your delivery package are in the same folder, move main.py and Python files into the backend folder, and app/, package.json, and Next.js files into the frontend folder. The .env file must reside in the same directory where main.py is executed.


4. Where to Obtain API Keys


4.1 Google Gemini API Key
Log in to your Google AI Studio account.
Create a new key under the API key section.
Write the key only to the backend .env file.
Do not put this key into page.tsx, frontend .env, GitHub, or screenshots. TruthLens uses the Google Gemini API directly for claim extraction and final reasoning.


4.2 Tavily API Key
Open a Tavily account.
Create an API key via the dashboard.
Add the key to the backend .env as TAVILY_API_KEY.
Tavily searches for source candidates for claims produced by Gemini. If no Tavily key is provided, the source chain may return empty or limited results, but toxicity analysis will still function.


4.3 Hugging Face Token
If the model repositories are public, HF_TOKEN can be left blank. If using private repositories or encountering Hugging Face rate limits, create a token with Read permissions from Hugging Face Settings → Access Tokens.
The token must be written only to the backend .env file and must not be exposed to the frontend.


4.4 Sightengine Credentials — Optional
You can use user and secret details from your Sightengine account to analyze whether an image is AI-generated. If these details are missing, text, OCR, and other analyses will continue to function; only the Sightengine visual AI signal will be unavailable.


4.5 Bluesky Credentials — Optional Demo
If you want to use the Bluesky social demo flow:
BLUESKY_HANDLE: Your Bluesky username.
BLUESKY_APP_PASSWORD: Your Bluesky application password.
These two variables are not mandatory for normal TruthLens text analysis. Do not use your real account password; create a Bluesky app password instead.


4.6 Cohere and NaraRouter
The active main.py flow does not use COHERE_API_KEY, NARAROUTER_API_KEY, or NARAROUTER_MODEL. Therefore, they are not required for operation. Unless running legacy experimental files like cohere_web_test.py or image_fix.py, you do not need to keep these keys in .env.
Recommended approach:
Code snippet
# Removable; not used by the active main.py
COHERE_API_KEY=
NARAROUTER_API_KEY=
NARAROUTER_MODEL=
If any of these values were previously used as real keys, revoke them from the respective service panel and generate new ones for security.


5. Backend .env File
Copy .env.example to .env in the backend folder:
macOS / Linux
Bash
cd backend
cp .env.example .env
Windows PowerShell
PowerShell
cd backend
Copy-Item .env.example .env
Open the .env file and populate the following fields:
Code snippet
# Mandatory: Direct Google Gemini API
GOOGLE_API_KEY=YOUR_GOOGLE_AI_STUDIO_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta

# Recommended: For claim evidence
TAVILY_API_KEY=YOUR_TAVILY_KEY

# Hugging Face Models
TOXICITY_MODEL_ID=Doruk2404/truthlens-toxic-lora
TOXICITY_BASE_MODEL=dbmdz/bert-base-turkish-cased
INSULT_MODEL_ID=nanelimon/bert-base-turkish-offensive
BULLYING_MODEL_ID=nanelimon/bert-base-turkish-bullying
HATE_MODEL_ID=ctoraman/hate-speech-berturk
HF_TOKEN=
TOXICITY_MAX_LENGTH=256
AUXILIARY_MODEL_MAX_LENGTH=256

# Optional Visual AI Analysis
SIGHTENGINE_API_USER=
SIGHTENGINE_API_SECRET=

# Optional Bluesky Social Demo
BLUESKY_HANDLE=
BLUESKY_APP_PASSWORD=

# Allow frontend development addresses
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
Hugging Face Cache Settings
If you want to download models to a specific drive on macOS or Linux, add cache variables to your .env:
Code snippet
HF_HOME=/Users/your_username/hf-cache
HF_HUB_CACHE=/Users/your_username/hf-cache/hub
TRANSFORMERS_CACHE=/Users/your_username/hf-cache/transformers
Windows Example:
Code snippet
HF_HOME=C:/Users/YourUsername/hf-cache
HF_HUB_CACHE=C:/Users/YourUsername/hf-cache/hub
TRANSFORMERS_CACHE=C:/Users/YourUsername/hf-cache/transformers
Make sure the folder actually exists. Cache variables allow models to be downloaded from Hugging Face; initial downloads cannot occur without an internet connection. If models were previously downloaded to the cache, offline loading may be possible, provided the cache path used by the backend is correct.
HF_HOME=/Users/dorukoz/hf-cache applies only to the user dorukoz on that machine. Do not copy this path verbatim onto another user's computer; use your own user directory.

6. .gitignore Security
The existing .gitignore is conceptually correct, but __pycache__// is not a standard Python cache pattern. Use the following version:
Plaintext
# Secrets and local environment
.env
.env.*
!.env.example

# Python virtual environments
venv/
.venv/
env/

# Python cache
__pycache__/
**/__pycache__/
*.py[cod]
*$py.class

# Hugging Face and model caches
.cache/
.huggingface/
hf-cache/
transformers-cache/

# Local application data
*.db
*.db-shm
*.db-wal

# Logs and local outputs
*.log
/tmp/

# Node / Next.js
node_modules/
.next/
out/
coverage/

# OS/editor files
.DS_Store
Thumbs.db
.vscode/
.idea/

# Test artifacts
raw_three_before.json
.env.example can be committed to Git; the real .env must never be committed. If you previously pushed API keys to Git, deleting the file is not enough; revoke the keys from the service panels and generate new ones.
Production Deployment: Vercel + Render
In this project, deploy the Next.js interface to Vercel and the FastAPI backend to a separate continuously running service on Render.
The render.yaml file disables PyTorch toxicity models by default to prevent OOM (Out Of Memory) crashes on 512 MiB RAM instances; in this setup, toxicity analysis uses a controlled fallback and does not generate model scores. To enable all four models, set TOXICITY_MODELS_ENABLED=true and use an instance with at least 4 GB of RAM. The backend must run with a single worker.
Import the GitHub repository into Vercel. Select frontend as the Root Directory; Next.js will be detected automatically.
Add NEXT_PUBLIC_API_BASE_URL under the Vercel project's Settings → Environment Variables. The value should be your Render API service URL, e.g., [https://truthlens-api.onrender.com](https://truthlens-api.onrender.com). Then redeploy on Vercel.
In Render, select New → Blueprint and choose the same GitHub repository. Render will create the truthlens-api service from the render.yaml file located at the root. When prompted, enter GOOGLE_API_KEY and TAVILY_API_KEY into the Render environment variables. HF_TOKEN is not required for public Hugging Face models; add it as a Render backend environment variable if dealing with rate limits or private models.
Add your exact Vercel frontend origin to the ALLOWED_ORIGINS variable in Render, e.g., [https://truthlens-ai.vercel.app](https://truthlens-ai.vercel.app) (without a trailing /). If using preview deployments, add them separated by commas as well. Redeploy the Render service.
Open https://<render-service-name>[.onrender.com/health](https://.onrender.com/health). You should receive an API health response; then try running an analysis from the Vercel frontend.
Toxicity models are disabled in the Render Blueprint by default; when enabled, they are downloaded from Hugging Face on first boot, which takes time for the service to become ready. Upgrade the Render instance RAM before enabling model usage. SQLite and Render persistent disks are intended for a single instance; do not scale horizontally or spin up multiple backend instances. Place API keys in the Render backend environment variables, not on Vercel.


7. macOS Installation and Execution
The following steps are for macOS. Open your Terminal app. If you named your project folder differently, replace truthlens-ai with your folder name.


7.1 Pre-checks
Bash
python3 --version
node --version
npm --version
Python 3.10+ and Node.js 20+ are recommended. If Node.js is not installed, install the LTS version from nodejs.org.


7.2 Enter Backend Folder and Create Virtual Environment
Bash
cd ~/truthlens-ai/backend
python3 -m venv .venv
source .venv/bin/activate
If you see (.venv) at the beginning of your terminal prompt, the virtual environment is active. For every new backend terminal window, you must run this command first:
Bash
source .venv/bin/activate


7.3 Install Python Dependencies
Bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
The initial installation installs PyTorch, Transformers, PEFT, Hugging Face Hub, Tesseract/Pillow, and FastAPI dependencies. If Tesseract is missing on your system for OCR, you can install it via Homebrew:
Bash
brew install tesseract


7.4 Create Backend .env File
Bash
cp .env.example .env
open -e .env
Verify at least GOOGLE_API_KEY, GEMINI_MODEL, TAVILY_API_KEY, and the Hugging Face model IDs inside .env. Write real keys only to this backend .env file.
On Apple Silicon Macs, models can run on the CPU. Initial model downloads require sufficient disk space and an internet connection.


7.5 Set Hugging Face Cache Path for macOS
For example, if your username is dorukoz:
Code snippet
HF_HOME=/Users/dorukoz/hf-cache
HF_HUB_CACHE=/Users/dorukoz/hf-cache/hub
TRANSFORMERS_CACHE=/Users/dorukoz/hf-cache/transformers
If you are under a different username, replace dorukoz with your own macOS username. To create these folders:
Bash
mkdir -p "$HOME/hf-cache/hub" "$HOME/hf-cache/transformers"


7.6 Start the Backend — Terminal 1
Bash
cd ~/truthlens-ai/backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
Leave this terminal open. Once the backend is ready, open these addresses:
[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)


7.7 Start the Frontend — Terminal 2
Open a new Terminal window; do not close the backend terminal.
Bash
cd ~/truthlens-ai/frontend
npm ci
The frontend expects the backend at [http://127.0.0.1:8000](http://127.0.0.1:8000) by default. If your backend address differs:
Bash
printf 'NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000\n' > .env.local
Then start the frontend:
Bash
npm run dev
Open http://localhost:3000 in your browser.


7.8 macOS Backend Health Check
In a new or second terminal:
Bash
curl http://127.0.0.1:8000/health
You should see google_gemini_configured: true and available: true for all four models. If there is a Hugging Face DNS or download issue, the respective model will show available: false; the frontend will display this as Model unavailable and will not generate fake scores.


8. Windows Installation and Execution
The following steps are for Windows 10/11 and PowerShell. Open PowerShell. If you named your project folder differently, replace truthlens-ai with your folder name.


8.1 Pre-checks
PowerShell
py --version
node --version
npm --version
Python 3.10+ and Node.js 20+ are recommended. Install Python from python.org and Node.js LTS from nodejs.org. Check the Add Python to PATH option during Python installation.


8.2 Enter Backend Folder and Create Virtual Environment
PowerShell
cd $HOME\truthlens-ai\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
If you see (.venv) at the beginning of your terminal prompt, the virtual environment is active. For every new PowerShell window, you must run this command first:
PowerShell
.\.venv\Scripts\Activate.ps1
If PowerShell throws a script execution policy error, run this command for the current user only:
PowerShell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
Then run the activation command again.


8.3 Install Python Dependencies
PowerShell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Initial installation pulls PyTorch, Transformers, PEFT, Hugging Face Hub, Tesseract/Pillow, and FastAPI dependencies. You may need to install Tesseract on Windows for OCR and ensure Tesseract is added to your PATH.


8.4 Create Backend .env File
PowerShell
Copy-Item .env.example .env
notepad .env
Verify at least GOOGLE_API_KEY, GEMINI_MODEL, TAVILY_API_KEY, and Hugging Face model IDs inside .env. Write real keys only to the backend .env file.


8.5 Set Hugging Face Cache Path for Windows
For example, if your Windows username is Doruk:
Code snippet
HF_HOME=C:/Users/Doruk/hf-cache
HF_HUB_CACHE=C:/Users/Doruk/hf-cache/hub
TRANSFORMERS_CACHE=C:/Users/Doruk/hf-cache/transformers
Alternatively, define cache variables temporarily in PowerShell:
PowerShell
$env:HF_HOME="$HOME\hf-cache"
$env:HF_HUB_CACHE="$HOME\hf-cache\hub"
$env:TRANSFORMERS_CACHE="$HOME\hf-cache\transformers"
New-Item -ItemType Directory -Force "$HOME\hf-cache\hub" | Out-Null
New-Item -ItemType Directory -Force "$HOME\hf-cache\transformers" | Out-Null


8.6 Start the Backend — PowerShell Terminal 1
PowerShell
cd $HOME\truthlens-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
Leave this window open. Once ready, visit:
[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)


8.7 Start the Frontend — PowerShell Terminal 2
Open a new PowerShell window; do not close the backend window.
PowerShell
cd $HOME\truthlens-ai\frontend
npm ci
If your backend address differs from the default [http://127.0.0.1:8000](http://127.0.0.1:8000):
PowerShell
Set-Content -Path .env.local -Value "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000"
Then start the frontend:
PowerShell
npm run dev
Open http://localhost:3000 in your browser.


8.8 Windows Backend Health Check
In PowerShell:
PowerShell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 10
Expect google_gemini_configured: true and available: true for all four models. If a Hugging Face DNS or download error occurs, the model becomes available: false; the frontend displays Model unavailable without generating fake scores.


8.9 Summary of Two Terminals on Windows
PowerShell Terminal 1 — Backend:
PowerShell
cd $HOME\truthlens-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
PowerShell Terminal 2 — Frontend:
PowerShell
cd $HOME\truthlens-ai\frontend
npm ci
npm run dev


9. Making Your First Analysis
Check the backend /health status.
Open the frontend at http://localhost:3000.
Type a sample text into the input field, e.g., "Sen tam bir aptalsın." (You are a total idiot).
Click the Analyze button.
Review the general toxicity engine results and model confidence on the results screen.
Check individual results for insult, bullying, and the hate model on the contextual toxicity card.
Inspect the claim, supporting/contradicting sources, and Tavily status for any verifiable sentence.
The hate model results are displayed in the interface with these meanings:
Nötr / normal içerik (Neutral / normal content)
Saldırgan / aşağılayıcı içerik (Offensive / derogatory content)
Nefret söylemi (Hate speech)
If a model is unavailable, the interface must display Model unavailable. This is not the same as a genuine 0%.


10. API Examples
Text Analysis
Bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"content":"Sen tam bir aptalsın."}'
The text field is also accepted for backward compatibility:
Bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"Bugün hava çok güzel."}'
URL Analysis
Bash
curl -X POST http://127.0.0.1:8000/analyze-url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
Important Response Fields
JSON
{
  "toxicity_label": "toxic",
  "toxicity_confidence": 0.9994,
  "toxicity_engine": "model",
  "toxicity_models": {
    "insult": {
      "score": 99.93,
      "engine": "insult_model",
      "raw": {}
    },
    "bullying": {
      "score": 99.99,
      "engine": "bullying_model",
      "raw": {}
    },
    "hate_speech": {
      "engine": "hate_model",
      "raw": {
        "Neutral / Normal": 0.4,
        "Offensive": 95.7,
        "Hate": 3.9
      }
    }
  },
  "pipeline_status": {},
  "moderation": {}
}
Percentages are for illustrative purposes. Actual results vary based on each text and model inference.


11. Tests
With the backend virtual environment active:
Bash
python -m py_compile main.py
python test_moderation_logic.py
python test_toxicity.py
python test_binary_toxicity_mapping.py
python test_multi_model_runtime.py
python test_analyze_raw_three.py
python test_hybrid_pipeline.py
Frontend production build test:
Bash
cd ../frontend
npm ci
npm run build
Real Hugging Face model tests require internet access and sufficient RAM. If models are not cached, they will be downloaded on first run. If there is no network/DNS, available=false is the expected outcome; the purpose of the test in this case is to verify that the fallback behavior does not produce fake scores.


12. Troubleshooting and Common Issues
Fallback (model unavailable) Appears
First, open /health. If one of the four models shows available=false, read the error field. Common causes include Hugging Face DNS access issues, interrupted initial model downloads, insufficient RAM/disk space, or incorrect cache paths.
Gemini Is Not Working
Verify that GOOGLE_API_KEY in .env is real and active, and that the line GEMINI_MODEL=gemini-3.5-flash-lite is present. Completely restart the backend after modifying .env.
Sources Are Empty
If TAVILY_API_KEY is missing or if claims cannot be extracted, the Tavily evidence step may remain empty. Check the status of gemini_claim_extraction, tavily, and gemini_final_reasoning within the pipeline_status field inside the /analyze response.
Frontend Cannot Connect to Backend
Verify that the backend is actually running on 127.0.0.1:8000. If using a different port, write NEXT_PUBLIC_API_BASE_URL into frontend .env.local and restart the frontend.
Receiving 422 Unprocessable Entity
The request body must contain at least one of the content or text fields:
JSON
{"content":"Text to be analyzed"}
Hugging Face DNS Error
Check your internet connection and DNS settings. If models were previously downloaded, make sure the paths in HF_HOME, HF_HUB_CACHE, and TRANSFORMERS_CACHE match the same user and backend environment. Without cache, models cannot run entirely offline without being downloaded in an internet-connected environment first.
Port Already in Use (macOS/Linux)
Bash
lsof -i :8000
kill -9 PID
Windows PowerShell:
PowerShell
netstat -ano | findstr :8000
taskkill /PID PID /F


13. Security Checklist
Keep real API keys inside .env.
Do not commit the .env file to Git.
Do not expose GOOGLE_API_KEY, TAVILY_API_KEY, HF_TOKEN, Sightengine secret, and Bluesky app password values to the frontend.
If a real key enters Git, revoke it from the panel and generate a new one.
Use a Bluesky app password, not your normal account password.
In production environments, restrict ALLOWED_ORIGINS strictly to your actual frontend domain.
Do not add the Hugging Face model cache or truthlens.db to public repositories.


14. Social / Bluesky Demo
The social demo screen of TruthLens illustrates the platform adapter pattern. If BLUESKY_HANDLE and BLUESKY_APP_PASSWORD are defined, the Bluesky feed and social actions can operate. The NSosyal integration is demonstrated through a prototype adapter/simulation contract; platform permissions, API contracts, and human approval flows must be separately verified before executing sharing, deletion, or punishment actions on a real production account.
The goal of DiyalogKalkanı is not automated deletion, but providing explainable and reversible decision support to the moderator.


15. Pre-production Checklist
[ ] .env created and real keys stored only in the backend
[ ] NaraRouter/Cohere legacy keys removed from active config
[ ] Backend requirements installed
[ ] /health endpoint accessible
[ ] available status of all four Hugging Face models verified
[ ] Gemini configured/success status verified
[ ] Tavily evidence test executed
[ ] Frontend opened on localhost:3000
[ ] Three sample texts analyzed
[ ] npm run build successful
[ ] Real .env not committed to Git
[ ] API keys do not appear in README or screenshots


16. License and Responsible Use
TruthLens AI is a moderation decision-support prototype. Because model results are probabilistic, they should not be used alone for irreversible legal, punitive, or account-impacting decisions. Human review, appeals, and audit logs must be maintained for medium and high-risk outcomes.
Licensing terms of open-source models and libraries used must also be reviewed, and conditions outlined in their respective model cards must be adhered to during distribution.


17. References
Google Gemini API Documentation
Tavily Documentation
Hugging Face — Doruk2404/truthlens-toxic-lora
Hugging Face — nanelimon/bert-base-turkish-offensive
Hugging Face — nanelimon/bert-base-turkish-bullying
Hugging Face — ctoraman/hate-speech-berturk
FastAPI Documentation
Next.js Documentation
Bluesky AT Protocol Documentation
Quickest Execution Summary
Bash
# Terminal 1
cd truthlens-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
cd truthlens-ai/frontend
npm ci
npm run dev

# Browser
open http://localhost:3000
On Windows, use .\.venv\Scripts\Activate.ps1 instead of source .venv/bin/activate.
