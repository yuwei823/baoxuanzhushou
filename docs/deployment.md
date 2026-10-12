# 阿里云 Docker 部署说明（内部使用 · baoxuanzhushou.app）

目标：把保宣合规助手部署到阿里云 ECS，通过 `https://baoxuanzhushou.app` 供团队内部访问；代码推送到 GitHub 后自动更新。

> `.app` 域名被浏览器强制 HTTPS。方案内置 Caddy 自动申请并续期 Let's Encrypt 证书，无需手动管理证书。

## 0. 前置条件

- 阿里云 ECS（建议 2C4G 及以上，Ubuntu 22.04/24.04），已安装 Docker 与 Docker Compose 插件
- 域名 DNS：在域名服务商处把 `baoxuanzhushou.app` 的 A 记录指向 ECS 公网 IP
- ECS 安全组放行：`80/443`（对外）、`22`（SSH，建议仅限自己的 IP）
- GitHub 私有仓库（存放代码，不含密钥）

## 1. ECS 初始化（一次性）

```bash
# 安装 Docker（官方脚本，Ubuntu）
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # 重新登录后生效

# 项目目录（root 用户直接在家目录下）
cd /root
git clone git@github.com:yuwei823/baoxuanzhushou.git
cd /root/baoxuanzhushou

# 服务端配置（密钥只在这台机器上，不入库）
cp .env.example .env
vim .env
```

`.env` 至少填写：

```
DASHSCOPE_API_KEY=sk-xxx
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BAILIAN_TEXT_MODEL=qwen-plus
BAILIAN_VISION_MODEL=qwen3-vl-plus
MODEL_CONCURRENCY=8
BATCH_RULE_COUNT=2
AUDIT_MAX_MODEL_ATTEMPTS=40
AUDIT_MAX_CONCURRENCY=2
```

- `AUDIT_MAX_CONCURRENCY`：同时进行的审核数上限，超限返回 429（防止误操作产生大量调用费用）。
- `MODEL_CONCURRENCY` / `BATCH_RULE_COUNT` / `AUDIT_MAX_MODEL_ATTEMPTS`：单次审核内的并发与分批参数。实测将单次审核从约 88 秒降到约 27–29 秒，并提高规则覆盖率。
- 服务默认对 `/api/*` 开放，不设访问口令。如需限制访问，请在 Caddy 层加认证，不要依赖应用内的口令。

## 2. 首次启动

```bash
cd /root/baoxuanzhushou
docker compose up -d --build
docker compose ps                # audit 应显示 healthy
curl -fsS http://127.0.0.1:8000/readyz
```

首次构建会在容器内生成 Linux 依赖锁（pip-compile）并安装；镜内含已发布法规快照与向量索引（hybrid 直接可用，无需在服务器上重新 build-index）。

约 1 分钟后访问 `https://baoxuanzhushou.app`，Caddy 自动完成证书签发。若打不开：

```bash
docker compose logs caddy      # 域名解析/证书问题
docker compose logs audit      # 服务问题
```

注意：审计单次约 1 分钟，浏览器等待正常；Caddy 反代没有读取超时，无需特殊配置。

## 3. CI/CD 自动更新（GitHub Actions）

工作流 `.github/workflows/deploy.yml`：push 到 `main` → 先跑测试 → SSH 登录 ECS → `git pull` + `docker compose up -d --build` → 检查 `/readyz`，失败则流水线报红。

GitHub 仓库 → Settings → Secrets and variables → Actions，添加三个仓库 Secrets：

| Secret | 值 |
|---|---|
| `SSH_HOST` | ECS 公网 IP |
| `SSH_USER` | ECS 登录用户（如 `ubuntu`） |
| `SSH_KEY` | 该用户的 SSH 私钥（PEM 全文） |

ECS 侧配合：

```bash
# 生成专用部署密钥（在 ECS 上，或本机生成后把公钥追加到 ECS）
ssh-keygen -t ed25519 -f ~/.ssh/deploy_ci
cat ~/.ssh/deploy_ci.pub >> ~/.ssh/authorized_keys

# GitHub 仓库 → Settings → Deploy keys → 添加只读 Deploy Key（用于 ECS git pull）
cat ~/.ssh/deploy_ci.pub   # 如果 CI 用同一把密钥登录，还需要仓库接受该公钥
```

> 也可复用你自己的登录密钥：把对应私钥放入 `SSH_KEY`，并确认 ECS `authorized_keys` 里有对应公钥。私有仓库的 `git pull` 需要 ECS 配置好 Deploy Key（`~/.ssh/config` 中 `github.com` 使用 `deploy_ci` 私钥）。

日常更新流程：本地 push → GitHub Actions 自动部署（约 2–3 分钟）→ 域名即新版本。也可以手动在 ECS 执行 `cd /root/baoxuanzhushou && git pull && docker compose up -d --build`。

## 4. 常见运维

```bash
docker compose logs -f audit        # 审核服务日志（已脱敏，不含原文与密钥）
docker compose ps                   # 状态
docker compose down                 # 停止（数据卷保留，证书不丢）
docker compose up -d --build        # 更新重建
```

日志只输出 trace_id、状态、覆盖率和调用统计，不包含提交文本与图片。

## 5. 边界与免责（必须保留）

- 规则卡由实施 agent 依据本地法规核对，**不是法律专家认证**；结论不替代现实资质核验，页面页脚已声明。
- 模型置信度未经校准；**P3 正式效果评估暂缓**，当前没有正式准确率指标，上线状态为“内部使用”，不得对外宣传效果达标。
- 新法规发布后：需新建规则快照、人工审阅并 `build-index` 重新构建向量索引，再更新镜像（索引绑定快照哈希）。
- 更新规则快照时，先本地发布并验证，再推送代码触发部署。
