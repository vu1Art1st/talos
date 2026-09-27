"""P2-5 指标格式守卫：Prometheus 文本合法，标签不留注入和敏感换行。"""
from app.services.metrics_service import _line


def test_prometheus_line_escapes_label_values():
    line = _line("talos_task_count", 3, kind="export", status='a"b\\c')
    assert line.startswith("talos_task_count{")
    assert 'status="a\\"b\\\\c"' in line
    assert "\n" not in line


def test_prometheus_line_without_labels():
    assert _line("talos_app_up", 1) == "talos_app_up 1"
