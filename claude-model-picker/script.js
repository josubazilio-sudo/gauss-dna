const MODELS = [
  { id: 'gemini', name: 'Gemini 3 Pro', provider: 'Google', price: 'Grátis', active: true },
  { id: 'deepseek', name: 'DeepSeek V3', provider: 'DeepSeek', price: 'Grátis', active: false },
  { id: 'llama', name: 'Llama 3.3 70B', provider: 'Meta', price: 'Grátis', active: false },
  { id: 'mistral', name: 'Mistral Large', provider: 'Mistral', price: 'Grátis', active: false },
  { id: 'qwen', name: 'Qwen 3 32B', provider: 'Alibaba', price: 'Grátis', active: false },
  { id: 'phi', name: 'Phi-4', provider: 'Microsoft', price: 'Grátis', active: false },
];

let engineHistory = [];
let currentEngine = MODELS.find(m => m.active);
let previousEngine = null;

function renderModelGrid() {
  const grid = document.getElementById('modelGrid');
  grid.innerHTML = MODELS.map(m => `
    <div class="model-card ${m.active ? 'active' : ''}" data-id="${m.id}">
      <div class="provider">${m.provider}</div>
      <div class="name">${m.name}</div>
      <div class="price">${m.price}</div>
    </div>
  `).join('');

  document.querySelectorAll('.model-card').forEach(card => {
    card.addEventListener('click', () => selectModel(card.dataset.id));
  });
}

function selectModel(id) {
  const model = MODELS.find(m => m.id === id);
  if (!model || model.active) return;

  MODELS.forEach(m => m.active = m.id === id);
  engineHistory.push(currentEngine);
  currentEngine = model;
  previousEngine = engineHistory[engineHistory.length - 1] || null;

  updateUI();
  updateConnectionStatus(true);
}

function trocarMotor() {
  const activeIndex = MODELS.findIndex(m => m.active);
  const nextIndex = (activeIndex + 1) % MODELS.length;
  selectModel(MODELS[nextIndex].id);
}

function reverter() {
  if (!previousEngine) return;

  const prevId = previousEngine.id;
  MODELS.forEach(m => m.active = m.id === prevId);

  engineHistory.pop();
  currentEngine = previousEngine;
  previousEngine = engineHistory.length > 0 ? engineHistory[engineHistory.length - 1] : null;

  updateUI();
  updateConnectionStatus(true);
}

function updateUI() {
  document.querySelectorAll('.model-card').forEach(card => {
    card.classList.toggle('active', card.dataset.id === currentEngine.id);
  });

  document.getElementById('activeEngine').textContent = currentEngine.name;
  document.getElementById('prevEngine').textContent = previousEngine ? previousEngine.name : '—';
  document.getElementById('prevEngine').classList.toggle('muted', !previousEngine);
  document.getElementById('reverterBtn').disabled = !previousEngine;
}

function updateConnectionStatus(connected) {
  const dot = document.querySelector('.status-dot');
  const status = document.getElementById('connStatus');
  if (connected) {
    dot.classList.remove('pending');
    status.textContent = 'Estabelecida';
  } else {
    dot.classList.add('pending');
    status.textContent = 'Pendente';
  }
}

