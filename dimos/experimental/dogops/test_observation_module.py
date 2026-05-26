from dimos.experimental.dogops.observation_module import DogOpsObservationModule


def test_observation_module_builds_observations_from_simulated_tags() -> None:
    module = DogOpsObservationModule()

    observations = module.observe_simulated_tags([20, 101, 102], zone_id="INBOUND_DOCK")

    assert [obs.tag_id for obs in observations] == [20, 101, 102]
    assert observations[0].entity_id == "INBOUND_DOCK"
    assert observations[1].entity_id == "PKG-101"
    assert observations[1].facts["detection_source"] == "simulation"


def test_observation_module_reports_stream_fallback() -> None:
    module = DogOpsObservationModule()

    status = module.image_stream_status()

    assert status["ok"] is False
    assert status["mode"] == "not_subscribed"
