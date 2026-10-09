"""APP-MODEL 领域模型单元测试（纯数据，无 IO / 无框架依赖）。

覆盖 `asterism/domain/model/model.py`：ModelRequest / ModelResponse。
隔离维度来自框架注入的上下文（TC-12），请求模型仅承载 tenant_id 不自行拼装。
"""
from asterism.domain.model.model import ModelRequest, ModelResponse


def test_model_request_defaults():
    r = ModelRequest(tenant_id="t-1", prompt="hi")
    assert r.model == "default"
    assert r.max_tokens == 2048


def test_model_request_keeps_tenant_from_context():
    r = ModelRequest(tenant_id="t-1", prompt="hi", model="m-1", max_tokens=128)
    assert (r.tenant_id, r.model, r.max_tokens) == ("t-1", "m-1", 128)
    assert r.prompt == "hi"


def test_model_response_optional_request_id():
    resp = ModelResponse(text="ok", tenant_id="t-1", model="m-1")
    assert resp.request_id is None
    resp2 = ModelResponse(text="ok", tenant_id="t-1", model="m-1", request_id="req-1")
    assert resp2.request_id == "req-1"
