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
    title: "Свое окно",
    hint: "Есть своё окно разработки? Бот поможет подключить",
    kind: "custom",
    installUrl: "https://t.me/neptuneapp_bot",
    setupTitle: "Подключение своего окна",
    yaml: false,
    configKind: "custom",
    note: "Напиши боту какое окно используешь — он даст готовый конфиг и инструкцию.",
    plan: [
      { t: "Написать боту", d: "Открой @neptuneapp_bot" },
      { t: "Указать окно", d: "Напиши какое окно разработки" },
      { t: "Отправить ключ", d: "Скопируй и отправь свой ключ" },
      { t: "Получить конфиг", d: "Бот даст готовую инструкцию" },
    ],
    steps: [
      "Открой бота <b>@neptuneapp_bot</b>.",
      "Напиши: «У меня [название окна], как подключить?»",
      "Скопируй и отправь свой <b>ключ</b> из вкладки «Модели».",
      "Бот пришлёт готовый <b>конфиг и инструкцию</b> для твоего окна.",
    ],
    visuals: [],
  },
};
