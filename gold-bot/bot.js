require("dotenv").config();
const express     = require("express");
const Anthropic   = require("@anthropic-ai/sdk");
const TelegramBot = require("node-telegram-bot-api");

const app    = express();
const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const PORT   = process.env.PORT_GOLD || 3002;
app.use(express.json());

// ─── Gestão de risco ──────────────────────────────────────────────
const BRL_RATE    = parseFloat(process.env.BRL_RATE    || "5.60");
const CAPITAL_BRL = parseFloat(process.env.CAPITAL_BRL || "500");
const CAPITAL_USD = CAPITAL_BRL / BRL_RATE;
const RISK_PCT    = parseFloat(process.env.RISK_PCT    || "0.03");

// ─── Telegram ─────────────────────────────────────────────────────
const bot = process.env.TELEGRAM_BOT_TOKEN
  ? new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, { polling: false })
  : null;

async function enviarTelegram(msg) {
  if (!bot || !process.env.TELEGRAM_CHAT_ID) return;
  try {
    await bot.sendMessage(process.env.TELEGRAM_CHAT_ID, msg, { parse_mode: "Markdown" });
  } catch (err) { log("ERRO", `Telegram: ${err.message}`); }
}

function log(tipo, msg) {
  const cores = { INFO: "\x1b[36m", OK: "\x1b[32m", ERRO: "\x1b[31m", SINAL: "\x1b[33m", SAIDA: "\x1b[35m" };
  const cor = cores[tipo] || "\x1b[0m";
  console.log(`${cor}[OURO][${new Date().toLocaleTimeString("pt-BR")}] [${tipo}]\x1b[0m ${msg}`);
}

// ─── MEXC — XAUUSDT ───────────────────────────────────────────────
const MEXC_API = "https://api.mexc.com/api/v3";
const SYMBOL   = "XAUUSDT";

async function fetchCandles() {
  try {
    const res  = await fetch(`${MEXC_API}/klines?symbol=${SYMBOL}&interval=4h&limit=250`);
    if (!res.ok) return null;
    const data = await res.json();
    if (!Array.isArray(data) || data.length < 200) return null;
    return data.map(k => ({ o: +k[1], h: +k[2], l: +k[3], c: +k[4], v: +k[5] }));
  } catch { return null; }
}

async function fetchPreco() {
  try {
    const res  = await fetch(`${MEXC_API}/ticker/price?symbol=${SYMBOL}`);
    const data = await res.json();
    return +data.price || null;
  } catch { return null; }
}

// ─── Indicadores ──────────────────────────────────────────────────
function ema(arr, len) {
  const k = 2 / (len + 1); let e = arr[0];
  return arr.map(v => (e = e + k * (v - e)));
}

function rsiLast(closes, len = 14) {
  let g = 0, l = 0;
  for (let i = 1; i <= len; i++) { const d = closes[i] - closes[i-1]; if (d > 0) g += d; else l -= d; }
  let ag = g / len, al = l / len;
  for (let i = len + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i-1];
    ag = (ag * (len - 1) + Math.max(d, 0)) / len;
    al = (al * (len - 1) + Math.max(-d, 0)) / len;
  }
  return al === 0 ? 100 : 100 - 100 / (1 + ag / al);
}

function atrLast(C, len = 14) {
  const slice = C.slice(-(len + 1));
  const trs   = slice.slice(1).map((c, i) =>
    Math.max(c.h - c.l, Math.abs(c.h - slice[i].c), Math.abs(c.l - slice[i].c))
  );
  return trs.reduce((a, b) => a + b) / trs.length;
}

function macdLast(cl) {
  const e12 = ema(cl, 12), e26 = ema(cl, 26);
  const line = e12.map((v, i) => v - e26[i]);
  const sig  = ema(line, 9);
  const n    = cl.length - 1;
  return { line: line[n], sig: sig[n], hist: line[n] - sig[n], histP: line[n-1] - sig[n-1] };
}

