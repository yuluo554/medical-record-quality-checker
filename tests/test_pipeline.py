"""编排层测试：顺序执行、耗时记录、失败即停且保留已完成结果。"""

import pytest

from mrqc.pipeline import CTX_TIMINGS, Pipeline


def test_nodes_run_in_order_with_timing():
    pipe = Pipeline()
    order = []

    pipe.add_node("a", lambda ctx: order.append("a")).add_node("b", lambda ctx: order.append("b"))
    ctx = pipe.run()
    assert order == ["a", "b"]
    assert pipe.success is True
    assert set(ctx[CTX_TIMINGS]) == {"a", "b"}
    assert all(r.seconds >= 0 for r in pipe.results)


def test_failure_stops_pipeline_and_keeps_results():
    pipe = Pipeline()
    ran = []

    def boom(ctx):
        raise RuntimeError("解析失败示例")

    pipe.add_node("ok", lambda ctx: ran.append("ok"))
    pipe.add_node("bad", boom)
    pipe.add_node("never", lambda ctx: ran.append("never"))
    pipe.run()
    assert ran == ["ok"]
    assert pipe.success is False
    assert [r.ok for r in pipe.results] == [True, False]
    assert "解析失败示例" in pipe.results[1].error
    assert len(pipe.results) == 2  # never 节点未执行


def test_duplicate_node_rejected():
    pipe = Pipeline()
    pipe.add_node("x", lambda ctx: None)
    with pytest.raises(ValueError, match="重复"):
        pipe.add_node("x", lambda ctx: None)
