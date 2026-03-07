const axios = require("axios");
const crypto = require("crypto");

function buildSignature(secret, bodyText) {
  return crypto.createHmac("sha256", secret).update(bodyText, "utf8").digest("hex");
}

async function postInbound(webhookUrl, webhookSecret, payload, logger) {
  if (!webhookUrl) return;
  const bodyText = JSON.stringify(payload);
  const signature = buildSignature(webhookSecret || "", bodyText);

  try {
    await axios.post(webhookUrl, payload, {
      timeout: 10000,
      headers: {
        "Content-Type": "application/json",
        "X-Channel-Provider": "whatsapp",
        "X-Webhook-Signature": signature
      }
    });
  } catch (err) {
    logger?.error({ err: err?.message }, "Failed to post inbound webhook");
  }
}

module.exports = {
  postInbound,
  buildSignature
};
