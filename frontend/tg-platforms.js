/* ZeusCode — окна разработки, куда люди вставляют ключ (OpenAI-compatible). */
window.ZC_PLATFORMS = {
  orca: {
    id: "orca",
    title: "Orca",
    hint: "Главное окно разработки — рекомендуется",
    kind: "desktop",
    installUrl: "https://github.com/stablyai/orca",
    setupTitle: "Orca — одна команда",
    yaml: false,
    configKind: "orca",
    note: "Установка + настройка ключа одной командой. Model name = gpt-5.5 (рекомендуется, но можно любой).",
    plan: [
      { t: "Установить", d: "Одна команда в терминале" },
      { t: "Готово", d: "Orca настроен и готов к работе" },
    ],
    steps: [
      "Открой <b>терминал</b>.",
      "Скопируй команду ниже и вставь в терминал.",
      "Нажми <code>Enter</code> — установка + настройка автоматически.",
      "Открой <b>Orca</b> и начни кодить.",
    ],
    visuals: [],
    setupCode: `# macOS
brew install --cask stablyai/orca/orca && \\
mkdir -p ~/.config/claude-code && \\
cat > ~/.config/claude-code/config.json << 'EOF'
{
  "provider": "openai",
  "apiBaseUrl": "https://zeuscode.ru/v1",
  "apiKey": "ВАШ_КЛЮЧ_СЮДА",
  "defaultModel": "gpt-5.5"
}
EOF

# Windows (PowerShell)
winget install StablyAI.Orca
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\\.config\\claude-code"
@"
{
  "provider": "openai",
  "apiBaseUrl": "https://zeuscode.ru/v1",
  "apiKey": "ВАШ_КЛЮЧ_СЮДА",
  "defaultModel": "gpt-5.5"
}
"@ | Out-File -FilePath "$env:USERPROFILE\\.config\\claude-code\\config.json"

# Linux
wget https://github.com/stablyai/orca/releases/latest/download/orca-linux-x86_64.AppImage && \\
chmod +x orca-linux-x86_64.AppImage && \\
mkdir -p ~/.config/claude-code && \\
cat > ~/.config/claude-code/config.json << 'EOF'
{
  "provider": "openai",
  "apiBaseUrl": "https://zeuscode.ru/v1",
  "apiKey": "ВАШ_КЛЮЧ_СЮДА",
  "defaultModel": "gpt-5.5"
}
EOF && \\
./orca-linux-x86_64.AppImage`,
  },

  unknown: {
    id: "unknown",
    title: "Не знаю где",
    hint: "Проведём через Orca — самый простой путь",
    kind: "onramp",
    installUrl: "https://github.com/stablyai/orca",
    setupTitle: "Простой путь",
    yaml: false,
    configKind: "orca",
    note: "Один ключ · model = gpt-5.5. Режим (Solo/Crew/ZeusCode Pro) — только в TG «Модели».",
    plan: [
      { t: "Установить", d: "Одна команда в терминале" },
      { t: "Готово", d: "Orca готов к работе" },
    ],
    steps: [
      "Открой <b>терминал</b>.",
      "Скопируй команду установки ниже.",
      "Вставь в терминал и нажми <code>Enter</code>.",
      "Открой <b>Orca</b> и начни кодить.",
    ],
    visuals: [],
  },
};
