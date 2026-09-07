package com.mirs.agent.business.common.observability;

import jakarta.servlet.AsyncEvent;
import jakarta.servlet.AsyncListener;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestCorrelationFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_HEADER = "X-Request-Id";
    public static final String REQUEST_ID_ATTRIBUTE = "requestId";

    private static final Logger LOGGER = LoggerFactory.getLogger(
            RequestCorrelationFilter.class
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String requestId = resolveRequestId(
                request.getHeader(REQUEST_ID_HEADER)
        );
        String operation = operationFor(
                request.getMethod(),
                request.getRequestURI()
        );
        long startedAt = System.nanoTime();
        AtomicBoolean logged = new AtomicBoolean(false);
        boolean asyncListenerRegistered = false;

        request.setAttribute(REQUEST_ID_ATTRIBUTE, requestId);
        response.setHeader(REQUEST_ID_HEADER, requestId);

        try (MDC.MDCCloseable ignored = MDC.putCloseable(
                "request_id",
                requestId
        )) {
            filterChain.doFilter(request, response);
            if (request.isAsyncStarted()) {
                request.getAsyncContext().addListener(
                        completionListener(
                                requestId,
                                operation,
                                response,
                                startedAt,
                                logged
                        )
                );
                asyncListenerRegistered = true;
            }
        } finally {
            if (!asyncListenerRegistered) {
                logCompletion(
                        requestId,
                        operation,
                        response.getStatus(),
                        errorCodeFor(response.getStatus()),
                        startedAt,
                        logged
                );
            }
        }
    }

    private static AsyncListener completionListener(
            String requestId,
            String operation,
            HttpServletResponse response,
            long startedAt,
            AtomicBoolean logged
    ) {
        return new AsyncListener() {
            @Override
            public void onComplete(AsyncEvent event) {
                logCompletion(
                        requestId,
                        operation,
                        response.getStatus(),
                        errorCodeFor(response.getStatus()),
                        startedAt,
                        logged
                );
            }

            @Override
            public void onTimeout(AsyncEvent event) {
                logCompletion(
                        requestId,
                        operation,
                        response.getStatus(),
                        "ASYNC_TIMEOUT",
                        startedAt,
                        logged
                );
            }

            @Override
            public void onError(AsyncEvent event) {
                logCompletion(
                        requestId,
                        operation,
                        response.getStatus(),
                        "ASYNC_ERROR",
                        startedAt,
                        logged
                );
            }

            @Override
            public void onStartAsync(AsyncEvent event) {
                event.getAsyncContext().addListener(this);
            }
        };
    }

    private static void logCompletion(
            String requestId,
            String operation,
            int status,
            String errorCode,
            long startedAt,
            AtomicBoolean logged
    ) {
        if (!logged.compareAndSet(false, true)) {
            return;
        }
        long durationMillis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt
        );
        LOGGER.info(
                "request_completed request_id={} operation={} status={} "
                        + "duration_ms={} error_code={}",
                requestId,
                operation,
                status,
                durationMillis,
                errorCode
        );
    }

    static String resolveRequestId(String providedRequestId) {
        if (providedRequestId != null) {
            try {
                return UUID.fromString(providedRequestId).toString();
            } catch (IllegalArgumentException ignored) {
                // Invalid external identifiers are replaced, never logged.
            }
        }
        return UUID.randomUUID().toString();
    }

    private static String errorCodeFor(int status) {
        return status >= 400 ? "HTTP_" + status : "NONE";
    }

    private static String operationFor(String method, String path) {
        if ("POST".equals(method)
                && "/api/v1/agent/threads".equals(path)) {
            return "AGENT_THREAD_CREATE";
        }
        if ("POST".equals(method)
                && "/api/v1/agent/chat/stream".equals(path)) {
            return "AGENT_CHAT_STREAM";
        }
        if ("POST".equals(method)
                && path.startsWith("/api/v1/agent/threads/")
                && path.endsWith("/resume")) {
            return "AGENT_THREAD_RESUME";
        }
        if ("POST".equals(method)
                && path.startsWith("/api/v1/orders/")
                && path.endsWith("/refund-requests")) {
            return "ORDER_REFUND_REQUEST";
        }
        if ("GET".equals(method)
                && path.startsWith("/api/v1/orders/")) {
            return "ORDER_QUERY";
        }
        if ("GET".equals(method)
                && "/api/v1/system/info".equals(path)) {
            return "SYSTEM_INFO";
        }
        return "OTHER";
    }
}
