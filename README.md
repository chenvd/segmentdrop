# SegmentDrop

在手机浏览器中读取 Emby 当前播放位置，编辑片头、回顾、片尾和预告区间，并提交到 TheIntroDB。

## 本地运行

项目本地虚拟环境使用 Python 3.13：

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000>，先在“设置”中填写 Emby 与 TheIntroDB 信息。

## Docker

```bash
docker compose pull
docker compose up -d
```

默认使用 Docker Hub 上的多架构镜像 `chenvd/segmentdrop:latest`，支持 `linux/amd64` 和 `linux/arm64`。配置保存在宿主机 `./data/config.json`。容器使用单 Uvicorn worker，默认限制 256 MB 内存。

如需从源码本地构建：

```bash
docker build -t segmentdrop:local .
docker run -d --name segmentdrop -p 8000:8000 -v "$(pwd)/data:/app/data" segmentdrop:local
```

## 发布镜像

GitHub Actions 在以下情况构建镜像：

- Pull Request：运行测试并构建双架构镜像，但不推送。
- 推送到 `main`：推送 `chenvd/segmentdrop:latest`、`main` 和 commit SHA 标签。
- 推送 `v1.2.3` 格式的 Git tag：推送 `1.2.3`、`1.2`、`1` 和 commit SHA 标签。
- 在 Actions 页面手动运行：使用当前分支生成对应标签并推送。

仓库的 Actions Secret 需要包含：

```text
DOCKER_HUB_ACCESS_TOKEN
```

该 Token 需要具有 Docker Hub 仓库 `chenvd/segmentdrop` 的读取和写入权限。

## 测试

```bash
.venv/bin/python -m unittest discover -v
```

详细产品与接口规则见 [需求文档.md](./需求文档.md)。
