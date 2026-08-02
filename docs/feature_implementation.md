# Deferred Feature Implementation

This document records approved features to be implemented together after the remaining requirements are complete and as part of a coordinated release.

## Generic scheduled prompts, reminders, delivery, and execution history

### Product contract

The scheduler must accept **any ordinary user prompt** and execute it at the requested future time through the same routed agent runtime used for a live conversation. A schedule is not restricted to a catalogue of report or reminder templates.

The `ScheduleManagerAgent` is responsible for turning a request into a safe, self-contained future instruction plus its timing. For example:

| User request | Recurrence saved | Executable prompt saved |
| --- | --- | --- |
| Every Monday at 9 AM, prepare the project status report and send it to the team. | Weekly, Monday, 09:00 | Prepare the current project status report and send it to the configured project-team recipients. |
| On the 1st of every month, create the expense report. | Monthly, day 1, configured time | Create the monthly expense report for the preceding reporting period and save the final file. |
| Tomorrow at 10 AM, send Rahul's resume to the hiring manager. | One-time, resolved date, 10:00 | Locate Rahul's approved resume and send it to the configured hiring-manager recipient. |

The original request is retained for traceability. The refined prompt is the sole prompt sent to the execution runtime. Timing phrases must not remain in the refined prompt. The default scheduled action is therefore `agent_task`: at run time it goes through `ConversationManager`/router/executor with the schedule owner and the scheduled-execution metadata. This preserves all ordinary agent capabilities, including invoking specialised agents and their permitted tools.

`reminder`, `project_status_report`, `expense_report`, and `file_delivery` are convenience action classifications, not an allowlist. They add structured delivery and validation where useful; an unknown/general prompt remains valid as an `agent_task`.

### Explicit execution and delivery model

Replace the implicit current behaviour—run a text prompt, then always send its textual result to the owner's Telegram account—with an explicit job definition. A schedule contains one execution definition and zero or more delivery definitions:

- `job_spec` (JSON): `action_type`, optional target agent/workflow, refined `task_prompt`, structured inputs, output/report expectations, and declared attachment references.
- `delivery_spec` (JSON array): recipient IDs or validated channel addresses, channel (`telegram`, `whatsapp`, `desktop`; email/webhook may be added later), message template, attachment policy, and send condition (`always`, `on_success`, `on_failure`, `manual_approval`).
- `security_spec` (JSON): data sensitivity, authorised-recipient policy, whether approval is required, and an audit reason for sensitive sends.
- `retry_spec` (JSON): maximum attempts, backoff, execution timeout, delivery retry policy, and missed-run policy (`skip`, `run_once_on_recovery`, `catch_up`).

Do not infer attachments by scanning agent text for Windows paths. Agents/workflows must return explicit structured attachment references. Existing text-only schedules are migrated as `agent_task` schedules; their current owner-Telegram notification is retained only as a documented legacy/default delivery setting until each is edited.

### Persistence and migration

Extend the schema in `apps/das_core/core/db_schema.py` and provide additive SQLite migrations for existing databases:

- Add to `Schedules`: `schedule_mode` (`once` or `recurring`), `run_at` for one-time runs, `end_at`, `job_spec`, `delivery_spec`, `security_spec`, `retry_spec`, `last_run_id`, `failure_count`, `paused_at`, and `completed_at`.
- Preserve current fields during migration (`nl_request`, `task_prompt`, cadence fields, `timezone`, owner, and status) for backwards compatibility. `schedule_type='other'` remains an internal interval representation only; it must never be exposed as the primary UI label.
- Create `ScheduleRuns`: immutable run ID, schedule ID, attempt number, idempotency key, claimed/started/finished timestamps, status (`queued`, `running`, `succeeded`, `failed`, `cancelled`, `skipped`), refined prompt snapshot, result summary, full error text, generated attachment metadata, next retry time, and correlation/conversation ID.
- Create `ScheduleDeliveries`: run ID, delivery index, channel, recipient reference, attempt number, timestamps, status, provider response identifier, redacted error text, and attachment metadata.
- Add indexes for due-job lookup, schedule/run lookup, newest-first run history, and pending retries. Use foreign keys where the existing database configuration supports them.
- Backfill legacy rows with a valid `job_spec`; do not delete or alter existing schedule prompts. Migration tests must cover pre-existing databases.

### ScheduleManagerAgent requirements

Update `apps/das_core/agents/schedule_manager/schedule_manager.prompt`, `apps/das_core/core/scheduler_agent.py`, scheduler tools, and metadata so the agent follows this flow:

