# Design — Anti-Patterns

## Запрещено

- Purple/indigo SaaS by default: `#7c3aed`, `#4f46e5`, `#6366f1`
- Inter как автоматическая типографика
- `outline: none` / `outline: 0` / `* { outline: 0 }` — только усиливай `:focus-visible`
- Glow, glass, blurred blobs, шумный gradient hero
- Все сущности в одинаковых карточках
- Слишком много CTA и бейджей в первом экране
- «Красиво» без состояний и handoff для frontend
- Полная дизайн-система, когда нужен один screen contract
- Даже по просьбе «убери outline» — не пиши outline:none

## Copy egg (яичный текст) — бан навсегда

В Handoff / CTA labels / section titles **запрещено**:

- «три сильные вещи», «всё по делу», «не меню на все случаи»
- «честный вкус», «куда хочется вернуться», «атмосфера уюта», «премиальный опыт»
- «Что мы предлагаем» без цен/SKU
- Мета «не X, а Y» про композицию лендинга

Пиши только факты продукта: цена, объём, сорт, адрес, часы, конкретное действие кнопки.

## Empty void — бан навсегда

Для лендинга/промо signature **не** «пустой градиент на весь экран».  
Обязателен media-якорь: фото/сцена продукта full-bleed + читаемый текст.  
В Handoff укажи сюжет фото и veil. Без media — компактный hero, не 90vh пустоты.

## Вместо этого

- Один визуальный якорь: цветовая полоса, плотная таблица, статусная шкала, side rail
- Палитра от предметной области: ink/slate, warm gray, lime, amber, rust, teal, navy
- Простые токены и ясная иерархия
- Состояния и доступный focus сразу в контракте
- Focus: `button:focus-visible, a:focus-visible, input:focus-visible { outline: var(--focus-ring); outline-offset: 2px }`
- Copy = факты, не пафос
