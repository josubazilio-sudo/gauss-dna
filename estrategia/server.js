require("dotenv").config();
const express = require("express");
const Anthropic = require("@anthropic-ai/sdk");
const TelegramBot = require("node-telegram-bot-api");

const app = express();
app.use(express.json());

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const PORT = process.env.PORT || 3000;
const SECRET = process.env.WEBHOOK_SECRET;

// ─── Telegram ─────────────────────────────────────────────────────
const bot = process.env.TELEGRAM_BOT_TOKEN
  ? new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, { polling: false })
  : null;

async function enviarTelegram(mensagem) {
  if (!bot || !process.env.TELEGRAM_CHAT_ID) return;
  try {
    await bot.sendMessage(process.env.TELEGRAM_CHAT_ID, mensagem, { parse_mode: "Markdown" });
  } catch (err) {
    log("ERRO", `Telegram: ${err.message}`);
  }
}

// ─── Log colorido no terminal ─────────────────────────────────────
function log(tipo, msg) {
  const cores = { INFO: "\x1b[36m", OK: "\x1b[32m", ERRO: "\x1b[31m", SINAL: "\x1b[33m" };
  const cor = cores[tipo] || "\x1b[0m";
  const hora = new Date().toLocaleTimeString("pt-BR");
  console.log(`${cor}[${hora}] [${tipo}]\x1b[0m ${msg}`);
}

// ─── Prompt do Claude ─────────────────────────────────────────────
function montarPrompt(alerta) {
  return `Você é um analista de trading especializado em criptomoedas.

Recebeu o seguinte alerta do TradingView:
- Par: ${alerta.ticker || "N/A"}
- Ação: ${alerta.action || "N/A"}
- Preço de entrada: ${alerta.price || "N/A"}
- Timeframe: ${alerta.interval || "N/A"}
- Stop Loss: ${alerta.stop || "N/A"}
- TP1: ${alerta.tp1 || "N/A"}
- TP Final: ${alerta.tp_final || "N/A"}
- ADX: ${alerta.adx || "N/A"}
- Score: ${alerta.score || "N/A"}
- Horário: ${alerta.time || new Date().toISOString()}

Com base nesses dados, responda em português:
1. O sinal é VÁLIDO ou INVÁLIDO? (explique em 1 linha)
2. Qual o risco/retorno estimado?
3. Algum alerta ou observação importante?
4. Recomendação final: ENTRAR, AGUARDAR ou IGNORAR

Seja objetivo — máximo 6 linhas no total.`;
}

// ─── Formata mensagem para o Telegram ────────────────────────────
function montarMensagemTelegram(alerta, analise) {
  const emoji = alerta.action === "LONG" ? "🟢" : alerta.action === "SHORT" ? "🔴" : "🔔";
  return `${emoji} *${alerta.action || "SINAL"} — ${alerta.ticker || "N/A"}*

💰 Preço: \`${alerta.price || "N/A"}\`
⏱ Timeframe: ${alerta.interval || "N/A"}
🛑 Stop: \`${alerta.stop || "N/A"}\`
🎯 TP1: \`${alerta.tp1 || "N/A"}\` | TP Final: \`${alerta.tp_final || "N/A"}\`
📊 ADX: ${alerta.adx || "N/A"} | Score: ${alerta.score || "N/A"}

🤖 *Análise Claude:*
${analise}`;
}

// ─── Rota principal — recebe alertas do TradingView ───────────────
app.post("/webhook", async (req, res) => {
  try {
    if (SECRET && req.headers["x-webhook-secret"] !== SECRET) {
      log("ERRO", "Acesso negado — secret incorreto");
      return res.status(401).json({ erro: "Não autorizado" });
    }

    const alerta = req.body;
    log("SINAL", `Alerta recebido: ${alerta.action} ${alerta.ticker} @ ${alerta.price}`);

    const resposta = await client.messages.create({
      model: "claude-sonnet-4-6",
      max_tokens: 400,
      messages: [{ role: "user", content: montarPrompt(alerta) }],
    });

    const analise = resposta.content[0].text;

    log("OK", `Análise Claude:\n${analise}`);
    console.log("─".repeat(60));

    // Envia para o Telegram
    await enviarTelegram(montarMensagemTelegram(alerta, analise));

    res.json({
      recebido: true,
      ticker: alerta.ticker,
      action: alerta.action,
      price: alerta.price,
      analise,
    });
  } catch (err) {
    log("ERRO", err.message);
    res.status(500).json({ erro: err.message });
  }
});

// ─── Rota de teste ────────────────────────────────────────────────
app.get("/", (req, res) => {
  res.send(`
    <h2>✅ Servidor TradingView + Claude + Telegram rodando</h2>
    <p>Endpoint: <code>POST /webhook</code></p>
    <p>Telegram: ${bot ? "✅ Configurado" : "⚠️ Não configurado (adicione TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env)"}</p>
    <p>Hora: ${new Date().toLocaleString("pt-BR")}</p>
    <h3>Teste rápido:</h3>
    <pre>curl -X POST http://localhost:${PORT}/webhook \\
  -H "Content-Type: application/json" \\
  -d '{"ticker":"NEARUSDT","action":"SHORT","price":"2.470","interval":"15","stop":"2.510","tp1":"2.432","tp_final":"2.358","adx":"22","score":"45"}'</pre>
  `);
});

app.listen(PORT, () => {
  log("INFO", `Servidor rodando em http://localhost:${PORT}`);
  log("INFO", `Telegram: ${bot ? "ativo" : "desativado — configure TELEGRAM_BOT_TOKEN"}`);
  console.log("─".repeat(60));
});
