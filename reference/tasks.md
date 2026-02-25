\# Desktop Agentic System — Zero-Touch Implementation Plan (for Codex CLI)



This markdown file is designed to be used with \*\*Codex CLI\*\* in two modes:



\* \*\*One‑shot mode (recommended for you):\*\* Codex executes \*all\* steps from Step 1 → Step 14 sequentially, running each step’s verification gate before continuing. It must \*\*stop immediately\*\* on the first failure and print the failing command output.

\* \*\*Step-by-step mode:\*\* Codex executes one step at a time.



\*\*Goal:\*\* Codex must implement the complete application by following each step sequentially, with \*\*tests + verification gates\*\* before proceeding.

\*\*No human interaction is required\*\*: each step includes its own verification, with deterministic local tests (mock LLM), and optional real Gemini integration.



---



\## 0) Global Rules (Codex must follow)



1\. \*\*Run in one‑shot mode unless explicitly instructed otherwise.\*\* Execute Step 1 → Step 14 in order.

2\. \*\*Do not skip steps.\*\* Complete Step N fully, then run the verification commands listed for Step N. Proceed only if they pass.

3\. \*\*No interactive prompts\*\* at runtime for tests or setup. Use defaults and environment variables.

4\. \*\*Keep changes minimal per step\*\*. Commit-quality increments.

5\. \*\*All LLM calls must go through `llm/` provider abstraction\*\*. No direct calls from core/router/executor to Gemini.

6\. \*\*All tool actions must be executed by `tools/` layer only\*\*. The LLM never performs file operations directly.

7\. \*\*CDA is the single source of truth\*\* for shared runtime objects, settings, and memory.

8\. \*\*LLM output must be JSON-only\*\*, validated against schema before use. If invalid, retry per policy; if still invalid, fail gracefully with a controlled error response.

9\. \*\*Failure handling:\*\* if any verification command fails, stop immediately and report what failed and why. Do not continue.



---



\## 1) Target Tech Choices



\* Language: \*\*Python 3.11+\*\*

\* UI: \*\*Tkinter\*\* (chat-style window + settings dialog)

\* Tests: \*\*pytest\*\*

\* Lint/format: \*\*ruff\*\* (optional), keep simple if needed

\* Gemini integration: implemented as a provider in `llm/gemini\_client.py` (real calls optional)

\* Default LLM for tests: `llm/mock\_client.py` (deterministic scripted outputs)



---



\## 2) Final Folder Structure (must match)



Create this structure exactly:



```

desktop-agentic-system/

├── main.py

├── core/

│   ├── \_\_init\_\_.py

│   ├── common\_data\_area.py

│   ├── controller.py

│   ├── router.py

│   ├── executor.py

│   └── lifecycle.py

├── ui/

│   ├── \_\_init\_\_.py

│   ├── chat\_ui.py

│   ├── settings\_ui.py

│   └── ui\_state.py

├── llm/

│   ├── \_\_init\_\_.py

│   ├── base\_client.py

│   ├── gemini\_client.py

│   ├── mock\_client.py

│   └── response\_validator.py

├── agents/

│   ├── \_\_init\_\_.py

│   ├── registry.py

│   ├── router/

│   │   └── router.prompt

│   └── file\_manager/

│       └── file\_manager.prompt

├── tools/

│   ├── \_\_init\_\_.py

│   ├── tool\_registry.py

│   └── filesystem/

│       ├── \_\_init\_\_.py

│       ├── list\_directory.py

│       ├── inspect\_file.py

│       ├── read\_file.py

│       ├── copy\_file.py

│       └── move\_file.py

├── prompts/

│   ├── \_\_init\_\_.py

│   ├── renderer.py

│   └── templates/

│       ├── agent\_template.txt

│       └── router\_template.txt

├── settings/

│   ├── \_\_init\_\_.py

│   ├── config\_loader.py

│   └── defaults.json

├── validation/

│   ├── \_\_init\_\_.py

│   ├── json\_schema.py

│   ├── router\_validator.py

│   └── executor\_validator.py

├── logging/

│   ├── \_\_init\_\_.py

│   └── execution\_logger.py

├── tests/

│   ├── \_\_init\_\_.py

│   ├── test\_cda.py

│   ├── test\_prompt\_renderer.py

│   ├── test\_router.py

│   ├── test\_executor.py

│   ├── test\_tools\_filesystem.py

│   └── test\_e2e\_filemanager.py

├── requirements.txt

└── README.md

```



---



\## 3) Application Behavior (Acceptance Criteria)



\### UI



\* A chat window where user types a message and sees responses.

\* A settings panel to set:



