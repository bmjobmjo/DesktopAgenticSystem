require("dotenv").config();
const express = require("express");
const { WhatsAppGatewayClient } = require("./baileys-client");

const HOST = process.env.HOST || "127.0.0.1";
const PORT = Number(process.env.PORT || 5715);

const app = express();
app.use(express.json({ limit: "1mb" }));

const wa = new WhatsAppGatewayClient({
  authDir: process.env.AUTH_DIR || "./auth_state",
  mediaDir: process.env.MEDIA_DIR || "./inbound_media",
  webhookUrl: process.env.WEBHOOK_URL || "",
  webhookSecret: process.env.WEBHOOK_SECRET || "",
  logLevel: process.env.LOG_LEVEL || "info"
});

app.get("/health", (_, res) => {
  res.json({ ok: true });
});

app.get("/status", (_, res) => {
  res.json(wa.getStatus());
});

app.get("/qr", (_, res) => {
  const st = wa.getStatus();
  res.json({
    ok: true,
    has_qr: st.has_qr,
    qr_data_url: st.qr_data_url || ""
  });
});

app.post("/send", async (req, res) => {
  const { to, text } = req.body || {};
  try {
    const out = await wa.sendText(to, text);
    res.json(out);
  } catch (err) {
    res.status(400).json({
      success: false,
      error: err?.message || String(err)
    });
  }
});

app.post("/disconnect", async (_, res) => {
  try {
    const out = await wa.disconnect();
    res.json(out);
  } catch (err) {
    res.status(400).json({
      success: false,
      error: err?.message || String(err)
    });
  }
});

app.listen(PORT, HOST, async () => {
  console.log(`whatsapp-gateway listening on http://${HOST}:${PORT}`);
  try {
    await wa.start();
  } catch (err) {
    console.error("Failed to initialize WhatsApp gateway:", err?.message || err);
  }
});
