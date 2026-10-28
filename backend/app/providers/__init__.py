from .base import available_providers, get_provider, ProviderError, register_provider  # noqa: F401
from .volcengine import VolcengineProvider  # noqa: F401
from .zhipu import ZhipuProvider  # noqa: F401

register_provider("volcengine", VolcengineProvider)
register_provider("zhipu", ZhipuProvider)


def _maybe_register_mock() -> None:
    """环境变量 ENABLE_MOCK_PROVIDER=1 时注册冒烟测试引擎（仅本地测试用）"""
    import os

    if os.environ.get("ENABLE_MOCK_PROVIDER") == "1":
        from .mock import MockProvider

        register_provider("mock", MockProvider)


_maybe_register_mock()
