from types import SimpleNamespace as NS

import pytest

from atlas.agents.base import Agent, Tool, schema


class FakeMessages:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def client(*responses):
    return NS(beta=NS(messages=FakeMessages(responses)))


def text(t):
    return NS(type="text", text=t)


def use(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


async def test_runs_parallel_tools_and_returns_final_text():
    seen = []
    tool = Tool("echo", "echo", schema({"x": {"type": "string"}}, ["x"]), lambda x: seen.append(x) or f"got {x}")
    c = client(NS(stop_reason="tool_use", content=[use("a", "echo", x="1"), use("b", "echo", x="2")]),
               NS(stop_reason="end_turn", content=[text("done")]))
    agent = Agent("t", "sys", [tool], "low", c)
    messages = [{"role": "user", "content": "hi"}]

    assert await agent.run(messages) == "done"
    assert seen == ["1", "2"]
    results = messages[2]["content"]  # both results in ONE user turn
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    call = c.beta.messages.calls[0]
    assert call["fallbacks"] == "default" and call["output_config"] == {"effort": "low"}


async def test_tool_errors_are_returned_to_the_model():
    def boom():
        raise RuntimeError("feed down")
    c = client(NS(stop_reason="tool_use", content=[use("a", "boom")]),
               NS(stop_reason="end_turn", content=[text("sorry, feed is down")]))
    messages = [{"role": "user", "content": "hi"}]
    await Agent("t", "sys", [Tool("boom", "", schema(), boom)], "low", c).run(messages)
    result = messages[2]["content"][0]
    assert result["is_error"] and "feed down" in result["content"]


async def test_async_tools_and_unknown_tool():
    async def slow():
        return {"ok": True}
    c = client(NS(stop_reason="tool_use", content=[use("a", "slow"), use("b", "nope")]),
               NS(stop_reason="end_turn", content=[text("ok")]))
    messages = [{"role": "user", "content": "hi"}]
    await Agent("t", "sys", [Tool("slow", "", schema(), slow)], "low", c).run(messages)
    a, b = messages[2]["content"]
    assert a["content"] == '{"ok": true}' and not a["is_error"]
    assert b["is_error"]


async def test_refusal():
    c = client(NS(stop_reason="refusal", content=[]))
    assert "can't" in await Agent("t", "sys", [], "low", c).ask("x")
