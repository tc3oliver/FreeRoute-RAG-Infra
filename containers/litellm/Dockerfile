# 以官方 main-stable 為底，補 redis 套件（async 用）
FROM ghcr.io/berriai/litellm:main-stable

# 安裝 python-redis (>=5)
RUN pip install --no-cache-dir "redis>=5"

# 工作目錄與埠由基底映像管理；entrypoint = litellm
