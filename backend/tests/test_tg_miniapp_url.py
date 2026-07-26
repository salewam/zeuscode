"""Mini App deep links for learn vs fusion picker."""


def test_miniapp_url_views():
    from app.telegram_bot import miniapp_url

    assert miniapp_url().endswith("/tg")
    assert "view=learn" in miniapp_url("learn")
    assert "view=fusion" in miniapp_url("fusion")
    assert "view=fusion" in miniapp_url("models")
    # hash must not be the only signal (Telegram strips it)
    assert "#" not in miniapp_url("learn")
    assert "#" not in miniapp_url("fusion")