&nbsp; \* Gemini API Key (string)

&nbsp; \* Accessible directories (list)

&nbsp; \* Default directory (string)

\* Settings stored in CDA, and persisted to a local JSON config file under `settings/` (e.g. `settings/user\_config.json`).



\### Runtime Flow



1\. User message → Controller

2\. Controller renders Router prompt → LLM → gets JSON `{selected\_agent,...}`

3\. Controller loads agent prompt template → Executor fills placeholders → LLM → gets JSON directive

4\. If directive is a tool call → Executor calls tools → stores tool result → loops

5\. Completion → response returned to UI



\### FileManager Agent Tools



\* list\_directory

\* inspect\_file

\* read\_file (PDF + text)

\* copy\_file

\* move\_file

\* \*\*No delete tool exists\*\* and agent prompt forbids deletion.



\### Testing



\* All tests pass with mock LLM without internet.

\* An end-to-end test simulates a user request like:



&nbsp; \* “List files in default directory”

&nbsp; \* Tool is called, output returned, and agent completes.



---



\# STEP-BY-STEP IMPLEMENTATION



\## Step 1 — Bootstrap Project \& Dependencies



\### Tasks



\* Create the full folder structure.

\* Add `requirements.txt`:



&nbsp; \* `pytest`

&nbsp; \* `pydantic` (optional but recommended for validation)

&nbsp; \* `PyPDF2` (for PDF extraction)

\* Add minimal `README.md` with run/test commands.

\* Add empty `\_\_init\_\_.py` where needed.



\### Verify



Run:



\* `python -m venv .venv`

\* `source .venv/bin/activate` (or Windows equivalent)

\* `pip install -r requirements.txt`

\* `pytest -q`



Expected:



\* Tests run (even if none exist yet) without errors.



---



\## Step 2 — Implement CommonDataArea (CDA) Singleton



\### Requirements



\* CDA is a \*\*singleton\*\* class shared by all components.

\* Stores:



&nbsp; \* `settings` (dict)

&nbsp; \* `memory` (dict)

&nbsp; \* `runtime\_objects` (dict)

&nbsp; \* `session` (dict)

\* Provide safe getters/setters:



&nbsp; \* `get\_setting(key, default=None)`

&nbsp; \* `set\_setting(key, value)`

&nbsp; \* `get\_memory(key, default=None)`

&nbsp; \* `set\_memory(key, value)`

&nbsp; \* `set\_runtime(name, obj)` / `get\_runtime(name)`



\### Files



\* `core/common\_data\_area.py`

\* Tests: `tests/test\_cda.py`



\### Verify



Run:



\* `pytest -q`



Expected:



\* CDA singleton behavior correct

\* CRUD methods work



---



\## Step 3 — Settings Loader + Defaults + Persistence



\### Requirements



\* `settings/defaults.json` contains defaults:



&nbsp; \* `llm\_provider`: `"mock"` (default)

&nbsp; \* `gemini\_api\_key`: `""`

&nbsp; \* `accessible\_directories`: `\[]`

&nbsp; \* `default\_directory`: `""`

\* `settings/config\_loader.py`:



&nbsp; \* loads defaults + merges user config if exists (`settings/user\_config.json`)

&nbsp; \* writes config back on changes

\* On app start, load settings into CDA.



\### Files



\* `settings/defaults.json`

\* `settings/config\_loader.py`

\* Update `tests` to validate load/merge/save.



\### Verify



Run:



\* `pytest -q`



Expected:



\* Settings loaded into CDA

\* Save/reload roundtrip works



---



\## Step 4 — Prompt Renderer



\### Requirements



\* `prompts/renderer.py` renders a prompt template with placeholders:



&nbsp; \* `{{USER\_PROMPT}}`, `{{CHAT\_HISTORY}}`, `{{PLAN}}`, `{{TOOL\_DATA}}`, etc.

&nbsp; \* Must not crash on missing placeholders; replace missing with empty string.

\* Provide a `render(template\_str: str, data: dict) -> str`.



\### Files



\* `prompts/renderer.py`

\* Tests: `tests/test\_prompt\_renderer.py`



\### Verify



Run:



\* `pytest -q`



Expected:



\* Template rendering deterministic



---



\## Step 5 — LLM Abstraction + Mock Client + JSON Validator



\### Requirements



\* `llm/base\_client.py`: interface for LLM clients:



&nbsp; \* `generate(prompt: str) -> str`

\* `llm/mock\_client.py`: deterministic scripted behavior for tests.



&nbsp; \* It should return different JSON depending on markers in prompt (router vs file\_manager).

