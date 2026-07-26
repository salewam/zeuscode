# Model power scores — research snapshot (2026-07-23)

## Sources
1. **Artificial Analysis Intelligence Index** — primary for chat  
   https://artificialanalysis.ai/leaderboards/models  
2. **LMArena / Chatbot Arena Elo** — fallback when AA missing  
3. **Image Arena / 2026 roundups** — GPT Image 2 #1, Nano Banana Pro / FLUX.2 / Seedream top tier  
4. **Frontend Code Arena** — small UI craft bias only (Fable, GPT-5.6 Sol, Opus 4.8)

## Map (chat)
`power = 400 + AA×10` (+ small UI craft bias ≤12)

| Model | AA | Power (approx) |
|-------|----|----------------|
| Claude Fable 5 | 60 | 1000 |
| GPT-5.6 Sol (max) | 59 | 1000 |
| Claude Opus 4.8 | 56 | 968 |
| GPT-5.6 Terra | 55 | 950 |
| Grok 4.5 | 54 | 944 |
| Claude Sonnet 5 | 53 | 936 |
| GPT-5.6 Luna / GPT-5.4 | 51 | 910 |
| Gemini 3.5 Flash | 50 | 900 |
| Gemini 3.1 Pro | 46 | 860 |
| DeepSeek V4 Pro | 44 | 840 |
| DeepSeek V4 Flash | 40 | 800 |
| Claude Haiku 4.5 | 30 | 700 |
| Gemini 2.5 Pro | 26 | 660 |

## Rule
AA beats Arena when both exist (Arena alone was inflating Gemini above Opus).
