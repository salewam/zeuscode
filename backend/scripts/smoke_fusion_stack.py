import asyncio
import time

from app.fusion import classify_query, resolve_routing, run_fusion


async def one(label: str, text: str, *, zeus: dict | None = None, model_id: str = "zeus/fusion") -> None:
    expect_mode, expect_by = resolve_routing(model_id, zeus, text)
    t0 = time.time()
    data = await run_fusion(
        messages=[{"role": "user", "content": text}],
        model_id=model_id,
        zeus=zeus,
    )
    wall = round(time.time() - t0, 2)
    os_ = data["onestack"]
    mode = os_["mode"]
    fusion_mode = os_.get("fusion_mode")
    routed_by = os_.get("routed_by")
    panel = os_["panel"]
    judge = os_.get("judge")
    ans = (data["choices"][0]["message"]["content"] or "")[:80]
    print(
        f"[{label}] expect={expect_mode}/{expect_by} got={fusion_mode}/{routed_by} "
        f"onestack={mode} wall={wall}s panel={panel} judge={judge}"
    )
    print(f"  classify={classify_query(text)!r} → {ans!r}")
    assert fusion_mode == expect_mode, (fusion_mode, expect_mode)
    assert routed_by == expect_by, (routed_by, expect_by)
    if expect_mode == "fast":
        assert len(panel) == 1 and judge is None
    else:
        assert len(panel) >= 2


async def main() -> None:
    await one("hi", "привет")
    await one("trivial", "поменяй цвет кнопки на красный")
    await one(
        "serious",
        "Напиши функцию на Python: быстрый binary search по отсортированному списку, с тестом.",
    )
    await one("force_full", "привет", zeus={"mode": "full"})
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
