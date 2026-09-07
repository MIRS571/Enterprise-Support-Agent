package com.mirs.agent.business.controller;

import com.mirs.agent.business.dto.ServiceInfoResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/system")
public class SystemController {

    @GetMapping("/info")
    public ServiceInfoResponse info() {
        return new ServiceInfoResponse(
                "business-service",
                "UP"
        );
    }
}