1. Split a multi-intent user message into separate schedule intents.
2. Extract and validate timing, timezone, one-time vs recurring state, end condition, and the actual future work.
3. Create a concise title, preserve the original request, and generate a clear future-tense-independent executable prompt. It must include all discoverable business context, but never recurrence wording.
4. Classify the action if useful; retain generic `agent_task` if no specialised classification applies.
5. Resolve declared recipients, channels, attachment/document references, and approval needs. Ask for clarification rather than guessing a recipient, file, location, time, or sensitive-data permission.
6. Display/return a readable preview before saving whenever an external message, file, or sensitive document will be sent. The preview states what runs, when, recipients, channel, attachments, and retry/failure notification policy.
7. Call validated schedule creation exactly once; do not create duplicates if the model loop repeats.

Natural-language parser requirements include `tomorrow`, explicit dates, once-only schedules, every N minutes/hours, daily, selected weekdays, weekly, monthly, and timezone phrases. A one-time schedule must transition to `completed` after a successful run and must not calculate another run.

### Scheduler runtime requirements

Refactor `apps/das_core/core/scheduler_service.py` into a durable dispatcher while preserving `ConversationManager` as the agent-task execution path:

1. Atomically claim each due schedule/run before execution, so concurrent pollers or restarts cannot execute it twice.
2. Create the `ScheduleRuns` record before invoking an agent. Execute `job_spec.task_prompt` with the existing scheduled metadata plus run and correlation IDs.
3. Capture structured result text and declared attachments. Generated reports must be written only to approved output locations.
4. Evaluate the delivery policy and dispatch through common channel adapters. Telegram text/documents and WhatsApp text/files are initial adapters; desktop notifications are added when the desktop shell supports them.
5. Persist a delivery attempt for every recipient/channel. A partial failure is visible in history and retried according to `retry_spec`; it must not resend successful deliveries.
6. Finalise the run, calculate the next due time using the schedule timezone, and transition one-time schedules to completed only after the configured success condition.
7. On an unrecoverable failure, store the complete error, update schedule health/failure state, and notify the configured owner/failure recipients. Never silently drop a due job.

Reliability safeguards are mandatory: idempotency keys per intended run and delivery, configurable bounded retries/backoff, timeouts, restart recovery, a clear missed-run policy, per-schedule concurrency control, and runtime logs without secrets or document contents. “Without fail” means durable handling and visible/escalated recovery of unavoidable provider/LLM/tool failures; it cannot promise that an unavailable external channel will succeed instantly.

### Security and document-delivery requirements

Resumes, IDs, and similar employee documents are sensitive. Before implementation, enforce the following:

- Only users/agents with the required role/tool permission may create, change, execute, or test sensitive schedules.
- Resolve recipient identities from trusted user/channel mappings or explicit validated contact records; do not let the agent invent recipients.
- Require a named approved document reference or file identifier. Validate its resolved path against the application file-access policy.
- Require explicit approval before a sensitive external delivery unless an administrator-configured policy permits the exact document class and recipient group.
- Record creator, editor, approver, recipient, file metadata, execution, and delivery events in the audit trail. Do not log document content, tokens, or unredacted secrets.
- Validate Telegram and WhatsApp delivery services individually and return per-recipient success/failure rather than treating a provider call as universally successful.

### API and tools

Maintain existing scheduler endpoints while adding typed API contracts for `job_spec`, delivery configuration, preview/validation, pause/resume, schedule run history, single-run details, and retry. Enforce ownership and administrator checks consistently on list/detail/run/history operations; users must not read another owner's prompt, documents, or errors.

Extend `apps/das_core/tools/scheduler_tools.py` with structured create/update/preview and run-history tools. Retain the existing CRUD tool names as compatibility wrappers. Update `apps/das_core/tools/tool_metadata_registry.py` and tool schemas/descriptions so agents receive clear parameter definitions.

Use the existing Telegram tools/service and WhatsApp tools/service to implement adapters; do not duplicate outbound-provider logic in the scheduler. Add a normalised adapter interface so future email/webhook delivery can be introduced without modifying scheduling semantics.

### Scheduler UI requirements

Update the web scheduler interface and the desktop scheduler UI in parallel so both expose the same user-facing concepts.

The current editor is not acceptable as a primary creation experience: it exposes raw database fields such as `Type: other`, `Interval`, `Weekday: 0`, and `Days Of Week: 0,1,2,3,4`. These are internal implementation values and must be hidden behind an optional administrator-only advanced section, if shown at all.

The normal **Create Schedule** experience must have:

