const fs = require("fs");
const path = require("path");
const pino = require("pino");
const QRCode = require("qrcode");
const { postInbound } = require("./webhook");

let baileysLib = null;
try {
  baileysLib = require("@whiskeysockets/baileys");
} catch (_) {
  baileysLib = null;
}

class WhatsAppGatewayClient {
  constructor(config) {
    this.config = config;
    this.logger = pino({ level: config.logLevel || "info" });
    this.sock = null;
    this.isReady = false;
    this.lastQrDataUrl = "";
    this.lastError = "";
    this.sessionJid = "";
    this._starting = false;
    this._manualDisconnect = false;
    this._reconnectTimer = null;
    this._reconnectAttempts = 0;
    this._baseBackoffMs = 1000;
    this._maxBackoffMs = 30000;
    this._watchdogTimer = null;
    this._lastConnectionUpdateTs = 0;
  }

  async start() {
    if (this._starting) return;
    if (this.isReady && this.sock) return;
    this._starting = true;
    // Fresh start attempts should not inherit manual-disconnect intent.
    this._manualDisconnect = false;
    this._clearReconnectTimer();
    this._startWatchdog();
    if (!baileysLib) {
      this.lastError = "Baileys package is not available. Run npm install in whatsapp-gateway.";
      this.logger.error(this.lastError);
      this._starting = false;
      return;
    }

    const {
      makeWASocket,
      useMultiFileAuthState,
      DisconnectReason,
      fetchLatestBaileysVersion,
      downloadMediaMessage
    } = baileysLib;

    const authDir = path.resolve(this.config.authDir || "./auth_state");
    fs.mkdirSync(authDir, { recursive: true });

    const { state, saveCreds } = await useMultiFileAuthState(authDir);
    const { version } = await fetchLatestBaileysVersion();

    try {
      this._teardownSocket(false);
      this.sock = makeWASocket({
        auth: state,
        version,
        logger: this.logger.child({ module: "baileys" })
      });

      this.sock.ev.on("creds.update", async () => {
        try {
          await saveCreds();
        } catch (err) {
          this.logger.warn({ err: err?.message }, "Failed saving Baileys creds");
        }
      });

      this.sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;
      this._lastConnectionUpdateTs = Date.now();

      if (qr) {
        try {
          this.lastQrDataUrl = await QRCode.toDataURL(qr);
        } catch (err) {
          this.logger.error({ err: err?.message }, "Failed to generate QR data URL");
        }
      }

      if (connection === "open") {
        this.isReady = true;
        this.lastError = "";
        this.lastQrDataUrl = "";
        this.sessionJid = this.sock?.user?.id || "";
        this._reconnectAttempts = 0;
        this._clearReconnectTimer();
        this.logger.info("WhatsApp connection open");
      }

      if (connection === "close") {
        this.isReady = false;
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const isRestartRequired =
          statusCode === DisconnectReason.restartRequired || statusCode === 515;
        const isLogoutLike =
          statusCode === DisconnectReason.loggedOut || statusCode === 401 || statusCode === 405;
        // Always reconnect on restart-required (515), even if a stale manual flag is set.
        const shouldReconnect = isRestartRequired || (!isLogoutLike && !this._manualDisconnect);
        this.lastError = `Connection closed (${statusCode || "unknown"})`;
        this.logger.warn(
          {
            statusCode,
            shouldReconnect,
            isRestartRequired,
            isLogoutLike,
            manualDisconnect: this._manualDisconnect
          },
          "WhatsApp connection closed"
        );
        this._teardownSocket(false);
        if (shouldReconnect) {
          this._scheduleReconnect("connection_close");
        } else if (this._manualDisconnect) {
          this._manualDisconnect = false;
        }
      }
      });

