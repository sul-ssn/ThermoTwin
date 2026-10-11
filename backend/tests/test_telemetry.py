from app.demo import make_demo
from app.telemetry import generate


def test_profiles_are_deterministic_and_distinct():
    n = make_demo(2)
    normal = generate(n, {}, 3)
    burst = generate(n, {}, 3, "pipe_break")
    assert normal["T-S-0"]["value"] > burst["T-S-0"]["value"]
    assert generate(n, {}, 3)["T-S-0"]["value"] == normal["T-S-0"]["value"]
    leak1 = generate(n, {}, 1, "gradual_leak")
    leak2 = generate(n, {}, 10, "gradual_leak")
    assert leak2["T-S-0"]["value"] < leak1["T-S-0"]["value"]


def test_loss_of_connection_preserves_last_sample():
    n = make_demo(2)
    first = generate(n, {}, 0)
    second = generate(n, first, 1, "no_connection")
    assert second["T-S-0"]["timestamp"] == first["T-S-0"]["timestamp"]
    assert second["T-S-0"]["status"] == "no_connection"
