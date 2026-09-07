from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.archive_stream import (
    JsonlArchiveSink,
    TimeWindowBuffer,
    stream_world_archives,
)


def test_time_window_buffer_evicts_only_outside_causal_memory():
    buffer = TimeWindowBuffer[str](3.0)
    buffer.append(0.0, "a")
    buffer.append(2.0, "b")
    buffer.append(4.0, "c")
    assert buffer.values(4.0) == ("b", "c")
    assert buffer.values(6.1) == ("c",)


def test_forensic_archives_can_stream_and_clear(tmp_path):
    world = Simulation(
        generate_pineland(
            SimulationConfig(
                agent_count=40,
                locality_count=17,
                horizon_days=1,
                seed=997,
            )
        )
    ).run(until=0.25).world
    assert world.event_log
    sink = JsonlArchiveSink(tmp_path / "archive.jsonl")
    counts = stream_world_archives(
        world, sink, fields=("event_log",), clear=True
    )
    assert counts["event_log"] > 0
    assert world.event_log == []
    assert (tmp_path / "archive.jsonl").read_text(encoding="utf-8")
