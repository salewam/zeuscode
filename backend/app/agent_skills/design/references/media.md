# Design — Media / фото для лендингов и презентаций

Пустой hero / один кадр на всё = FAIL. Оркестратор даёт **Media pack** с 3 URL — копируй разные.

## Пулы (если brief без pack — бери из таблицы, разные ID)

### СТО
| Сюжет | URL |
|--------|-----|
| механик у капота | `https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?auto=format&fit=crop&w=2000&q=80` |
| подъёмник | `https://images.unsplash.com/photo-1619642751034-765dfdf7c58d?auto=format&fit=crop&w=2000&q=80` |
| шины | `https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=2000&q=80` |
| верстак | `https://images.unsplash.com/photo-1487754180451-c456f719a1fc?auto=format&fit=crop&w=2000&q=80` |
| авто / диагностика | `https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=2000&q=80` |
| вечер / фары | `https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=2000&q=80` |

### Кофе / барбер / услуга / deck
См. `app/media_packs.py` MEDIA_POOLS — те же правила.

## Handoff (обязательно)

```text
Media: hero=<url1>; mid=<url2>; extra=<url3>; remote OK; veil=…; object-position=…
```

**ЗАПРЕТ:** один и тот же `photo-XXXX` на hero и mid.  
**ЗАПРЕТ:** `path=assets/…` без файла. Дефолт = remote https.

## Бан

- Hero только gradient / solid
- Один Unsplash ID на всю страницу или все слайды
- Inset card вместо full-bleed на промо
- `000-00-00` в handoff

## Чеклист

- [ ] ≥2 разных photo-ID в артефактах FE/deck
- [ ] URL из brief pack (не выдуманный ID)
- [ ] Veil + object-position для hero
