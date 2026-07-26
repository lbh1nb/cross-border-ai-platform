"""真实亚马逊采集器：通过 HTTP 请求抓取 Best Seller 页面。

⚠️ 当前为预留接口，未实现真实抓取逻辑。
原因：
1. 亚马逊反爬严格，需要代理池和验证码处理
2. 页面结构频繁变动，维护成本高
3. 可能违反亚马逊服务条款

未来实现方案：
1. 接入第三方 API（Keepa / Jungle Scout / Helium 10）
2. 或使用 Playwright 无头浏览器抓取
"""

from __future__ import annotations

from .base import BaseCollector, ProductInfo


class RealAmazonCollector(BaseCollector):
    """真实亚马逊采集器（预留接口）。

    TODO: 未来接入第三方 API 或 Playwright 实现。
    """

    def __init__(self, proxy_pool: list[str] | None = None) -> None:
        self._proxy_pool = proxy_pool or []

    def collect(
        self, category: str, limit: int = 20, platform: str = "亚马逊"
    ) -> list[ProductInfo]:
        """采集指定品类的真实商品数据。

        Raises:
            NotImplementedError: 当前版本未实现真实抓取。
        """
        raise NotImplementedError(
            "真实采集器尚未实现。请使用 MockMultiPlatformCollector，"
            "或接入第三方 API（Keepa / Jungle Scout）。"
        )
