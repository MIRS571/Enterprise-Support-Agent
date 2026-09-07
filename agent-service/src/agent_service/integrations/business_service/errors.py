class BusinessServiceError(RuntimeError):
    """Base exception for Java business-service calls."""


class OrderNotFoundError(BusinessServiceError):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"订单不存在或当前用户无权访问：{order_id}")


class RefundNotAllowedError(BusinessServiceError):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"订单当前状态不允许申请退款：{order_id}")


class RefundRequestOutcomeUnknownError(BusinessServiceError):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"退款申请结果未知：{order_id}")


class IdempotencyConflictError(BusinessServiceError):
    """The same idempotency key was reused for a different request."""


class IdempotencyInProgressError(BusinessServiceError):
    """An identical request currently owns the idempotency claim."""


class IdempotencyUnavailableError(BusinessServiceError):
    """The mutation was not started because idempotency is unavailable."""


class BusinessServiceTimeoutError(BusinessServiceError):
    pass


class BusinessServiceUnavailableError(BusinessServiceError):
    pass


class UpstreamServiceError(BusinessServiceError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"business-service 返回异常状态：{status_code}")


class UpstreamContractError(BusinessServiceError):
    pass