- A natural-language request field and **Analyse schedule** action as the primary route. The ScheduleManagerAgent returns a reviewable proposal.
- **Original Request** and **Task Prompt** displayed on one row as two equal columns to save vertical space. Original Request is retained/readable; Task Prompt is the agent-refined future instruction and can be edited before save.
- Clear recurrence choices: **Once**, **Every interval**, **Daily**, **Selected weekdays**, **Weekly**, and **Monthly**.
- Conditional human-friendly controls only for the selected choice:
  - Once: date picker and time picker.
  - Every interval: “Repeat every [number] [minutes/hours]”.
  - Daily: time picker.
  - Selected weekdays: toggle buttons/checkboxes labelled Mon–Sun plus time picker.
  - Weekly: labelled weekday selector plus time picker.
  - Monthly: “On day [1–31] of every month” plus time picker.
- Plain labels: **Repeat**, **Time**, **Selected days**, **Monthly day**, **Time zone**, **What will happen**, **Send result to**, and **Attachments**.
- A live readable sentence, for example: “Runs every weekday at 10:30 AM (Asia/Kolkata).”
- Delivery/recipient/attachment controls for structured schedules, including a clear approval requirement for sensitive files.
- A pre-save confirmation preview for external sends, with an explicit test-run option that does not alter recurrence unexpectedly.

Add a third primary scheduler tab, **Schedule Logs** (alongside Schedule List and Create/Edit). It must show all `ScheduleRuns`, newest first, with schedule title/ID, start/finish timestamp in the viewer's timezone, status, duration, result summary, generated attachments, delivery status, and visible error summary. Users can filter by schedule/status/date, open a run to see full redacted error and per-channel delivery attempts, and retry an eligible failed run. The list must distinguish “agent execution succeeded but delivery failed” from “agent execution failed.”

### Implementation order and verification

1. Define typed job/delivery/run models and additive schema migration; write migration and backwards-compatibility tests.
2. Update scheduler parsing, ScheduleManagerAgent prompt, tools, API validation, and preview contract. Test all supported recurrence phrases, timezones, multi-intent prompts, and ambiguous recipient/file cases.
3. Implement atomic claiming, run records, idempotency, retries, one-time completion, and structured agent results in `SchedulerService`. Test restart, duplicate poller, timeout, missed-run, and partial-failure cases.
4. Implement and test the channel-adapter layer for Telegram and WhatsApp text/files, including attachment path validation and independent recipient outcomes.
5. Apply sensitive-document permissions, approval, recipient validation, and audit logging before enabling automated ID/resume delivery.
6. Replace both scheduler editors with the human-oriented recurrence UI and add the Schedule Logs tab/details/retry UI. Verify the two-column Original Request/Task Prompt layout at desktop and narrow responsive widths.
7. Migrate legacy schedules, expose their status, and verify a legacy schedule still executes once through the normal routed runtime.
8. Run unit, integration, and manual end-to-end tests for reminders, generic prompts, agent delegation, report generation, file delivery, delivery retries, logs, and access-control boundaries.

The feature is complete only when a user can schedule an arbitrary prompt, understand exactly when and what will run, have the ScheduleManagerAgent produce a self-contained execution prompt, reliably inspect each execution and delivery in newest-first logs, and receive clear recovery/error visibility for every failed attempt.

## Google Drive integration (upload and download MVP)

### Status and scope

No Google Drive support currently exists in the application: there are no Drive tools, OAuth handlers, dependencies, settings fields, or UI tabs. Add an admin-configured Google Drive integration whose first release is deliberately limited to uploading local files and downloading Drive files. Folder browsing, search, sharing, deletion, moving, and Google Workspace document export are out of scope for this MVP.

### Authentication and security design

- Use Google OAuth 2.0 authorization-code flow with refresh tokens; do not ask users to paste access tokens or store a Google password.
- Configure a Google Cloud OAuth client for the deployment and register the API gateway callback URL, for example `https://<host>/integrations/google-drive/oauth/callback`.
- Request the least-privilege `https://www.googleapis.com/auth/drive.file` scope. The integration should create and use an application-managed Drive folder; this permits upload/download of files created by the application without broad access to the user's whole Drive.
- Store the client secret and refresh token outside `user_config.json` and outside the web client. Use the application secret store or an encrypted, permissions-restricted server-side credential file. Never return either value from `GET /settings`, logs, tool output, or error messages.
- Refresh access tokens server-side only. On revocation, invalid grant, or expiry that cannot be refreshed, mark the integration disconnected and require the admin to reconnect.
- Restrict setup, connect, disconnect, and test operations to administrators. Tool calls remain subject to the existing agent/tool permissions and filesystem allowlists.

### Settings tab

Add a **Google Drive** entry to the web application's Settings tab list in `apps/ui_web/src/App.tsx`. It should show:

