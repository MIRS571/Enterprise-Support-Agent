package com.mirs.agent.business.common.api;

import com.mirs.agent.business.order.service.OrderNotFoundException;
import com.mirs.agent.business.order.service.IdempotencyConflictException;
import com.mirs.agent.business.order.service.IdempotencyInProgressException;
import com.mirs.agent.business.order.service.IdempotencyOutcomeUnknownException;
import com.mirs.agent.business.order.service.IdempotencyUnavailableException;
import com.mirs.agent.business.order.service.RefundNotAllowedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.time.Instant;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(WebClientResponseException.class)
    public ResponseEntity<ApiErrorResponse> handleAgentResponseError(
            WebClientResponseException exception
    ) {
        String code = switch (exception.getStatusCode().value()) {
            case 404 -> "AGENT_RESOURCE_NOT_FOUND";
            case 429 -> "AGENT_RATE_LIMITED";
            case 503 -> "AGENT_SERVICE_UNAVAILABLE";
            default -> "AGENT_UPSTREAM_ERROR";
        };
        return ResponseEntity.status(exception.getStatusCode()).body(
                new ApiErrorResponse(
                        code,
                        "Agent 服务暂时无法完成请求",
                        Instant.now()
                )
        );
    }

    @ExceptionHandler(WebClientRequestException.class)
    public ResponseEntity<ApiErrorResponse> handleAgentConnectionError(
            WebClientRequestException exception
    ) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
                new ApiErrorResponse(
                        "AGENT_SERVICE_UNAVAILABLE",
                        "Agent 服务暂时不可用",
                        Instant.now()
                )
        );
    }

    @ExceptionHandler(IdempotencyConflictException.class)
    public ResponseEntity<ApiErrorResponse> handleIdempotencyConflict(
            IdempotencyConflictException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                new ApiErrorResponse(
                        "IDEMPOTENCY_CONFLICT",
                        exception.getMessage(),
                        Instant.now()
                )
        );
    }

    @ExceptionHandler(IdempotencyInProgressException.class)
    public ResponseEntity<ApiErrorResponse> handleIdempotencyInProgress(
            IdempotencyInProgressException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                new ApiErrorResponse(
                        "IDEMPOTENCY_IN_PROGRESS",
                        exception.getMessage(),
                        Instant.now()
                )
        );
    }

    @ExceptionHandler(IdempotencyUnavailableException.class)
    public ResponseEntity<ApiErrorResponse> handleIdempotencyUnavailable(
            IdempotencyUnavailableException exception
    ) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
                new ApiErrorResponse(
                        "IDEMPOTENCY_UNAVAILABLE",
                        exception.getMessage(),
                        Instant.now()
                )
        );
    }

    @ExceptionHandler(IdempotencyOutcomeUnknownException.class)
    public ResponseEntity<ApiErrorResponse> handleIdempotencyOutcomeUnknown(
            IdempotencyOutcomeUnknownException exception
    ) {
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT).body(
                new ApiErrorResponse(
                        "IDEMPOTENCY_OUTCOME_UNKNOWN",
                        exception.getMessage(),
                        Instant.now()
                )
        );
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleOrderNotFound(
            OrderNotFoundException exception
    ) {
        ApiErrorResponse error = new ApiErrorResponse(
                "ORDER_NOT_FOUND",
                exception.getMessage(),
                Instant.now()
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error);
    }

    @ExceptionHandler(RefundNotAllowedException.class)
    public ResponseEntity<ApiErrorResponse> handleRefundNotAllowed(
            RefundNotAllowedException exception
    ) {
        ApiErrorResponse error = new ApiErrorResponse(
                "REFUND_NOT_ALLOWED",
                exception.getMessage(),
                Instant.now()
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(error);
    }
}