function adxLast(C, len = 14) {
  const pdm = [], mdm = [], tr = [];
  for (let i = 1; i < C.length; i++) {
    const { h, l } = C[i], ph = C[i-1].h, pl = C[i-1].l, pc = C[i-1].c;
    const up = h - ph, dn = pl - l;
    pdm.push(up > dn && up > 0 ? up : 0);
    mdm.push(dn > up && dn > 0 ? dn : 0);
    tr.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }
  function rma(a) {
    let s = a.slice(0, len).reduce((x, y) => x + y);
    const o = [s];
    for (let i = len; i < a.length; i++) { s = s - s / len + a[i]; o.push(s); }
    return o;
  }
  const rt = rma(tr), rp = rma(pdm), rm = rma(mdm);
  const dx = rt.map((t, i) => {
    const p = (rp[i] / t || 0) * 100, m = (rm[i] / t || 0) * 100;
    return Math.abs(p - m) / ((p + m) || 1) * 100;
  });
  const adxA = rma(dx), idx = adxA.length - 1;
  return { adx: adxA[idx], pdi: (rp[idx]/rt[idx])*100, mdi: (rm[idx]/rt[idx])*100 };
}

// ─── Análise XAUUSDT ──────────────────────────────────────────────
function analisar(C, modo = "candidato") {
  const n = C.length;
  if (n < 210) return null;
  const cl    = C.map(c => c.c);
  const price = cl[n - 1];

  const e21a = ema(cl, 21), e50a = ema(cl, 50), e200a = ema(cl, 200);
  const e21  = e21a[n-1], e50 = e50a[n-1];

  const crossUp   = e21a[n-1] > e50a[n-1] && e21a[n-2] <= e50a[n-2];
  const crossDown = e21a[n-1] < e50a[n-1] && e21a[n-2] >= e50a[n-2];
  const emaLong   = e21a[n-1] > e50a[n-1];
  const emaShort  = e21a[n-1] < e50a[n-1];

  const rsiVal = rsiLast(cl.slice(-53));
  const atrVal = atrLast(C);
  const { line: macdLine, sig: macdSig, hist, histP } = macdLast(cl);
  const { adx: adxVal } = adxLast(C.slice(-60));
  const volMa   = C.slice(-20).reduce((a, c) => a + c.v, 0) / 20;
  const volFort = C[n-1].v > volMa * 1.1;
  const macdBull = macdLine > macdSig && hist > histP;
  const macdBear = macdLine < macdSig && hist < histP;

  const isBull = crossUp || emaLong;
  let score = 0;
  score += (price > e21a[n-1] && e21 > e50) ? 30 : (price > e50 ? 10 : 0);
  score += (isBull ? macdBull : macdBear) ? 20 : 0;
  score += adxVal > 30 ? 20 : adxVal > 22 ? 10 : 0;
  score += volFort ? 10 : 0;
  score += isBull
    ? (rsiVal > 50 && rsiVal < 70 ? 20 : rsiVal > 50 ? 10 : 0)
    : (rsiVal > 30 && rsiVal < 50 ? 20 : rsiVal < 50 ? 10 : 0);
  score = Math.min(100, Math.round(score));

  if (modo === "candidato") {
    if (!crossUp && !crossDown) return null;
    if (crossUp   && rsiVal <= 50) return null;
    if (crossDown && rsiVal >= 50) return null;
    const atr = atrVal;
    return {
      tipo: crossUp ? "COMPRA" : "VENDA",
      price: +price.toFixed(2),
      stop:     crossUp ? +(price - atr * 1.5).toFixed(2) : +(price + atr * 1.5).toFixed(2),
      tp1:      crossUp ? +(price + atr * 1.5).toFixed(2) : +(price - atr * 1.5).toFixed(2),
      tp_final: crossUp ? +(price + atr * 3.0).toFixed(2) : +(price - atr * 3.0).toFixed(2),
      e21: +e21.toFixed(2), e50: +e50.toFixed(2),
      rsi: +rsiVal.toFixed(1), atr: +atrVal.toFixed(2),
      adx: +adxVal.toFixed(1), score,
    };
  }

  if (modo === "monitor") {
    return { price: +price.toFixed(2), emaLong, emaShort, crossUp, crossDown,
             rsi: +rsiVal.toFixed(1), adx: +adxVal.toFixed(1), score };
  }
  return null;
}

