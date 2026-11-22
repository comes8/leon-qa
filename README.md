# Leon QA · Web3 测试工作台

用于组织现货、合约、资金与链上业务的需求分析、测试设计、接口调试、自动化执行和结果追踪。

## 主要内容

- **Web3 测试专区**：需求与规则、业务建模、测试点、用例、评审和版本记录。
- **业务资料**：仓库自带 9 个业务 Skill、14 个 Prompt 和 25 份参考文档，可按项目导入知识库。
- **接口测试**：接口中心、环境配置、数据依赖、断言、串行场景与执行记录。
- **AI 辅助**：按项目配置模型与 writer/reviewer；生成内容经评审后再用于测试。
- **本地模拟业务**：现货、合约、资金和 DEX 的隔离夹具，用于练习和确定性回归。模拟规则不代表真实交易所全部规则。
- **项目执行器**：登记外部测试项目后运行对应检查，收集真实执行证据。

技术栈：Vue 3 + TypeScript + Vite / FastAPI + SQLAlchemy / SQLite、MySQL 或 PostgreSQL / Redis。

## 本地启动（源码方式）

准备 Python 3.12、Node.js 22.12+、Redis 和 uv。后端支持 Python 3.11–3.12。

```bash
git clone https://github.com/comes8/leon-qa.git
cd leon-qa
cd backend
uv sync --frozen
cp .env.example .env
```

编辑 `backend/.env`：为 `SECRET_KEY` 和 `INITIAL_ADMIN_PASSWORD` 分别设置独立随机值（管理员密码至少 12 位）；默认使用 SQLite，Redis 端口为 `16379`。可在本机生成随机值：

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

若本机没有 Redis，可单独启动开发依赖：

```bash
docker run -d --name leonqa-dev-redis -p 127.0.0.1:16379:6379 redis:7-alpine
```

在后端目录启动（首次启动会创建表结构和干净的管理员账号）：

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 18171
```

另一个终端启动前端：

```bash
cd leon-qa/frontend
npm ci --legacy-peer-deps
npm run dev:original -- --host 127.0.0.1 --port 18170 --strictPort
```

访问 `http://127.0.0.1:18170`，账号为 `admin`，密码为首次初始化时设置的 `INITIAL_ADMIN_PASSWORD`。修改该变量不会覆盖已有账号密码。新环境需自行创建项目、导入资料，并在界面配置模型服务和测试环境。

业务资料默认从 `resources/web3-cex-business-skills` 读取；如需使用其他资料包，通过环境变量 `LEON_QA_BUSINESS_ASSETS` 指定。资料导入只读取文档，不会执行 Skill 文件。

## Docker Compose

```bash
cp .env.example .env
# 编辑 .env，设置两个独立随机值
# 如果本机已有 Leon QA 占用 18170/18171，请先修改 compose 的映射端口
docker compose up -d --build
```

前端端口 `18170`，后端端口 `18171`，均只绑定本机。此方式使用独立的 SQLite/Redis 数据卷。业务资料只读挂载到后端。Compose 文件是单机部署入口，本次发布未执行完整容器镜像构建验证。

根目录的 `./leonqa` 和本地运维文档保留了原工作站进程管理逻辑，依赖登记的测试项目和已有依赖容器；全新安装请先使用上面的源码方式或 Compose，而不要直接套用原工作站容器配置。

## 测试与使用说明

后端已有的 Web3/执行器测试可以在配置好测试环境后通过 `python -m unittest` 运行。测试必须使用独立数据库，不要指向工作数据库。外部测试项目、浏览器驱动、JMeter 等执行依赖需按实际模块配置，不随源码上传。

- [Web3 测试专区](README_WEB3_WORKSPACE.md)
- [Web3 场景与本地模拟](README_WEB3.md)
- [项目执行器](README_QA_RUNNER.md)
- [接口调试与执行](README_QA_DEBUG.md)
- [本地运维（原工作站）](README_QA_OPERATIONS.md)
- [历史功能开发参考](docs/PLATFORM_REFERENCE.md)

## 公开代码范围

本仓库是整理后的当前源码快照，包含业务文档、模板、静态资源和测试。历史数据库导出、上传附件、用户账号记录、对话数据、模型密钥、本机环境配置、日志、报告和原仓库 Git 历史均未包含。新的数据库只初始化基础菜单、角色、字典和由部署者设置密码的管理员。

这是持续开发中的工具；真实业务测试仍需要需求、接口文档、授权测试环境、正确的业务判据与人工评审。发布 GitHub 源码不会把本地平台部署成互联网网站。

## 许可证

沿用项目原有 [MIT 许可证](LICENSE)，原版权声明保留。