function generateConfig() {
  const apiKey = document.getElementById('apiKey').value.trim();
  if (!apiKey) {
    alert('Insira sua API Key do OpenRouter primeiro.');
    return;
  }

  const modelMap = {
    'Gemini 3 Pro': 'google/gemini-3-pro',
    'DeepSeek V3': 'deepseek/deepseek-v3',
    'Llama 3.3 70B': 'meta-llama/llama-3.3-70b',
    'Mistral Large': 'mistral/mistral-large',
    'Qwen 3 32B': 'qwen/qwen-3-32b',
    'Phi-4': 'microsoft/phi-4',
  };

  const modelRoute = modelMap[currentEngine.name] || 'google/gemini-3-pro';

  const nl = '\n';
  const psScript = [
    '# 🔄 Claude Code — Troca de Motor Automática',
    '# Execute este script no PowerShell.',
    '# Ele busca o settings.json do Claude Code no seu PC e altera o modelo.',
    '',
    'Write-Host "=== Claude Code - Troca de Motor ===" -ForegroundColor Cyan',
    '',
    '# === 1. LOCALIZA O ARQUIVO settings.json DO CLAUDE CODE ===',
    '$settingsPath = "$env:USERPROFILE\\.claude\\settings.json"',
    '$claudeDir = "$env:USERPROFILE\\.claude"',
    '',
    'if (-not (Test-Path $claudeDir)) {',
    '    Write-Host "[!] Pasta .claude nao encontrada - criando..." -ForegroundColor Yellow',
    '    New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null',
    '}',
    '',
    'if (Test-Path $settingsPath) {',
    '    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json',
    '    Write-Host "[OK] Arquivo encontrado: $settingsPath" -ForegroundColor Green',
    '} else {',
    '    Write-Host "[!] Criando novo settings.json..." -ForegroundColor Yellow',
    '    $settings = @{}',
    '}',
    '',
    '# === 2. ALTERA O MOTOR PARA OPENROUTER/FREE ===',
    '$settings.ANTHROPIC_MODEL = "openrouter/free"',
    '',
    '$settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath -Force',
    'Write-Host "[OK] ANTHROPIC_MODEL alterado para: openrouter/free" -ForegroundColor Green',
    '',
    '# === 3. CONFIGURA VARIAVEIS DE AMBIENTE OPENROUTER ===',
    '[Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", "' + apiKey + '", "User")',
    '[Environment]::SetEnvironmentVariable("OPENROUTER_MODEL", "' + modelRoute + '", "User")',
    '[Environment]::SetEnvironmentVariable("OPENROUTER_SITE_URL", "claude-code", "User")',
    '[Environment]::SetEnvironmentVariable("OPENROUTER_APP_NAME", "Claude Code", "User")',
    '',
    '# === 4. ADICIONA NO PERFIL DO POWERSHELL (pra persistir) ===',
    '$profilePath = $PROFILE.CurrentUserAllHosts',
    'if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Path $profilePath -Force | Out-Null }',
    '',
    '$currentProfile = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue',
    'if ($currentProfile -and $currentProfile.Contains("OPENROUTER")) {',
    '    Write-Host "[OK] Variaveis ja existem no perfil PowerShell" -ForegroundColor Green',
    '} else {',
    '    Add-Content $profilePath "`n# === Claude Code - OpenRouter ==="',
    '    Add-Content $profilePath "`$env:OPENROUTER_API_KEY=`"' + apiKey + '`""',
    '    Add-Content $profilePath "`$env:OPENROUTER_MODEL=`"' + modelRoute + '`""',
    '    Add-Content $profilePath "`$env:OPENROUTER_SITE_URL=`"claude-code`""',
    '    Add-Content $profilePath "`$env:OPENROUTER_APP_NAME=`"Claude Code`""',
    '    Write-Host "[OK] Variaveis adicionadas ao perfil PowerShell" -ForegroundColor Green',
    '}',
    '',
    '# === 5. MOSTRA MODELOS DISPONIVEIS ===',
    'Write-Host ""',
    'Write-Host "Modelos disponiveis para trocar:" -ForegroundColor Cyan',
    'Write-Host "  - Gemini 3 Pro (google/gemini-3-pro)" -ForegroundColor White',
    'Write-Host "  - DeepSeek V3 (deepseek/deepseek-v3)" -ForegroundColor White',
    'Write-Host "  - Llama 3.3 70B (meta-llama/llama-3.3-70b)" -ForegroundColor White',
    'Write-Host "  - Mistral Large (mistral/mistral-large)" -ForegroundColor White',
    'Write-Host "  - Qwen 3 32B (qwen/qwen-3-32b)" -ForegroundColor White',
    'Write-Host "  - Phi-4 (microsoft/phi-4)" -ForegroundColor White',
    'Write-Host ""',
    'Write-Host "Para trocar o motor manualmente:" -ForegroundColor Yellow',
    'Write-Host "  `$env:OPENROUTER_MODEL=`"OUTRO_MODELO_AQUI`"" -ForegroundColor Yellow',
    'Write-Host ""',
    'Write-Host "=== PRONTO! Reinicie o terminal Claude Code ===" -ForegroundColor Cyan',
    'Write-Host "Modelo ativo: ' + currentEngine.name + ' (' + modelRoute + ')" -ForegroundColor White',
    'Write-Host ""',
    'Write-Host "Dica: Se quiser voltar ao modelo anterior, execute:" -ForegroundColor Gray',
  ].join(nl);

  return psScript;
}

document.addEventListener('DOMContentLoaded', () => {
  renderModelGrid();

  document.getElementById('initBtn').addEventListener('click', () => {
    const config = generateConfig();
    if (config) {
      document.getElementById('copyBtn').textContent = 'Copiar';
      document.getElementById('copyBtn').dataset.config = config;
      document.getElementById('promptOutput').value = config;
      document.getElementById('promptArea').style.display = 'block';
    }
  });

  document.getElementById('swapBtn').addEventListener('click', trocarMotor);

  document.getElementById('trocarMotorBtn').addEventListener('click', trocarMotor);

  document.getElementById('reverterBtn').addEventListener('click', reverter);

  document.getElementById('copyBtn').addEventListener('click', () => {
    const config = document.getElementById('copyBtn').dataset.config;
    if (!config) {
      alert('Clique em "Inicializar" primeiro para gerar a configuração.');
      return;
    }
    navigator.clipboard.writeText(config).then(() => {
      document.getElementById('copyBtn').textContent = 'Copiado!';
      setTimeout(() => {
        document.getElementById('copyBtn').textContent = 'Copiar';
      }, 2000);
    }).catch(() => {
      alert('Erro ao copiar. Copie manualmente.');
    });
  });

  document.getElementById('apiKey').addEventListener('input', (e) => {
    const hasKey = e.target.value.trim().length > 0;
    updateConnectionStatus(hasKey);
  });

  // Tab switching
  document.querySelectorAll('.tabs').forEach(tabGroup => {
    tabGroup.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        tabGroup.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
      });
    });
  });
});
