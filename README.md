# 智枢 Studio / Zhishu Studio

面向需求分析、方案设计、开发审查与源码交付的本地 AI Agent 工作台。Python 标准库提供服务，浏览器界面支持需求文档导入、参考图片、模型与推理强度选择、任务队列、预览及版本恢复。

## 架构与来源

本仓库仅包含 Studio 应用层，不包含 DeepSeek Harness 核心框架。模型执行通过 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的 `dsh --profile headless` 接口完成；会话、模型适配与执行权限由 Harness 提供。上游许可证保留在 LICENSE，第三方 Skill 的来源及许可证位于各自目录。

## 环境与启动

需要 Python 3.11+、Node.js ^22.19 或 >=24，以及兼容的 DeepSeek Harness CLI。当前源码来自 Harness v0.2.1-alpha.4 开发阶段，尚未验证所有 npm 发行版本的兼容性。

```sh
npm install
npm run build
python3 studio/server.py
```

访问 http://127.0.0.1:3088。启动后可以管理项目和手动编辑方案；AI 执行还需要安装并配置 Harness。

如已有 `dsh`，确保它位于 PATH；也可通过启动环境指定命令：

```sh
export STUDIO_DSH_COMMAND='/absolute/path/to/dsh'
export GPT_GE_DEFAULT_API_KEY='your-default-group-key'
export GPT_GE_CODEX_API_KEY='your-codex-group-key'
python3 studio/server.py
```

模型配置位于 `studio/harness.patch.yml` 和 `studio/model-routing.json`。现有 GPT.GE 网关、模型名称及提供方分组是配置示例，需要按实际可用服务调整；仓库不包含密钥，也不保证示例模型当前可用。密钥通过环境变量提供，应用不会自动读取 `.env`。更改网关时同步检查两个配置文件及相关测试预期。

## 本地数据

上传文件、项目、会话和生成内容默认保存在 `studio/.data/`，可通过 STUDIO_DATA_DIR 指定。服务面向单用户本机使用，勿直接暴露到公网。源码导出不包含本机运行数据及原仓库提交历史。

## 验证

```sh
npm run test:python
npm test
```

这些测试使用本地夹具，不验证真实模型、完整 Harness 集成或生成应用的部署能力。依赖完整 Harness 源码树的两个集成测试未纳入此独立发行版。完整工作流说明见 [英文](studio/README.md) / [中文](studio/README.zh.md)；其中相邻源码构建命令仅适用于在完整 Harness 检出目录中运行 Studio。
