FROM eclipse-temurin:21-jre

ARG TLA2TOOLS_VERSION=1.8.0
ARG TLA2TOOLS_URL=https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar

LABEL org.opencontainers.image.title="FlowSpec TLC"
LABEL org.opencontainers.image.description="Isolated TLC runtime for FlowSpec model checking."
LABEL org.opencontainers.image.source="https://github.com/flowspec/flowspec"
LABEL org.opencontainers.image.version="${TLA2TOOLS_VERSION}"

RUN test -n "$TLA2TOOLS_URL"
ADD ${TLA2TOOLS_URL} /opt/tla2tools.jar

WORKDIR /work
ENTRYPOINT ["java", "-jar", "/opt/tla2tools.jar"]