\* `llm/response\_validator.py`:



&nbsp; \* Validate JSON-only output (must parse)

&nbsp; \* Basic schema checks delegated to validation layer.



\### Verify



Run:



\* `pytest -q`



Expected:



\* Mock LLM returns valid JSON

\* Validator catches invalid JSON



---



\## Step 6 — JSON Schemas + Validators



\### Requirements



Implement strict validators:



1\. Router schema:



```json

{

&nbsp; "selected\_agent": "string",

&nbsp; "confidence": "low|medium|high",

&nbsp; "reason": "string"

}

```



2\. Executor schema:



In addition to execution planning, the agent must provide \*\*user-facing progress feedback\*\* so the UI can inform the user what is happening during multi‑step execution. This feedback is informational only and does not change executor authority.



```json

{

&nbsp; "plan": {"current\_step": "string", "revised\_plan": "string"},

&nbsp; "action": {

&nbsp;   "type": "tool\_call|request\_user\_input|continue|complete",

&nbsp;   "tool\_request": {"tool\_name": "string", "parameters": "object"}

&nbsp; },

&nbsp; "conversation\_update": {"content": "string"},

&nbsp; "reasoning": {"summary": "string"},

&nbsp; "ui\_feedback": {

&nbsp;   "status": "string",

&nbsp;   "message": "string",

&nbsp;   "progress\_hint": "string"

&nbsp; }

}

```



\* Implement in:



&nbsp; \* `validation/json\_schema.py`

&nbsp; \* `validation/router\_validator.py`

&nbsp; \* `validation/executor\_validator.py`



\### Verify



Run:



\* `pytest -q`



Expected:



\* Schema validators pass for correct payloads and fail for incorrect



---



\## Step 7 — Agents Registry + Prompt Files (Router + FileManager)



\### Requirements



\* `agents/registry.py`:



&nbsp; \* Lists available agents and their prompt file paths

&nbsp; \* Returns metadata for router (name, description)

\* Add prompt files:



&nbsp; \* `agents/router/router.prompt` (minimal router prompt)

&nbsp; \* `agents/file\_manager/file\_manager.prompt` (FileManager template with settings injection: accessible dirs, default dir)

\* Prompts must instruct: \*\*JSON only\*\*, strict schema, tool list.



\### Verify



Run:



\* `pytest -q`



Expected:



\* Registry loads prompts successfully



---



\## Step 8 — Tool Registry + Filesystem Tools (No Delete)



\### Requirements



Implement filesystem tools with \*\*path boundary enforcement\*\*:



\* All tool calls must validate that target paths are within:



&nbsp; \* `CDA.settings\["accessible\_directories"]`

\* If no accessible directories configured:



&nbsp; \* Tool calls should fail with a controlled error result.

\* Tools:



&nbsp; \* `list\_directory(directory\_path)`

&nbsp; \* `inspect\_file(file\_path)` (size, mtime, extension)

&nbsp; \* `read\_file(file\_path)`:



&nbsp;   \* If PDF: extract text via PyPDF2

&nbsp;   \* If text: read safely

&nbsp; \* `copy\_file(source\_path, destination\_path)`

&nbsp; \* `move\_file(source\_path, destination\_path)`

\* Return tool outputs as dictionaries.



\### Files



\* `tools/tool\_registry.py`

\* `tools/filesystem/\*.py`

\* Tests: `tests/test\_tools\_filesystem.py`



\### Verify



Run:



\* `pytest -q`



Expected:



\* Tools work inside allowed directories

\* Tools reject outside paths

\* No delete tool exists anywhere



---



\## Step 9 — Router Component (LLM-driven)



\### Requirements



\* `core/router.py`:



&nbsp; \* Render router prompt with agent list + user prompt + optional chat history

&nbsp; \* Call LLM client from CDA settings (mock by default)

&nbsp; \* Validate router JSON via router validator

\* Router returns structured route decision object



\### Tests



\* `tests/test\_router.py` uses mock LLM and registry.



\### Verify



Run:



\* `pytest -q`



Expected:



\* Router selects FileManager for file-related requests



---



\## Step 10 — Executor Component (LLM + Tool Loop)



\### Requirements



\* `core/executor.py`:



&nbsp; \* Load selected agent prompt template

&nbsp; \* Build placeholder data from CDA:



&nbsp;   \* settings: accessible dirs, default dir

&nbsp;   \* memory: plan, steps, tool data, history

&nbsp;   \* user prompt

&nbsp; \* Render prompt

&nbsp; \* Call LLM

&nbsp; \* Validate executor JSON schema

