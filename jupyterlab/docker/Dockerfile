# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG OWNER=jupyter
ARG BASE_CONTAINER=quay.io/jupyter/datascience-notebook:2025-11-25

# Stage 0: Base com dependências do sistema (cacheia para sempre)
FROM $BASE_CONTAINER AS system-base

# Copiar ferramentas necessárias para todos os stages
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=eclipse-temurin:11-jdk /opt/java/openjdk /usr/lib/jvm/java-11-openjdk-amd64
COPY --from=node:20-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-slim /usr/local/lib/node_modules /usr/local/lib/node_modules

# Variáveis de ambiente
ENV PROJ_LIB='/opt/conda/share/proj' \
    LOCALTILESERVER_CLIENT_PREFIX='proxy/{port}' \
    JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 \
    UDUNITS2_INCLUDE=/usr/include/ \
    UDUNITS2_LIB=/usr/lib/x86_64-linux-gnu \
    PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/include/glib-2.0:/opt/conda/lib/pkgconfig:/usr/include/x86_64-linux-gnu/:/usr/include/librsvg-2.0/:/usr/include/x86_64-linux-gnu/bits" \
    DOWNLOAD_STATIC_LIBV8=1 \
    LD_LIBRARY_PATH="/opt/conda/lib:/usr/lib/jvm/java-11-openjdk-amd64/lib/server:/usr/lib/x86_64-linux-gnu" \
    PATH="/usr/lib/jvm/java-11-openjdk-amd64/bin:/usr/local/bin:/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/include/glib-2.0:/opt/conda/lib/pkgconfig/:/usr/include/openssl/:/usr/include/librsvg-2.0/:/usr/include/x86_64-linux-gnu/:/usr/include/x86_64-linux-gnu/bits:/usr/include:/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/include/ImageMagick-6:/opt/conda/lib/pkgconfig/:${PATH}"

USER root

RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Pacotes do sistema em uma única camada otimizada
RUN apt-get update --yes && \
    apt-get upgrade --yes && \
    apt-get install --yes --no-install-recommends \
    libspatialindex-dev libpq-dev libpoppler-cpp-dev librsvg2-dev screen postgis \
    figlet libxmlsec1-dev libfreetype-dev libcairo2-dev libtiff-dev libjpeg-dev \
    libpng-dev libharfbuzz-dev openmpi-bin libopenmpi-dev libicu-dev rclone \
    iputils-ping htop libhdf5-dev libcurl4-gnutls-dev libssl-dev libxml2-dev \
    libxt-dev zlib1g-dev libbz2-dev liblzma-dev gawk libssh2-1-dev \
    libgl1-mesa-dev libglu1-mesa-dev libsasal2-dev libglpk40 libgdal-dev \
    libgeos++-dev libudunits2-dev libproj-dev libx11-dev libfftw3-dev \
    libmagick++-dev cargo libsqlite3-dev libtiff5-dev \
    curl build-essential libc6-dev \
    libv8-dev libnode-dev fontconfig apt-transport-https ca-certificates gnupg \
    cmake pkg-config git python3-qgis && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update --yes && \
    apt-get install --yes --no-install-recommends google-cloud-cli && \
    mkdir -p /usr/share/fonts/nerd-fonts && \
    curl -fLo /tmp/nerd-fonts.zip https://github.com/ryanoasis/nerd-fonts/releases/download/v3.3.0/BigBlueTerminal.zip && \
    unzip -q /tmp/nerd-fonts.zip -d /tmp && \
    mv /tmp/*.ttf /usr/share/fonts/nerd-fonts/ 2>/dev/null || true && \
    fc-cache -fv && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN mkdir -p /etc/parallel && echo "--will-cite" > /etc/parallel/config

# LOG: Verificar JupyterLab após system-base
RUN echo "========== STAGE: system-base ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "========================================"

# Stage 1: Build R packages (lento, mas cacheia bem)
FROM system-base AS r-builder

# LOG: Verificar JupyterLab no r-builder
RUN echo "========== STAGE: r-builder ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "======================================"

USER root

# Pacotes R (Adicionado r-languageserver para corrigir o erro do LSP)
RUN mamba install -c conda-forge --yes \
    sqlite parallel\
    udunits2 r-sf r-geojsonio r-lidr r-magick imagemagick r-units \
    r-arrow r-sits r-kohonen \
    r-terra r-summarytools r-rlas r-rcppeigen r-stars r-rnaturalearth r-foreign \
    r-workflowr r-coin r-rmarkdown r-mgcv r-mongolite r-viridislite r-tidyverse \
    r-ranger r-tuneranger r-mlr r-cowplot r-car r-fitdistrplus r-pacman \
    r-readxl r-readr r-leaflet r-rnaturalearthdata r-languageserver \
    r-corrplot r-mice r-missForest r-gridExtra r-hrbrthemes r-gt r-brms && \
    mamba clean --all -f -y && \
    fix-permissions "${CONDA_DIR}"

RUN R CMD javareconf

COPY script/install.R /tmp/install.R
RUN Rscript /tmp/install.R && \
    chown -R ${NB_UID}:${NB_GID} /opt/conda/lib/R/library

USER ${NB_UID}

# Stage 2: Imagem final com Python + R
# CORREÇÃO CRÍTICA: Herdar de r-builder garante que as dependências lib*.so do Conda não sejam perdidas
FROM r-builder

# LOG: Verificar JupyterLab no stage final
RUN echo "========== STAGE: final ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "=================================="

LABEL maintainer="Jairo Matos da Rocha <devjairomr@gmail.com>"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER ${NB_UID}

# Instalar pyarrow e polars via pip (wheels disponíveis)
RUN pip install --no-cache-dir pyarrow polars

# CRÍTICO: Pin JupyterLab 4 para evitar downgrade
RUN pip install --no-cache-dir 'jupyterlab>=4.0,<5.0'

# LOG: Verificar JupyterLab após pin
RUN echo "========== Após pin JupyterLab ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "========================================="

# Pacotes uv - Python puro (SEM dependências de pyarrow)
RUN uv pip install --system --no-cache \
    google-cloud-bigquery google-cloud-bigquery-storage google-cloud-storage \
    google-auth google-auth-oauthlib google-auth-httplib2 db-dtypes \
    rasterio shapely fiona pyproj \
    geopandas \
    pyogrio \
    psycopg2-binary \
    lz4 \
    xarray \
    networkx rtree geoalchemy2 \
    cloudpickle msgpack toolz \
    whitebox rasterstats \
    netcdf4 h5netcdf zarr \
    rioxarray \
    tables \
    boto3 s3fs fsspec \
    localtileserver osmnx \
    contextily \
    folium \
    pystac-client \
    xarray_leaflet \
    sentinelsat planetary-computer stackstac rio-cogeo \
    geemap leafmap pygis \
    eemont \
    jedi \
    pydeck \
    tqdm \
    bertopic wordcloud \
    xarray-spatial \
    geoviews hvplot datashader \
    earthpy \
    satpy \
    pydantic pydantic-settings \
    motor pymongo \
    minio \
    dynaconf python-dotenv pytz \
    loguru rich \
    unidecode beautifulsoup4 ijson \
    pyalex thefuzz \
    python-geohash \
    tenacity retry \
    geoparquet geextract matplotlib_map_utils \
    geocube \
    verde \
    pysal \
    momepy \
    movingpandas \
    splot \
    exactextract

# Pacotes que PRECISAM de pyarrow (instalar após pyarrow/polars do conda)
RUN uv pip install --system --no-cache \
    dask distributed dask-ml dask-geopandas \
    duckdb

# LOG: Verificar JupyterLab após UV
RUN echo "========== Após UV ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "============================="

# geobr via pip tradicional
RUN pip install --no-cache-dir geobr

# LOG: Verificar JupyterLab após geobr
RUN echo "========== Após geobr ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "================================"

USER root

# Temas compatíveis com JupyterLab 4
RUN uv pip install --system --no-cache --no-deps \
    theme-darcula \
    jupyterlab-night \
    jupyterlab_pygments \
    catppuccin-jupyterlab

# Extensões JupyterLab 4
RUN uv pip install --system --no-cache \
    jupyterlab-myst \
    jupyterlab-spellchecker \
    jupyter-collaboration \
    jupyterlab-lsp \
    python-lsp-server \
    jupyterlab-execute-time \
    jupyterlab-code-formatter \
    jupyterlab-unfold \
    jupyterlab-skip-traceback \
    nbdime

# Ferramentas SQL e formatadores de código
RUN uv pip install --system --no-cache \
    jupysql \
    sql-magic \
    black \
    isort \
    autopep8

# CRÍTICO: Desinstalar ipyvue/ipyvuetify instalados via pip (versão quebrada sem deps npm)
# e reinstalar via mamba (versão prebuilt com deps npm bundadas)
RUN pip uninstall -y ipyvue ipyvuetify && \
    pip install ipyvuetify

# Build de produção (cache bust: 2024-11-28-008)
RUN jupyter lab clean --all && \
    jupyter lab build --dev-build=False --minimize=True || \
    (echo "========== JUPYTER BUILD ERROR LOG ==========" && \
     cat /tmp/jupyterlab-debug-*.log 2>/dev/null | tail -250 && \
     echo "=============================================" && \
     exit 1)

# LOG: Verificar JupyterLab final
RUN echo "========== Após build ==========" && \
    python -c "import jupyterlab; print(f'JupyterLab: {jupyterlab.__version__}')" && \
    echo "================================"

RUN chown -R ${NB_UID}:${NB_GID} /home/${NB_USER}/work && \
    mkdir -p /work && \
    chown -R ${NB_UID}:${NB_GID} /work && \
    rm -rf /tmp/* /var/tmp/*

USER ${NB_UID}
WORKDIR /work

# Debug: Mostrar versões instaladas e salvar em arquivo
RUN echo "==================== BUILD INFO ====================" && \
    echo "JupyterLab: $(jupyter lab --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -n1)" && \
    echo "Python: $(python --version)" && \
    echo "R: $(R --version | head -n1)" && \
    echo "Node: $(node --version)" && \
    echo "Java: $(java -version 2>&1 | head -n1)" && \
    echo "UV: $(uv --version)" && \
    echo "Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")" && \
    echo "====================================================" && \
    { \
        echo "==================== BUILD INFO ===================="; \
        echo "JupyterLab: $(jupyter lab --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -n1)"; \
        echo "Python: $(python --version)"; \
        echo "R: $(R --version | head -n1)"; \
        echo "Node: $(node --version)"; \
        echo "Java: $(java -version 2>&1 | head -n1)"; \
        echo "UV: $(uv --version)"; \
        echo "Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"; \
        echo "===================================================="; \
    } > /home/${NB_USER}/BUILD_INFO.txt

# Script de startup para mostrar BUILD INFO
RUN echo '#!/bin/bash' > /home/${NB_USER}/startup.sh && \
    echo 'cat /home/${NB_USER}/BUILD_INFO.txt' >> /home/${NB_USER}/startup.sh && \
    echo 'exec "$@"' >> /home/${NB_USER}/startup.sh && \
    chmod +x /home/${NB_USER}/startup.sh

ENTRYPOINT ["/home/jovyan/startup.sh"]
CMD ["start-notebook.py"]