// ─── Cálculo de posição ───────────────────────────────────────────
function calcPosicao(preco, stop) {
  const risco_usd = CAPITAL_USD * RISK_PCT;
  const dist      = Math.abs(preco - stop);
  const qty_oz    = dist > 0 ? risco_usd / dist : 0;
  return {
    risco_usd:  +risco_usd.toFixed(2),
    risco_brl:  +(risco_usd * BRL_RATE).toFixed(2),
    qty_oz:     +qty_oz.toFixed(4),
    valor_pos:  +(qty_oz * preco).toFixed(2),
    margem_5x:  +((qty_oz * preco) / 5).toFixed(2),
  };
}

function fmtP(p) { return p != null ? p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "N/A"; }

// ─── Prompts Claude ───────────────────────────────────────────────
function promptConfirmacao(s, precoAtual) {
  const var_ = precoAtual ? ((precoAtual - s.price) / s.price * 100).toFixed(2) : "N/A";
  return `Você é analista especializado em ouro (XAUUSD) no H4.
Sinal detectado há 5h — Trend Master Flow:
- Ação: ${s.tipo} | Preço: $${s.price} → $${precoAtual || "N/A"} (${var_}%)
- Stop: $${s.stop} | TP1: $${s.tp1} | TP Final: $${s.tp_final}
- EMA21: $${s.e21} | EMA50: $${s.e50} | RSI: ${s.rsi} | ADX: ${s.adx}
Responda em português (máx 6 linhas):
1. VÁLIDO ou INVALIDADO?
2. Preço a favor ou contra?
3. Recomendação: ENTRAR, AGUARDAR ou IGNORAR`;
}

function promptEntrada(s) {
  return `Você é analista especializado em ouro (XAUUSD) no H4.
Sinal novo — Trend Master Flow:
- Ação: ${s.tipo} | Preço: $${s.price}
- Stop: $${s.stop} | TP1: $${s.tp1} | TP Final: $${s.tp_final}
- RSI: ${s.rsi} | ADX: ${s.adx} | Score: ${s.score}
Responda em português (máx 6 linhas):
1. VÁLIDO ou INVÁLIDO?
2. Observação (DXY, yields, geopolítica)?
3. Recomendação: ENTRAR, AGUARDAR ou IGNORAR`;
}

function promptSaida(estado, posicao, motivo) {
  return `Você é analista especializado em ouro (XAUUSD) no H4.
Sinal de SAÍDA — Trend Master Flow:
- Posição: ${posicao} | Preço: $${estado.price}
- RSI: ${estado.rsi} | ADX: ${estado.adx} | Motivo: ${motivo}
Responda em português (máx 5 linhas):
1. FECHAR AGORA, FECHAR PARCIAL ou AGUARDAR?
2. O que causou a reversão?`;
}

// ─── Mensagens Telegram ───────────────────────────────────────────
function msgEntrada(s, analise, lote) {
  const emoji     = s.tipo === "COMPRA" ? "🟡" : "🔴";
  const loteLabel = lote === 1 ? "Manhã" : lote === 2 ? "Tarde 13h" : "Tarde 17h";
  const pos       = calcPosicao(s.price, s.stop);
  const agora     = new Date().toLocaleString("pt-BR");
  return `${emoji} *${s.tipo} OURO — XAUUSDT*

🥇 *XAU/USDT* | 🕐 Gráfico: *H4* | ${loteLabel}
📈 Trend Master Flow — cruzamento EMA21/50

💰 Entrada: \`$${fmtP(s.price)}\`
🛑 Stop: \`$${fmtP(s.stop)}\` (1.5 ATR)
🎯 TP1 (1.5R): \`$${fmtP(s.tp1)}\` → fechar 50%
🏆 TP Final (3.0R): \`$${fmtP(s.tp_final)}\` → fechar 50%

📐 *Gestão de risco (3% de R$${CAPITAL_BRL})*
  Risco: \`$${pos.risco_usd}\` (R$${pos.risco_brl})
  Quantidade: \`${pos.qty_oz} oz\` (~\`$${pos.valor_pos} USDT\`)
  Alavancagem 5x: \`$${pos.margem_5x} colateral\`

📊 Score: *${s.score}/100* | RSI: ${s.rsi} | ADX: ${s.adx}
⚠️ _Saída apenas na reversão H4_
⏰ ${agora}

🤖 *Análise Claude:*
${analise}`;
}

