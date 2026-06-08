require("dotenv").config();
const express     = require("express");
const Anthropic   = require("@anthropic-ai/sdk");
const TelegramBot = require("node-telegram-bot-api");

const app    = express();
const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const PORT   = process.env.PORT_H4 || 3001;
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
  console.log(`${cor}[H4][${new Date().toLocaleTimeString("pt-BR")}] [${tipo}]\x1b[0m ${msg}`);
}

// ─── MEXC ─────────────────────────────────────────────────────────
const MEXC_API = "https://api.mexc.com/api/v3";
const STABLES  = new Set(["USDC","BUSD","TUSD","USDP","FDUSD","DAI","USDD","SUSD","AEUR","EURL"]);
const BAD_SUB  = ["UP","DOWN","BULL","BEAR","HEDGE"];

async function buscarTopCriptos(n = 100) {
  const res  = await fetch(`${MEXC_API}/ticker/24hr`);
  const data = await res.json();
  return data
    .filter(t => {
      const s = t.symbol, base = s.slice(0, -4);
      if (!s.endsWith("USDT")) return false;
      if (STABLES.has(base)) return false;
      if (BAD_SUB.some(x => base.includes(x))) return false;
      return +t.quoteVolume > 1e6;
    })
    .sort((a, b) => +b.quoteVolume - +a.quoteVolume)
    .slice(0, n)
    .map(t => t.symbol);
}

async function fetchCandles(symbol) {
  try {
    const res  = await fetch(`${MEXC_API}/klines?symbol=${symbol}&interval=4h&limit=250`);
    if (!res.ok) return null;
    const data = await res.json();
    if (!Array.isArray(data) || data.length < 200) return null;
    return data.map(k => ({ o: +k[1], h: +k[2], l: +k[3], c: +k[4], v: +k[5] }));
  } catch { return null; }
}