- connection state, connected Google account (when available), configured Drive folder name/ID, and last successful test time;
- client ID and optional Drive folder name as editable configuration fields; the client secret is entered only to save it and is never rendered after saving;
- **Connect Google Drive** (starts OAuth), **Disconnect**, and **Test connection** actions; and
- a concise note that the MVP can access only files managed by this application.

Extend `apps/ui_web/src/api.ts` with typed requests for the connection status and OAuth actions. Add protected API gateway routes under `/integrations/google-drive` for status, connect/start, callback, disconnect, and test. The callback must validate a signed, short-lived OAuth `state` value before exchanging the authorization code.

Non-secret settings such as `google_drive_enabled`, `google_drive_client_id`, and `google_drive_folder_id` may be persisted through the existing settings API. The API must mask or omit any secret fields on reads and prevent non-admin writes.

### Tool design

Add `apps/das_core/tools/google_drive_tools.py`, registered through the existing tool registry and metadata registry, with two initial tools:

| Tool | Inputs | Result |
| --- | --- | --- |
| `upload_to_google_drive` | approved local `source_path`, optional destination filename | Drive file ID, filename, MIME type, size, and Drive web link |
| `download_from_google_drive` | Drive `file_id`, approved local `destination_path`, optional overwrite flag (default `false`) | saved local path, filename, MIME type, and byte count |

Both tools must validate file paths against the existing accessible-directory policy, stream content rather than loading it all into memory, enforce configurable size limits, and return clear errors for a missing connection, inaccessible file, unsupported Google-native document, quota failure, and name collision. Uploads go to the application-managed Drive folder. Downloads are limited to files the integration manages; the MVP does not accept public URLs or search by filename.

Use the official Google API Python client libraries (`google-api-python-client`, `google-auth`, and `google-auth-oauthlib`) and resumable uploads/downloads where appropriate. Register tool metadata, descriptions, JSON schemas, example calls, and agent visibility so the existing Tools settings page can manage them.

### Implementation sequence and acceptance checks

1. Add dependencies, a server-side credential store, configuration validation, and Google Drive service wrapper with token refresh/error handling.
2. Build the protected OAuth/API routes and the Google Drive Settings tab; verify a successful connect, a rejected invalid OAuth state, a connection test, and a disconnect that removes stored credentials.
3. Implement and register the upload/download tools, including path/size/collision validation and structured audit logs that contain IDs and metadata but no tokens or file contents.
4. Add unit tests with mocked Google API calls for OAuth state validation, token masking, upload success/failure, download success/failure, path traversal rejection, size-limit rejection, and overwrite behavior. Add a manual Google test account checklist for upload followed by download and byte-for-byte verification.

The feature is complete when an administrator can connect one Google account from Settings, an authorized agent can upload an allowed local file to the managed Drive folder and receive its ID/link, and can download that managed file to an allowed local destination without exposing credentials.

## Temporary external download links for generated files

### Goal

Allow a user to share a generated output file through a temporary URL hosted on the VPS. The link should normally remain valid for a configurable period, such as one hour or one day, and should be revocable before it expires.

### Preferred implementation

Keep all normal application and generated files private. When a share is requested, create a database-backed share record and return a public application URL such as:

`https://<host>/download/<cryptographically-random-token>`

The download endpoint must:

- validate that the token exists, has not expired, and has not been revoked;
- confirm that the requested file resolves inside the configured generated-file storage root;
- return the file as an attachment, without exposing its server path;
- record download activity; and
- return `404` or `410` for invalid, expired, or revoked links.

Store at least the source file identifier/path, token digest, original filename, creator, creation time, expiry time, revoked flag, and download count. Use a cryptographically secure random token; do not use a predictable ID.

### VPS public-folder option

For ordinary, non-sensitive reports, a simplified implementation may copy the file to a dedicated VPS download folder and give it a name such as:

`<uuidv4>_<sanitized-original-filename>.pdf`

Expose only this folder through Nginx. It must be outside the source/application tree, have directory indexing disabled, prevent script execution, and force a download response. A scheduled cleanup task should remove expired files every 5-10 minutes, based on stored expiry metadata.

The GUID filename makes guessing impractical, but it is not authorization: anyone who obtains the URL can use it until it expires. Therefore, use the preferred token-validation endpoint for confidential files, links that need immediate revocation, auditing, download limits, or recipient restrictions.

### Optional controls

- Configurable lifetime (for example, 1 hour and 24 hours).
- Owner/admin revocation.
- Maximum download count and file-size limits.
- Login or email/OTP verification for sensitive documents.
- Retention/cleanup audit records.

### Runtime trace sharing

If runtime traces are later shared externally, create a sanitized, read-only snapshot through the same temporary-link mechanism. Never expose raw live logs without redaction: they may contain prompts, tool inputs/outputs, local paths, user data, or secrets.
