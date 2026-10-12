"""L3 密文定位引用解析（运行时仅在调用供应商时读取明文，TC-02）。

``credential_handle`` 只存定位引用（如 ``env://SILICONFLOW_API_KEY``），应用代码其余地方
均不读明文；唯独在此处、调用供应商前，按引用从密钥后端取回真实秘钥（可读次数 = 1，且只用于
发给供应商，不落日志 / 不回显）。
"""
from __future__ import annotations

import os

from asterism.seedwork.exceptions import BusinessError


def resolve_credential(handle: str) -> str:
    """将 L3 密文定位引用解析为真实秘钥。

    支持：
    - ``env://<VAR>``：从环境变量读取（部署密钥后端注入，如 SILICONFLOW_API_KEY）

    后续可扩展 ``secret://kms/<id>`` 等后端，不影响调用方。
    """
    if not handle:
        raise BusinessError("AST-ERR-4001", message="credential_handle 为空，无法解析秘钥")
    if handle.startswith("env://"):
        var = handle[len("env://"):]
        val = os.environ.get(var)
        if not val:
            raise BusinessError(
                "AST-ERR-4001", message=f"密钥后端未提供环境变量 {var!r}（credential_handle={handle}）"
            )
        return val
    if handle.startswith("secret://"):
        raise BusinessError("AST-ERR-4001", message=f"secret:// 密钥后端尚未接入（handle={handle}）")
    raise BusinessError("AST-ERR-4001", message=f"不支持的 credential_handle 格式: {handle}")