async function fetchPreco(symbol) {
  try {
    const res  = await fetch(`${MEXC_API}/ticker/price?symbol=${symbol}`);
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

// ─── Análise Trend Master Flow ────────────────────────────────────
function analisar(symbol, C, modo = "candidato") {
  const n = C.length;
  if (n < 210) return null;
  const cl    = C.map(c => c.c);
  const price = cl[n - 1];

  const e21a = ema(cl, 21), e50a = ema(cl, 50), e200a = ema(cl, 200);
  const e21  = e21a[n-1], e50 = e50a[n-1], e200 = e200a[n-1];

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
  score += (price > e200 && e21 > e50) ? 30 : (price > e200 ? 10 : 0);
  score += (isBull ? macdBull : macdBear) ? 20 : 0;
  score += adxVal > 30 ? 20 : adxVal > 22 ? 10 : 0;
  score += volFort ? 10 : 0;
  score += isBull
    ? (rsiVal > 50 && rsiVal < 70 ? 20 : rsiVal > 50 ? 10 : 0)
    : (rsiVal > 30 && rsiVal < 50 ? 20 : rsiVal < 50 ? 10 : 0);
  score = Math.min(100, Math.round(score));

  const slM = 1.5, tp1M = 1.5, tp2M = 3.0;

  if (modo === "candidato") {
    if (!crossUp && !crossDown) return null;
    if (crossUp   && rsiVal <= 50) return null;
    if (crossDown && rsiVal >= 50) return null;
    return {
      symbol, tipo: crossUp ? "COMPRA" : "VENDA",
      price: +price.toFixed(8),
      stop:     crossUp ? +(price - atrVal * slM).toFixed(8)  : +(price + atrVal * slM).toFixed(8),
      tp1:      crossUp ? +(price + atrVal * tp1M).toFixed(8) : +(price - atrVal * tp1M).toFixed(8),
      tp_final: crossUp ? +(price + atrVal * tp2M).toFixed(8) : +(price - atrVal * tp2M).toFixed(8),
      e21: +e21.toFixed(8), e50: +e50.toFixed(8),
      rsi: +rsiVal.toFixed(1), atr: +atrVal.toFixed(8),
      adx: +adxVal.toFixed(1), score,
    };
  }

  if (modo === "monitor") {
    return {
      symbol, price: +price.toFixed(8),
      emaLong, emaShort, crossUp, crossDown,
      rsi: +rsiVal.toFixed(1), adx: +adxVal.toFixed(1), score,
    };
  }

  return null;
}

// ─── Cálculo de posição ───────────────────────────────────────────
function calcPosicao(preco, stop) {
  const risco_usd = CAPITAL_USD * RISK_PCT;
  const dist_stop = Math.abs(preco - stop);
  const qty       = dist_stop > 0 ? risco_usd / dist_stop : 0;
  const valor_pos = qty * preco;
  const margem_5x = valor_pos / 5;
  return {
    risco_usd:  +risco_usd.toFixed(2),
    risco_brl:  +(risco_usd * BRL_RATE).toFixed(2),
    qty:        +qty.toFixed(4),
    valor_pos:  +valor_pos.toFixed(2),
    margem_5x:  +margem_5x.toFixed(2),
  };
}

// ─── Prompts Claude ───────────────────────────────────────────────
function promptConfirmacao(s, precoAtual) {
  const var_ = precoAtual ? ((precoAtual - s.price) / s.price * 100).toFixed(2) : "N/A";
  return `Você é um analista de swing trading H4 em criptomoedas.

Sinal detectado há 5 horas (Trend Master Flow):
- Par: ${s.symbol} | Ação: ${s.tipo}
- Preço na detecção: ${s.price} → Atual: ${precoAtual || "N/A"} (${var_}%)
- Stop: ${s.stop} | TP1: ${s.tp1} | TP Final: ${s.tp_final}
- EMA21: ${s.e21} | EMA50: ${s.e50} | RSI: ${s.rsi} | ADX: ${s.adx} | Score: ${s.score}

Após 5h de confirmação, responda em português:
1. Sinal CONTINUA VÁLIDO ou foi INVALIDADO? (1 linha)
2. Preço se moveu a favor ou contra?
3. Risco/retorno ainda favorável?
4. Recomendação: ENTRAR AGORA, AGUARDAR ou IGNORAR

Máximo 6 linhas.`;
}

function promptEntrada(s) {
  return `Você é um analista de swing trading H4 em criptomoedas.

Sinal validado agora (Trend Master Flow):
- Par: ${s.symbol} | Ação: ${s.tipo}
- Preço atual: ${s.price}
- Stop: ${s.stop} | TP1: ${s.tp1} | TP Final: ${s.tp_final}
- EMA21: ${s.e21} | EMA50: ${s.e50} | RSI: ${s.rsi} | ADX: ${s.adx} | Score: ${s.score}

Cruzamento EMA21/EMA50 + RSI confirmado. Operação swing de 1–5 dias.
Responda em português:
1. Sinal VÁLIDO ou INVÁLIDO? (1 linha)
2. Risco/retorno estimado?
3. Observação importante?
4. Recomendação: ENTRAR, AGUARDAR ou IGNORAR

Máximo 6 linhas.`;
}

function promptSaida(s, posicao, motivo) {
  return `Você é um analista de swing trading H4 em criptomoedas.

Sinal de SAÍDA detectado pelo Trend Master Flow:
- Par: ${s.symbol} | Posição aberta: ${posicao}
- Preço atual: ${s.price}
- RSI: ${s.rsi} | ADX: ${s.adx} | Score: ${s.score}
- Motivo: ${motivo}

Responda em português:
1. Saída CONFIRMADA ou pode aguardar? (1 linha)
2. O que causou a reversão?
3. Recomendação: FECHAR AGORA, FECHAR PARCIAL ou AGUARDAR

Máximo 5 linhas.`;
}

// ─── Formatação de mensagens ──────────────────────────────────────
function e(v) { return String(v ?? "N/A").replace(/[_*`[\]]/g, "\\$&"); }

function fmtP(p) {
  if (!p && p !== 0) return "N/A";
  if (p < 0.0001) return p.toFixed(8);
  if (p < 0.01)   return p.toFixed(6);
  if (p < 1)      return p.toFixed(5);
  if (p < 100)    return p.toFixed(4);
  return p.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function msgEntrada(s, analise, rank, lote) {
  const emoji     = s.tipo === "COMPRA" ? "🟢" : "🔴";
  const medal     = rank === 1 ? "🥇" : "🥈";
  const loteLabel = lote === 1 ? "Manhã" : lote === 2 ? "Tarde 13h" : "Tarde 17h";
  const pos       = calcPosicao(s.price, s.stop);
  return `${medal}${emoji} *${e(s.tipo)} — ${e(s.symbol)}*

💰 Preço: \`${fmtP(s.price)}\`
⏱ Timeframe: 4H \\| ${loteLabel} \\| Top ${rank}
🛑 Stop: \`${fmtP(s.stop)}\`
🎯 TP1: \`${fmtP(s.tp1)}\` \\| TP Final: \`${fmtP(s.tp_final)}\`
📊 ADX: ${e(String(s.adx))} \\| Score: ${e(String(s.score))}

📐 *Gestão de risco (3% de R\\$${CAPITAL_BRL})*
  Risco: \`$${pos.risco_usd}\` \\(R\\$${pos.risco_brl}\\)
  Quantidade: \`${pos.qty} ${e(s.symbol.replace("USDT",""))}\` \\(~\`$${pos.valor_pos} USDT\`\\)
  Alavancagem 5x: \`$${pos.margem_5x} colateral\`
⚠️ _Saída apenas na reversão H4_

🤖 *Análise Claude:*
${analise}`;
}

function msgConfirmacaoComVariacao(s, precoAtual, analise, rank) {
  const var_   = precoAtual ? ((precoAtual - s.price) / s.price * 100).toFixed(2) : null;
  const varTxt = var_ !== null ? (parseFloat(var_) >= 0 ? `\\+${var_}%` : `${var_}%`) : "";
  const emoji  = s.tipo === "COMPRA" ? "🟢" : "🔴";
  const medal  = rank === 1 ? "🥇" : "🥈";
  const pos    = calcPosicao(s.price, s.stop);
  return `${medal}${emoji} *${e(s.tipo)} — ${e(s.symbol)}*

💰 Preço: \`${fmtP(s.price)}\` → \`${fmtP(precoAtual)}\` _(${varTxt})_
⏱ Timeframe: 4H \\| Manhã Top ${rank} \\| confirmado 5h
🛑 Stop: \`${fmtP(s.stop)}\`
🎯 TP1: \`${fmtP(s.tp1)}\` \\| TP Final: \`${fmtP(s.tp_final)}\`
📊 ADX: ${e(String(s.adx))} \\| Score: ${e(String(s.score))}

📐 *Gestão de risco (3% de R\\$${CAPITAL_BRL})*
  Risco: \`$${pos.risco_usd}\` \\(R\\$${pos.risco_brl}\\)
  Quantidade: \`${pos.qty} ${e(s.symbol.replace("USDT",""))}\` \\(~\`$${pos.valor_pos} USDT\`\\)
  Alavancagem 5x: \`$${pos.margem_5x} colateral\`
⚠️ _Saída apenas na reversão H4_

🤖 *Análise Claude:*
${analise}`;
}

function msgSaida(symbol, posicao, estadoAtual, analise) {
  return `⚪ *SAÍDA ${e(posicao)} — ${e(symbol)}*

💰 Preço: \`${fmtP(estadoAtual.price)}\`
⏱ Timeframe: 4H \\| Reversão detectada
📊 ADX: ${e(String(estadoAtual.adx))} \\| Score: ${e(String(estadoAtual.score))}

🤖 *Análise Claude:*
${analise}`;
}

// ─── Estado global ────────────────────────────────────────────────
let candidatosManha = [];
let posicoesAbertas = new Map();
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
  candidatosManha = [];
  try {
    await enviarTelegram("🔍 *[H4] Scan matinal iniciado*\n_Analisando top 100 MEXC no H4..._");
    log("INFO", "Scan matinal iniciado — top 100 MEXC");
    const simbolos   = await buscarTopCriptos(100);
    const resultados = [];
    for (const symbol of simbolos) {
      try {
        const candles = await fetchCandles(symbol);
        if (!candles) continue;
        const sinal = analisar(symbol, candles, "candidato");
        if (sinal) resultados.push(sinal);
        await new Promise(r => setTimeout(r, 80));
      } catch { }
    }
    resultados.sort((a, b) => b.score - a.score);
    candidatosManha = resultados.slice(0, 2);

    if (candidatosManha.length === 0) {
      await enviarTelegram("⚠️ *[H4]* Nenhum sinal encontrado esta manhã.");
      return;
    }
    const lista = candidatosManha.map((s, i) =>
      `${i === 0 ? "🥇" : "🥈"} *${s.symbol}* — ${s.tipo} | Score: ${s.score}`
    ).join("\n");
    await enviarTelegram(`✅ *[H4] ${candidatosManha.length} sinal(is) selecionado(s)*\n\n${lista}\n\n_Confirmação em 5 horas..._`);
    log("OK", `Candidatos: ${candidatosManha.map(s => s.symbol).join(", ")}`);
  } catch (err) {
    log("ERRO", `Scan manhã: ${err.message}`);
  } finally {
    scanEmAndamento = false;
  }
}

// ─── Passo 2 — Confirmação + 2ª leva 13:00 ───────────────────────
async function confirmarEBuscarTarde() {
  for (let i = 0; i < candidatosManha.length; i++) {
    const s = candidatosManha[i];
    try {
      const precoAtual = await fetchPreco(s.symbol);
      const analise    = await chamarClaude(promptConfirmacao(s, precoAtual));
      log("OK", `Confirmação ${s.symbol}:\n${analise}`);
      await enviarTelegram(msgConfirmacaoComVariacao(s, precoAtual, analise, i + 1));
      posicoesAbertas.set(s.symbol, s.tipo);
      await new Promise(r => setTimeout(r, 2000));
    } catch (err) {
      log("ERRO", `Confirmação ${s.symbol}: ${err.message}`);
    }
  }

  try {
    await enviarTelegram("🔍 *[H4] Buscando 2ª leva...*\n_Sinais com entrada válida agora_");
    const excluir    = candidatosManha.map(s => s.symbol);
    candidatosManha  = [];
    const simbolos   = await buscarTopCriptos(100);
    const resultados = [];
    for (const symbol of simbolos) {
      if (excluir.includes(symbol)) continue;
      try {
        const candles = await fetchCandles(symbol);
        if (!candles) continue;
        const sinal = analisar(symbol, candles, "candidato");
        if (sinal) resultados.push(sinal);
        await new Promise(r => setTimeout(r, 80));
      } catch { }
    }
    resultados.sort((a, b) => b.score - a.score);
    const tarde = resultados.slice(0, 2);

    if (tarde.length === 0) {
      await enviarTelegram("⚠️ *[H4]* Nenhum sinal novo para a tarde.");
    } else {
      for (let i = 0; i < tarde.length; i++) {
        const s       = tarde[i];
        const analise = await chamarClaude(promptEntrada(s));
        log("OK", `2ª leva ${s.symbol}:\n${analise}`);
        await enviarTelegram(msgEntrada(s, analise, i + 1, 2));
        posicoesAbertas.set(s.symbol, s.tipo);
        await new Promise(r => setTimeout(r, 2000));
      }
    }
  } catch (err) {
    log("ERRO", `2ª leva: ${err.message}`);
  }
  iniciarMonitor();
}

// ─── Passo 3 — 3ª leva 17:00 ─────────────────────────────────────
async function buscarNoturno() {
  try {
    await enviarTelegram("🔍 *[H4] 3ª leva — 17:00*\n_Buscando mais 2 sinais..._");
    log("INFO", "Scan 3ª leva (17h) iniciado");
    const excluir    = [...posicoesAbertas.keys()];
    const simbolos   = await buscarTopCriptos(100);
    const resultados = [];
    for (const symbol of simbolos) {
      if (excluir.includes(symbol)) continue;
      try {
        const candles = await fetchCandles(symbol);
        if (!candles) continue;
        const sinal = analisar(symbol, candles, "candidato");
        if (sinal) resultados.push(sinal);
        await new Promise(r => setTimeout(r, 80));
      } catch { }
    }
    resultados.sort((a, b) => b.score - a.score);
    const noturno = resultados.slice(0, 2);

    if (noturno.length === 0) {
      await enviarTelegram("⚠️ *[H4]* Nenhum sinal novo às 17h.");
      return;
    }
    for (let i = 0; i < noturno.length; i++) {
      const s       = noturno[i];
      const analise = await chamarClaude(promptEntrada(s));
      log("OK", `3ª leva ${s.symbol}:\n${analise}`);
      await enviarTelegram(msgEntrada(s, analise, i + 1, 3));
      posicoesAbertas.set(s.symbol, s.tipo);
      await new Promise(r => setTimeout(r, 2000));
    }
    iniciarMonitor();
  } catch (err) {
    log("ERRO", `3ª leva: ${err.message}`);
  }
}

// ─── Monitor de saídas (a cada 4h) ───────────────────────────────
async function verificarSaidas() {
  if (posicoesAbertas.size === 0) return;
  log("INFO", `Monitorando ${posicoesAbertas.size} posição(ões)...`);
  for (const [symbol, posicao] of posicoesAbertas) {
    try {
      const candles = await fetchCandles(symbol);
      if (!candles) continue;
      const estado = analisar(symbol, candles, "monitor");
      if (!estado) continue;
      const reverteCompra = posicao === "COMPRA" && estado.crossDown;
      const reverteVenda  = posicao === "VENDA"  && estado.crossUp;
      if (reverteCompra || reverteVenda) {
        const motivo = reverteCompra
          ? "EMA21 cruzou abaixo da EMA50 — tendência revertida para baixa"
          : "EMA21 cruzou acima da EMA50 — tendência revertida para alta";
        const analise = await chamarClaude(promptSaida(estado, posicao, motivo));
        log("SAIDA", `SAÍDA ${posicao} ${symbol}`);
        await enviarTelegram(msgSaida(symbol, posicao, estado, analise));
        posicoesAbertas.delete(symbol);
        await new Promise(r => setTimeout(r, 2000));
      }
      await new Promise(r => setTimeout(r, 100));
    } catch (err) {
      log("ERRO", `Monitor ${symbol}: ${err.message}`);
    }
  }
  if (posicoesAbertas.size === 0) pararMonitor();
}

function iniciarMonitor() {
  if (monitorAtivo) return;
  monitorAtivo    = true;
  monitorInterval = setInterval(verificarSaidas, 4 * 60 * 60 * 1000);
  log("INFO", "Monitor de saídas ativado (a cada 4h)");
}

function pararMonitor() {
  if (monitorInterval) clearInterval(monitorInterval);
  monitorAtivo    = false;
  monitorInterval = null;
  log("INFO", "Monitor desativado — sem posições abertas");
}

// ─── Agendador ────────────────────────────────────────────────────
const HORA_SCAN_BRT    = 8;
const HORA_NOTURNO_BRT = 17;
const HORAS_ESPERA     = 5;

function msAte(horaBRT) {
  const agora = new Date();
  const alvo  = new Date(agora);
  alvo.setUTCHours((horaBRT + 3) % 24, 0, 0, 0);
  if (alvo <= agora) alvo.setUTCDate(alvo.getUTCDate() + 1);
  return alvo - agora;
}

function agendarCiclo() {
  const msScan    = msAte(HORA_SCAN_BRT);
  const msNoturno = msAte(HORA_NOTURNO_BRT);
  log("INFO", `Ciclo: 08:00 scan | 13:00 confirmação+2ª leva | 17:00 3ª leva`);
  log("INFO", `08h em ${Math.round(msScan/60000)}min | 17h em ${Math.round(msNoturno/60000)}min`);

  setTimeout(async () => {
    await scanManha();
    setTimeout(confirmarEBuscarTarde, HORAS_ESPERA * 60 * 60 * 1000);
  }, msScan);

  setTimeout(buscarNoturno, msNoturno);
  setTimeout(agendarCiclo, 24 * 60 * 60 * 1000);
}

// ─── Rotas ────────────────────────────────────────────────────────
app.get("/scan",      async (req, res) => { res.json({ ok: true }); await scanManha(); setTimeout(confirmarEBuscarTarde, HORAS_ESPERA * 60 * 60 * 1000); });
app.get("/confirmar", async (req, res) => { res.json({ ok: true }); await confirmarEBuscarTarde(); });
app.get("/noturno",   async (req, res) => { res.json({ ok: true }); await buscarNoturno(); });
app.get("/saidas",    async (req, res) => { res.json({ ok: true }); await verificarSaidas(); });
app.get("/posicoes",  (req, res) => {
  res.json({ total: posicoesAbertas.size, posicoes: [...posicoesAbertas.entries()].map(([sym, lado]) => ({ sym, lado })) });
});
app.get("/teste", async (req, res) => {
  const sinalTeste = {
    symbol: "BTCUSDT", tipo: "COMPRA",
    price: 105000, stop: 103425, tp1: 106575, tp_final: 109725,
    e21: 104200, e50: 102800, rsi: 58.4, atr: 1050, adx: 28.6, score: 80,
  };
  const pos = calcPosicao(sinalTeste.price, sinalTeste.stop);
  const agora = new Date().toLocaleString("pt-BR");
  const msg =
    `🧪 *[TESTE] COMPRA — BTCUSDT*\n\n` +
    `🟢 *BTC/USDT* | 🕐 Gráfico: *H4*\n` +
    `📈 Trend Master Flow — cruzamento EMA21/50\n\n` +
    `💰 Entrada: \`$${fmtP(sinalTeste.price)}\`\n` +
    `🛑 Stop: \`$${fmtP(sinalTeste.stop)}\` (1.5 ATR)\n` +
    `🎯 TP1 (1.5R): \`$${fmtP(sinalTeste.tp1)}\` → fechar 50%\n` +
    `🏆 TP Final (3.0R): \`$${fmtP(sinalTeste.tp_final)}\` → fechar 50%\n\n` +
    `📐 *Gestão de risco (3% de R$${CAPITAL_BRL})*\n` +
    `  Risco: \`$${pos.risco_usd}\` (R$${pos.risco_brl})\n` +
    `  Spot: \`${pos.qty} BTC\` (~\`$${pos.valor_pos} USDT\`)\n` +
    `  Alavancagem 5x: \`$${pos.margem_5x} colateral\`\n\n` +
    `📊 Score: *${sinalTeste.score}/100* | RSI: ${sinalTeste.rsi} | ADX: ${sinalTeste.adx}\n` +
    `⚠️ _Saída apenas na reversão H4_\n` +
    `⏰ ${agora}`;
  await enviarTelegram(msg);
  log("INFO", "Mensagem de teste enviada");
  res.json({ ok: true, msg });
});
app.get("/", (req, res) => {
  const pos = [...posicoesAbertas.entries()];
  res.send(`<h2>✅ Bot H4 Cripto — Trend Master Flow</h2>
    <p>Porta: <strong>${PORT}</strong> | Telegram: ${bot ? "✅" : "⚠️"} | Top: <strong>100 pares USDT</strong></p>
    <ul>
      <li>⏰ 08:00 BRT — scan top 100 MEXC</li>
      <li>⏰ 13:00 BRT — confirmação + 2ª leva</li>
      <li>⏰ 17:00 BRT — 3ª leva</li>
      <li>🔄 A cada 4h — monitor de saídas</li>
    </ul>
    <p>Posições: ${pos.length > 0 ? pos.map(([s,l]) => `${s}:${l}`).join(", ") : "nenhuma"}</p>
    <p><a href="/scan">Scan</a> | <a href="/confirmar">Confirmar</a> | <a href="/noturno">17h</a> | <a href="/saidas">Saídas</a> | <a href="/posicoes">JSON</a></p>
    <p>${new Date().toLocaleString("pt-BR")}</p>`);
});

// ─── Inicia ───────────────────────────────────────────────────────
app.listen(PORT, () => {
  log("INFO", `Bot H4 Cripto rodando em http://localhost:${PORT}`);
  log("INFO", `Capital: R$${CAPITAL_BRL} | Risco: ${RISK_PCT * 100}% por trade`);
  log("INFO", `Telegram: ${bot ? "ativo" : "desativado — configure TELEGRAM_BOT_TOKEN"}`);
  console.log("─".repeat(60));
  agendarCiclo();
});
