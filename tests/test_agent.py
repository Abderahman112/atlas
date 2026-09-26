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
    agent = Agent("t", "sys", [tool], "low", c, model="claude-opus-5")
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


def test_model_options_per_model():
    from atlas.agents.base import model_options
    assert model_options("claude-haiku-4-5", "high") == {}
    assert model_options("claude-sonnet-5", "low") == {"output_config": {"effort": "low"}}
    opus = model_options("claude-opus-5", "medium")
    assert opus["fallbacks"] == "default" and opus["output_config"] == {"effort": "medium"}


async def test_haiku_request_has_no_effort_or_fallbacks():
    c = client(NS(stop_reason="end_turn", content=[text("hi")]))
    await Agent("t", "sys", [], "low", c, model="claude-haiku-4-5").ask("x")
    call = c.beta.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert "output_config" not in call and "fallbacks" not in call and "betas" not in call


async def test_refusal():
    c = client(NS(stop_reason="refusal", content=[]))
    assert "can't" in await Agent("t", "sys", [], "low", c).ask("x")
