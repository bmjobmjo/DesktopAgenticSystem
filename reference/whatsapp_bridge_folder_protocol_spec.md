# DAS WhatsApp Bridge Shared Folder Protocol

Version: 1.0-draft
Date: 2026-03-15
Status: Proposed

## 1. Purpose

This document defines a simple file-system based integration between:

- DAS (Desktop Agentic System)
- A vendor-built WhatsApp Bridge

This protocol is intended for:

- the same machine
- a trusted LAN
- a reliable shared network folder

It is designed to be simpler than a WebSocket integration.

## 2. Core Idea

The WhatsApp Bridge and DAS exchange messages using a shared folder.

- The bridge writes inbound WhatsApp messages into `received`
- DAS reads from `received`
- DAS writes outbound messages into `send`
- The bridge reads from `send`
- After successful processing, message folders are moved to `backup`
- Failed items are moved to `error`

Each message is represented as one folder containing:

- `message.json`
- optional `attachments/` files

## 3. Shared Root Folder

One shared root folder must be configured on both sides.

Example:

`D:\DAS_WhatsApp_Exchange`

Recommended subfolders:

```text
<root>\
  received\
  send\
  working\
  backup\
  error\
  staging\
```

Meaning:

- `received`:
  Bridge writes inbound messages here for DAS to consume.
- `send`:
  DAS writes outbound messages here for the bridge to consume.
- `working`:
  Consumer moves a message folder here while processing it.
- `backup`:
  Successfully processed message folders are archived here.
- `error`:
  Failed message folders are moved here.
- `staging`:
  Writer creates message folders here first, then moves them into final location when complete.

## 4. Folder Naming

### 4.1 Mobile Number Folder

Under `received` and `send`, a mobile-number folder is created for each user.

Example:

```text
received\919876543210\
send\919876543210\
```

Rules:

- use digits only in folder names
- do not include `+`
- store the full E.164 number inside `message.json`

Example:

- folder name: `919876543210`
- JSON value: `+919876543210`

### 4.2 Message Folder

Each message must have a unique message folder name.

Recommended format:

`YYYYMMDDTHHMMSSZ_<random8>`

Example:

`20260315T143055Z_a13f20c9`

This avoids collisions and keeps folders sortable by time.

## 5. Folder Structure Per Message

Example inbound message:

```text
received\
  919876543210\
    20260315T143055Z_a13f20c9\
      message.json
      attachments\
        invoice.pdf
        photo.jpg
```

Example outbound message:

```text
send\
  919876543210\
    20260315T143115Z_7be102d4\
      message.json
      attachments\
        report.pdf
```

Attachments are optional.

## 6. `message.json` Format

### 6.1 Common Rules

- JSON must be UTF-8 encoded
- line endings may be Windows or Unix style
- text fields must be plain text
- attachment file names in JSON must match actual files in `attachments`

### 6.2 Inbound Message Written by Bridge

File: `received\<mobile>\<message_folder>\message.json`

Example:

```json
{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "inbound",
  "message_id": "20260315T143055Z_a13f20c9",
  "provider": "whatsapp",
  "bridge_id": "whatsapp-main",
  "provider_message_id": "wamid-123456",
  "sender_id": "+919876543210",
  "sender_folder": "919876543210",
  "recipient_id": "+911234567890",
  "timestamp_utc": "2026-03-15T14:30:55Z",
  "text": "show my attendance for this week",
  "attachments": [
    {
      "file_name": "invoice.pdf",
      "relative_path": "attachments/invoice.pdf",
      "mime_type": "application/pdf"
    }
  ]
}
```

Required fields for inbound:

- `protocol`
- `direction`
- `message_id`
- `provider`
- `bridge_id`
- `sender_id`
- `sender_folder`
- `timestamp_utc`
- `text`
- `attachments`

Optional fields for inbound:

- `provider_message_id`
- `recipient_id`

### 6.3 Outbound Message Written by DAS

File: `send\<mobile>\<message_folder>\message.json`

Example:

```json
{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "outbound",
  "message_id": "20260315T143115Z_7be102d4",
  "outbound_id": "das-out-000001",
  "sender_id": "+911234567890",
  "recipient_id": "+919876543210",
  "recipient_folder": "919876543210",
  "timestamp_utc": "2026-03-15T14:31:15Z",
  "text": "Your attendance this week is 5 out of 5.",
  "attachments": []
}
```

Required fields for outbound:

- `protocol`
- `direction`
- `message_id`
- `recipient_id`
- `recipient_folder`
- `timestamp_utc`
- `text`
- `attachments`

Optional fields for outbound:

- `outbound_id`
- `sender_id`

## 7. Attachment Rules

If a message has attachments:

- create an `attachments` subfolder
- place all files there
- list them in `message.json`

Attachment file names should be preserved where possible.
If the original provider name is unsafe for the file system, sanitize it before writing.

## 8. Write Rules

To avoid partial reads, the writer must not create message folders directly inside `received` or `send`.

### 8.1 Correct Write Sequence

For every message:

1. Create the message folder under `staging`
2. Write `message.json`
3. Write all attachments
4. Verify all files are complete
5. Move the whole message folder to final location under `received` or `send`

Example:

```text
staging\received\919876543210\20260315T143055Z_a13f20c9\
```

then move to:

```text
received\919876543210\20260315T143055Z_a13f20c9\
```

Important:

