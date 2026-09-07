FROM maven:3.9.11-eclipse-temurin-21 AS build

WORKDIR /workspace

COPY pom.xml ./
RUN mvn -B dependency:go-offline

COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre

WORKDIR /app

COPY --from=build \
    --chown=10001:10001 \
    /workspace/target/business-service-0.1.0-SNAPSHOT.jar \
    /app/business-service.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/business-service.jar"]