      this.sock.ev.on("messages.upsert", async (event) => {
      const messages = event?.messages || [];
      for (const msg of messages) {
        try {
          if (!msg?.message || msg.key?.fromMe) continue;

          const text = this._extractText(msg);
          const files = await this._extractInboundFiles(msg, downloadMediaMessage);
          const effectiveText = text || (files.length ? "Process the attached files." : "");
          if (!effectiveText && !files.length) continue;

          const payload = {
            provider: "whatsapp",
            interface: "WhatsApp",
            channel_user_id: msg?.key?.participant || msg?.key?.remoteJid || "",
            session_id: msg?.key?.remoteJid || "",
            message_id: msg?.key?.id || "",
            text: effectiveText,
            files,
            timestamp: msg?.messageTimestamp || Date.now()
          };

          this.logger.info(
            {
              from: payload.channel_user_id,
              message_id: payload.message_id,
              text_preview: effectiveText.slice(0, 120),
              files: files.length
            },
            "Inbound WhatsApp message received"
          );

          await postInbound(this.config.webhookUrl, this.config.webhookSecret, payload, this.logger);
        } catch (err) {
          this.logger.error({ err: err?.message }, "Failed processing inbound message");
        }
      }
      });
    } catch (err) {
      this.lastError = err?.message || String(err);
      this.logger.error({ err: this.lastError }, "Failed to initialize Baileys socket");
      this._teardownSocket(false);
      if (!this._manualDisconnect) {
        this._scheduleReconnect("start_error");
      }
    } finally {
      this._starting = false;
    }
  }

  _clearReconnectTimer() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  _scheduleReconnect(reason) {
    if (this._manualDisconnect) return;
    if (this._reconnectTimer) return;

    const expDelay = this._baseBackoffMs * Math.pow(2, this._reconnectAttempts);
    const baseDelay = Math.min(this._maxBackoffMs, expDelay);
    const jitter = Math.floor(Math.random() * 500);
    const delay = Math.max(this._baseBackoffMs, baseDelay + jitter);
    this._reconnectAttempts += 1;

    this.logger.info(
      { reason, delay_ms: delay, attempt: this._reconnectAttempts },
      "Scheduling WhatsApp reconnect"
    );
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.start().catch((err) => {
        this.lastError = err?.message || String(err);
        this.logger.error({ err: this.lastError }, "Reconnect attempt failed");
        this._scheduleReconnect("reconnect_error");
      });
    }, delay);
  }

  _startWatchdog() {
    if (this._watchdogTimer) return;
    this._watchdogTimer = setInterval(() => {
      if (this._manualDisconnect || this._starting) return;
      const hasSocket = !!this.sock;
      const wsState = this.sock?.ws?.readyState;
      const wsClosed = typeof wsState === "number" ? wsState >= 2 : false;
      const stale =
        !this.isReady &&
        this._lastConnectionUpdateTs > 0 &&
        Date.now() - this._lastConnectionUpdateTs > 120000;

      if (!hasSocket || wsClosed || stale) {
        this.logger.warn(
          { hasSocket, wsState, stale, isReady: this.isReady },
          "Watchdog detected unstable socket; attempting recovery"
        );
        this._teardownSocket(false);
        this._scheduleReconnect("watchdog");
      }
    }, 30000);
  }

  _teardownSocket(resetManualFlag) {
    const socket = this.sock;
    this.sock = null;
    if (!socket) {
      if (resetManualFlag) this._manualDisconnect = false;
      return;
    }
    try {
      if (socket.ev && typeof socket.ev.removeAllListeners === "function") {
        socket.ev.removeAllListeners();
      }
    } catch (_) {}
    try {
      if (socket.ws && typeof socket.ws.close === "function") {
        socket.ws.close();
      }
    } catch (_) {}
    if (resetManualFlag) this._manualDisconnect = false;
  }

  _extractText(msg) {
    const m = msg?.message || {};
    return (
      m?.conversation ||
      m?.extendedTextMessage?.text ||
      m?.imageMessage?.caption ||
      m?.videoMessage?.caption ||
      ""
    ).trim();
  }

  _ensureMediaDir() {
    const mediaDir = path.resolve(this.config.mediaDir || "./inbound_media");
    fs.mkdirSync(mediaDir, { recursive: true });
    return mediaDir;
  }

  _mediaInfoFromMessage(msg) {
    const m = msg?.message || {};
    if (m?.documentMessage) {
      const d = m.documentMessage;
      return {
        kind: "document",
        mimetype: d.mimetype || "application/octet-stream",
        originalName: d.fileName || "",
        caption: d.caption || ""
      };
    }
    if (m?.imageMessage) {
      const d = m.imageMessage;
      return {
        kind: "image",
        mimetype: d.mimetype || "image/jpeg",
        originalName: "",
        caption: d.caption || ""
      };
    }
    if (m?.videoMessage) {
      const d = m.videoMessage;
      return {
        kind: "video",
        mimetype: d.mimetype || "video/mp4",
        originalName: "",
        caption: d.caption || ""
      };
    }
    if (m?.audioMessage) {
      const d = m.audioMessage;
      return {
        kind: "audio",
        mimetype: d.mimetype || "audio/ogg",
        originalName: "",
        caption: ""
      };
    }
    return null;
  }

  _extFromMime(mime) {
    const map = {
      "application/pdf": ".pdf",
      "text/plain": ".txt",
      "image/jpeg": ".jpg",
      "image/png": ".png",
      "video/mp4": ".mp4",
      "audio/ogg": ".ogg",
      "audio/mpeg": ".mp3",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"
    };
    return map[String(mime || "").toLowerCase()] || "";
  }

  async _extractInboundFiles(msg, downloadMediaMessage) {
    const info = this._mediaInfoFromMessage(msg);
    if (!info) return [];
    if (typeof downloadMediaMessage !== "function") return [];
    if (!this.sock) return [];

    try {
      const buffer = await downloadMediaMessage(
        msg,
        "buffer",
        {},
        { logger: this.logger, reuploadRequest: this.sock.updateMediaMessage }
      );
      if (!buffer || !Buffer.isBuffer(buffer) || buffer.length === 0) return [];

      const mediaDir = this._ensureMediaDir();
      const extFromName = path.extname(info.originalName || "");
      const ext = extFromName || this._extFromMime(info.mimetype) || "";
      const base = `${Date.now()}_${msg?.key?.id || "msg"}_${info.kind}`;
      const filename = `${base}${ext}`;
      const absPath = path.join(mediaDir, filename);
      fs.writeFileSync(absPath, buffer);

      return [
        {
          path: absPath,
          name: info.originalName || filename,
          mime_type: info.mimetype,
          kind: info.kind,
          size_bytes: buffer.length
        }
      ];
    } catch (err) {
      this.logger.warn({ err: err?.message }, "Failed to extract inbound media");
      return [];
    }
  }

  async sendText(to, text) {
    if (!this.sock) {
      throw new Error("WhatsApp socket not initialized");
    }
    if (!to || !text) {
      throw new Error("Both 'to' and 'text' are required");
    }
    const res = await this.sock.sendMessage(to, { text });
    return {
      success: true,
      id: res?.key?.id || "",
      to
    };
  }

  async disconnect() {
    this._manualDisconnect = true;
    this._clearReconnectTimer();
    try {
      this._teardownSocket(false);
    } catch (err) {
      this.logger.warn({ err: err?.message }, "socket close reported an error");
    }

    this.isReady = false;
    this.sessionJid = "";
    this.lastQrDataUrl = "";
    this.lastError = "Disconnected by user";
    this.sock = null;
    // Force fresh pairing by clearing persisted auth state.
    try {
      const authDir = path.resolve(this.config.authDir || "./auth_state");
      fs.rmSync(authDir, { recursive: true, force: true });
      fs.mkdirSync(authDir, { recursive: true });
    } catch (err) {
      this.logger.warn({ err: err?.message }, "Failed to reset auth state directory");
    }
    // Re-open a fresh session so QR can be generated immediately.
    setTimeout(() => {
      this.start().catch((err) => {
        this.lastError = err?.message || String(err);
        this.logger.error({ err: this.lastError }, "Failed to restart after disconnect");
      });
    }, 300);
    return { success: true };
  }

  getStatus() {
    return {
      connected: this.isReady,
      has_qr: !!this.lastQrDataUrl,
      qr_data_url: this.lastQrDataUrl,
      session_jid: this.sessionJid,
      last_error: this.lastError
    };
  }
}

module.exports = {
  WhatsAppGatewayClient
};