- The move from `staging` to the final folder should happen on the same disk/share.
- The final folder should appear only after the message is fully written.

## 9. Read and Process Rules

### 9.1 DAS Reading Inbound Messages

DAS must:

1. Poll `received`
2. Find a message folder
3. Move it to `working`
4. Read and validate `message.json`
5. Process the message
6. Move it to `backup` on success
7. Move it to `error` on failure

Example move:

```text
received\919876543210\20260315T143055Z_a13f20c9\
```

to:

```text
working\received\919876543210\20260315T143055Z_a13f20c9\
```

then on success:

```text
backup\received\919876543210\20260315T143055Z_a13f20c9\
```

### 9.2 Bridge Reading Outbound Messages

The bridge must:

1. Poll `send`
2. Find a message folder
3. Move it to `working`
4. Read and validate `message.json`
5. Deliver the message to WhatsApp/provider
6. Move it to `backup` on success
7. Move it to `error` on failure

Example move:

```text
send\919876543210\20260315T143115Z_7be102d4\
```

to:

```text
working\send\919876543210\20260315T143115Z_7be102d4\
```

then on success:

```text
backup\send\919876543210\20260315T143115Z_7be102d4\
```

## 10. DAS-Side Business Rules

When DAS reads an inbound message, DAS must:

1. validate the JSON structure
2. normalize and verify the sender number
3. resolve the sender to an internal DAS user
4. create or resume a DAS chat session
5. process the message
6. create outbound message folders in `send` if a reply is needed

### 10.1 Sender-to-User Mapping

Recommended DAS resolution order:

1. look up a channel mapping for:
   - provider = `whatsapp`
   - sender_id = mobile number
2. if not found, optionally look up `Users.mobile_number`
3. if still not found, treat as unknown sender

### 10.2 Unknown Sender

If the sender is not known in DAS:

- DAS may ignore the message
- or DAS may create an outbound message to that sender such as:
  - `Your number is not registered in this system.`

This behavior is a DAS configuration choice.

## 11. Bridge-Side Business Rules

The bridge vendor is responsible for:

- connecting to WhatsApp or the chosen provider
- reading inbound provider messages
- downloading provider media if required
- writing valid inbound message folders into `received`
- reading outbound message folders from `send`
- sending those messages to WhatsApp/provider
- moving processed items to `backup` or `error`

The bridge vendor is not responsible for:

- DAS user lookup
- DAS session management
- DAS business logic
- DAS agent orchestration

## 12. Polling Rules

Recommended polling interval:

- every 1 to 2 seconds

Both DAS and the bridge should:

- continue polling forever while running
- skip empty folders quickly
- log failures
- recover automatically after temporary file/share errors

## 13. Duplicate Handling

The bridge should not intentionally write the same provider message more than once.

DAS should still protect against duplicates using:

- `provider_message_id`, if present
- otherwise `sender_id + timestamp_utc + text`, if necessary

If DAS detects a duplicate inbound message:

- it should archive it without processing again

## 14. Error Handling

If a message cannot be processed, move the message folder to `error`.

Each failed message folder should include an additional file:

`error.txt`

Example contents:

```text
2026-03-15T14:31:20Z
USER_NOT_MAPPED
Sender +919876543210 is not registered in DAS
```

Recommended error codes:

- `INVALID_JSON`
- `INVALID_MOBILE_NUMBER`
- `USER_NOT_MAPPED`
- `ATTACHMENT_MISSING`
- `DELIVERY_FAILED`
- `INTERNAL_ERROR`

## 15. Backup and Retention

Processed items should not be deleted immediately.

Recommended retention:

- `backup`: keep 7 to 30 days
- `error`: keep until reviewed or manually cleaned

Optional cleanup job:

- delete `backup` items older than retention policy

## 16. Minimal Acceptance Requirements for Vendor

The bridge implementation is acceptable when it can:

- monitor WhatsApp/provider for inbound messages
- write inbound messages into `received` exactly in the format defined here
- include attachments using the defined `attachments` folder
- monitor `send` for outbound messages
- send outbound messages to WhatsApp/provider
- move processed items to `backup`
- move failed items to `error`
- write `error.txt` on failures
- normalize phone numbers consistently

## 17. Example End-to-End Flow

### 17.1 Inbound User Message

1. User sends WhatsApp message to business number
2. Bridge receives the message
3. Bridge writes:

```text
received\919876543210\20260315T143055Z_a13f20c9\
  message.json
```

4. DAS detects the folder
5. DAS moves it to `working`
6. DAS processes it
7. DAS creates a reply in:

```text
send\919876543210\20260315T143115Z_7be102d4\
  message.json
```

8. Bridge detects the outbound folder
9. Bridge sends the reply to WhatsApp
10. Bridge moves the outbound folder to `backup`
11. DAS moves the inbound folder to `backup`

## 18. Recommended Configuration Values

The vendor bridge should support configuration for:

- shared root folder path
- polling interval
- WhatsApp/provider credentials
- maximum attachment size
- log folder

DAS should support configuration for:

- shared root folder path
- polling interval
- unknown sender behavior
- backup retention policy

## 19. Summary

This protocol keeps the integration intentionally simple:

- Bridge writes inbound messages to `received`
- DAS writes outbound messages to `send`
- Each message is a folder with `message.json` and optional attachments
- `staging`, `working`, `backup`, and `error` make the exchange reliable and easy to debug

This document is the implementation contract for both DAS and the WhatsApp Bridge vendor.
