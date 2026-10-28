ARG NODE_IMAGE=node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392

FROM ${NODE_IMAGE} AS debian
ARG SOURCE_DATE_EPOCH
ARG DEBIAN_SNAPSHOT=20261020T000000Z
RUN test -n "$SOURCE_DATE_EPOCH" \
 && rm -f /etc/apt/sources.list.d/* \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s bookworm main\ndeb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s bookworm-updates main\ndeb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/%s bookworm-security main\n' "$DEBIAN_SNAPSHOT" "$DEBIAN_SNAPSHOT" "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list \
 && printf 'Acquire::Retries "5";\nAPT::Install-Recommends "false";\nAPT::Install-Suggests "false";\n' > /etc/apt/apt.conf.d/90blendworks

FROM debian AS blender
ARG SOURCE_DATE_EPOCH
ARG BLENDER_TARBALL=blender-5.2.3-linux-x64.tar.xz
ARG BLENDER_SHA256=78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec
COPY --from=blender-download ${BLENDER_TARBALL} /tmp/blender.tar.xz
RUN test -n "$SOURCE_DATE_EPOCH" \
 && echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c - \
 && apt-get update -qq && apt-get install -y -qq xz-utils >/dev/null \
 && mkdir -p /opt/blender \
 && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 --no-same-owner \
 && rm /tmp/blender.tar.xz

FROM debian AS runtime
ARG SOURCE_DATE_EPOCH
RUN test -n "$SOURCE_DATE_EPOCH" \
 && apt-get update -qq \
 && apt-get install -y -qq git libx11-6 libxrender1 libxfixes3 libxi6 libxkbcommon0 libsm6 libice6 libxext6 libgl1 >/dev/null \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /var/cache/debconf/*-old /var/cache/ldconfig/aux-cache /var/log/* /var/lib/dpkg/*-old

FROM runtime AS build
ARG SOURCE_DATE_EPOCH
ENV npm_config_cache=/tmp/npm-cache npm_config_update_notifier=false npm_config_fund=false npm_config_audit=false
ADD source.tar /opt/blendworks/
WORKDIR /opt/blendworks
RUN --mount=type=secret,id=extra-ca,required=false \
    test -n "$SOURCE_DATE_EPOCH" \
 && NODE_EXTRA_CA_CERTS=/run/secrets/extra-ca npm ci --no-progress \
 && npm run build \
 && rm -rf /tmp/npm-cache /root/.npm .cache

FROM runtime
ARG BLENDWORKS_COMMIT
LABEL org.blendworks.commit="${BLENDWORKS_COMMIT}" org.blendworks.blender="5.2.3" org.opencontainers.image.title="blendworks-judge"
COPY --from=blender /opt/blender /opt/blender
COPY --from=build /opt/blendworks /opt/blendworks
COPY --chmod=0755 entry /opt/blendworks-entry
COPY --chmod=0755 blendworks-judge /usr/local/bin/blendworks-judge
ENV BLENDER=/opt/blender/blender \
    BLENDWORKS_HOME=/opt/blendworks \
    BLENDWORKS_ENTRY=/opt/blendworks-entry \
    BLENDWORKS_SCRATCH=/tmp/blendworks \
    BLENDWORKS_DEVICE=cpu \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/blendworks-judge"]