&nbsp; \* Extract `ui\_feedback` and immediately forward it to controller/UI so the user can see execution progress

&nbsp; \* If `tool\_call`: invoke tool via tool\_registry, store result into CDA.memory\["tool\_data"], loop

&nbsp; \* If `request\_user\_input`: return a structured response telling controller/UI to ask user

&nbsp; \* If `continue`: loop execution

&nbsp; \* If `complete`: return final conversation\_update content



\### Tests



\* `tests/test\_executor.py`: mock LLM returns a tool\_call then complete.



\### Verify



Run:



\* `pytest -q`



Expected:



\* Executor performs one tool call and completes deterministically



---



\## Step 11 — Controller Orchestrator



\### Requirements



\* `core/controller.py`:



&nbsp; \* receives user message

&nbsp; \* calls router

&nbsp; \* calls executor with selected agent

&nbsp; \* updates CDA memory/history

&nbsp; \* returns final assistant message to UI



\### Tests



\* Add an E2E test:



&nbsp; \* `tests/test\_e2e\_filemanager.py`

&nbsp; \* Prepare a temp directory, set it as accessible/default in CDA settings

&nbsp; \* Simulate: “List directory”

&nbsp; \* Expect tool results appear in final output



\### Verify



Run:



\* `pytest -q`



Expected:



\* End-to-end path works with no network



---



\## Step 12 — Tkinter Chat UI + Settings UI



\### Requirements



\* `ui/chat\_ui.py`:



&nbsp; \* chat window with:



&nbsp;   \* text input

&nbsp;   \* send button

&nbsp;   \* chat transcript area

&nbsp; \* calls `Controller.handle\_user\_message(text)` and prints output

\* `ui/settings\_ui.py`:



&nbsp; \* UI to set:



&nbsp;   \* Gemini key

&nbsp;   \* accessible directories (comma-separated or multi-line)

&nbsp;   \* default directory

&nbsp; \* Save settings to `settings/user\_config.json` via config\_loader

&nbsp; \* Update CDA immediately

\* `main.py`:



&nbsp; \* bootstrap CDA

&nbsp; \* load settings

&nbsp; \* instantiate LLM client (mock by default; Gemini if provider set to gemini)

&nbsp; \* instantiate router/executor/controller; store in CDA.runtime\_objects

&nbsp; \* launch UI



\### Verify



Manual non-interactive check is not possible, so add a smoke test:



\* `python -c "import main"` should not crash



Run:



\* `pytest -q`

\* `python -c "import main"`



Expected:



\* All tests pass

\* Import does not crash



---



\## Step 13 — Gemini Provider (Optional Real Calls)



\### Requirements



\* `llm/gemini\_client.py` implements `BaseLLMClient`.

\* Reads Gemini key from CDA settings.

\* Only used if `CDA.settings\["llm\_provider"] == "gemini"`.

\* If key missing: raise a controlled exception with a clear error message (but app must not crash; controller returns error to UI).



\### Verify



Run:



\* `pytest -q`



Expected:



\* Tests still pass (mock default)

\* Gemini client code exists and imports cleanly



---



\## Step 14 — Hardening: Retries + Error Handling + Logging



\### Requirements



\* Add:



&nbsp; \* retry policy in router/executor for invalid JSON (e.g., 2 retries)

&nbsp; \* structured error returns to UI

\* `logging/execution\_logger.py`:



&nbsp; \* minimal file logger to `logs/run.log` (create folder if needed)

&nbsp; \* log router choice and tool calls (no secrets)



\### Verify



Run:



\* `pytest -q`



Expected:



\* Pass

\* Logs produced during tests or e2e test



---



\# Final Deliverables



By completing all steps, the project must provide:



1\. A working Tkinter chat UI

2\. Router + executor agent pipeline

3\. FileManager agent with:



&nbsp;  \* directory listing

&nbsp;  \* file inspection

&nbsp;  \* file reading (PDF supported)

&nbsp;  \* copy/move

&nbsp;  \* NO delete

4\. CDA singleton shared runtime hub

5\. Deterministic unit + e2e tests with mock LLM

6\. Optional Gemini provider integration



---



\# Commands Summary (Codex should run frequently)



\* Install:



&nbsp; \* `pip install -r requirements.txt`

\* Test:



&nbsp; \* `pytest -q`

\* Run:



&nbsp; \* `python main.py`



---



\# Notes for Codex CLI Execution



\* Prefer mock LLM for all automated tests.

\* Do not require user input during tests.

\* Use `tempfile.TemporaryDirectory()` in tests for filesystem operations.

\* Ensure path boundary enforcement always uses normalized absolute paths.



END OF PLAN