function msgConfirmacao(s, precoAtual, analise) {
  const var_   = precoAtual ? ((precoAtual - s.price) / s.price * 100).toFixed(2) : null;
  const varTxt = var_ !== null ? (parseFloat(var_) >= 0 ? `+${var_}%` : `${var_}%`) : "";
  const pos    = calcPosicao(s.price, s.stop);
  const agora  = new Date().toLocaleString("pt-BR");
  return `🟡 *${s.tipo} OURO — XAUUSDT* ✅ Confirmado 5h

🥇 *XAU/USDT* | 🕐 Gráfico: *H4*
📈 Trend Master Flow

💰 Entrada: \`$${fmtP(s.price)}\` → \`$${fmtP(precoAtual)}\` _(${varTxt})_
🛑 Stop: \`$${fmtP(s.stop)}\` (1.5 ATR)
🎯 TP1 (1.5R): \`$${fmtP(s.tp1)}\` → fechar 50%
🏆 TP Final (3.0R): \`$${fmtP(s.tp_final)}\` → fechar 50%

📐 *Gestão de risco (3% de R$${CAPITAL_BRL})*
  Risco: \`$${pos.risco_usd}\` (R$${pos.risco_brl})
  Quantidade: \`${pos.qty_oz} oz\` (~\`$${pos.valor_pos} USDT\`)
  Alavancagem 5x: \`$${pos.margem_5x} colateral\`

📊 Score: *${s.score}/100* | RSI: ${s.rsi} | ADX: ${s.adx}
⚠️ _Saída apenas na reversão H4_
⏰ ${agora}

🤖 *Análise Claude:*
${analise}`;
}

function msgSaida(posicao, estado, analise) {
  const agora = new Date().toLocaleString("pt-BR");
  return `⚪ *SAÍDA ${posicao} — XAUUSDT*

🥇 *XAU/USDT* | 🕐 H4 | Reversão detectada
💰 Preço: \`$${fmtP(estado.price)}\`
📊 RSI: ${estado.rsi} | ADX: ${estado.adx}
⏰ ${agora}

🤖 *Análise Claude:*
${analise}`;
}

// ─── Estado global ────────────────────────────────────────────────
let candidatoManha  = null;
let posicaoAberta   = null;
let monitorAtivo    = false;
let monitorInterval = null;
let scanEmAndamento = false;

async function chamarClaude(prompt) {
  const resp = await client.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 400,
    messages: [{ role: "user", content: prompt }],
  });
  return resp.content?.[0]?.text || "(sem análise)";
}

// ─── Passo 1 — Scan manhã 08:00 ──────────────────────────────────
async function scanManha() {
  if (scanEmAndamento) return;
  scanEmAndamento = true;
  candidatoManha  = null;
  try {
    await enviarTelegram("🔍 *[OURO H4] Scan matinal iniciado*\n_Analisando XAUUSDT no H4..._");
    log("INFO", "Scan matinal iniciado");
    const candles = await fetchCandles();
    if (!candles) { await enviarTelegram("⚠️ *[OURO H4]* Sem dados para XAUUSDT."); return; }
    const sinal = analisar(candles, "candidato");
    if (!sinal) {
      const m = analisar(candles, "monitor");
      await enviarTelegram(`⚠️ *[OURO H4]* Sem cruzamento EMA21/50 esta manhã.\nRSI: ${m?.rsi ?? "N/A"} | ADX: ${m?.adx ?? "N/A"}`);
      return;
    }
    candidatoManha = sinal;
    await enviarTelegram(`✅ *[OURO H4] Sinal detectado*\n\n🟡 XAUUSDT — ${sinal.tipo} | Score: ${sinal.score}\n\n_Confirmação em 5 horas..._`);
    log("OK", `${sinal.tipo} $${sinal.price} Score ${sinal.score}`);
  } catch (err) { log("ERRO", `Scan manhã: ${err.message}`); }
  finally { scanEmAndamento = false; }
}

