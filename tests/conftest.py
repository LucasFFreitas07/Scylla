import pytest

from scylla.processes import ProcessInfo


@pytest.fixture
def sample_proc() -> ProcessInfo:
    return ProcessInfo(
        pid=42,
        name="sleep",
        username="lucas",
        cpu_percent=0.0,
        memory_percent=0.1,
        status="sleeping",
        cmdline="sleep 300",
    )
