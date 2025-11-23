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
python agent_backend.py
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