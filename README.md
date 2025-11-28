
# 🔑 Environment Variables Guide

This project requires the following credentials.  
Create a `.env` or `.env.example` file and fill in the values as instructed below.

---

## 🚀 1. GOOGLE_API_KEY
Used for Google AI APIs (e.g., Gemini, Vertex AI).

**How to get it:**
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Log in with your Google account.
3. Go to the **API Keys** tab.
4. Click **Create API Key**.
5. Copy the key into your `.env` file.

---

## 📝 2. NOTION_TOKEN
Used to access the Notion API.

**How to get it:**
1. Go to [Notion Integrations](https://www.notion.so/my-integrations).
2. Click **+ New Integration**.
3. Name your integration → **Submit**.
4. Copy the **Internal Integration Token** from the integration page.
5. Paste it into your `.env`.

---

## 🧩 3. GOOGLE_OAUTH_CLIENT_ID & GOOGLE_OAUTH_CLIENT_SECRET
Used for OAuth authentication (Google login, Drive, Gmail, etc.).

**How to create OAuth credentials:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **APIs & Services → Credentials**.
3. Click **Create Credentials → OAuth client ID**.
4. Select **Web Application** (or Desktop, depending on your project).
5. Enter **Authorized redirect URIs**, e.g.:

http://localhost:3001

http://localhost:3002

6. Click **Create** → you will get:
- **Client ID**
- **Client Secret**

Paste these into your `.env`.
---

📊 4. LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_BASE_URL

Used for tracking LLM observability with Langfuse.

How to get them:
1. Go to Langfuse Cloud￼.
2. Select your project.
3. Go to Project Settings → API Keys.
4. Create:
    * Public Key
    * Secret Key
5. Base URL is usually:

https://cloud.langfuse.com

---

# Installation external tool
## Installl MCP - Google
### Install `bun`
Access this web and install: https://bun.com/docs/installation

### MCP - Google
```bash
git clone https://github.com/vakharwalad23/google-mcp.git
cd ./google-mcp
bun install
cd ..
```

## Install Notion - MCP
```bash
npm install @notionhq/notion-mcp-server
```
---
# Chatbot backend using `venv1`
Using $2$ different `venv` for avoid dependency confict of `pip` between frontend and backend.
## Install Virtual Environment 1
```bash
### Windows
python -m venv venv1

# Activate venv (Windows)
.\venv1\Scripts\activate

# Activate venv (macOS/Linux)
source venv1/bin/activate
```
## Library installation
```bash
pip install -r requirements1.txt
```
## Running
```bash
python app.py
```
---

# Frontend by `streamlit` using `venv2`
## Install Virtual Environment 2
```bash
### Windows
python3.10 -m venv venv2

# Activate venv (Windows)
.\venv2\Scripts\activate

# Activate venv (macOS/Linux)
source venv2/bin/activate
```
## Library installation
```bash
pip install -r requirements2.txt
```
```bash
streamlit run Homepage.py
```