// ─── Passo 2 — Confirmação 13:00 ─────────────────────────────────
async function confirmarEBuscarTarde() {
  if (candidatoManha) {
    try {
      const precoAtual = await fetchPreco();
      const analise    = await chamarClaude(promptConfirmacao(candidatoManha, precoAtual));
      await enviarTelegram(msgConfirmacao(candidatoManha, precoAtual, analise));
      posicaoAberta  = candidatoManha.tipo;
      candidatoManha = null;
      iniciarMonitor();
    } catch (err) { log("ERRO", `Confirmação: ${err.message}`); }
  } else if (!posicaoAberta) {
    try {
      const candles = await fetchCandles();
      if (candles) {
        const sinal = analisar(candles, "candidato");
        if (sinal) {
          const analise = await chamarClaude(promptEntrada(sinal));
          await enviarTelegram(msgEntrada(sinal, analise, 2));
          posicaoAberta = sinal.tipo;
          iniciarMonitor();
        } else { await enviarTelegram("⚠️ *[OURO H4]* Sem sinal novo para a tarde."); }
      }
    } catch (err) { log("ERRO", `2ª leva: ${err.message}`); }
  }
}

// ─── Passo 3 — 3ª leva 17:00 ─────────────────────────────────────
async function buscarNoturno() {
  if (posicaoAberta) { log("INFO", "3ª leva — posição já aberta"); return; }
  try {
    const candles = await fetchCandles();
    if (!candles) return;
    const sinal = analisar(candles, "candidato");
    if (!sinal) { await enviarTelegram("⚠️ *[OURO H4]* Sem sinal novo às 17h."); return; }
    const analise = await chamarClaude(promptEntrada(sinal));
    await enviarTelegram(msgEntrada(sinal, analise, 3));
    posicaoAberta = sinal.tipo;
    iniciarMonitor();
  } catch (err) { log("ERRO", `3ª leva: ${err.message}`); }
}

// ─── Monitor de saídas (a cada 4h) ───────────────────────────────
async function verificarSaidas() {
  if (!posicaoAberta) return;
  try {
    const candles = await fetchCandles();
    if (!candles) return;
    const estado = analisar(candles, "monitor");
    if (!estado) return;
    const reverteCompra = posicaoAberta === "COMPRA" && estado.crossDown;
    const reverteVenda  = posicaoAberta === "VENDA"  && estado.crossUp;
    if (reverteCompra || reverteVenda) {
      const motivo  = reverteCompra ? "EMA21 cruzou abaixo da EMA50" : "EMA21 cruzou acima da EMA50";
      const analise = await chamarClaude(promptSaida(estado, posicaoAberta, motivo));
      await enviarTelegram(msgSaida(posicaoAberta, estado, analise));
      log("SAIDA", `SAÍDA ${posicaoAberta} XAUUSDT`);
      posicaoAberta = null;
      pararMonitor();
    }
  } catch (err) { log("ERRO", `Monitor: ${err.message}`); }
}

function iniciarMonitor() {
  if (monitorAtivo) return;
  monitorAtivo    = true;
  monitorInterval = setInterval(verificarSaidas, 4 * 60 * 60 * 1000);
  log("INFO", "Monitor de saída ativado (a cada 4h)");
}

function pararMonitor() {
  if (monitorInterval) clearInterval(monitorInterval);
  monitorAtivo = false; monitorInterval = null;
  log("INFO", "Monitor desativado");
}

// ─── Agendador ────────────────────────────────────────────────────
function msAte(horaBRT) {
  const agora = new Date(), alvo = new Date(agora);
  alvo.setUTCHours((horaBRT + 3) % 24, 0, 0, 0);
  if (alvo <= agora) alvo.setUTCDate(alvo.getUTCDate() + 1);
  return alvo - agora;
}

function agendarCiclo() {
  const msScan = msAte(8), msNot = msAte(17);
  log("INFO", `08h em ${Math.round(msScan/60000)}min | 17h em ${Math.round(msNot/60000)}min`);
  setTimeout(async () => { await scanManha(); setTimeout(confirmarEBuscarTarde, 5 * 60 * 60 * 1000); }, msScan);
  setTimeout(buscarNoturno, msNot);
  setTimeout(agendarCiclo, 24 * 60 * 60 * 1000);
}

