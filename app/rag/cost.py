"""只计算服务商真实返回的 Token；没有价格配置就不编造费用。"""


def usage_report(input_tokens: int | None, output_tokens: int | None, settings) -> dict:
    """仅在 Token 和两项价格均已知时计算金额；不估算本地模型 Token 成本。"""
    cost = None
    if (
        input_tokens is not None
        and output_tokens is not None
        and settings.input_price_per_million is not None
        and settings.output_price_per_million is not None
    ):
        cost = (
            input_tokens * settings.input_price_per_million
            + output_tokens * settings.output_price_per_million
        ) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated": False,
        "configured_currency_cost": cost,
    }
