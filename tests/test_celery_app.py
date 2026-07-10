from worker.celery_app import celery_app


def test_celery_app_is_configured_with_redis_broker():
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.timezone == "UTC"