// ─── Rotas ────────────────────────────────────────────────────────
app.get("/scan",      async (req, res) => { res.json({ ok: true }); await scanManha(); setTimeout(confirmarEBuscarTarde, 5 * 60 * 60 * 1000); });
app.get("/confirmar", async (req, res) => { res.json({ ok: true }); await confirmarEBuscarTarde(); });
app.get("/noturno",   async (req, res) => { res.json({ ok: true }); await buscarNoturno(); });
app.get("/saidas",    async (req, res) => { res.json({ ok: true }); await verificarSaidas(); });
app.get("/posicao",   (req, res) => res.json({ posicao: posicaoAberta || "nenhuma" }));
app.get("/teste", async (req, res) => {
  const s   = { tipo: "COMPRA", price: 3320.50, stop: 3270.75, tp1: 3370.25, tp_final: 3420.00,
                e21: 3305.20, e50: 3290.10, rsi: 57.3, atr: 33.5, adx: 27.8, score: 75 };
  const pos = calcPosicao(s.price, s.stop);
  const msg =
    `🧪 *[TESTE] COMPRA OURO — XAUUSDT*\n\n` +
    `🥇 *XAU/USDT* | 🕐 Gráfico: *H4*\n` +
    `📈 Trend Master Flow — cruzamento EMA21/50\n\n` +
    `💰 Entrada: \`$${fmtP(s.price)}\`\n` +
    `🛑 Stop: \`$${fmtP(s.stop)}\` (1.5 ATR)\n` +
    `🎯 TP1 (1.5R): \`$${fmtP(s.tp1)}\` → fechar 50%\n` +
    `🏆 TP Final (3.0R): \`$${fmtP(s.tp_final)}\` → fechar 50%\n\n` +
    `📐 *Gestão de risco (3% de R$${CAPITAL_BRL})*\n` +
    `  Risco: \`$${pos.risco_usd}\` (R$${pos.risco_brl})\n` +
    `  Quantidade: \`${pos.qty_oz} oz\` (~\`$${pos.valor_pos} USDT\`)\n` +
    `  Alavancagem 5x: \`$${pos.margem_5x} colateral\`\n\n` +
    `📊 Score: *${s.score}/100* | RSI: ${s.rsi} | ADX: ${s.adx}\n` +
    `⚠️ _Saída apenas na reversão H4_\n` +
    `⏰ ${new Date().toLocaleString("pt-BR")}`;
  await enviarTelegram(msg);
  log("INFO", "Mensagem de teste enviada");
  res.json({ ok: true, msg });
});
app.get("/", (req, res) => {
  res.send(`<h2>✅ Bot OURO H4 — Trend Master Flow</h2>
    <p>Porta: <strong>${PORT}</strong> | Telegram: ${bot ? "✅" : "⚠️"} | Ativo: <strong>XAUUSDT</strong></p>
    <ul>
      <li>⏰ 08:00 BRT — scan XAUUSDT H4</li>
      <li>⏰ 13:00 BRT — confirmação (5h depois)</li>
      <li>⏰ 17:00 BRT — 3ª leva</li>
      <li>🔄 A cada 4h — monitor de saída</li>
    </ul>
    <p>Posição: <strong>${posicaoAberta || "nenhuma"}</strong></p>
    <p><a href="/scan">Scan</a> | <a href="/confirmar">Confirmar</a> | <a href="/noturno">17h</a> | <a href="/saidas">Saídas</a> | <a href="/teste">Teste</a> | <a href="/posicao">JSON</a></p>
    <p>${new Date().toLocaleString("pt-BR")}</p>`);
});

// ─── Inicia ───────────────────────────────────────────────────────
app.listen(PORT, () => {
  log("INFO", `Bot OURO H4 rodando em http://localhost:${PORT}`);
  log("INFO", `Capital: R$${CAPITAL_BRL} | Risco: ${RISK_PCT * 100}% por trade`);
  log("INFO", `Telegram: ${bot ? "ativo" : "desativado — configure TELEGRAM_BOT_TOKEN"}`);
  console.log("─".repeat(60));
  agendarCiclo();
});
