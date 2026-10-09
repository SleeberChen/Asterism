"""APP-MODEL 端口契约单元测试。

覆盖 `asterism/domain/model/ports.py`：ModelPort。
实现须经插件内核注册（TC-11），不得绕过内核直接实例化供应商客户端。
"""
from asterism.domain.model.model import ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort


class _FakeModel:
    def __init__(self):
        self.seen = []

    def complete(self, request):
        self.seen.append(request)
        return ModelResponse(
            text="stub:" + request.prompt,
            tenant_id=request.tenant_id,
            model=request.model,
        )


def test_model_port_satisfied_by_duck_typed_impl():
    assert isinstance(_FakeModel(), ModelPort)


def test_model_port_round_trip_keeps_tenant():
    impl = _FakeModel()
    resp = impl.complete(ModelRequest(tenant_id="t-1", prompt="hi"))
    assert resp.tenant_id == "t-1"
    assert resp.text == "stub:hi"
    assert resp.model == "default"
    assert impl.seen[0].prompt == "hi"
